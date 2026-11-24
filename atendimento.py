"""O "cérebro" do Rende: decide o que responder, sem saber qual é o canal (Telegram hoje).

- comandos: iniciar (/start), ver_perfil (/perfil), recomecar (/novo), esquecer (/esquecer);
- responder: texto, áudio, foto ou PDF (conversa com IA + ferramentas, ou cadastro);
- acao: botões ("cad:...", "per:...", "pl:...", "esq:...");
- montar_plano e trocar_prato: ações demoradas, com progresso informado ao canal.
Tudo devolve uma lista de telas.Saida, que o canal desenha.
"""
import asyncio
import logging
import os
from collections import defaultdict

import banco
import cadastro
import cardapio
import ferramentas
import mercado
import pdf
import prompts
import roteador
import telas
from cardapio import NOME_DIA, NOME_REFEICAO
from ia_comum import ErroIA
from telas import Botao, Saida

log = logging.getLogger("rende.atendimento")

MAX_PASSOS = 6                      # idas e vindas IA <-> ferramentas por mensagem
AUDIO_MAXIMO_SEGUNDOS = 120         # 2 minutos
ARQUIVO_MAXIMO_BYTES = 10 * 1024 * 1024  # 10 MB
ROTULOS = {"audio": "(mensagem de voz)", "imagem": "(foto)", "pdf": "(documento PDF)"}
DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]

_travas: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)  # uma coisa por vez para cada pessoa
_versoes: dict[str, int] = defaultdict(int)  # muda no /novo e /esquecer: respostas atrasadas são descartadas


# Tipos de áudio que o Gemini aceita; o Telegram às vezes manda nomes alternativos
_MIME_AUDIO = {"audio/x-m4a": "audio/mp4", "audio/m4a": "audio/mp4", "audio/x-wav": "audio/wav",
               "audio/wave": "audio/wav", "audio/mp3": "audio/mpeg", "audio/opus": "audio/ogg",
               "audio/x-flac": "audio/flac", "audio/x-aac": "audio/aac"}


def mime_de_audio(mime: str | None) -> str:
    mime = (mime or "").lower().split(";")[0].strip()
    if not mime.startswith("audio/"):
        return "audio/ogg"
    return _MIME_AUDIO.get(mime, mime)


# --- limites -----------------------------------------------------------------------
def _limite_dia() -> int:
    return int(os.getenv("LIMITE_MSG_DIA") or 30)


def motivo_para_recusar(usuario: str, duracao_s: float = 0, tamanho_bytes: int = 0) -> str | None:
    """Antes de baixar um arquivo: limite diário, áudio longo ou arquivo grande."""
    if banco.mensagens_hoje(usuario) >= _limite_dia():
        return prompts.LIMITE_DIA.format(limite=_limite_dia())
    if duracao_s > AUDIO_MAXIMO_SEGUNDOS:
        return prompts.AUDIO_LONGO
    if tamanho_bytes > ARQUIVO_MAXIMO_BYTES:
        return prompts.ARQUIVO_GRANDE
    return None


# --- comandos ----------------------------------------------------------------------
async def iniciar(usuario: str) -> list[Saida]:
    perfil = banco.obter_ou_criar_usuario(usuario)
    if cadastro.concluido(perfil):
        botoes = [[Botao("📅 Meu plano", "pl:res"), Botao("✨ Novo plano", "pl:refazer")],
                  [Botao("👤 Meu perfil", "per:ver")]]
        return [telas.tela(prompts.SAUDACAO_CONHECIDO.format(nome=perfil["nome"]), botoes)]
    passo = cadastro.passo_atual(perfil)
    if not perfil.get("nome") or passo in (None, "nome"):
        banco.limpar_historico(usuario)
        return cadastro.iniciar(usuario)
    return ([telas.texto(f"Que bom te ver de novo, *{perfil['nome']}*! Vamos continuar de onde paramos 🙂")]
            + cadastro.ir_para(usuario, passo if passo in cadastro.PASSOS else "pessoas"))


