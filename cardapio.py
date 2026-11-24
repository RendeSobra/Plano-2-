"""Gera, confere e altera o plano da semana (cardápio + lista por embalagem) e as receitas.

Quem decide o modelo é o roteador (Claude para gerar e trocar o cardápio; Gemini
para as receitas). Tudo o que a IA devolve passa pela conferência em código:
estrutura, alergias, utensílios, repetição de pratos, embalagens e orçamento.
"""
import copy
import json
import logging
import math
import re
from collections.abc import Awaitable, Callable

import banco
import cesta
import prompts
import restricoes
import roteador
from ia_comum import ErroIA

log = logging.getLogger("rende.cardapio")

# --- catálogo (usado também no cadastro e nas telas) ----------------------------
DIAS = [("seg", "Segunda"), ("ter", "Terça"), ("qua", "Quarta"), ("qui", "Quinta"),
        ("sex", "Sexta"), ("sab", "Sábado"), ("dom", "Domingo")]
REFEICOES = [("cafe", "Café da manhã", "☕"), ("almoco", "Almoço", "🍛"), ("jantar", "Jantar", "🍲"),
             ("lanche", "Lanche", "🥪"), ("marmita", "Marmita", "🍱")]
VIBES = {"rapido": "Rápido e fácil", "domingo": "Cozinhar no domingo para a semana",
         "uma_panela": "Uma panela só", "vo": "Comida de vó", "leve": "Leve/saudável",
         "fitness": "Fitness (mais proteína)"}
UTENSILIOS = {"fogao": "Fogão", "forno": "Forno", "microondas": "Micro-ondas", "airfryer": "Airfryer",
              "pressao": "Panela de pressão", "eletrica": "Panela elétrica"}
MERCADOS = {"assai": "Assaí", "atacadao": "Atacadão/Carrefour", "tatico": "Tático", "barao": "Barão",
            "cerrado": "Cerrado", "diadia": "Dia a Dia", "qualquer": "Qualquer um"}
SECOES = ["Hortifrúti", "Açougue e aves", "Ovos e laticínios", "Padaria", "Mercearia",
          "Temperos e outros"]
NOME_DIA = dict(DIAS)
NOME_REFEICAO = {k: n for k, n, _ in REFEICOES}
ICONE_REFEICAO = {k: i for k, _, i in REFEICOES}
PRINCIPAIS = {"almoco", "jantar"}  # onde vale "o mesmo prato no máximo 1 vez por semana"
REPETIR_SEMANA_PASSADA_MAX = 2      # a partir de quantos pratos repetidos da semana passada o plano é refeito

ETAPAS = ["Vendo as promoções da semana", "Escolhendo as receitas", "Calculando a cesta",
          "Conferindo o orçamento", "Finalizando"]


class PlanoInvalido(Exception):
    """A IA não conseguiu um plano que passe na conferência (ex.: alergia) depois das tentativas."""


class SemFolga(PlanoInvalido):
    """A troca não cabe no orçamento. `folga`: quanto sobra para o prato novo (negativo = já passou)."""

    def __init__(self, mensagem: str, folga: float):
        super().__init__(mensagem)
        self.folga = folga


# --- esquemas JSON pedidos à IA ------------------------------------------------
# Formato COMPACTO (24/11): o que a IA escreve é o que se paga. O cardápio volta só com
# pratos, ingredientes com quantidade e compras, sem modo de preparo (a receita é gerada
# quando a pessoa abre o prato). Chaves curtas, café/lanche repetido numa entrada só
# ("dias": [...]), ingrediente sem unidade (vem da embalagem) e "perecível" deduzido da
# seção. Medido com o plano real de 23/11: 7.446 -> ~4.700 tokens de JSON.
# O resto do código continua usando o formato interno (ver expandir()).
_INGR = {"type": "object", "additionalProperties": False, "required": ["item", "qtd"],
         "properties": {"item": {"type": "string"}, "qtd": {"type": "number"}}}
_PRATO = {  # campos comuns ao cardápio e à troca
    "prato": {"type": "string"},
    "min": {"type": "integer"},
    "equip": {"type": "array", "items": {"type": "string", "enum": list(UTENSILIOS)}},
    "ingr": {"type": "array", "items": _INGR},
    "sobra": {"type": "string"},
}
_REFEICAO = {"type": "object", "additionalProperties": False,
             "required": ["dias", "tipo", "prato", "min", "equip", "ingr", "sobra"],
             "properties": {"dias": {"type": "array", "items": {"type": "string", "enum": [d for d, _ in DIAS]}},
                            "tipo": {"type": "string", "enum": [r for r, _, _ in REFEICOES]},
                            **_PRATO}}
_REFEICAO_TROCA = {"type": "object", "additionalProperties": False,
                   "required": ["prato", "min", "equip", "ingr", "sobra"], "properties": _PRATO}
