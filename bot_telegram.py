"""Única parte do Rende que conversa com o Telegram: recebe mensagens e botões,
baixa arquivos (só para a memória) e desenha as telas (texto + botões).

Para ligar o bot:   .venv\\Scripts\\python bot_telegram.py
Para desligar:      Ctrl+C
"""
import asyncio
import contextlib
import html
import io
import logging
import os
import re
import sys
from datetime import time as horario, timedelta

import httpx
from dotenv import load_dotenv
from telegram import (BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, KeyboardButton,
                      Message, ReplyKeyboardMarkup, Update)
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler,
                          filters)
from telegram.request import HTTPXRequest

load_dotenv()

import atendimento  # noqa: E402  (depois do load_dotenv: os módulos leem o .env)
import avisos  # noqa: E402
import banco  # noqa: E402
import cardapio  # noqa: E402
import coletor  # noqa: E402
import prompts  # noqa: E402
import telas  # noqa: E402
from telas import Saida  # noqa: E402

# --- registro (log) ----------------------------------------------------------
# Esconde o token do Telegram e as chaves das IAs, mesmo dentro de mensagens de erro.
_SEGREDOS = [v for v in (os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("GEMINI_API_KEY"),
                         os.getenv("ANTHROPIC_API_KEY")) if v]
_CARA_DE_TOKEN = re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}|sk-ant-[A-Za-z0-9_-]{10,}")


class _FormatoSemSegredos(logging.Formatter):
    def format(self, registro: logging.LogRecord) -> str:
        texto = super().format(registro)
        for segredo in _SEGREDOS:
            texto = texto.replace(segredo, "<segredo>")
        return _CARA_DE_TOKEN.sub("<segredo>", texto)