async def ver_perfil(usuario: str) -> list[Saida]:
    perfil = banco.obter_ou_criar_usuario(usuario)
    if not cadastro.concluido(perfil):
        return await iniciar(usuario)
    return [cadastro.resumo_perfil(perfil)]


async def recomecar(usuario: str) -> list[Saida]:
    _versoes[usuario] += 1
    banco.limpar_historico(usuario)
    return [telas.texto(prompts.RECOMECO)]


def perguntar_esquecer() -> list[Saida]:
    return [telas.tela(prompts.ESQUECER_PERGUNTA, [[Botao("🗑️ Sim, apagar tudo", "esq:sim")],
                                                    [Botao("❌ Cancelar", "esq:nao")]])]


async def esquecer(usuario: str) -> list[Saida]:
    _versoes[usuario] += 1
    banco.apagar_usuario(usuario)
    log.info("Dados de um usuário apagados a pedido (LGPD).")
    return [Saida(texto=prompts.ESQUECIDO, editar=True)]


# --- botões ------------------------------------------------------------------------
def _dia_de_hoje(plano: dict) -> str:
    hoje = cardapio.DIAS[banco.agora().weekday()][0]
    return hoje if hoje in telas.dias_do_plano(plano) else telas.dias_do_plano(plano)[0]


async def acao(usuario: str, acao_txt: str) -> list[Saida]:
    """Botões simples. 'pl:montar' e 'pl:tro:...' são demoradas: o canal chama montar_plano/trocar_prato."""
    banco.obter_ou_criar_usuario(usuario)
    if acao_txt.startswith("cad:"):
        return cadastro.acao(usuario, acao_txt)
    if acao_txt == "per:ver":
        return [cadastro.resumo_perfil(banco.usuario(usuario), editar_msg=True)]
    if acao_txt.startswith("per:"):
        return cadastro.editar(usuario, acao_txt.split(":", 1)[1])
    if acao_txt == "esq:sim":
        return await esquecer(usuario)
    if acao_txt == "esq:nao":
        return [Saida(texto=prompts.ESQUECER_CANCELADO, editar=True)]
    if acao_txt.startswith("pl:"):
        return await _acao_plano(usuario, acao_txt)
    if acao_txt.startswith("mm:"):
        return _acao_mercado(usuario, acao_txt)
    return [telas.texto("Não entendi esse botão 🤔")]


def _acao_mercado(usuario: str, acao_txt: str) -> list[Saida]:
    """🛒 Modo mercado: mm:ver, mm:t:<plano>:<i> (marca/desmarca), mm:p (paguei outro preço),
    mm:pi:<plano>:<i> (pede o preço daquele item), mm:fim (terminei), mm:x (título de seção)."""
    if acao_txt == "mm:x":
        return []  # título de seção: não faz nada
    plano = banco.plano_atual(usuario)
    if plano is None:
        return [telas.tela(prompts.SEM_PLANO, [[Botao("✨ Montar agora", "pl:montar")]])]
    banco.atualizar_perfil(usuario, aguardando=None)  # qualquer botão cancela a espera de um preço
    partes = acao_txt.split(":")
    if partes[1] in ("t", "pi"):
        if len(partes) < 4 or partes[2] != str(plano["id"]):  # botão de um plano que já mudou
            return [telas.modo_mercado(plano, aviso="O plano mudou: atualizei a lista.")]
        i = int(partes[3])
        if partes[1] == "t":
            return [telas.modo_mercado(mercado.alternar(usuario, i))]
        linha = mercado.linha_por_indice(plano, i)
        if linha is None:
            return [telas.modo_mercado(plano)]
        banco.atualizar_perfil(usuario, aguardando=f"preco:{plano['id']}:{i}")
        return [telas.pedir_preco(linha)]
    if partes[1] == "p":
        return [telas.escolher_item_preco(plano)]
    if partes[1] == "fim":
        plano = mercado.terminar(usuario)
        log.info("Modo mercado: compras encerradas (%d itens sem encontrar).",
                 len(plano["mercado"]["nao_encontrei"]))
        return [telas.compras_encerradas(plano, banco.usuario(usuario))]
    return [telas.modo_mercado(plano)]