_COMPRA = {"type": "object", "additionalProperties": False,
           "required": ["item", "emb", "tam", "un", "preco", "secao", "promo"],
           "properties": {"item": {"type": "string"}, "emb": {"type": "string"}, "tam": {"type": "number"},
                          "un": {"type": "string", "enum": ["g", "ml", "un"]}, "preco": {"type": "number"},
                          "secao": {"type": "string", "enum": SECOES}, "promo": {"type": "integer"}}}
ESQUEMA_PLANO = {"type": "object", "additionalProperties": False, "required": ["refeicoes", "compras"],
                 "properties": {"refeicoes": {"type": "array", "items": _REFEICAO},
                                "compras": {"type": "array", "items": _COMPRA}}}
ESQUEMA_TROCA = {"type": "object", "additionalProperties": False, "required": ["refeicao", "compras_novas"],
                 "properties": {"refeicao": _REFEICAO_TROCA,
                                "compras_novas": {"type": "array", "items": _COMPRA}}}
# O que estraga não vai para a despensa da semana seguinte.
PERECIVEL = {"Hortifrúti": True, "Açougue e aves": True, "Ovos e laticínios": True, "Padaria": True,
             "Mercearia": False, "Temperos e outros": False}
_ORDEM_DIA = {d: i for i, (d, _) in enumerate(DIAS)}
_ORDEM_REFEICAO = {r: i for i, (r, _, _) in enumerate(REFEICOES)}
# Quantidade de um ingrediente numa refeição que só pode ser engano (ex.: 300 "un" de ovo),
# para até 4 porções; cresce com a família.
LIMITE_QTD = {"un": 60, "g": 6000, "ml": 6000}
ESQUEMA_RECEITA = {"type": "object", "additionalProperties": False,
                   "required": ["ingredientes", "passos", "tempo_min", "dica"],
                   "properties": {"ingredientes": {"type": "array", "items": {"type": "string"}},
                                  "passos": {"type": "array", "items": {"type": "string"}},
                                  "tempo_min": {"type": "integer"}, "dica": {"type": "string"}}}


# --- ajudantes ------------------------------------------------------------------
def ler_json(texto: str) -> dict:
    texto = (texto or "").strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
    return json.loads(texto)


def produto_de_compra(c: dict) -> dict:
    """Uma compra do formato compacto -> produto do formato interno (o que cesta, telas e PDF usam)."""
    return {"item": c["item"], "nome": c["item"], "embalagem": c["emb"], "tamanho": c["tam"], "unidade": c["un"],
            "preco": c["preco"], "secao": c["secao"], "perecivel": PERECIVEL.get(c["secao"], True),
            "promocao_id": int(c.get("promo") or 0)}


def refeicoes_de(entrada: dict, unidades: dict[str, str]) -> list[dict]:
    """Uma entrada compacta (um prato em vários dias) -> uma refeição interna por dia.
    A unidade de cada ingrediente é a da embalagem; sem embalagem fica '?' e a conferência reprova."""
    return [{"dia": dia, "tipo": entrada["tipo"], "prato": entrada["prato"], "tempo_min": entrada["min"],
             "equipamentos": list(entrada.get("equip") or []),
             "ingredientes": [{"item": i["item"], "quantidade": i["qtd"],
                               "unidade": unidades.get(cesta.chave(i["item"]), "?")} for i in entrada["ingr"]],
             "sobra_planejada": entrada.get("sobra") or ""}
            for dia in entrada["dias"]]


def expandir(dados: dict) -> dict:
    """Resposta compacta da IA -> plano no formato interno (refeicoes por dia + produtos)."""
    produtos = [produto_de_compra(c) for c in dados["compras"]]
    unidades: dict[str, str] = {}
    for p in produtos:
        unidades.setdefault(cesta.chave(p["item"]), p["unidade"])  # item repetido: vale o primeiro (como na cesta)
    refeicoes = [r for entrada in dados["refeicoes"] for r in refeicoes_de(entrada, unidades)]
    refeicoes.sort(key=lambda r: (_ORDEM_DIA.get(r["dia"], 99), _ORDEM_REFEICAO.get(r["tipo"], 99)))
    return {"refeicoes": refeicoes, "produtos": produtos}


def orcamento_semanal(perfil: dict) -> float:
    valor = float(perfil.get("orcamento") or 0)
    return round(valor / 4.3, 2) if perfil.get("periodo") == "mes" else valor


def sobra_util(texto: str | None) -> bool:
    """A IA às vezes escreve 'Sem sobra.' em vez de deixar vazio: isso não é sobra planejada."""
    t = restricoes.normalizar(texto or "")
    return bool(t) and not t.startswith(("sem sobra", "nenhuma", "nao ha", "nao tem", "sem "))


def favoritos(perfil: dict) -> list[str]:
    return [v["prato"] for v in perfil.get("preferencias_pratos", {}).values() if v.get("nota", 0) >= 4]


