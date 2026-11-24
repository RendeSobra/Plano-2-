"""Avisos automáticos (C14), sem depender do Telegram: decide QUEM recebe O QUÊ.
O canal (bot_telegram.py) chama estas funções pelo JobQueue e só entrega as mensagens.

- Promoção nova: avisa quem tem avisos ligados, mora na cidade da oferta e tem o produto
  na lista do plano atual ou nos pratos favoritos/preferências. Respeita as restrições
  (nunca avisa de algo que a pessoa não pode comer).
- Resumo semanal: no dia e na hora que a pessoa escolheu (padrão sábado 9h), com as
  promoções da semana, a comemoração da sobra e o convite para montar o cardápio.
- No máximo 1 aviso por dia por pessoa. Aviso de promoção só das 8h às 21h e nunca no
  dia do resumo (o resumo já traz as promoções).
"""
import logging
import re
from datetime import datetime

import banco
import cadastro
import mercado
import promocoes
import restricoes
import telas
from telas import Botao, Saida

log = logging.getLogger("rende.avisos")

HORA_INICIO, HORA_FIM = 8, 21     # avisos de promoção só nesse intervalo
MAX_ITENS_AVISO = 5
MAX_ITENS_RESUMO = 6
NOMES_DIA_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
_NEGACAO = re.compile(r"\b(nao gosto|nao como|nao quero|sem|odeio|evito)\b(\s+\w+){0,3}\s*$")


def _cidade(texto: str | None) -> str:
    return restricoes.normalizar(texto or promocoes.CIDADE_PADRAO)


def _ativos() -> list[dict]:
    """Pessoas com cadastro concluído e avisos ligados."""
    linhas = banco._db().execute("SELECT telegram_id FROM usuarios WHERE avisos_ativos = 1").fetchall()
    perfis = [banco.usuario(l["telegram_id"]) for l in linhas]
    return [p for p in perfis if p and cadastro.concluido(p)]


def interesses(perfil: dict) -> list[str]:
    """Itens da lista do plano atual + pratos favoritos (nota 4 ou 5)."""
    plano = banco.plano_atual(perfil["telegram_id"])
    itens = []
    if plano and plano.get("cesta"):
        itens += [l.get("nome") or l["item"] for l in plano["cesta"]["linhas"] if l.get("pacotes", 0) > 0]
    itens += [v["prato"] for v in (perfil.get("preferencias_pratos") or {}).values()
              if isinstance(v, dict) and v.get("nota", 0) >= 4]
    return itens


def _nas_preferencias(perfil: dict, nome: str) -> bool:
    """O produto aparece no texto de preferências sem estar negado ('não gosto de peixe')."""
    texto = restricoes.normalizar(perfil.get("preferencias") or "")
    alvo = promocoes.termos(nome)
    if not texto or not alvo:
        return False
    for achado in re.finditer(rf"\b{re.escape(restricoes.normalizar(nome))}\b", texto):
        if not _NEGACAO.search(texto[:achado.start()]):
            return True
    return False


def pode_comer(perfil: dict, nome: str) -> bool:
    return not restricoes.violacoes(nome, perfil.get("restricoes") or [], perfil.get("restricoes_outras"))


def relevantes(perfil: dict, promos: list[dict]) -> list[dict]:
    """Promoções da cidade da pessoa, que ela pode comer e que combinam com a lista/preferências."""
    cidade, itens = _cidade(perfil.get("cidade")), interesses(perfil)
    escolhidas = []
    for p in promos:
        if _cidade(p.get("cidade")) != cidade or not pode_comer(perfil, p["produto"]):
            continue
        if any(promocoes.combina(i, p["produto"]) for i in itens) or _nas_preferencias(perfil, p["produto"]):
            escolhidas.append(p)
    return escolhidas


def _linha(p: dict) -> str:
    descricao = " ".join(x for x in (p["produto"], p.get("marca"), p.get("tamanho")) if x)
    condicao = f" ({p['condicao']})" if p.get("condicao") else ""
    return f"• {descricao}: *{telas.brl(p['preco'])}* no {p['mercado']} até {telas.data_br(p['validade'])}{condicao}"