def _resposta_de_preco(usuario: str, perfil: dict, texto: str) -> list[Saida] | None:
    """A pessoa tocou em [✏️ Paguei outro preço] e agora escreveu o valor. None = não era um preço
    (a espera é cancelada e a mensagem segue para a conversa normal)."""
    aguardando = perfil.get("aguardando") or ""
    banco.atualizar_perfil(usuario, aguardando=None)
    _, plano_id, indice = aguardando.split(":")
    preco = mercado.ler_preco(texto)
    plano = banco.plano_atual(usuario)
    if preco is None or plano is None or str(plano["id"]) != plano_id:
        return None
    plano, linha = mercado.informar_preco(usuario, int(indice), preco)
    if linha is None:
        return None
    aviso = f"✏️ Anotei: {linha['nome']} por {telas.brl(preco)} ({linha['embalagem']})."
    return [telas.modo_mercado(plano, editar=False, aviso=aviso)]


async def _acao_plano(usuario: str, acao_txt: str) -> list[Saida]:
    partes = acao_txt.split(":")
    plano, perfil = banco.plano_atual(usuario), banco.usuario(usuario)
    if partes[1] == "refazer":
        return [telas.confirmar_refazer()] if plano else [Saida(tipo="acao", acao="pl:montar")]
    if plano is None:
        return [telas.tela(prompts.SEM_PLANO, [[Botao("✨ Montar agora", "pl:montar")]])]

    if partes[1] == "res":
        return [telas.resultado(plano, perfil, editar=True)]
    if partes[1] == "dia":
        return [telas.dia(plano, partes[2] if len(partes) > 2 else _dia_de_hoje(plano))]
    if partes[1] == "lista":
        return [telas.lista(plano)]
    if partes[1] == "pdf":
        minutos = float(os.getenv("APAGAR_PDF_APOS_MIN") or 5)
        tempo = f"{minutos:g}".replace(".", ",")
        aviso = (f" Abra ou baixe: esta mensagem some em {tempo} min (o arquivo baixado continua no seu celular)."
                 if minutos > 0 else "")
        return [Saida(tipo="documento", texto="📄 Sua lista de compras." + aviso, dados=pdf.gerar(plano, perfil),
                      nome_arquivo=pdf.nome_arquivo(perfil), apagar_apos=minutos * 60)]
    if partes[1] == "ajo":  # plano acima do orçamento: a pessoa escolheu como resolver
        return _ajustar_orcamento(usuario, plano, partes[2] if len(partes) > 2 else "")

    d, t = partes[2], partes[3]
    try:
        prato = plano["refeicoes"][cardapio.indice(plano, d, t)]["prato"]
    except KeyError:
        return [telas.texto("Esse prato não está mais no seu plano.")]
    if partes[1] in ("rec", "pas"):
        try:
            rec = await cardapio.receita(usuario, d, t)
        except (cardapio.PlanoInvalido, ErroIA) as erro:
            log.error("Receita falhou: %s", erro)
            return [telas.texto("Não consegui preparar essa receita agora 😕 Tenta de novo daqui a pouco?")]
        if partes[1] == "rec":
            return [telas.receita(banco.plano_atual(usuario), perfil, d, t, rec)]
        return [telas.passo(rec, d, t, int(partes[4]))]
    if partes[1] == "fiz":
        return [telas.pedir_nota(prato, d, t)]
    if partes[1] == "not":
        nota = int(partes[4])
        cardapio.avaliar(usuario, prato, nota)
        return [telas.nota_salva(prato, nota)]
    return [telas.texto("Não entendi esse botão 🤔")]