def rejeitados(perfil: dict) -> list[str]:
    return [v["prato"] for v in perfil.get("preferencias_pratos", {}).values() if v.get("nota", 5) <= 2]


def pratos_semana_passada(usuario: str) -> list[str]:
    semana = banco.semana_atual()
    for plano in banco.planos(usuario, 3):
        if plano["semana"] != semana:
            return [r["prato"] for r in plano.get("refeicoes", []) if r["tipo"] in PRINCIPAIS]
    return []


def despensa_base(usuario: str, perfil: dict) -> dict:
    """O que a pessoa tem em casa ANTES do plano desta semana.
    Plano de semana passada: herda o que sobrou dele. Refazer na mesma semana: usa o mesmo ponto de partida."""
    atual = banco.plano_atual(usuario)
    if atual is None:
        return perfil.get("despensa") or {}
    if atual["semana"] != banco.semana_atual():
        return atual.get("cesta", {}).get("despensa_final") or {}
    if (atual.get("mercado") or {}).get("finalizado"):  # já fez as compras (Modo mercado): o que tem agora
        return perfil.get("despensa") or {}
    return atual.get("despensa_inicial") or {}


def _slots(perfil: dict) -> list[tuple[str, str]]:
    dias = [d for d, _ in DIAS if d in (perfil.get("dias") or [])]
    tipos = [r for r, _, _ in REFEICOES if r in (perfil.get("refeicoes") or [])]
    return [(d, t) for d in dias for t in tipos]


# --- conferência em código -----------------------------------------------------
def conferir(plano: dict, perfil: dict, calc: dict, orcamento: float,
             semana_passada: list[str] | None = None) -> tuple[list[str], list[str]]:
    """(problemas graves, avisos). Graves fazem a IA refazer; avisos só são registrados."""
    graves, avisos = [], []
    esperados = _slots(perfil)
    recebidos = [(r.get("dia"), r.get("tipo")) for r in plano.get("refeicoes", [])]
    faltando = [s for s in esperados if s not in recebidos]
    sobrando = [s for s in recebidos if s not in esperados]
    repetidos = {s for s in recebidos if recebidos.count(s) > 1}
    if faltando:
        graves.append("faltam refeições: " + ", ".join(f"{NOME_REFEICAO[t]} de {NOME_DIA[d]}" for d, t in faltando))
    if sobrando:
        graves.append("refeições que não foram pedidas: " + ", ".join(f"{t} de {d}" for d, t in sobrando))
    if repetidos:
        graves.append("o mesmo horário aparece mais de uma vez: " + ", ".join(f"{t} de {d}" for d, t in repetidos))

    escala = max(1.0, cesta.porcoes(perfil.get("adultos"), perfil.get("criancas")) / 4)
    for r in plano.get("refeicoes", []):
        if not r.get("ingredientes"):
            graves.append(f"'{r.get('prato')}' está sem ingredientes")
        for ing in r.get("ingredientes", []):
            qtd, limite_un = float(ing.get("quantidade") or 0), LIMITE_QTD.get(ing.get("unidade"))
            if qtd <= 0:
                graves.append(f"quantidade zerada de {ing['item']} em '{r.get('prato')}'")
            elif limite_un and qtd > limite_un * escala:
                graves.append(f"quantidade fora do normal: {qtd:g} {ing['unidade']} de {ing['item']} em "
                              f"'{r.get('prato')}' (a quantidade vai na unidade da embalagem)")
    for p in plano.get("produtos", []):
        if float(p.get("tamanho") or 0) <= 0 or float(p.get("preco") or 0) <= 0:
            graves.append(f"embalagem inválida para '{p.get('item')}'")
    if calc["sem_produto"]:
        graves.append("ingredientes sem embalagem na lista: " + ", ".join(calc["sem_produto"]))
    if calc["unidade_errada"]:
        graves.append("unidade diferente entre receita e embalagem: " + ", ".join(calc["unidade_errada"]))

    # alergias e restrições (nomes dos pratos, ingredientes e produtos)
    textos = [r.get("prato", "") for r in plano.get("refeicoes", [])]
    textos += [i["item"] for r in plano.get("refeicoes", []) for i in r.get("ingredientes", [])]
    textos += [p.get("nome", "") for p in plano.get("produtos", [])]
    graves += restricoes.violacoes_em(textos, perfil.get("restricoes") or [], perfil.get("restricoes_outras"))

    # utensílios: só o que a pessoa tem
    tem = set(perfil.get("utensilios") or [])
    if tem:
        for r in plano.get("refeicoes", []):
            faltam = set(r.get("equipamentos") or []) - tem
            if faltam:
                graves.append(f"'{r.get('prato')}' usa {', '.join(UTENSILIOS[f] for f in faltam)}, que a pessoa não tem")

    # variedade: mesmo prato no máximo 1 vez por semana (almoço e jantar)
    vistos: dict[str, str] = {}
    for r in plano.get("refeicoes", []):
        if r.get("tipo") in PRINCIPAIS:
            k = restricoes.normalizar(r.get("prato", ""))
            if k in vistos:
                graves.append(f"'{r.get('prato')}' aparece mais de uma vez na semana")
            vistos[k] = r.get("prato", "")
    rejeitar = {restricoes.normalizar(p) for p in rejeitados(perfil)}
    for k, prato in vistos.items():
        if k in rejeitar:
            graves.append(f"'{prato}' foi rejeitado pela pessoa antes")
    preferidos = {restricoes.normalizar(p) for p in favoritos(perfil)}
    repetiu = [p for p in (semana_passada or []) if restricoes.normalizar(p) in vistos
               and restricoes.normalizar(p) not in preferidos]
    if len(repetiu) >= REPETIR_SEMANA_PASSADA_MAX:  # 1 coincidência ("arroz, feijão e frango") é aviso
        graves.append(f"repete {len(repetiu)} pratos da semana passada (troque por outros): " + ", ".join(repetiu))
    elif repetiu:
        avisos.append("repete pratos da semana passada: " + ", ".join(repetiu))

    if orcamento and calc["total"] > orcamento + 0.009:
        graves.append(f"passou R$ {calc['total'] - orcamento:.2f} do orçamento: o total das embalagens deu "
                      f"R$ {calc['total']:.2f}, acima do orçamento de R$ {orcamento:.2f}"
                      + _dicas_orcamento(plano, calc))
    return graves, avisos