def _desconto(p: dict) -> float:
    return (p["preco_anterior"] - p["preco"]) / p["preco_anterior"] if p.get("preco_anterior") else 0.0


def _dia_do_resumo(perfil: dict, agora: datetime) -> bool:
    numero = perfil.get("aviso_dia_semana")
    return agora.weekday() == (5 if numero is None else int(numero))


# --- promoção nova --------------------------------------------------------------------------
def avisos_de_promocoes(agora: datetime | None = None) -> list[tuple[str, Saida]]:
    """Promoções cadastradas desde a última rodada -> no máximo 1 aviso por pessoa por dia."""
    agora = agora or banco.agora()
    if not HORA_INICIO <= agora.hour < HORA_FIM:
        return []  # fora do horário: as promoções novas esperam (o marcador não anda)
    ultimo = banco.estado("avisos_ultima_promo")
    if ultimo is None:  # primeira vez: não avisa de tudo o que já existia
        banco.gravar_estado("avisos_ultima_promo", str(banco.ultima_promocao_id()))
        return []
    novas = banco.promocoes_desde(int(ultimo))
    if not novas:
        return []
    banco.gravar_estado("avisos_ultima_promo", str(max(p["id"] for p in novas)))
    hoje = agora.date().isoformat()
    saidas = []
    for perfil in _ativos():
        if perfil.get("ultimo_aviso_dia") == hoje or _dia_do_resumo(perfil, agora):
            continue
        achadas = relevantes(perfil, novas)
        if not achadas:
            continue
        achadas.sort(key=lambda p: (-_desconto(p), p["preco"]))
        texto = [f"🔥 *{perfil.get('nome') or 'Oi'}*, achei promoção do que você usa:", ""]
        texto += [_linha(p) for p in achadas[:MAX_ITENS_AVISO]]
        if len(achadas) > MAX_ITENS_AVISO:
            texto.append(f"...e mais {len(achadas) - MAX_ITENS_AVISO}.")
        texto += ["", "No máximo 1 aviso por dia. Para desligar: /avisos"]
        botoes = [[Botao("🔥 Promoções", "pr:ver"), Botao("🛒 Lista", "pl:lista")]]
        banco.atualizar_perfil(perfil["telegram_id"], ultimo_aviso_dia=hoje)
        saidas.append((perfil["telegram_id"], telas.tela("\n".join(texto), botoes)))
    log.info("Avisos de promoção: %d promoções novas, %d avisos.", len(novas), len(saidas))
    return saidas


# --- resumo semanal ---------------------------------------------------------------------------
def _comemoracao(perfil: dict) -> str:
    plano = banco.plano_atual(perfil["telegram_id"])
    if not plano or not plano.get("cesta"):
        return ""
    total, orcamento = mercado.resumo(plano)["valor_total"], plano.get("orcamento") or 0
    if orcamento and total < orcamento:
        return f"💚 Seu último plano ficou em {telas.brl(total)} de {telas.brl(orcamento)}: sobrou *{telas.brl(orcamento - total)}*! 🎉"
    return ""