def _ajustar_orcamento(usuario: str, plano: dict, como: str) -> list[Saida]:
    """Lacuna 3: tirar lanches e aumentar o orçamento são só conta; pratos mais simples monta de novo."""
    if como == "simples":
        return [Saida(tipo="acao", acao="pl:montar", texto=cardapio.pedido_mais_simples(plano))]
    if como == "lanches" and cardapio.tem_lanches(plano):
        plano = cardapio.tirar_lanches(usuario)
        aviso = "✂️ Tirei os lanches desta semana e dos próximos planos (dá para voltar no /perfil)."
    elif como == "orc":
        plano = cardapio.aumentar_orcamento(usuario)
        perfil = banco.usuario(usuario)
        periodo = "mês" if perfil.get("periodo") == "mes" else "semana"
        aviso = f"💰 Orçamento atualizado para {telas.brl(perfil['orcamento'])} por {periodo} (também no seu perfil)."
    else:
        return [telas.resultado(plano, banco.usuario(usuario), editar=True)]
    banco.adicionar_mensagem(usuario, "assistente", f"({aviso} Total agora {telas.brl(plano['cesta']['total'])} "
                                                    f"de {telas.brl(plano['orcamento'])}.)")
    return [telas.resultado(plano, banco.usuario(usuario), editar=True, aviso=aviso)]


# --- ações demoradas (com progresso) --------------------------------------------------
async def montar_plano(usuario: str, pedido: str = "", progresso: cardapio.Progresso = cardapio._nada) -> list[Saida]:
    perfil = banco.obter_ou_criar_usuario(usuario)
    if not cadastro.concluido(perfil):
        return [telas.texto(prompts.PLANO_PRECISA_CADASTRO)] + await iniciar(usuario)
    async with _travas[usuario]:
        try:
            plano = await cardapio.gerar_plano(usuario, pedido, progresso)
        except (cardapio.PlanoInvalido, ErroIA) as erro:
            log.error("Plano falhou: %s", erro)
            return [telas.texto(prompts.PLANO_ERRO)]
        banco.adicionar_mensagem(usuario, "assistente",
                                 f"(Montei o plano da semana: total {telas.brl(plano['cesta']['total'])} "
                                 f"de {telas.brl(plano['orcamento'])}.)")
    return [telas.resultado(plano, banco.usuario(usuario))]


async def trocar_prato(usuario: str, dia: str, tipo: str, pedido: str = "") -> list[Saida]:
    async with _travas[usuario]:
        try:
            antes = banco.plano_atual(usuario)["refeicoes"][cardapio.indice(banco.plano_atual(usuario), dia, tipo)]["prato"]
            plano = await cardapio.trocar_prato(usuario, dia, tipo, pedido)
        except cardapio.SemFolga as erro:  # repetir não adianta: explica em vez de convidar a tentar de novo
            log.info("Troca sem espaço no orçamento: %s", erro)
            return [telas.texto(prompts.TROCA_SEM_FOLGA.format(folga=telas.brl(max(erro.folga, 0))))]
        except (cardapio.PlanoInvalido, ErroIA, KeyError, TypeError) as erro:
            log.error("Troca falhou: %s", erro)
            return [telas.texto("Não consegui trocar esse prato agora 😕 Quer tentar de novo?")]
    novo = plano["refeicoes"][cardapio.indice(plano, dia, tipo)]["prato"]
    total, orc = plano["cesta"]["total"], plano["orcamento"]
    banco.adicionar_mensagem(usuario, "assistente",
                             f"(Troquei {NOME_REFEICAO[tipo]} de {NOME_DIA[dia]}: '{antes}' -> '{novo}'.)")
    resto = f"sobra {telas.brl(orc - total)}" if total <= orc else f"passou {telas.brl(total - orc)}"
    # a confirmação vai no topo da própria tela do dia (sem mensagem extra no chat)
    aviso = (f"🔁 Troquei! {NOME_REFEICAO[tipo]} agora é *{novo}*.\n"
             f"Total: *{telas.brl(total)}* ({resto}).")
    return [telas.dia(plano, dia, editar=True, aviso=aviso)]