def _dicas_orcamento(plano: dict, calc: dict) -> str:
    """Diz a quem refaz o plano ONDE cortar: os itens que mais pesam e as embalagens grandes demais
    para o uso (no teste real de 24/11: açúcar 5 kg para usar 270 g, café 500 g para usar 175 g)."""
    tamanhos = {cesta.chave(p["item"]): float(p.get("tamanho") or 0) for p in plano.get("produtos", [])}
    caros = sorted((l for l in calc["linhas"] if l["custo"] > 0), key=lambda l: -l["custo"])[:5]
    grandes = []
    for l in calc["linhas"]:
        comprado = l["pacotes"] * tamanhos.get(cesta.chave(l["item"]), 0)
        usa = l["precisa"] - l["da_despensa"]
        if comprado > 0 and l["custo"] >= 5 and usa / comprado < 0.4:
            grandes.append(f"{l['item']} (usa {usa:g} {l['unidade']}, compra {cesta.texto_embalagem(l)} "
                           f"por R$ {l['custo']:.2f})")
    dicas = ""
    if caros:
        dicas += ". Itens que mais pesam: " + "; ".join(f"{l['item']} R$ {l['custo']:.2f}" for l in caros)
    if grandes:
        dicas += ". Embalagens grandes demais para o uso (troque por uma menor): " + "; ".join(grandes)
    return dicas


# --- geração do plano -------------------------------------------------------------
def _linhas_perfil(perfil: dict) -> list[str]:
    porc = cesta.porcoes(perfil.get("adultos"), perfil.get("criancas"))
    restr = [restricoes.NOMES.get(r, r) for r in perfil.get("restricoes") or []]
    if perfil.get("restricoes_outras"):
        restr.append(perfil["restricoes_outras"])
    mercados = [MERCADOS.get(m, m) for m in perfil.get("mercados") or []]
    return [
        f"Família: {perfil.get('adultos') or 0} adulto(s) e {perfil.get('criancas') or 0} criança(s) = "
        f"{porc:g} porções por refeição (criança = meia porção).",
        f"Vibe: {VIBES.get(perfil.get('vibe'), 'livre')}.",
        f"Restrições (PROIBIDO usar): {', '.join(restr) or 'nenhuma'}.",
        f"Cozinha disponível (use SÓ isto): {', '.join(UTENSILIOS[u] for u in perfil.get('utensilios') or []) or 'fogão'}.",
        f"Mercados: {', '.join(mercados) or 'qualquer um'}. Cidade: {perfil.get('cidade') or 'Goiânia'}.",
    ]


