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
from datetime import timedelta

from dotenv import load_dotenv
from telegram import (BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, KeyboardButton,
                      Message, ReplyKeyboardMarkup, Update)
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler,
                          filters)

load_dotenv()

import atendimento  # noqa: E402  (depois do load_dotenv: os módulos leem o .env)
import banco  # noqa: E402
import cardapio  # noqa: E402
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
ESPERA_ENTRE_ETAPAS = 0.8  # para a "animação" ser visível e não estourar o limite de edições
NOME_BOT = "Rende"
DESCRICAO = ("Seu amigo do mercado: monto o cardápio da semana no seu orçamento, com a lista de compras "
             "por embalagem, receitas passo a passo e promoções.")
COMANDOS = [BotCommand("start", "Começar"), BotCommand("perfil", "Ver ou mudar meu perfil"),
            BotCommand("novo", "Recomeçar a conversa (mantém o perfil)"),
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
    return re.sub(r"\*([^*\n]+?)\*", r"<b>\1</b>", texto)


def sem_formatacao(texto: str) -> str:
    return texto.replace("*", "")


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


async def _editar(mensagem: Message, texto: str, teclado=None) -> bool:
    """Edita uma mensagem (navegação por botões). Devolve False se não deu para editar."""
    if len(texto) > TAMANHO_MAXIMO:
        return False
    try:
        await mensagem.edit_text(para_html(texto), parse_mode=ParseMode.HTML, reply_markup=teclado)
        return True
    except BadRequest as erro:
        if "not modified" in str(erro).lower():
            return True
        log.warning("Não deu para editar a mensagem (%s); enviando uma nova.", erro)
        return False


# --- "digitando..." -------------------------------------------------------------
async def _manter_digitando(bot, chat_id: int, parar: asyncio.Event) -> None:
    relogio = asyncio.get_running_loop().time
    inicio, avisou = relogio(), False
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
        parar.set()
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


async def executar_acao(context: ContextTypes.DEFAULT_TYPE, chat_id: int, usuario: str, acao: str,
                        texto: str = "", origem: Message | None = None) -> None:
    if acao == "pl:montar":
        await montar_com_animacao(context, chat_id, usuario, texto, origem)
    elif acao.startswith("pl:tro:"):
        _, _, dia, tipo = acao.split(":")
        await trocar_com_progresso(context, chat_id, usuario, dia, tipo, texto, origem)
    else:
        async with _digitando(context.bot, chat_id):
            saidas = await atendimento.acao(usuario, acao)
        await mostrar(context, chat_id, usuario, saidas, origem)


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
    consulta = update.callback_query
    await consulta.answer()  # tira o "relógio" do botão na hora
    await executar_acao(context, consulta.message.chat.id, str(consulta.from_user.id), consulta.data,
                        origem=consulta.message)


async def ao_dar_erro(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Erro inesperado ao tratar uma mensagem", exc_info=context.error)


async def ao_ligar(app: Application) -> None:
    banco.conectar()
    try:
        await app.bot.set_my_name(NOME_BOT)
        await app.bot.set_my_description(DESCRICAO)
        await app.bot.set_my_commands(COMANDOS)
    except TelegramError as erro:
        log.warning("Não consegui atualizar nome/descrição/comandos no Telegram: %s", erro)
    log.info("Bot @%s ligado. Para desligar, aperte Ctrl+C.", app.bot.username)


def main() -> None:
    faltando = [n for n in ("TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY", "GEMINI_MODEL") if not os.getenv(n)]
    if faltando:
        sys.exit("Falta preencher no arquivo .env: " + ", ".join(faltando))
    if not os.getenv("ANTHROPIC_API_KEY"):
        log.warning("Sem ANTHROPIC_API_KEY: o cardápio vai ser feito pelo Gemini (o roteador avisa no log).")

    app = (Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"])
           .concurrent_updates(True).post_init(ao_ligar).build())
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("perfil", cmd_perfil))
    app.add_handler(CommandHandler("novo", cmd_novo))
    app.add_handler(CommandHandler("esquecer", cmd_esquecer))
    app.add_handler(CommandHandler("custos", cmd_custos))
    app.add_handler(MessageHandler(filters.COMMAND, comando_desconhecido))
    app.add_handler(CallbackQueryHandler(botao))
    app.add_handler(MessageHandler(filters.TEXT, mensagem_de_texto))
    app.add_handler(MessageHandler(filters.VOICE, mensagem_de_voz))
    app.add_handler(MessageHandler(filters.PHOTO, foto))
    app.add_handler(MessageHandler(filters.Document.PDF | filters.Document.IMAGE, documento))
    app.add_handler(MessageHandler(filters.LOCATION, localizacao))
    app.add_handler(MessageHandler(filters.Sticker.ALL, figurinha))
    app.add_handler(MessageHandler(~filters.TEXT, tipo_nao_suportado))
    app.add_error_handler(ao_dar_erro)
    app.run_polling(allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY])


if __name__ == "__main__":
    main()