# --- conversa ------------------------------------------------------------------------
def _perfil_txt(perfil: dict) -> str:
    favoritos, rejeitados = cardapio.favoritos(perfil), cardapio.rejeitados(perfil)
    linhas = [f"Nome: {perfil.get('nome') or '(ainda não sei)'}",
              f"Família: {perfil.get('adultos') or '?'} adulto(s), {perfil.get('criancas') or 0} criança(s)",
              f"Refeições: {', '.join(perfil.get('refeicoes') or []) or '?'}; dias: {', '.join(perfil.get('dias') or []) or '?'}",
              f"Vibe: {cardapio.VIBES.get(perfil.get('vibe'), '?')}",
              f"Restrições: {', '.join(perfil.get('restricoes') or []) or 'nenhuma'}"
              + (f"; outras: {perfil['restricoes_outras']}" if perfil.get("restricoes_outras") else ""),
              f"Cozinha: {', '.join(perfil.get('utensilios') or []) or '?'}",
              f"Mercados: {', '.join(perfil.get('mercados') or []) or '?'}; cidade: {perfil.get('cidade') or '?'}",
              f"Orçamento: {telas.brl(perfil['orcamento']) if perfil.get('orcamento') else '?'} por "
              f"{'mês' if perfil.get('periodo') == 'mes' else 'semana'}",
              f"Avisos de promoção: {'ligados' if perfil.get('avisos_ativos') else 'desligados'}"]
    if perfil.get("preferencias"):
        linhas.append(f"Observações: {perfil['preferencias']}")
    if favoritos:
        linhas.append(f"Pratos favoritos: {'; '.join(favoritos)}")
    if rejeitados:
        linhas.append(f"Pratos rejeitados: {'; '.join(rejeitados)}")
    return "\n".join(linhas)


def _plano_txt(plano: dict) -> str:
    total, orc = plano["cesta"]["total"], plano.get("orcamento") or 0
    linhas = [f"Total {telas.brl(total)} de {telas.brl(orc)} ({'sobra' if total <= orc else 'passou'} "
              f"{telas.brl(abs(orc - total))}). Pratos:"]
    linhas += [f"- {NOME_DIA[r['dia']]} ({r['dia']}) {NOME_REFEICAO[r['tipo']]} ({r['tipo']}): {r['prato']}"
               for r in plano["refeicoes"]]
    return "\n".join(linhas)


def _sistema_extra(usuario: str, passo_cadastro: str | None) -> str:
    """Parte das instruções que muda (perfil, plano, data). A parte fixa (prompts.CONVERSA)
    vai separada para o Claude guardar em cache."""
    perfil = banco.usuario(usuario)
    partes = ["# Perfil salvo da pessoa\n" + _perfil_txt(perfil)]
    plano = banco.plano_atual(usuario)
    if plano:
        partes.append("# Plano atual da semana\n" + _plano_txt(plano))
    agora = banco.agora()
    partes.append(f"# Hoje\n{DIAS_SEMANA[agora.weekday()]}, {agora.strftime('%d/%m/%Y')}")
    if passo_cadastro:
        partes.append(prompts.CADASTRO.format(passo=passo_cadastro,
                                              pergunta=cadastro.PERGUNTAS.get(passo_cadastro, "")))
    return "\n\n".join(partes)