def _briefing_plano(usuario: str, perfil: dict, despensa: dict, promos: list[dict], pedido: str) -> str:
    slots = _slots(perfil)
    linhas = _linhas_perfil(perfil)
    linhas.append(f"Planeje EXATAMENTE estas {len(slots)} refeições: "
                  + "; ".join(f"{NOME_DIA[d]} ({d}) {NOME_REFEICAO[t]} ({t})" for d, t in slots) + ".")
    orcamento = orcamento_semanal(perfil)
    linhas.append(f"Orçamento da semana: R$ {orcamento:.2f} (o total das embalagens precisa caber; "
                  f"em média R$ {orcamento / max(1, len(slots)):.2f} por refeição para a família toda).")
    if despensa:
        def _qtd(v: dict) -> str:
            if v.get("unidade") == "?":
                return "quantidade não informada"
            return f"{v['quantidade']} {v['unidade']}"
        linhas.append("Despensa (já tem em casa; use primeiro): "
                      + "; ".join(f"{v.get('item', k)} ({_qtd(v)})" for k, v in despensa.items()))
    if promos:
        linhas.append("Promoções válidas (preço exato; use o id em promocao_id quando usar):")
        linhas += [f"- id {p['id']} · {p['mercado']} · {p['produto']}"
                   f"{' ' + p['tamanho'] if p.get('tamanho') else ''} · R$ {p['preco']:.2f} · até {p['validade']}"
                   for p in promos[:40]]
    if favoritos(perfil):
        linhas.append("Pratos favoritos (pode repetir): " + "; ".join(favoritos(perfil)))
    if rejeitados(perfil):
        linhas.append("Pratos rejeitados (NÃO use): " + "; ".join(rejeitados(perfil)))
    passada = pratos_semana_passada(usuario)
    if passada:
        linhas.append("Pratos da semana passada (evite repetir, salvo favoritos): " + "; ".join(passada))
    if perfil.get("preferencias"):
        linhas.append(f"Observações da pessoa: {perfil['preferencias']}")
    if pedido:
        linhas.append(f"Pedido especial agora: {pedido}")
    return "\n".join(linhas)


PALAVRAS_OTIMIZAR = ("promo", "otimiz", "mais barato", "economizar", "mercados")


def caso_complexo(perfil: dict, promos: list[dict], pedido: str = "") -> bool:
    """Vai direto para o nível mais forte: 3 ou mais restrições ao mesmo tempo, ou
    pedido de otimizar a compra com promoções de vários mercados."""
    restr = len(perfil.get("restricoes") or []) + (1 if perfil.get("restricoes_outras") else 0)
    if restr >= 3:
        return True
    varios_mercados = len({restricoes.normalizar(p["mercado"]) for p in promos}) >= 2
    pede_otimizar = any(p in restricoes.normalizar(pedido) for p in PALAVRAS_OTIMIZAR)
    return varios_mercados and pede_otimizar


def _promos_do_perfil(perfil: dict) -> list[dict]:
    promos = banco.promocoes_validas(cidade=perfil.get("cidade") or "Goiânia")
    mercados = [m for m in (perfil.get("mercados") or []) if m != "qualquer"]
    if mercados:
        nomes = [restricoes.normalizar(MERCADOS.get(m, m)).split()[0] for m in mercados]
        promos = [p for p in promos if any(n in restricoes.normalizar(p["mercado"]) for n in nomes)]
    return promos


Progresso = Callable[[int], Awaitable[None]]


async def _nada(_etapa: int) -> None:
    return None


async def gerar_plano(usuario: str, pedido: str = "", progresso: Progresso = _nada) -> dict:
    """Monta o plano da semana. `progresso(i)` avisa quando começa a etapa ETAPAS[i]."""
    perfil = banco.usuario(usuario)
    orcamento = orcamento_semanal(perfil)

    await progresso(0)  # Vendo as promoções da semana
    promos = _promos_do_perfil(perfil)
    despensa = despensa_base(usuario, perfil)
    passada = pratos_semana_passada(usuario)

    mensagens = [{"papel": "usuario", "texto": _briefing_plano(usuario, perfil, despensa, promos, pedido)}]

    async def conferir_resposta(resposta) -> list[str]:
        """Guarda em resposta.conferencia o (plano, calc, graves, avisos) desta tentativa."""
        await progresso(2)  # Calculando a cesta (em código)
        try:
            plano = expandir(ler_json(resposta.texto))
            calc = cesta.calcular(plano, despensa)
        except (json.JSONDecodeError, TypeError, KeyError, ValueError) as erro:
            resposta.conferencia = (None, None, [f"JSON inválido ({erro})"], [])
            return [f"JSON inválido ({erro})"]
        await progresso(3)  # Conferindo o orçamento (e alergias, repetição, utensílios)
        graves, avisos = conferir(plano, perfil, calc, orcamento, passada)
        resposta.conferencia = (plano, calc, graves, avisos)
        return graves

    async def ao_tentar(_tentativa: int) -> None:
        await progresso(1)  # Escolhendo as receitas (na 2ª vez, a tela mostra "Ajustando")

    resposta = await roteador.gerar("cardapio", sistema=prompts.PLANO, mensagens=mensagens,
                                    esquema_json=ESQUEMA_PLANO, tempo=180, conferir=conferir_resposta,
                                    complexo=caso_complexo(perfil, promos, pedido), ao_tentar=ao_tentar)
    plano, calc, graves, avisos = resposta.conferencia or (None, None, ["sem conferência"], [])
    if plano is None or (graves and not all("acima do orçamento" in g for g in graves)):
        raise PlanoInvalido("; ".join(graves))
    if graves:
        log.info("Plano entregue acima do orçamento (melhor resultado possível): %s", "; ".join(graves))
    if avisos:
        log.info("Plano aceito com avisos: %s", "; ".join(avisos))

    await progresso(4)  # Finalizando
    conteudo = {
        **plano,
        "cesta": calc,
        "orcamento": orcamento,
        "porcoes": cesta.porcoes(perfil.get("adultos"), perfil.get("criancas")),
        "despensa_inicial": despensa,
        "receitas": {},
        "promocoes": {str(p["id"]): p for p in promos},
        "modelo": resposta.modelo,
        "nivel": resposta.nivel,
        "semana": banco.semana_atual(),
    }
    conteudo["id"] = banco.salvar_plano(usuario, conteudo)
    banco.atualizar_perfil(usuario, despensa=despensa)
    return conteudo