_saida_log = logging.StreamHandler()
_saida_log.setFormatter(_FormatoSemSegredos("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_saida_log])
# httpx/httpx2 registram cada endereço chamado (o do Telegram contém o token); os SDKs das IAs são verbosos.
for _nome in ("httpx", "httpx2", "google_genai", "anthropic", "apscheduler"):
    logging.getLogger(_nome).setLevel(logging.WARNING)
log = logging.getLogger("rende")

# --- configuração ------------------------------------------------------------
TAMANHO_MAXIMO = 4000
AVISO_DE_DEMORA_APOS = 25  # segundos
# A "animação" do plano é feita editando a mesma mensagem. Cada edição já custa ~0,2 s de ida e
# volta até o Telegram, então o intervalo real entre quadros é esta espera + a edição (~0,65 s):
# visível para quem lê e longe do limite de edições do Telegram.
ESPERA_ENTRE_ETAPAS = 0.45
# Quanto o Rende espera antes de mostrar "digitando...". Abaixo disso a tela já ficou pronta
# (botões resolvidos em código levam ~1 ms) e o aviso só atrasaria a resposta.
ANTES_DE_DIGITANDO = 0.25
# Conexão com o Telegram: o httpx fecha conexão parada em 5 s (padrão que o PTB não muda), e
# reabrir custa ~0,7 s contra ~0,2 s de uma aberta. Como entre dois toques passa bem mais que
# 5 s, toda resposta pagava o aperto de mão. Mantemos a conexão viva e aquecida de tempos em
# tempos. Medido em 24/11: 712 ms -> 235 ms numa chamada depois de 8 s parado.
# RENDE_MEDIR_LATENCIA=1 no .env faz cada toque de botão registrar o tempo de cada etapa.
# Fica desligado por padrão para não encher o log em uso normal.
MEDIR_LATENCIA = (os.getenv("RENDE_MEDIR_LATENCIA") or "").strip() in ("1", "true", "sim")
KEEPALIVE_SEGUNDOS = 600.0
# Medido em 24/11: a conexão continua rápida depois de 65 s e de 125 s parada (201-208 ms). Não
# sabemos onde o servidor do Telegram desiste, então reaquecemos dentro da janela já comprovada.
INTERVALO_AQUECIMENTO = 120
HORA_COLETA = os.getenv("COLETOR_HORA") or "06:00"   # coleta diária das promoções (horário de Brasília)
_trava_coleta = asyncio.Lock()                       # nunca duas coletas ao mesmo tempo
NOME_BOT = "Rende"
DESCRICAO = ("Seu amigo do mercado: monto o cardápio da semana no seu orçamento, com a lista de compras "
             "por embalagem, receitas passo a passo e promoções.")
COMANDOS = [BotCommand("start", "Começar"), BotCommand("perfil", "Ver ou mudar meu perfil"),
            BotCommand("novo", "Recomeçar a conversa (mantém o perfil)"),
            BotCommand("avisos", "Ligar ou desligar os avisos de promoção"),
            BotCommand("esquecer", "Apagar todos os meus dados")]


# --- formatação ----------------------------------------------------------------
def dividir(texto: str, limite: int = TAMANHO_MAXIMO) -> list[str]:
    partes = []
    while len(texto) > limite:
        corte = texto.rfind("\n\n", 0, limite)
        if corte <= 0:
            corte = texto.rfind("\n", 0, limite)
        if corte <= 0:
            corte = texto.rfind(" ", 0, limite)
        if corte <= 0:
            corte = limite
        partes.append(texto[:corte].rstrip())
        texto = texto[corte:].lstrip()
    if texto.strip():
        partes.append(texto)
    return partes


def para_html(texto: str) -> str:
    """Converte o *negrito* (estilo WhatsApp) para o HTML do Telegram."""
    texto = texto.replace("**", "*")
    texto = re.sub(r"(?m)^#{1,6}\s*(.+)$", r"*\1*", texto)
    texto = re.sub(r"(?m)^(\s*)\* ", r"\1• ", texto)
    texto = html.escape(texto, quote=False)
    # O par de asteriscos só vira negrito quando abre colado no texto e fecha colado nele:
    # senão "2 * 3 = 6 e 4 * 5 = 20" deixaria o meio da frase em negrito.
    return re.sub(r"\*(?!\s)([^*\n]+?)(?<!\s)\*", r"<b>\1</b>", texto)


def sem_formatacao(texto: str) -> str:
    return texto.replace("*", "")


# Tarefas que rodam em paralelo com a resposta (ex.: confirmar o toque no botão). A referência
# fica guardada até terminarem: sem isso o Python pode recolher a tarefa antes da hora.
_em_voo: set[asyncio.Task] = set()


def _em_paralelo(corrotina) -> None:
    """Dispara algo que a pessoa não precisa esperar; erro de rede aqui só vira aviso no log."""
    async def protegida():
        try:
            await corrotina
        except TelegramError as erro:
            log.debug("Chamada em paralelo falhou (sem efeito para a pessoa): %s", erro)

    tarefa = asyncio.create_task(protegida())
    _em_voo.add(tarefa)
    tarefa.add_done_callback(_em_voo.discard)


def _teclado(saida: Saida) -> InlineKeyboardMarkup | None:
    if not saida.botoes:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(b.rotulo, callback_data=b.acao) for b in linha]
                                 for linha in saida.botoes])


async def _enviar_texto(bot, chat_id: int, texto: str, teclado=None) -> Message | None:
    partes = dividir(texto) or [""]
    enviada = None
    for i, parte in enumerate(partes):
        markup = teclado if i == len(partes) - 1 else None  # botões na última parte
        try:
            enviada = await bot.send_message(chat_id, para_html(parte), parse_mode=ParseMode.HTML, reply_markup=markup)
        except BadRequest as erro:
            log.warning("O Telegram recusou a formatação (%s). Enviando sem formatação.", erro)
            enviada = await bot.send_message(chat_id, sem_formatacao(parte), reply_markup=markup)
    return enviada


# Quando a pessoa toca vários botões seguidos (marcar/desmarcar numa tela de checkbox), as
# edições são juntadas: só o estado final é desenhado. Protege do limite de edições do
# Telegram e deixa a tela mais fluida — um toque isolado não espera nada.
INTERVALO_MINIMO_EDICAO = 0.4
_ultima_edicao: dict[tuple[int, int], float] = {}
_versao_edicao: dict[tuple[int, int], int] = {}