async def _conversar(usuario: str, historico: list[dict], mensagem: dict, passo_cadastro: str | None = None,
                     tarefa: str | None = None) -> tuple[ferramentas.Contexto, str]:
    ctx = ferramentas.Contexto(usuario=usuario)
    especialista_ok = roteador.liberado(roteador.claude("sonnet"))[0]
    definicoes = ferramentas.definicoes(cadastro=bool(passo_cadastro),
                                        com_especialista=especialista_ok and tarefa != "complexo")
    tarefa = tarefa or ("cadastro" if passo_cadastro else "midia" if mensagem.get("anexo") else "conversa")
    mensagens = historico + [mensagem]
    for _ in range(MAX_PASSOS):
        resposta = await roteador.gerar(tarefa, sistema=prompts.CONVERSA,
                                        sistema_extra=_sistema_extra(usuario, passo_cadastro),
                                        mensagens=mensagens, ferramentas=definicoes)
        if not resposta.chamadas:
            return ctx, resposta.texto
        mensagens.append({"papel": "assistente", "texto": resposta.texto,
                          "chamadas": resposta.chamadas, "bruto": resposta.bruto})
        resultados = []
        for chamada in resposta.chamadas:
            resultados.append({"id": chamada.id, "nome": chamada.nome,
                               "conteudo": await ferramentas.executar(chamada, ctx)})
        mensagens.append({"papel": "ferramenta", "resultados": resultados})
        if ctx.especialista and tarefa != "complexo":
            # pedido complexo: o turno inteiro é refeito pelo modelo mais forte (roteador -> Claude)
            mensagem2 = {**mensagem, "texto": f"{mensagem.get('texto', '')}\n(Resumo do pedido: {ctx.especialista})".strip()}
            ctx2, final = await _conversar(usuario, historico, mensagem2, tarefa="complexo")
            ctx2.saidas = ctx.saidas + ctx2.saidas
            return ctx2, final
    return ctx, ""


async def responder(usuario: str, texto: str, anexo: dict | None = None) -> list[Saida]:
    """Mensagem de texto, voz, foto ou PDF. anexo: {"tipo", "mime_type", "dados"} (só na memória)."""
    perfil = banco.obter_ou_criar_usuario(usuario)
    async with _travas[usuario]:
        if banco.mensagens_hoje(usuario) >= _limite_dia():
            return [telas.texto(prompts.LIMITE_DIA.format(limite=_limite_dia()))]
        versao = _versoes[usuario]
        passo = cadastro.passo_atual(perfil)
        if passo is None and not perfil.get("nome"):  # chegou sem /start
            banco.contar_mensagem(usuario)
            return cadastro.iniciar(usuario)
        if passo and not anexo:
            rapida = cadastro.resposta_escrita(usuario, texto)
            if rapida is not None:
                banco.contar_mensagem(usuario)
                return rapida
        if (perfil.get("aguardando") or "").startswith("preco:") and not anexo:
            preco = _resposta_de_preco(usuario, perfil, texto)
            if preco is not None:
                banco.contar_mensagem(usuario)
                return preco

        texto_hist = f"{ROTULOS[anexo['tipo']]} {texto}".strip() if anexo else texto
        mensagem = {"papel": "usuario", "texto": texto_hist, **({"anexo": anexo} if anexo else {})}
        try:
            ctx, final = await _conversar(usuario, banco.historico(usuario), mensagem, passo_cadastro=passo)
        except ErroIA as erro:
            log.error("A IA falhou ao responder: %s", erro)
            return [] if versao != _versoes[usuario] else [telas.texto(prompts.ERRO_IA)]
        if versao != _versoes[usuario]:
            log.info("Resposta descartada: a pessoa recomeçou enquanto a IA pensava.")
            return []

        banco.adicionar_mensagem(usuario, "usuario", texto_hist)
        if final:
            banco.adicionar_mensagem(usuario, "assistente", final)
        banco.contar_mensagem(usuario)

        saidas = ([telas.texto(final)] if final else []) + ctx.saidas
        if passo:  # respondeu o cadastro escrevendo ou por áudio
            if ctx.perfil_salvo:
                saidas += cadastro.avancar(usuario, editar_msg=False)
            else:
                saidas.append(cadastro.tela_do_passo(banco.usuario(usuario), passo))
        return saidas


async def figurinha(usuario: str) -> list[Saida]:
    if banco.mensagens_hoje(usuario) >= _limite_dia():
        return [telas.texto(prompts.LIMITE_DIA.format(limite=_limite_dia()))]
    banco.contar_mensagem(usuario)
    return [telas.texto(prompts.FIGURINHA)]