# --- plano acima do orçamento (Pedido I, lacuna 3) ---------------------------------------
# Quando nenhum modelo fecha no orçamento, o melhor plano é entregue com o aviso de quanto
# passou e três saídas: tirar os lanches, aumentar o orçamento ou refazer com pratos mais
# simples. As duas primeiras são só conta (sem IA, sem custo); a terceira monta de novo.
def _salvar(plano: dict) -> dict:
    banco.atualizar_plano(plano["id"], {k: v for k, v in plano.items() if k not in ("id", "criado_em")})
    return plano


def excesso(plano: dict) -> float:
    """Quanto o plano passou do orçamento (0 se coube)."""
    return round(max(0.0, plano["cesta"]["total"] - (plano.get("orcamento") or 0)), 2)


def tem_lanches(plano: dict) -> bool:
    return any(r["tipo"] == "lanche" for r in plano.get("refeicoes", []))


def valor_para_caber(plano: dict) -> float:
    """O orçamento semanal (arredondado para cima, de 10 em 10) em que o plano atual cabe."""
    return float(math.ceil(plano["cesta"]["total"] / 10 - 1e-9) * 10)


def tirar_lanches(usuario: str) -> dict:
    """Tira os lanches do plano atual e do perfil (os próximos planos também vêm sem) e refaz a conta."""
    plano = banco.plano_atual(usuario)
    mantidas = [r for r in plano["refeicoes"] if r["tipo"] != "lanche"]
    plano["receitas"] = {k: v for k, v in (plano.get("receitas") or {}).items() if not k.endswith(":lanche")}
    plano["refeicoes"] = mantidas
    plano["cesta"] = cesta.calcular(plano, plano.get("despensa_inicial") or {})
    perfil = banco.usuario(usuario)
    banco.atualizar_perfil(usuario, refeicoes=[r for r in perfil.get("refeicoes") or [] if r != "lanche"])
    return _salvar(plano)


def aumentar_orcamento(usuario: str) -> dict:
    """Sobe o orçamento (perfil e plano atual) para o valor em que o plano cabe."""
    plano = banco.plano_atual(usuario)
    semanal = valor_para_caber(plano)
    perfil = banco.usuario(usuario)
    no_perfil = float(math.ceil(semanal * 4.3 / 10) * 10) if perfil.get("periodo") == "mes" else semanal
    banco.atualizar_perfil(usuario, orcamento=no_perfil)
    plano["orcamento"] = orcamento_semanal(banco.usuario(usuario))
    return _salvar(plano)


def pedido_mais_simples(plano: dict) -> str:
    """O pedido especial para refazer o plano mais barato (vai para o modelo junto com o perfil)."""
    return (f"Pratos mais simples e baratos: o plano anterior passou R$ {excesso(plano):.2f} do orçamento. "
            "Use proteínas baratas (ovo, frango, carne moída), mais feijão, legumes da época e "
            "embalagens menores; repita o café da manhã nos dias da semana.")


# --- troca de um prato --------------------------------------------------------------
def indice(plano: dict, dia: str, tipo: str) -> int:
    for i, r in enumerate(plano.get("refeicoes", [])):
        if r["dia"] == dia and r["tipo"] == tipo:
            return i
    raise KeyError(f"{tipo} de {dia} não está no plano")