async def _editar(mensagem: Message, texto: str, teclado=None) -> bool:
    """Edita uma mensagem (navegação por botões). Devolve False se não deu para editar."""
    if len(texto) > TAMANHO_MAXIMO:
        return False
    chave = (mensagem.chat_id, mensagem.message_id)
    minha_vez = _versao_edicao[chave] = _versao_edicao.get(chave, 0) + 1
    relogio = asyncio.get_running_loop().time
    espera = INTERVALO_MINIMO_EDICAO - (relogio() - _ultima_edicao.get(chave, -999))
    if espera > 0:
        await asyncio.sleep(espera)
        if _versao_edicao.get(chave) != minha_vez:
            return True  # chegou um toque mais novo: ele desenha o estado final
    _ultima_edicao[chave] = relogio()
    try:
        await mensagem.edit_text(para_html(texto), parse_mode=ParseMode.HTML, reply_markup=teclado)
        return True
    except RetryAfter as erro:  # limite de edições do Telegram: a próxima edição já leva o estado atual
        log.warning("O Telegram pediu para esperar %.0f s antes de editar de novo.", erro.retry_after)
        _ultima_edicao[chave] = relogio() + float(erro.retry_after)
        return True
    except BadRequest as erro:
        if "not modified" in str(erro).lower():
            return True
        log.warning("Não deu para editar a mensagem (%s); enviando uma nova.", erro)
        return False


# --- "digitando..." -------------------------------------------------------------
async def _manter_digitando(bot, chat_id: int, parar: asyncio.Event) -> None:
    """Mantém o "digitando..." enquanto o Rende trabalha.

    Começa esperando ANTES_DE_DIGITANDO: a maioria dos botões é resolvida em código, em
    poucos milissegundos, e aí nenhuma chamada ao Telegram chega a ser feita. Sem essa
    espera, todo toque pagava uma ida e volta de ~220 ms só para mostrar "digitando..."
    numa tela que já estava pronta."""
    relogio = asyncio.get_running_loop().time
    inicio, avisou = relogio(), False
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(parar.wait(), timeout=ANTES_DE_DIGITANDO)
    while not parar.is_set():
        if not avisou and relogio() - inicio >= AVISO_DE_DEMORA_APOS:
            avisou = True
            with contextlib.suppress(Exception):
                await bot.send_message(chat_id=chat_id, text=prompts.DEMORA)
        with contextlib.suppress(Exception):
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        espera = 4.0 if avisou else max(0.01, min(4.0, AVISO_DE_DEMORA_APOS - (relogio() - inicio)))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(parar.wait(), timeout=espera)


@contextlib.asynccontextmanager
async def _digitando(bot, chat_id: int):
    parar = asyncio.Event()
    tarefa = asyncio.create_task(_manter_digitando(bot, chat_id, parar))
    try:
        yield
    finally:
        # Cancela em vez de esperar: se houver um "digitando..." em voo, aguardar a resposta
        # do Telegram atrasaria a mensagem de verdade em mais uma ida e volta.
        parar.set()
        tarefa.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarefa


# --- desenhar as saídas ------------------------------------------------------------
async def _apagar_mensagem(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tarefa agendada: some com uma mensagem do bot (ex.: o PDF depois de alguns minutos)."""
    chat_id, mensagem_id = context.job.data
    with contextlib.suppress(TelegramError):  # se a pessoa já apagou, tudo bem
        await context.bot.delete_message(chat_id, mensagem_id)
    dados_chat = context.application.chat_data[chat_id]
    if dados_chat.get("ultimo_documento") == mensagem_id:
        dados_chat.pop("ultimo_documento")


async def mostrar(context: ContextTypes.DEFAULT_TYPE, chat_id: int, usuario: str, saidas: list[Saida],
                  origem: Message | None = None) -> None:
    """Desenha as telas. origem = mensagem do botão tocado (para editar em vez de mandar outra)."""
    bot = context.bot
    for saida in saidas:
        if saida.tipo == "aviso":
            continue  # só o toast/alerta do toque; nenhuma mensagem muda
        if saida.tipo == "acao":
            await executar_acao(context, chat_id, usuario, saida.acao, saida.texto, origem)
            continue
        if saida.tipo == "documento":
            dados_chat = context.application.chat_data[chat_id]
            anterior = dados_chat.pop("ultimo_documento", None)
            if anterior:  # só o PDF mais recente fica no chat
                with contextlib.suppress(TelegramError):
                    await bot.delete_message(chat_id, anterior)
            enviada = await bot.send_document(chat_id, document=InputFile(io.BytesIO(saida.dados),
                                                                          filename=saida.nome_arquivo),
                                              caption=saida.texto or None)
            dados_chat["ultimo_documento"] = enviada.message_id
            if saida.apagar_apos > 0 and context.job_queue:
                context.job_queue.run_once(_apagar_mensagem, saida.apagar_apos,
                                           data=(chat_id, enviada.message_id), chat_id=chat_id)
            continue  # o PDF existiu só na memória
        if saida.tipo == "pedir_localizacao":
            botao = KeyboardButton("📍 Enviar minha localização", request_location=True)
            await bot.send_message(chat_id, para_html(saida.texto), parse_mode=ParseMode.HTML,
                                   reply_markup=ReplyKeyboardMarkup([[botao]], resize_keyboard=True,
                                                                    one_time_keyboard=True))
            continue
        teclado = _teclado(saida)
        if saida.editar and origem is not None and await _editar(origem, saida.texto, teclado):
            origem = None  # só a primeira tela substitui a mensagem do botão
            continue
        await _enviar_texto(bot, chat_id, saida.texto, teclado)


def _confirmar_toque(consulta, saidas: list[Saida] | None = None) -> None:
    """Tira o relógio do botão. Sem texto: marcar/desmarcar não mostra balão nenhum, porque o
    próprio botão virando ✅/⬜ já é o retorno. Só erro de verdade (tocar em "Continuar" sem
    nada marcado) abre a caixinha com OK. Vai em paralelo: ninguém espera por isso."""
    if consulta is None:
        return
    erro = next((s for s in (saidas or []) if s.alerta and s.toast), None)
    if erro is None:
        _em_paralelo(consulta.answer())
    else:
        _em_paralelo(consulta.answer(text=erro.toast[:200], show_alert=True))


async def executar_acao(context: ContextTypes.DEFAULT_TYPE, chat_id: int, usuario: str, acao: str,
                        texto: str = "", origem: Message | None = None, consulta=None) -> None:
    if acao == "pl:montar":
        _confirmar_toque(consulta)  # ação demorada: confirma o toque já
        await montar_com_animacao(context, chat_id, usuario, texto, origem)
    elif acao.startswith("pl:tro:"):
        _confirmar_toque(consulta)
        _, _, dia, tipo = acao.split(":")
        await trocar_com_progresso(context, chat_id, usuario, dia, tipo, texto, origem)
    else:
        relogio = asyncio.get_running_loop().time
        t0 = relogio()
        async with _digitando(context.bot, chat_id):
            saidas = await atendimento.acao(usuario, acao)
        # O trabalho leva ~1 ms, então dá para confirmar o toque já sabendo o que dizer no toast
        t1 = relogio()
        _confirmar_toque(consulta, saidas)
        t2 = relogio()
        await mostrar(context, chat_id, usuario, saidas, origem)
        if MEDIR_LATENCIA and consulta is not None:
            log.info("latencia [%s]: estado %.1f ms | answerCallbackQuery %.1f ms (em paralelo) | "
                     "edicao %.1f ms | total %.1f ms", acao, (t1 - t0) * 1000, (t2 - t1) * 1000,
                     (relogio() - t2) * 1000, (relogio() - t0) * 1000)


async def montar_com_animacao(context, chat_id: int, usuario: str, pedido: str = "",
                              origem: Message | None = None) -> None:
    """Uma mensagem editada a cada etapa REAL da montagem do plano."""
    loop = asyncio.get_running_loop()
    msg = None
    if origem is not None and await _editar(origem, telas.progresso(0)):
        msg = origem
    if msg is None:
        msg = await _enviar_texto(context.bot, chat_id, telas.progresso(0))
    estado = {"maior": -1, "ultima": loop.time()}

    async def progresso(etapa: int) -> None:
        ajustando = etapa <= estado["maior"]
        estado["maior"] = max(estado["maior"], etapa)
        espera = ESPERA_ENTRE_ETAPAS - (loop.time() - estado["ultima"])
        if espera > 0:
            await asyncio.sleep(espera)
        await _editar(msg, telas.progresso(etapa, ajustando))
        estado["ultima"] = loop.time()

    saidas = await atendimento.montar_plano(usuario, pedido, progresso)
    if saidas and saidas[0].botoes:  # deu certo: marca tudo como concluído
        await _editar(msg, telas.progresso(len(cardapio.ETAPAS), concluido=True))
    await mostrar(context, chat_id, usuario, saidas)


async def trocar_com_progresso(context, chat_id: int, usuario: str, dia: str, tipo: str, pedido: str = "",
                               origem: Message | None = None) -> None:
    aviso = f"🔁 Trocando {cardapio.NOME_REFEICAO[tipo].lower()} de {cardapio.NOME_DIA[dia].lower()}..."
    msg = origem if (origem is not None and await _editar(origem, aviso)) else await _enviar_texto(context.bot, chat_id, aviso)
    async with _digitando(context.bot, chat_id):
        saidas = await atendimento.trocar_prato(usuario, dia, tipo, pedido)
    await mostrar(context, chat_id, usuario, saidas, origem=msg)


# --- comandos -----------------------------------------------------------------------
def _usuario(update: Update) -> str:
    return str(update.effective_user.id)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await mostrar(context, update.effective_chat.id, _usuario(update), await atendimento.iniciar(_usuario(update)))


async def cmd_perfil(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await mostrar(context, update.effective_chat.id, _usuario(update), await atendimento.ver_perfil(_usuario(update)))


async def cmd_novo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await mostrar(context, update.effective_chat.id, _usuario(update), await atendimento.recomecar(_usuario(update)))


async def cmd_esquecer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await mostrar(context, update.effective_chat.id, _usuario(update), atendimento.perguntar_esquecer())


async def cmd_custos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    usuario = _usuario(update)
    saidas = atendimento.custos() if atendimento.eh_admin(usuario) else [telas.texto(prompts.SO_ADMIN)]
    await mostrar(context, update.effective_chat.id, usuario, saidas)


async def avisar_admins(bot, texto: str) -> None:
    for admin in atendimento.admins():
        with contextlib.suppress(TelegramError, ValueError):
            await _enviar_texto(bot, int(admin), texto)


async def rodar_coleta(bot) -> list[coletor.ResultadoRede]:
    """Coleta as promoções dos sites; se uma rede quebrar, o admin recebe um aviso.
    Depois, as promoções novas viram avisos para quem tem o produto na lista."""
    async with _trava_coleta:
        resultados = await coletor.coletar()
    problemas = coletor.falhas(resultados)
    if problemas:
        linhas = "\n".join(f"• {p}" for p in problemas[:10])
        await avisar_admins(bot, f"⚠️ *Coletor de promoções com problema*\n{linhas}")
    await enviar_avisos(bot)
    return resultados


# --- avisos (C14) ---------------------------------------------------------------------
_trava_avisos = asyncio.Lock()


async def enviar_avisos(bot) -> int:
    """Manda o que avisos.pendentes() decidir (resumos semanais e promoções novas)."""
    async with _trava_avisos:
        enviados = 0
        for usuario, saida in avisos.pendentes():
            try:
                await _enviar_texto(bot, int(usuario), saida.texto, _teclado(saida))
                enviados += 1
            except Forbidden:  # a pessoa bloqueou o bot: para de mandar avisos
                avisos.desligar_por_bloqueio(usuario)
            except (TelegramError, ValueError) as erro:
                log.warning("Não consegui entregar um aviso: %s", erro)
            await asyncio.sleep(0.05)  # bem abaixo do limite do Telegram (30 mensagens/s)
        return enviados


async def tarefa_avisos(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue, a cada 15 min: resumo semanal na hora escolhida e avisos de promoção nova."""
    try:
        await enviar_avisos(context.bot)
    except Exception:
        log.exception("A rodada de avisos falhou")


async def tarefa_limpeza(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue, todo dia: promoções vencidas somem do banco."""
    apagadas = banco.apagar_promocoes_vencidas()
    if apagadas:
        log.info("Limpeza: %d promoções vencidas apagadas.", apagadas)


async def cmd_avisos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/avisos liga e desliga os avisos."""
    usuario = _usuario(update)
    await mostrar(context, update.effective_chat.id, usuario, [avisos.alternar(usuario)])


async def cmd_promo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/promo (só admin): cadastra uma oferta à mão; os avisos saem logo em seguida."""
    usuario = _usuario(update)
    texto = (update.effective_message.text or "").partition(" ")[2]
    saidas, nova = atendimento.cadastrar_promocao(usuario, texto)
    await mostrar(context, update.effective_chat.id, usuario, saidas)
    if nova:
        await enviar_avisos(context.bot)


async def tarefa_coleta(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue: 1 coleta por dia (C13)."""
    try:
        await rodar_coleta(context.bot)
    except Exception:
        log.exception("A coleta diária de promoções falhou")
        await avisar_admins(context.bot, "⚠️ A coleta diária de promoções falhou. Veja o registro do bot.")


async def cmd_coletar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/coletar (só admin): roda a coleta na hora e mostra o resultado por rede."""
    usuario, chat_id = _usuario(update), update.effective_chat.id
    if not atendimento.eh_admin(usuario):
        await mostrar(context, chat_id, usuario, [telas.texto(prompts.SO_ADMIN)])
        return
    if _trava_coleta.locked():
        await mostrar(context, chat_id, usuario, [telas.texto("⏳ Já tem uma coleta rodando. Espere ela terminar.")])
        return
    aviso = await _enviar_texto(context.bot, chat_id, "🔎 Coletando as promoções dos sites (5 s entre acessos "
                                                      "a cada site; pode levar alguns minutos)...")
    async with _digitando(context.bot, chat_id):
        resultados = await rodar_coleta(context.bot)
    if aviso is None or not await _editar(aviso, coletor.texto_resultado(resultados)):
        await mostrar(context, chat_id, usuario, [telas.texto(coletor.texto_resultado(resultados))])


async def comando_desconhecido(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await mostrar(context, update.effective_chat.id, _usuario(update), [telas.texto(prompts.COMANDO_DESCONHECIDO)])


# --- mensagens ---------------------------------------------------------------------
async def mensagem_de_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with _digitando(context.bot, update.effective_chat.id):
        saidas = await atendimento.responder(_usuario(update), update.effective_message.text)
    await mostrar(context, update.effective_chat.id, _usuario(update), saidas)


def _segundos(duracao: int | timedelta | None) -> float:
    if isinstance(duracao, timedelta):
        return duracao.total_seconds()
    return float(duracao or 0)


async def _receber_arquivo(update: Update, context: ContextTypes.DEFAULT_TYPE, *, file_id: str, tipo: str,
                           mime_type: str, tamanho: int | None, duracao: float = 0) -> None:
    """Baixa áudio, foto ou PDF só para a memória (nunca grava no disco) e manda para o atendimento."""
    usuario, chat_id = _usuario(update), update.effective_chat.id
    recusa = atendimento.motivo_para_recusar(usuario, duracao_s=duracao, tamanho_bytes=tamanho or 0)
    if recusa:
        await mostrar(context, chat_id, usuario, [telas.texto(recusa)])
        return
    async with _digitando(context.bot, chat_id):
        try:
            arquivo = await context.bot.get_file(file_id)
            dados = bytes(await arquivo.download_as_bytearray())
        except TelegramError as erro:
            log.error("Não consegui baixar um arquivo mandado pela pessoa: %s", erro)
            await mostrar(context, chat_id, usuario, [telas.texto(prompts.ERRO_DOWNLOAD)])
            return
        saidas = await atendimento.responder(usuario, update.effective_message.caption or "",
                                             anexo={"tipo": tipo, "mime_type": mime_type, "dados": dados})
        del dados  # o arquivo só existiu na memória
    await mostrar(context, chat_id, usuario, saidas)


async def mensagem_de_voz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    voz = update.effective_message.voice
    await _receber_arquivo(update, context, file_id=voz.file_id, tipo="audio", mime_type=voz.mime_type or "audio/ogg",
                           tamanho=voz.file_size, duracao=_segundos(voz.duration))


async def arquivo_de_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Áudio mandado como arquivo (mp3, m4a...), não como mensagem de voz (C6). Como documento,
    o Telegram não informa a duração: vale o limite de tamanho (10 MB)."""
    mensagem = update.effective_message
    audio = mensagem.audio or mensagem.document
    duracao = _segundos(getattr(audio, "duration", 0))
    await _receber_arquivo(update, context, file_id=audio.file_id, tipo="audio",
                           mime_type=atendimento.mime_de_audio(audio.mime_type), tamanho=audio.file_size,
                           duracao=duracao)


async def foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    maior = update.effective_message.photo[-1]  # o último tamanho é o maior
    await _receber_arquivo(update, context, file_id=maior.file_id, tipo="imagem", mime_type="image/jpeg",
                           tamanho=maior.file_size)


async def documento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.effective_message.document
    mime = doc.mime_type or ""
    tipo = "pdf" if mime == "application/pdf" else "imagem"
    await _receber_arquivo(update, context, file_id=doc.file_id, tipo=tipo, mime_type=mime, tamanho=doc.file_size)


async def localizacao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    loc = update.effective_message.location
    saidas = await atendimento.receber_localizacao(_usuario(update), loc.latitude, loc.longitude)
    await mostrar(context, update.effective_chat.id, _usuario(update), saidas)


async def figurinha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await mostrar(context, update.effective_chat.id, _usuario(update), await atendimento.figurinha(_usuario(update)))


async def tipo_nao_suportado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await mostrar(context, update.effective_chat.id, _usuario(update), [telas.texto(prompts.TIPO_NAO_SUPORTADO)])


async def botao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toque num botão. A confirmação vai SEM esperar a resposta do Telegram (esperar custava
    uma ida e volta de ~0,2 s antes de qualquer trabalho começar); o Telegram aceita a
    confirmação em até 15 s. Quem a dispara é o `executar_acao`, que sabe o texto do toast."""
    consulta = update.callback_query
    inicio = asyncio.get_running_loop().time()
    await executar_acao(context, consulta.message.chat.id, str(consulta.from_user.id), consulta.data,
                        origem=consulta.message, consulta=consulta)
    if MEDIR_LATENCIA:
        log.info("latencia: botao %s respondido em %.0f ms (trabalho + edicao)",
                 consulta.data.split(":")[0], (asyncio.get_running_loop().time() - inicio) * 1000)


async def ao_dar_erro(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Qualquer falha não prevista. O erro vai inteiro para o log e a pessoa recebe um aviso
    curto: sem isto, o 'digitando...' simplesmente parava e o chat ficava mudo."""
    log.error("Erro inesperado ao tratar uma mensagem", exc_info=context.error)
    chat = getattr(update, "effective_chat", None)
    if chat is None:  # erro fora de uma conversa (ex.: no polling): não há a quem avisar
        return
    with contextlib.suppress(TelegramError):
        await context.bot.send_message(chat.id, prompts.ERRO_INESPERADO)


async def _manter_conexao_quente(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tarefa periódica: uma chamada mínima só para a conexão com o Telegram não esfriar.

    Abrir conexão nova (DNS + TLS) custa ~0,7 s; usar uma já aberta custa ~0,2 s. Entre dois
    toques de botão costuma passar bem mais tempo do que o servidor espera, e sem isto toda
    primeira resposta depois de uma pausa pagava o aperto de mão de novo."""
    with contextlib.suppress(TelegramError):
        await context.bot.get_me()


async def ao_ligar(app: Application) -> None:
    banco.conectar()
    try:
        await app.bot.set_my_name(NOME_BOT)
        await app.bot.set_my_description(DESCRICAO)
        await app.bot.set_my_commands(COMANDOS)
    except TelegramError as erro:
        log.warning("Não consegui atualizar nome/descrição/comandos no Telegram: %s", erro)
    if app.job_queue:
        app.job_queue.run_repeating(_manter_conexao_quente, interval=INTERVALO_AQUECIMENTO, first=INTERVALO_AQUECIMENTO)
    log.info("Bot @%s ligado. Para desligar, aperte Ctrl+C.", app.bot.username)


def _conexao_telegram(tamanho: int = 256) -> HTTPXRequest:
    """Conexão com a API do Telegram, com keepalive longo.

    O PTB monta `httpx.Limits(max_connections=...)` e deixa o `keepalive_expiry` no padrão do
    httpx, que é 5 segundos: entre um toque e outro a conexão morria e a resposta seguinte
    pagava DNS + TLS outra vez. `httpx_kwargs` é aplicado por último pelo PTB, então este
    `limits` substitui o dele. Só a conexão das mensagens muda; a do getUpdates fica como está
    (ela já vive aberta por causa do long polling, e tem tempos próprios)."""
    return HTTPXRequest(connection_pool_size=tamanho,
                        httpx_kwargs={"limits": httpx.Limits(max_connections=tamanho,
                                                             keepalive_expiry=KEEPALIVE_SEGUNDOS)})


def main() -> None:
    faltando = [n for n in ("TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY", "GEMINI_MODEL") if not os.getenv(n)]
    if faltando:
        sys.exit("Falta preencher no arquivo .env: " + ", ".join(faltando))
    if not os.getenv("ANTHROPIC_API_KEY"):
        log.warning("Sem ANTHROPIC_API_KEY: o cardápio vai ser feito pelo Gemini (o roteador avisa no log).")

    app = (Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"])
           .request(_conexao_telegram())
           .concurrent_updates(True).post_init(ao_ligar).build())
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("perfil", cmd_perfil))
    app.add_handler(CommandHandler("novo", cmd_novo))
    app.add_handler(CommandHandler("esquecer", cmd_esquecer))
    app.add_handler(CommandHandler("custos", cmd_custos))
    app.add_handler(CommandHandler("coletar", cmd_coletar))
    app.add_handler(CommandHandler("avisos", cmd_avisos))
    app.add_handler(CommandHandler("promo", cmd_promo))
    app.add_handler(MessageHandler(filters.COMMAND, comando_desconhecido))
    app.add_handler(CallbackQueryHandler(botao))
    app.add_handler(MessageHandler(filters.TEXT, mensagem_de_texto))
    app.add_handler(MessageHandler(filters.VOICE, mensagem_de_voz))
    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, arquivo_de_audio))
    app.add_handler(MessageHandler(filters.PHOTO, foto))
    app.add_handler(MessageHandler(filters.Document.PDF | filters.Document.IMAGE, documento))
    app.add_handler(MessageHandler(filters.LOCATION, localizacao))
    app.add_handler(MessageHandler(filters.Sticker.ALL, figurinha))
    app.add_handler(MessageHandler(~filters.TEXT, tipo_nao_suportado))
    app.add_error_handler(ao_dar_erro)
    hora, minuto = (int(x) for x in HORA_COLETA.split(":"))
    app.job_queue.run_daily(tarefa_coleta, time=horario(hora, minuto, tzinfo=banco.FUSO_BRASILIA), name="coleta")
    app.job_queue.run_daily(tarefa_limpeza, time=horario(0, 10, tzinfo=banco.FUSO_BRASILIA), name="limpeza")
    app.job_queue.run_repeating(tarefa_avisos, interval=15 * 60, first=60, name="avisos")
    app.run_polling(allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY])


if __name__ == "__main__":
    main()