async def receber_localizacao(usuario: str, latitude: float, longitude: float) -> list[Saida]:
    if banco.mensagens_hoje(usuario) >= _limite_dia():
        return [telas.texto(prompts.LIMITE_DIA.format(limite=_limite_dia()))]
    banco.contar_mensagem(usuario)
    banco.atualizar_perfil(usuario, latitude=latitude, longitude=longitude,
                           localizacao_em=banco.agora().isoformat(timespec="seconds"))
    return [telas.texto("📍 Guardei sua localização! Em breve vou mostrar os mercados perto de você.")]


# --- administração --------------------------------------------------------------------
def eh_admin(usuario: str) -> bool:
    return usuario in {i.strip() for i in (os.getenv("ADMIN_IDS") or "").split(",") if i.strip()}


NOMES_NIVEL = {"gemini": "Gemini", "gemini-reserva": "Gemini reserva", "haiku": "Haiku", "sonnet": "Sonnet",
               "opus": "Opus"}
NOMES_TAREFA = {"conversa": "conversa", "midia": "áudio/foto", "cadastro": "cadastro", "receita": "receitas",
                "cardapio": "gerar cardápio", "troca": "trocar prato", "complexo": "pedido complexo",
                "encarte": "encartes"}


def _mil(n: int | None) -> str:
    n = n or 0
    return f"{n / 1000:.1f}k".replace(".", ",") if n >= 1000 else str(n)


def custos() -> list[Saida]:
    hoje, mes = banco.hoje(), banco.primeiro_dia_do_mes()
    cotacao = float(os.getenv("COTACAO_DOLAR") or 0)

    def dolar(valor: float) -> str:
        return f"US$ {valor:.4f}".replace(".", ",") + (f" (≈ {telas.brl(valor * cotacao)})" if cotacao else "")

    def bloco(titulo: str, desde: str) -> list[str]:
        linhas = banco.resumo_custos(desde)
        saida = [f"*{titulo}*"]
        for l in linhas:
            cache = f" · cache {_mil(l['cache_leitura'])} lidos" if l["cache_leitura"] else ""
            chamadas = f"{l['chamadas']} chamada" + ("s" if l["chamadas"] != 1 else "")
            saida.append(f"• {NOMES_NIVEL.get(l['nivel'], l['nivel'] or l['modelo'])}: {chamadas} · "
                         f"{_mil(l['entrada'])} entrada / {_mil(l['saida'])} saída{cache} · {dolar(l['custo'] or 0)}")
        if not linhas:
            saida.append("• nenhuma chamada")
        saida.append(f"Total: {dolar(sum(l['custo'] or 0 for l in linhas))}")
        return saida

    linhas = ["💸 *Custos de IA*", ""] + bloco(f"Hoje ({telas.data_br(hoje)})", hoje) + [""] + bloco("Este mês", mes)
    tarefas = banco.chamadas_por_tarefa(hoje)
    if tarefas:
        linhas += ["", "*Quem fez o quê hoje*"]
        linhas += [f"• {NOMES_TAREFA.get(t['tarefa'], t['tarefa'])}: {NOMES_NIVEL.get(t['nivel'], t['nivel'])} "
                   f"({t['vezes']}x, {dolar(t['custo'] or 0)})" for t in tarefas]
    subidas = banco.resumo_escalonamentos(hoje)
    linhas += ["", f"*Subidas de nível hoje:* {sum(s['vezes'] for s in subidas)}"]
    linhas += [f"• {s['motivo']}: {s['vezes']}x" for s in subidas]
    limites = " · ".join(f"{NOMES_NIVEL[n]} {banco.chamadas_modelo_hoje(roteador.claude(n).modelo)}/{roteador.limite(n)}"
                         for n in ("haiku", "sonnet", "opus"))
    linhas += ["", f"Limites hoje: {limites}", "Preços de tabela. No plano gratuito do Gemini o custo real é zero."]
    return [telas.texto("\n".join(linhas))]