async def trocar_prato(usuario: str, dia: str, tipo: str, pedido: str = "") -> dict:
    """Troca só um prato e recalcula a cesta, sempre dentro do orçamento."""
    perfil = banco.usuario(usuario)
    atual = banco.plano_atual(usuario)
    i = indice(atual, dia, tipo)
    antigo = atual["refeicoes"][i]
    orcamento = atual.get("orcamento") or orcamento_semanal(perfil)
    # Folga exata: a lista recalculada SEM o prato antigo (embalagens inteiras), não uma
    # conta proporcional, que prometia mais dinheiro do que existia (teste real de 24/11).
    sem_prato = copy.deepcopy(atual)
    del sem_prato["refeicoes"][i]
    calc_sem = cesta.calcular(sem_prato, atual.get("despensa_inicial") or {})
    folga = round(orcamento - calc_sem["total"], 2)
    if folga < 0:  # nem um prato de graça caberia: não gasta com a IA
        raise SemFolga(f"sem esse prato a lista já passa R$ {-folga:.2f} do orçamento", folga)
    tamanhos = {cesta.chave(p["item"]): float(p["tamanho"]) for p in atual.get("produtos", [])}
    sobras = []
    for linha in calc_sem["linhas"]:
        sobra = linha["pacotes"] * tamanhos.get(cesta.chave(linha["item"]), 0) - (linha["precisa"] - linha["da_despensa"])
        if sobra > 0:
            sobras.append(f"{linha['item']} {sobra:g} {linha['unidade']}")
    outros =[f"{NOME_DIA[r['dia']]} {NOME_REFEICAO[r['tipo']]}: {r['prato']}"
              for j, r in enumerate(atual["refeicoes"]) if j != i]
    produtos = [f"{p['item']} ({p['embalagem']}, {p['tamanho']:g} {p['unidade']}, R$ {p['preco']:.2f})"
                for p in atual.get("produtos", [])]
    nao_achou = (atual.get("mercado") or {}).get("nao_encontrei") or []
    sobra_antiga = (antigo.get("sobra_planejada") or "").strip()
    manter_sobra = ([f"IMPORTANTE: o prato antigo deixava esta sobra planejada, que outras refeições usam: "
                     f"'{sobra_antiga}'. O prato novo precisa deixar a MESMA sobra (mesmo ingrediente extra) "
                     f"e dizer isso em \"sobra\"."] if sobra_util(sobra_antiga) else [])
    briefing = "\n".join(_linhas_perfil(perfil) + [
        f"Troque SÓ esta refeição: {NOME_REFEICAO[tipo]} de {NOME_DIA[dia]} ({dia}/{tipo}), hoje '{antigo['prato']}'.",
        f"Pedido da pessoa: {pedido or 'quero outro prato'}.",
    ] + manter_sobra + [
        "Não repita nenhum destes pratos da semana: " + "; ".join(outros),
        "Produtos já na lista (reaproveite os itens e use o MESMO nome em 'item'): " + "; ".join(produtos),
        f"Orçamento da semana R$ {orcamento:.2f}. Sem o prato antigo, a lista fica em R$ {calc_sem['total']:.2f}: "
        f"o prato novo pode acrescentar NO MÁXIMO R$ {folga:.2f} em embalagens novas (conta o preço da "
        f"embalagem inteira, não só o que o prato usa). Se não couber, monte o prato só com o que já está na lista.",
    ] + ([f"Sobras das embalagens já compradas (usar não custa nada): {'; '.join(sobras)}"] if sobras else [])
      + ([f"Pratos rejeitados (NÃO use): {'; '.join(rejeitados(perfil))}"] if rejeitados(perfil) else [])
      + ([f"A pessoa NÃO encontrou no mercado (não use): {'; '.join(nao_achou)}"] if nao_achou else []))
    mensagens = [{"papel": "usuario", "texto": briefing}]

    def conferir_troca(resposta) -> list[str]:
        try:
            dados = ler_json(resposta.texto)
            plano_novo = copy.deepcopy(atual)
            existentes = {cesta.chave(p["item"]) for p in plano_novo["produtos"]}
            plano_novo["produtos"] += [produto_de_compra(c) for c in dados.get("compras_novas", [])
                                       if cesta.chave(c["item"]) not in existentes]
            unidades = {}
            for p in plano_novo["produtos"]:
                unidades.setdefault(cesta.chave(p["item"]), p["unidade"])
            # a troca é sempre deste horário
            novo = refeicoes_de({**dados["refeicao"], "dias": [dia], "tipo": tipo}, unidades)[0]
            plano_novo["refeicoes"][i] = novo
            calc_novo = cesta.calcular(plano_novo, atual.get("despensa_inicial") or {})
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as erro:
            return [f"JSON inválido ({erro})"]
        graves, _ = conferir(plano_novo, perfil, calc_novo, orcamento)
        if restricoes.normalizar(novo["prato"]) == restricoes.normalizar(antigo["prato"]):
            graves.append("o prato novo é igual ao antigo")
        if sobra_util(sobra_antiga) and not sobra_util(novo.get("sobra_planejada")):
            graves.append(f"o prato novo não deixa a sobra que outras refeições usam: '{sobra_antiga}'")
        faltou = {cesta.chave(x) for x in nao_achou}
        usa_o_que_faltou = [i["item"] for i in novo["ingredientes"] if cesta.chave(i["item"]) in faltou]
        if usa_o_que_faltou:
            graves.append(f"o prato novo usa o que a pessoa não encontrou no mercado: {', '.join(usa_o_que_faltou)}")
        resposta.conferencia = (plano_novo, calc_novo, graves)
        return graves

    resposta = await roteador.gerar("troca", sistema=prompts.TROCA, mensagens=mensagens,
                                    esquema_json=ESQUEMA_TROCA, tempo=120, conferir=conferir_troca)
    novo_plano, calc, graves = resposta.conferencia or (None, None, resposta.problemas or ["JSON inválido"])
    if graves:  # na troca, nada de passar do orçamento: o plano fica como estava
        if roteador.categoria(graves) == "orçamento":
            raise SemFolga("; ".join(graves), folga)
        raise PlanoInvalido("; ".join(graves))

    novo_plano["cesta"] = calc
    novo_plano.setdefault("receitas", {}).pop(f"{dia}:{tipo}", None)
    banco.atualizar_plano(atual["id"], {k: v for k, v in novo_plano.items() if k not in ("id", "criado_em")})
    return banco.plano_atual(usuario)