def resumo_semanal(perfil: dict, promos: list[dict]) -> Saida:
    nome = perfil.get("nome") or ""
    texto = [f"☀️ *Bom dia{', ' + nome if nome else ''}!* Seu resumo da semana:", ""]
    comemoracao = _comemoracao(perfil)
    if comemoracao:
        texto += [comemoracao, ""]
    cidade = perfil.get("cidade") or promocoes.CIDADE_PADRAO
    da_cidade = [p for p in promos if _cidade(p.get("cidade")) == _cidade(cidade)
                 and promocoes.eh_comida(p["produto"]) and pode_comer(perfil, p["produto"])]
    if da_cidade:
        suas = relevantes(perfil, da_cidade)
        outras = sorted((p for p in da_cidade if p not in suas), key=lambda p: (-_desconto(p), p["preco"]))
        escolhidas = (sorted(suas, key=lambda p: (-_desconto(p), p["preco"])) + outras)[:MAX_ITENS_RESUMO]
        texto.append(f"🔥 *{len(da_cidade)} promoções em {cidade}* esta semana. Destaques:")
        texto += [_linha(p) for p in escolhidas]
    else:
        texto.append("Ainda não tenho promoções novas na sua cidade esta semana.")
    texto += ["", "Quer que eu monte o cardápio da próxima semana já com as promoções?",
              "", "Para desligar os avisos: /avisos"]
    botoes = [[Botao("📅 Montar cardápio", "pl:montar")], [Botao("🔥 Promoções", "pr:ver")]]
    return telas.tela("\n".join(texto), botoes)


def resumos_semanais(agora: datetime | None = None) -> list[tuple[str, Saida]]:
    """Quem escolheu hoje e já passou da hora escolhida recebe o resumo (uma vez)."""
    agora = agora or banco.agora()
    hoje, hora = agora.date().isoformat(), agora.strftime("%H:%M")
    promos = None
    saidas = []
    for perfil in _ativos():
        if not _dia_do_resumo(perfil, agora) or hora < (perfil.get("aviso_horario") or "09:00"):
            continue
        if perfil.get("ultimo_resumo_dia") == hoje:
            continue
        if promos is None:
            promos = banco.promocoes_validas(limite=1000)
        banco.atualizar_perfil(perfil["telegram_id"], ultimo_resumo_dia=hoje, ultimo_aviso_dia=hoje)
        saidas.append((perfil["telegram_id"], resumo_semanal(perfil, promos)))
    if saidas:
        log.info("Resumo semanal: %d enviados.", len(saidas))
    return saidas


def pendentes(agora: datetime | None = None) -> list[tuple[str, Saida]]:
    """Tudo o que deve sair agora: primeiro os resumos do dia, depois os avisos de promoção."""
    agora = agora or banco.agora()
    return resumos_semanais(agora) + avisos_de_promocoes(agora)


# --- /avisos ----------------------------------------------------------------------------------
def tela_avisos(perfil: dict, editar: bool = False) -> Saida:
    numero = perfil.get("aviso_dia_semana")
    numero = 5 if numero is None else int(numero)
    dia = ("todo " if numero >= 5 else "toda ") + NOMES_DIA_SEMANA[numero]
    hora = perfil.get("aviso_horario") or "09:00"
    if perfil.get("avisos_ativos"):
        texto = ("🔔 *Avisos ligados.* Eu te aviso quando entrar promoção do que está na sua lista "
                 f"(no máximo 1 aviso por dia, das {HORA_INICIO}h às {HORA_FIM}h) e mando um resumo da semana "
                 f"{dia} às {hora}.\n\nPara mudar o dia ou a hora, é só me dizer: "
                 "\"quero o resumo no domingo às 8h\".")
        botoes = [[Botao("🔕 Desligar avisos", "av:off")]]
    else:
        texto = "🔕 *Avisos desligados.* Não vou mandar mensagens sem você pedir."
        botoes = [[Botao("🔔 Ligar avisos", "av:on")]]
    return telas.tela(texto, botoes, editar)


def alternar(usuario: str) -> Saida:
    """/avisos liga e desliga."""
    perfil = banco.obter_ou_criar_usuario(usuario)
    perfil = banco.atualizar_perfil(usuario, avisos_ativos=0 if perfil.get("avisos_ativos") else 1)
    return tela_avisos(perfil)


def acao(usuario: str, acao_txt: str) -> Saida:
    perfil = banco.atualizar_perfil(usuario, avisos_ativos=1 if acao_txt == "av:on" else 0)
    return tela_avisos(perfil, editar=True)


def desligar_por_bloqueio(usuario: str) -> None:
    """A pessoa bloqueou o bot: para de tentar mandar avisos."""
    banco.atualizar_perfil(usuario, avisos_ativos=0)