# --- receita ------------------------------------------------------------------------
async def receita(usuario: str, dia: str, tipo: str) -> dict:
    """Ingredientes na quantidade da família, tempo e passo a passo (gerada uma vez e guardada no plano)."""
    plano = banco.plano_atual(usuario)
    chave_receita = f"{dia}:{tipo}"
    perfil = banco.usuario(usuario)
    porc = cesta.porcoes(perfil.get("adultos"), perfil.get("criancas"))
    guardada = (plano.get("receitas") or {}).get(chave_receita)
    # Guardada vale enquanto a família for do mesmo tamanho (C10: ao escalar porções, ajustar
    # também o modo de preparo). Receita antiga, sem 'porcoes', continua valendo.
    if guardada and float(guardada.get("porcoes", porc)) == porc:
        return guardada
    ref = plano["refeicoes"][indice(plano, dia, tipo)]
    porc_plano = float(plano.get("porcoes") or porc)
    fator = porc / porc_plano if porc_plano else 1.0

    def qtd(i: dict) -> str:
        valor = float(i["quantidade"]) * fator
        valor = round(valor * 2) / 2 if i["unidade"] == "un" else round(valor)
        return f"{valor:g} {i['unidade']}"

    ajuste = ([f"A família mudou desde o plano ({porc_plano:g} -> {porc:g} porções): as quantidades abaixo já "
               f"estão ajustadas; ajuste também os passos (panela, tempo, quantidade de água)."]
              if fator != 1 else [])
    briefing = "\n".join(_linhas_perfil(perfil) + [
        f"Prato: {ref['prato']} ({NOME_REFEICAO[tipo]}), para {porc:g} porções.",
        "Ingredientes (quantidades exatas para a família): " + "; ".join(f"{i['item']} {qtd(i)}"
                                                                       for i in ref["ingredientes"]),
        f"Equipamentos: {', '.join(UTENSILIOS[e] for e in ref.get('equipamentos') or []) or 'fogão'}.",
        f"Tempo previsto: {ref.get('tempo_min')} min.",
    ] + ajuste + ([f"Sobra planejada: {ref['sobra_planejada']}"] if ref.get("sobra_planejada") else []))
    mensagens = [{"papel": "usuario", "texto": briefing}]

    def conferir_receita(resposta) -> list[str]:
        try:
            dados = ler_json(resposta.texto)
            textos = list(dados["ingredientes"]) + list(dados["passos"])
        except (json.JSONDecodeError, KeyError, TypeError) as erro:
            return [f"JSON inválido ({erro})"]
        return restricoes.violacoes_em(textos, perfil.get("restricoes") or [], perfil.get("restricoes_outras"))

    resposta = await roteador.gerar("receita", sistema=prompts.RECEITA, mensagens=mensagens,
                                    esquema_json=ESQUEMA_RECEITA, tempo=60, conferir=conferir_receita)
    if resposta.problemas:
        raise PlanoInvalido("; ".join(resposta.problemas))
    rec = {**ler_json(resposta.texto), "porcoes": porc, "porcoes_plano": porc_plano}

    plano.setdefault("receitas", {})[chave_receita] = rec
    banco.atualizar_plano(plano["id"], {k: v for k, v in plano.items() if k not in ("id", "criado_em")})
    return rec


# --- notas dos pratos ------------------------------------------------------------------
def avaliar(usuario: str, prato: str, nota: int) -> None:
    """Guarda a nota (1 a 5). 4-5 = favorito; 1-2 = rejeitado nos próximos cardápios."""
    perfil = banco.usuario(usuario)
    notas = dict(perfil.get("preferencias_pratos") or {})
    notas[restricoes.normalizar(prato)] = {"prato": prato, "nota": max(1, min(5, int(nota)))}
    banco.atualizar_perfil(usuario, preferencias_pratos=notas)


__all__ = ["gerar_plano", "trocar_prato", "receita", "avaliar", "conferir", "PlanoInvalido", "ErroIA"]
