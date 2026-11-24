"""Testes automáticos do Rende. Não chamam nenhuma IA de verdade (são simuladas)
nem o Telegram, e usam um banco de dados só na memória.

Para rodar:   .venv\\Scripts\\python testes\\testar.py
"""
import asyncio
import io
import copy
import json
import re
import logging
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456789:AAbbCCddEEffGGhhIIjjKKllMMnnOOppQQr")
os.environ.setdefault("GEMINI_API_KEY", "chave-gemini-de-teste")
os.environ["GEMINI_MODEL"], os.environ["GEMINI_MODEL_RESERVA"] = "gemini-3.5-flash-lite", "gemini-3.6-flash"
os.environ.update(CLAUDE_MODELO_BARATO="claude-haiku-5-5", CLAUDE_MODELO_PADRAO="claude-sonnet-5-5",
                  CLAUDE_MODELO_FORTE="claude-opus-5-5", LIMITE_HAIKU_DIA="500", LIMITE_SONNET_DIA="100",
                  LIMITE_OPUS_DIA="20")
os.environ.pop("ANTHROPIC_API_KEY", None)  # os testes nunca chamam a API de verdade
os.environ["LIMITE_MSG_DIA"], os.environ["ADMIN_IDS"] = "30", "999"
logging.basicConfig(level=logging.CRITICAL)

import banco  # noqa: E402
import cadastro  # noqa: E402
import cardapio  # noqa: E402
import cesta  # noqa: E402
import ferramentas  # noqa: E402
import ia  # noqa: E402
import ia_claude  # noqa: E402
import pdf  # noqa: E402
import restricoes  # noqa: E402
import roteador  # noqa: E402
import telas  # noqa: E402
from ia_comum import Chamada, ErroIA, RespostaIA  # noqa: E402

falhas: list[str] = []
total = 0


def ok(condicao, nome: str) -> None:
    global total
    total += 1
    if not condicao:
        falhas.append(nome)
    print(("OK    " if condicao else "FALHA ") + nome)


def secao(titulo: str) -> None:
    print(f"\n== {titulo} ==")


def novo_banco() -> None:
    banco.conectar(":memory:")


class _Coletor(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.textos: list[str] = []

    def emit(self, registro: logging.LogRecord) -> None:
        self.textos.append(registro.getMessage())


def capturar_log(nome: str, funcao) -> list[str]:
    """Roda funcao() e devolve as mensagens que o logger `nome` (e os filhos dele) registraram."""
    logger = logging.getLogger(nome)
    coletor, nivel_antigo, propaga_antes = _Coletor(), logger.level, logger.propagate
    logger.addHandler(coletor)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # não imprime na tela durante os testes
    try:
        funcao()
    finally:
        logger.removeHandler(coletor)
        logger.setLevel(nivel_antigo)
        logger.propagate = propaga_antes
    return coletor.textos


# --- IAs simuladas ---------------------------------------------------------------------
class IAFalsa:
    """Adaptador simulado: devolve respostas de uma fila ou levanta erros."""

    def __init__(self, provedor: str, disponivel: bool = True):
        self.provedor, self._disponivel = provedor, disponivel
        self.fila: list = []
        self.chamadas: list[dict] = []

    def disponivel(self) -> bool:
        return self._disponivel

    async def gerar(self, *, modelo, sistema, mensagens, sistema_extra="", ferramentas=None, esquema_json=None,
                    esforco=None, tempo=None):
        self.chamadas.append({"modelo": modelo, "mensagens": mensagens, "ferramentas": ferramentas,
                              "esquema": esquema_json, "esforco": esforco, "sistema_extra": sistema_extra})
        item = self.fila.pop(0) if self.fila else "ok"
        if isinstance(item, Exception):
            raise item
        if isinstance(item, RespostaIA):
            item.provedor, item.modelo = self.provedor, modelo
            return item
        texto = json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)
        return RespostaIA(texto=texto, provedor=self.provedor, modelo=modelo, tokens_entrada=1000, tokens_saida=500)


def instalar_ias(claude_disponivel: bool = True) -> tuple[IAFalsa, IAFalsa]:
    gemini, claude = IAFalsa("gemini"), IAFalsa("claude", claude_disponivel)
    roteador.ADAPTADORES["gemini"], roteador.ADAPTADORES["claude"] = gemini, claude
    return gemini, claude


# --- dados de exemplo -----------------------------------------------------------------
PERFIL = dict(nome="Ana", adultos=2, criancas=1, refeicoes=["almoco", "jantar"], dias=["seg", "ter", "qua"],
              vibe="vo", restricoes=["lactose"], utensilios=["fogao", "pressao"], mercados=["qualquer"],
              periodo="semana", orcamento=200.0, cidade="Goiânia", cadastro_passo=None)


def refeicao(dia, tipo, prato, ingredientes, equipamentos=("fogao",), tempo=30):
    return {"dia": dia, "tipo": tipo, "prato": prato, "tempo_min": tempo, "equipamentos": list(equipamentos),
            "ingredientes": [{"item": i, "quantidade": q, "unidade": u} for i, q, u in ingredientes],
            "sobra_planejada": ""}


def produto(item, embalagem, tamanho, unidade, preco, secao, perecivel, promocao_id=0):
    return {"item": item, "nome": item.capitalize(), "embalagem": embalagem, "tamanho": tamanho, "unidade": unidade,
            "preco": preco, "secao": secao, "perecivel": perecivel, "promocao_id": promocao_id}


def _prato_ia(r: dict) -> dict:
    return {"prato": r["prato"], "min": r["tempo_min"], "equip": list(r["equipamentos"]),
            "ingr": [{"item": i["item"], "qtd": i["quantidade"]} for i in r["ingredientes"]],
            "sobra": r.get("sobra_planejada") or ""}


def compra_ia(p: dict) -> dict:
    return {"item": p["item"], "emb": p["embalagem"], "tam": p["tamanho"], "un": p["unidade"], "preco": p["preco"],
            "secao": p["secao"], "promo": p.get("promocao_id", 0)}


def para_ia(plano: dict) -> dict:
    """Plano no formato interno -> resposta compacta, como a IA escreve (um dia por entrada)."""
    return {"refeicoes": [{"dias": [r["dia"]], "tipo": r["tipo"], **_prato_ia(r)} for r in plano["refeicoes"]],
            "compras": [compra_ia(p) for p in plano["produtos"]]}


def troca_ia(ref: dict, compras_novas=()) -> dict:
    """Resposta compacta de uma troca de prato."""
    return {"refeicao": _prato_ia(ref), "compras_novas": [compra_ia(p) for p in compras_novas]}


def plano_valido() -> dict:
    return {
        "refeicoes": [
            refeicao("seg", "almoco", "Arroz, feijão e frango acebolado",
                     [("arroz", 250, "g"), ("feijão", 150, "g"), ("frango", 400, "g"), ("cebola", 1, "un")],
                     ("fogao", "pressao")),
            refeicao("seg", "jantar", "Sopa de legumes com frango",
                     [("frango", 300, "g"), ("batata", 400, "g"), ("cenoura", 200, "g")]),
            refeicao("ter", "almoco", "Arroz, feijão e carne moída",
                     [("arroz", 250, "g"), ("feijão", 150, "g"), ("carne moída", 400, "g")]),
            refeicao("ter", "jantar", "Feijão tropeiro com ovo",
                     [("farinha de mandioca", 200, "g"), ("ovo", 4, "un"), ("cebola", 1, "un")]),
            refeicao("qua", "almoco", "Macarrão ao molho com carne moída",
                     [("macarrão", 500, "g"), ("molho de tomate", 340, "g"), ("carne moída", 300, "g")]),
            refeicao("qua", "jantar", "Cuscuz com ovo mexido", [("flocão de milho", 300, "g"), ("ovo", 5, "un")]),
        ],
        "produtos": [
            produto("arroz", "pacote 5 kg", 5000, "g", 24.90, "Mercearia", False),
            produto("feijão", "pacote 1 kg", 1000, "g", 8.90, "Mercearia", False),
            produto("frango", "bandeja 1 kg", 1000, "g", 17.90, "Açougue e aves", True),
            produto("cebola", "unidade", 1, "un", 0.80, "Hortifrúti", True),
            produto("batata", "kg", 1000, "g", 6.00, "Hortifrúti", True),
            produto("cenoura", "kg", 1000, "g", 5.00, "Hortifrúti", True),
            produto("carne moída", "bandeja 1 kg", 1000, "g", 32.00, "Açougue e aves", True),
            produto("farinha de mandioca", "pacote 500 g", 500, "g", 6.50, "Mercearia", False),
            produto("ovo", "bandeja com 30 ovos", 30, "un", 19.90, "Ovos e laticínios", True),
            produto("macarrão", "pacote 500 g", 500, "g", 4.50, "Mercearia", False),
            produto("molho de tomate", "sachê 340 g", 340, "g", 3.20, "Mercearia", False),
            produto("flocão de milho", "pacote 500 g", 500, "g", 3.50, "Mercearia", False),
        ],
        "reaproveitamento": ["O feijão de segunda vira tropeiro na terça"],
    }


def criar_usuario(uid="u1", **extras) -> dict:
    banco.obter_ou_criar_usuario(uid)
    return banco.atualizar_perfil(uid, **{**PERFIL, **extras})


# =======================================================================================
secao("Banco de dados")
novo_banco()
p = criar_usuario()
ok(p["refeicoes"] == ["almoco", "jantar"] and p["restricoes"] == ["lactose"] and p["despensa"] == {},
   "perfil guarda e devolve listas/dicionários (JSON)")
for i in range(35):
    banco.adicionar_mensagem("u1", "usuario", f"m{i}")
h = banco.historico("u1")
ok(len(h) == 30 and h[0]["texto"] == "m5" and h[-1]["texto"] == "m34", "histórico guarda só as últimas 30")
for i in range(4):
    banco.salvar_plano("u1", {"refeicoes": [], "n": i})
ok([x["n"] for x in banco.planos("u1", 5)] == [3, 2, 1], "guarda só os 3 últimos planos (o mais novo é o atual)")
banco.adicionar_promocao(mercado="Assaí", produto="arroz", preco=22.9, validade="2099-12-31", cidade="Goiânia", origem="admin")
banco.adicionar_promocao(mercado="Tático", produto="feijão", preco=6.9, validade="2000-01-01", cidade="Goiânia", origem="admin")
ok([x["produto"] for x in banco.promocoes_validas(cidade="goiânia")] == ["arroz"], "promoção vencida não aparece")
ok(banco.apagar_promocoes_vencidas() == 1, "promoções vencidas são apagadas")
banco.contar_mensagem("u1")
banco.apagar_usuario("u1")
ok(banco.usuario("u1") is None and banco.historico("u1") == [] and banco.planos("u1") == [] and banco.mensagens_hoje("u1") == 0,
   "/esquecer apaga perfil, conversa, planos e contagem (LGPD)")

# =======================================================================================
secao("Alergias e restrições (conferência em código)")
v = restricoes.violacoes
ok(v("Arroz com queijo coalho", ["lactose"]), "lactose: queijo é barrado")
ok(not v("Frango ao leite de coco", ["lactose"]), "lactose: leite de coco é permitido")
ok(not v("Creme de leite sem lactose", ["lactose"]), "lactose: 'sem lactose' é permitido")
ok(v("Pão de queijo", ["lactose"]) and not v("Pão de queijo", ["gluten"]), "pão de queijo: tem lactose, não tem glúten")
ok(v("Macarrão alho e óleo", ["gluten"]) and not v("Macarrão de arroz", ["gluten"]), "glúten: macarrão barrado, de arroz liberado")
ok(not v("Cuscuz com ovo", ["gluten"]) and v("Cuscuz marroquino", ["gluten"]), "cuscuz de milho liberado; marroquino barrado")
ok(v("Strogonoff de frango", ["vegetariano"]) and v("Moqueca de tilápia", ["vegetariano"]), "vegetariano: frango e peixe barrados")
ok(v("Bolo de AMENDOIM", ["amendoim"]) and v("Camarão na moranga", ["frutos_do_mar"]), "amendoim e frutos do mar (maiúsculas e acentos)")
ok(v("Arroz com coentro", [], "coentro, pimenta") and not v("Arroz branco", [], "coentro, pimenta"), "restrições escritas pela pessoa")
ok(not v("Ovo cozido", ["lactose", "gluten"]), "sem falso alarme quando não há restrição daquele tipo")
ok(not v("Couve manteiga refogada", ["lactose"]) and not v("Couve-manteiga", ["lactose"])
   and v("Manteiga de garrafa", ["lactose"]), "couve-manteiga não é laticínio (falso alarme visto no teste real)")
ok(cesta.porcoes_txt(2.5) == "2,5 porções" and cesta.porcoes_txt(1) == "1 porção", "porções em português (vírgula e singular)")

# =======================================================================================
secao("Cesta por embalagem e despensa")
calc = cesta.calcular(plano_valido(), {})
linha = {l["item"]: l for l in calc["linhas"]}
ok(linha["arroz"]["pacotes"] == 1 and linha["arroz"]["custo"] == 24.90, "500 g de arroz -> compra 1 pacote de 5 kg (preço da embalagem)")
ok(linha["ovo"]["pacotes"] == 1 and linha["frango"]["pacotes"] == 1, "9 ovos -> 1 bandeja; 700 g de frango -> 1 bandeja de 1 kg")
ok(linha["macarrão"]["pacotes"] == 1 and linha["cebola"]["pacotes"] == 2, "embalagens inteiras (2 cebolas, 1 pacote de macarrão)")
esperado = round(sum(l["custo"] for l in calc["linhas"]), 2)
ok(calc["total"] == esperado == 133.90, f"total = soma das embalagens (R$ {calc['total']:.2f})")
ok(calc["despensa_final"]["arroz"]["quantidade"] == 4500 and "frango" not in calc["despensa_final"],
   "sobra de arroz (não perecível) vai para a despensa; frango (perecível) não")
calc2 = cesta.calcular(plano_valido(), calc["despensa_final"])
linha2 = {l["item"]: l for l in calc2["linhas"]}
ok(linha2["arroz"]["pacotes"] == 0 and linha2["arroz"]["da_despensa"] == 500 and calc2["total"] < calc["total"],
   "semana seguinte usa a despensa e não compra arroz de novo")
ok(calc2["despensa_final"]["arroz"]["quantidade"] == 4000, "despensa desconta o que foi usado")
quebrado = plano_valido()
quebrado["refeicoes"][0]["ingredientes"].append({"item": "pimentão", "quantidade": 1, "unidade": "un"})
quebrado["refeicoes"][1]["ingredientes"][1]["unidade"] = "un"
c3 = cesta.calcular(quebrado, {})
ok(c3["sem_produto"] == ["pimentão"] and c3["unidade_errada"], "detecta ingrediente sem embalagem e unidade trocada")
ok(len(calc["custo_refeicoes"]) == 6 and calc["custo_refeicoes"][0] > 0, "custo por refeição calculado")

# =======================================================================================
secao("Conferência do plano (estrutura, alergia, variedade, cozinha, orçamento)")
novo_banco()
perfil = criar_usuario()
graves, avisos = cardapio.conferir(plano_valido(), perfil, calc, 200)
ok(graves == [] and avisos == [], "plano válido passa sem problemas")
ruim = plano_valido()
ruim["refeicoes"][2]["prato"] = "Lasanha de queijo"
ruim["refeicoes"][2]["ingredientes"].append({"item": "queijo muçarela", "quantidade": 200, "unidade": "g"})
ruim["produtos"].append(produto("queijo muçarela", "pacote 500 g", 500, "g", 22, "Ovos e laticínios", True))
g, _ = cardapio.conferir(ruim, perfil, cesta.calcular(ruim, {}), 200)
ok(any("Lactose" in x for x in g), "ingrediente com lactose é barrado mesmo se a IA errar")
ruim = plano_valido()
ruim["refeicoes"][4]["prato"] = ruim["refeicoes"][0]["prato"]
g, _ = cardapio.conferir(ruim, perfil, cesta.calcular(ruim, {}), 200)
ok(any("mais de uma vez" in x for x in g), "mesmo prato 2 vezes na semana é barrado")
ruim = plano_valido()
ruim["refeicoes"].pop()
g, _ = cardapio.conferir(ruim, perfil, cesta.calcular(ruim, {}), 200)
ok(any("faltam refeições" in x for x in g), "refeição faltando é barrada")
ruim = plano_valido()
ruim["refeicoes"][0]["equipamentos"] = ["forno"]
g, _ = cardapio.conferir(ruim, perfil, cesta.calcular(ruim, {}), 200)
ok(any("Forno" in x for x in g), "prato que usa forno é barrado para quem não tem forno")
g, _ = cardapio.conferir(plano_valido(), perfil, calc, 100)
ok(any("acima do orçamento" in x for x in g), "total acima do orçamento é barrado")
perfil_r = banco.atualizar_perfil("u1", preferencias_pratos={"cuscuz com ovo mexido": {"prato": "Cuscuz com ovo mexido", "nota": 1}})
g, _ = cardapio.conferir(plano_valido(), perfil_r, calc, 200)
ok(any("rejeitado" in x for x in g), "prato rejeitado (nota 1) não volta")
banco.atualizar_perfil("u1", preferencias_pratos={})
_, av = cardapio.conferir(plano_valido(), banco.usuario("u1"), calc, 200, ["Arroz, feijão e carne moída"])
ok(av and "semana passada" in av[0], "repetir prato da semana passada gera aviso")

# =======================================================================================
secao("Escada de modelos (IAs simuladas)")
HAIKU, SONNET, OPUS = "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"
X = [{"papel": "usuario", "texto": "x"}]


def gerar(tarefa, **kw):
    return asyncio.run(roteador.gerar(tarefa, sistema="s", mensagens=kw.pop("mensagens", X), **kw))


def modelos(ia_falsa):
    return [c["modelo"] for c in ia_falsa.chamadas]


novo_banco()
gemini, claude = instalar_ias()
r = gerar("conversa")
ok(r.nivel == "gemini" and gemini.chamadas[-1]["esforco"] is None, "conversa começa no Gemini")
r = gerar("receita")
ok(r.nivel == "gemini", "receita começa no Gemini")
r = gerar("cardapio")
ok(r.modelo == SONNET and claude.chamadas[-1]["esforco"] == "low",
   "gerar cardápio começa no Sonnet (effort low: o raciocínio é cobrado como saída)")
os.environ["ESFORCO_CARDAPIO"] = "medium"
gerar("cardapio")
os.environ["ESFORCO_CARDAPIO"] = "altissimo"
gerar("cardapio")
os.environ.pop("ESFORCO_CARDAPIO")
ok([c["esforco"] for c in claude.chamadas[-2:]] == ["medium", "low"],
   "ESFORCO_CARDAPIO no .env muda o effort do Sonnet (valor inválido volta para low)")
r = gerar("troca")
ok(r.modelo == HAIKU and claude.chamadas[-1]["esforco"] == "medium", "trocar prato começa no Haiku (effort medium)")
r = gerar("cardapio", complexo=True)
ok(r.modelo == OPUS and "complexo" in r.motivo, "caso complexo: cardápio vai direto para o Opus")
gemini.fila = [ErroIA("429", cota=True), ErroIA("503")]
r = gerar("conversa")
ok(r.modelo == HAIKU and claude.chamadas[-1]["esforco"] == "low", "Gemini sem cota e reserva fora do ar -> Haiku (effort low)")
gemini.fila = [ErroIA("503")]
r = gerar("conversa")
ok(r.nivel == "gemini-reserva", "Gemini principal fora do ar -> Gemini reserva antes do Haiku")
gemini.fila = [ErroIA("503"), ErroIA("503")]
claude.chamadas.clear()
audio = [{"papel": "usuario", "texto": "", "anexo": {"mime_type": "audio/ogg", "dados": b"OggS"}}]
try:
    gerar("midia", mensagens=audio)
    ok(False, "áudio nunca vai para o Claude")
except ErroIA:
    ok(claude.chamadas == [], "áudio nunca vai para o Claude, nem como substituto")

# reprovação sobe um nível, levando o motivo
novo_banco()
gemini, claude = instalar_ias()
claude.fila = ["reprovado", "aprovado"]


def conferir_simples(resp):
    return [] if resp.texto == "aprovado" else ["passou R$ 23,00 do orçamento"]


r = gerar("cardapio", conferir=conferir_simples)
ok(modelos(claude) == [SONNET, OPUS] and r.modelo == OPUS and r.motivo.startswith("escalonamento"),
   "cardápio reprovado no Sonnet -> refeito UMA vez no Opus")
ok("passou R$ 23,00 do orçamento" in claude.chamadas[1]["mensagens"][-1]["texto"]
   and claude.chamadas[1]["mensagens"][-2]["texto"] == "reprovado", "o Opus recebe a resposta reprovada e o motivo")
ok([c["esforco"] for c in claude.chamadas] == ["low", "medium"],
   "cardápio: Sonnet com effort low; o Opus refaz com effort medium")
ok(banco.resumo_escalonamentos(banco.hoje()) == [{"motivo": "orçamento", "vezes": 1}], "subida registrada com o motivo (orçamento)")
claude.chamadas.clear()
claude.fila = ["r1", "r2", "aprovado"]
r = gerar("troca", conferir=conferir_simples)
ok(modelos(claude) == [HAIKU, SONNET, OPUS] and r.modelo == OPUS, "trocar prato: Haiku -> Sonnet -> Opus")
claude.chamadas.clear()
claude.fila = ["r1", "r2"]
r = gerar("cardapio", conferir=conferir_simples)
ok(modelos(claude) == [SONNET, OPUS] and r.problemas, "sem nenhum aprovado, devolve o melhor resultado com os problemas")

# recusa e erro sobem um nível; se o Claude todo falhar, vai para o Gemini
claude.chamadas.clear()
claude.fila = [RespostaIA(recusou=True, tokens_entrada=10, tokens_saida=1)]
r = gerar("troca")
ok(modelos(claude) == [HAIKU, SONNET] and "recusou" in r.motivo, "Haiku recusou -> Sonnet")
claude.chamadas.clear()
claude.fila = [ErroIA("500"), ErroIA("timeout")]
r = gerar("cardapio")
ok(modelos(claude) == [SONNET, OPUS] and r.provedor == "gemini" and "último recurso" in r.motivo,
   "Sonnet e Opus com erro -> último recurso: Gemini (avisado no log)")

# limites diários por modelo
os.environ["LIMITE_OPUS_DIA"] = "0"
novo_banco()
gemini, claude = instalar_ias()
claude.fila = ["reprovado", "aprovado"]
r = gerar("cardapio", conferir=conferir_simples)
ok(modelos(claude) == [SONNET, SONNET] and r.texto == "aprovado" and "repetindo sonnet" in r.motivo,
   "Opus no limite: fica no Sonnet (mais uma vez, com a correção) e entrega o melhor resultado")
os.environ["LIMITE_OPUS_DIA"] = "20"
os.environ["LIMITE_HAIKU_DIA"] = "1"
claude.chamadas.clear()
gerar("troca")
gerar("troca")
ok(modelos(claude) == [HAIKU, SONNET], "Haiku no limite (1/dia): a troca seguinte começa no Sonnet")
os.environ["LIMITE_HAIKU_DIA"] = "500"
custos_hoje = {c["modelo"]: c for c in banco.resumo_custos(banco.hoje())}
ok(abs(custos_hoje[SONNET]["custo"] - custos_hoje[SONNET]["chamadas"] * (1000 * 2 + 500 * 10) / 1e6) < 1e-9,
   "custo do Sonnet registrado (tokens x preço de tabela)")
ok(abs(roteador.custo_usd(OPUS, 1000, 500, cache_leitura=10_000, cache_escrita=2000)
       - (1000 * 4 + 2000 * 4 * 1.25 + 10_000 * 0.20 + 500 * 20) / 1e6) < 1e-12,
   "custo considera cache lido (barato) e cache gravado (1,25x)")
instalar_ias(claude_disponivel=False)
r = gerar("cardapio")
ok(r.provedor == "gemini" and "último recurso" in r.motivo, "sem chave do Claude: cardápio cai no Gemini")

# caso complexo e chamada real ao SDK do Claude (cliente simulado)
p3 = dict(PERFIL, restricoes=["lactose", "gluten"], restricoes_outras="coentro")
ok(cardapio.caso_complexo(p3, [], "") and not cardapio.caso_complexo(PERFIL, [], ""), "3 restrições = caso complexo")
promos2 = [{"mercado": "Assaí"}, {"mercado": "Tático"}]
ok(cardapio.caso_complexo(PERFIL, promos2, "otimiza com as promoções") and not cardapio.caso_complexo(PERFIL, promos2, ""),
   "otimizar com promoções de vários mercados = caso complexo")


class ClienteClaudeFalso:
    """Imita o AsyncAnthropic: anota se a chamada foi por create ou por stream."""

    def __init__(self, stop_reason: str = "end_turn"):
        self.parametros = None
        self.usou = None
        self.stop_reason = stop_reason
        self.messages = self

    def with_options(self, **_):
        return self

    def _resposta(self):
        from types import SimpleNamespace as NS
        return NS(stop_reason=self.stop_reason, content=[NS(type="text", text="oi")],
                  usage=NS(input_tokens=50, output_tokens=5, cache_read_input_tokens=1800, cache_creation_input_tokens=0))

    async def create(self, **parametros):
        self.parametros, self.usou = parametros, "create"
        return self._resposta()

    def stream(self, **parametros):
        self.parametros, self.usou = parametros, "stream"
        cliente = self

        class _Fluxo:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

            async def get_final_message(self):
                return cliente._resposta()

        return _Fluxo()


os.environ["ANTHROPIC_API_KEY"] = "sk-ant-teste"
falso = ClienteClaudeFalso()
ia_claude._cliente = falso
resp = asyncio.run(ia_claude.gerar(modelo=HAIKU, sistema="FIXO", sistema_extra="VARIA", mensagens=X, esforco="low",
                                   ferramentas=[ferramentas.SALVAR_PERFIL]))
pr = falso.parametros
ok(pr["system"][0] == {"type": "text", "text": "FIXO", "cache_control": {"type": "ephemeral"}}
   and pr["system"][1] == {"type": "text", "text": "VARIA"}, "Claude: instruções fixas com cache_control; parte variável sem cache")
ok(not any(k in pr for k in ("thinking", "temperature", "top_p", "top_k")) and pr["tool_choice"] == {"type": "auto"}
   and pr["output_config"] == {"effort": "low"}, "Claude: sem thinking/temperature/top_p/top_k; tool_choice auto; effort explícito")
ok(resp.cache_leitura == 1800 and resp.tokens_entrada == 50, "Claude: lê usage.cache_read_input_tokens")
ok(falso.usou == "stream" and pr["max_tokens"] == 32000,
   "Claude: resposta por streaming com limite de 32 mil tokens (o cardápio não é mais cortado no meio)")
ia_claude._cliente = ClienteClaudeFalso(stop_reason="max_tokens")
avisos = capturar_log("rende.ia_claude", lambda: asyncio.run(ia_claude.gerar(modelo=SONNET, sistema="FIXO", mensagens=X)))
ok(any("cortada" in a for a in avisos), "Claude: resposta cortada no limite de tokens fica registrada no log")
ia_claude._cliente = None
os.environ.pop("ANTHROPIC_API_KEY")

# =======================================================================================
secao("Geração e troca do plano (IAs simuladas)")
novo_banco()
gemini, claude = instalar_ias()
criar_usuario()
com_lactose = plano_valido()
com_lactose["refeicoes"][3]["prato"] = "Omelete com queijo"
claude.fila = [para_ia(com_lactose), para_ia(plano_valido())]
etapas: list[int] = []


async def anotar(etapa):
    etapas.append(etapa)


plano = asyncio.run(cardapio.gerar_plano("u1", progresso=anotar))
ok(modelos(claude) == [SONNET, OPUS] and "Lactose" in claude.chamadas[1]["mensagens"][-1]["texto"],
   "plano do Sonnet com alergia (queijo x lactose) é refeito pelo Opus, que recebe o motivo")
ok(plano["nivel"] == "opus", "o plano guarda qual nível o fez")
ok(etapas == [0, 1, 2, 3, 1, 2, 3, 4], f"a 'animação' acompanha as etapas reais, inclusive o ajuste ({etapas})")
ok(plano["cesta"]["total"] == 133.90 and banco.plano_atual("u1")["id"] == plano["id"], "plano salvo com o total calculado em código")

claude.fila = [troca_ia(refeicao("ter", "jantar", "Omelete de forno", [("ovo", 6, "un")], ("forno",))),
               troca_ia(refeicao("ter", "jantar", "Sopa de feijão com macarrão",
                                 [("feijão", 200, "g"), ("macarrão", 100, "g")]))]
claude.chamadas.clear()
novo = asyncio.run(cardapio.trocar_prato("u1", "ter", "jantar", "algo de panela"))
i = cardapio.indice(novo, "ter", "jantar")
ok(novo["refeicoes"][i]["prato"] == "Sopa de feijão com macarrão" and modelos(claude) == [HAIKU, SONNET],
   "troca do Haiku reprovada (usa forno) é refeita pelo Sonnet")
ok(sum(1 for a, b in zip(plano["refeicoes"], novo["refeicoes"]) if a["prato"] != b["prato"]) == 1,
   "a troca muda só aquele prato")
ok(novo["cesta"]["total"] <= novo["orcamento"] and novo["cesta"]["total"] != plano["cesta"]["total"],
   f"total recalculado e dentro do orçamento (R$ {novo['cesta']['total']:.2f})")
claude.fila = [troca_ia(refeicao("ter", "jantar", "Cuscuz com ovo mexido", [("ovo", 2, "un")]))] * 3
try:
    asyncio.run(cardapio.trocar_prato("u1", "ter", "jantar"))
    ok(False, "troca que repete prato da semana é recusada")
except cardapio.PlanoInvalido:
    ok(banco.plano_atual("u1")["refeicoes"][i]["prato"] == "Sopa de feijão com macarrão",
       "troca que repete prato é recusada e o plano não muda sozinho")

gemini.fila = [{"ingredientes": ["2 xícaras de feijão (200 g)", "1 xícara de macarrão (100 g)"],
                "passos": ["Cozinhe o feijão.", "Junte o macarrão.", "Sirva."], "tempo_min": 30, "dica": "Use o caldo."}]
rec = asyncio.run(cardapio.receita("u1", "ter", "jantar"))
rec2 = asyncio.run(cardapio.receita("u1", "ter", "jantar"))
ok(len(rec["passos"]) == 3 and rec2 == rec and len(gemini.chamadas) == 1, "receita gerada pelo Gemini uma vez e guardada no plano")
cardapio.avaliar("u1", "Sopa de feijão com macarrão", 5)
ok(cardapio.favoritos(banco.usuario("u1")) == ["Sopa de feijão com macarrão"], "nota 5 vira favorito no perfil")

# =======================================================================================
secao("Cardápio compacto: menos tokens, sem modo de preparo (custo, 24/11)")
esquemas = json.dumps([cardapio.ESQUEMA_PLANO, cardapio.ESQUEMA_TROCA], ensure_ascii=False)
ok(not any(p in esquemas for p in ('"passos"', "preparo", "reaproveitamento", '"nome"', '"perecivel"', '"unidade"')),
   "o JSON do cardápio e da troca não pede modo de preparo, explicações nem campos que o código deduz")
ok("sem modo de preparo" in cardapio.prompts.PLANO and "sem modo de preparo" in cardapio.prompts.TROCA,
   "as instruções dizem que a receita só é escrita quando a pessoa abre o prato")
compacto = {"refeicoes": [
    {"dias": ["qua", "seg", "ter"], "tipo": "cafe", "prato": "Cuscuz com ovo", "min": 15, "equip": ["fogao"],
     "ingr": [{"item": "flocão", "qtd": 200}, {"item": "Ovo", "qtd": 4}], "sobra": ""},
    {"dias": ["seg"], "tipo": "almoco", "prato": "Arroz, feijão e frango", "min": 40, "equip": ["fogao", "pressao"],
     "ingr": [{"item": "arroz", "qtd": 250}, {"item": "frango", "qtd": 600}], "sobra": "frango extra vai no jantar"}],
    "compras": [{"item": "flocão", "emb": "pacote 500 g", "tam": 500, "un": "g", "preco": 3.5, "secao": "Mercearia", "promo": 0},
                {"item": "ovo", "emb": "bandeja 30 ovos", "tam": 30, "un": "un", "preco": 19.9, "secao": "Ovos e laticínios", "promo": 0},
                {"item": "arroz", "emb": "pacote 5 kg", "tam": 5000, "un": "g", "preco": 24.9, "secao": "Mercearia", "promo": 0},
                {"item": "frango", "emb": "bandeja 1 kg", "tam": 1000, "un": "g", "preco": 17.9, "secao": "Açougue e aves", "promo": 7}]}
interno = cardapio.expandir(compacto)
ok([(r["dia"], r["tipo"]) for r in interno["refeicoes"]] == [("seg", "cafe"), ("seg", "almoco"), ("ter", "cafe"), ("qua", "cafe")],
   "café repetido em 3 dias vira 3 refeições (uma entrada só no JSON), na ordem da semana")
ing_ovo = interno["refeicoes"][0]["ingredientes"][1]
ok(ing_ovo["unidade"] == "un" and interno["refeicoes"][1]["ingredientes"][1]["unidade"] == "g",
   "a unidade do ingrediente vem da embalagem (Ovo -> un; frango -> g)")
prod = {p["item"]: p for p in interno["produtos"]}
ok(not prod["arroz"]["perecivel"] and prod["frango"]["perecivel"] and prod["ovo"]["perecivel"]
   and prod["frango"]["promocao_id"] == 7 and prod["arroz"]["embalagem"] == "pacote 5 kg",
   "perecível vem da seção (Mercearia não estraga; açougue e ovos estragam) e a promoção é mantida")
interno["refeicoes"][2]["ingredientes"][0]["quantidade"] = 999
ok(interno["refeicoes"][0]["ingredientes"][0]["quantidade"] == 200, "cada dia do café é uma refeição independente")
calc_c = cesta.calcular(cardapio.expandir(compacto), {})
ok(calc_c["total"] == round(3.5 * 2 + 19.9 + 24.9 + 17.9, 2), f"cesta calculada do formato compacto (R$ {calc_c['total']:.2f})")
sem_compra = copy.deepcopy(compacto)
sem_compra["refeicoes"][1]["ingr"].append({"item": "pimentão", "qtd": 1})
plano_sc = cardapio.expandir(sem_compra)
novo_banco()
perfil_c = criar_usuario(refeicoes=["cafe", "almoco"], dias=["seg"], utensilios=["fogao", "pressao"], restricoes=[])
g, _ = cardapio.conferir(plano_sc, perfil_c, cesta.calcular(plano_sc, {}), 500)
ok(any("sem embalagem" in x and "pimentão" in x for x in g), "ingrediente sem compra na lista é barrado")
absurdo = copy.deepcopy(compacto)
absurdo["refeicoes"][1]["ingr"][0]["qtd"] = 250000
plano_ab = cardapio.expandir(absurdo)
g, _ = cardapio.conferir(plano_ab, perfil_c, cesta.calcular(plano_ab, {}), 5000)
ok(any("fora do normal" in x for x in g), "quantidade absurda (unidade trocada pela IA) é barrada")
gemini, claude = instalar_ias()
criar_usuario("u9", refeicoes=["cafe", "almoco", "jantar"], dias=["seg", "ter", "qua"])
agrupado = para_ia(plano_valido())
agrupado["refeicoes"].append({"dias": ["seg", "ter", "qua"], "tipo": "cafe", "prato": "Cuscuz com ovo", "min": 15,
                              "equip": ["fogao"], "ingr": [{"item": "flocão de milho", "qtd": 150}, {"item": "ovo", "qtd": 3}],
                              "sobra": ""})
claude.fila = [agrupado]
plano_ag = asyncio.run(cardapio.gerar_plano("u9"))
ok(len(plano_ag["refeicoes"]) == 9 and modelos(claude) == [SONNET] and plano_ag["cesta"]["total"] > 0
   and plano_ag["receitas"] == {},
   "plano com café agrupado é aceito pelo Sonnet de primeira, sem receitas prontas (geradas ao abrir)")
ok("por refeição" in claude.chamadas[0]["mensagens"][0]["texto"]
   and f"R$ {200 / 9:.2f} por refeição" in claude.chamadas[0]["mensagens"][0]["texto"],
   "o pedido diz quanto dá, em média, por refeição (R$ 200 / 9 refeições)")
g, _ = cardapio.conferir(plano_valido(), banco.usuario("u1") or criar_usuario(), calc, 100)
estouro = next(x for x in g if "orçamento" in x)
ok("Itens que mais pesam: carne moída R$ 32.00" in estouro
   and "arroz (usa 500 g, compra 1 pacote 5 kg por R$ 24.90)" in estouro,
   "orçamento estourado: a correção diz os itens que mais pesam e as embalagens grandes demais para o uso")
ok(roteador.categoria([estouro]) == "orçamento" and roteador.categoria([estouro, "tem queijo (Lactose)"]) == "alergia/restrição",
   "nome de item na dica ('ovo') não faz o estouro de orçamento virar 'alergia' no registro")

# =======================================================================================
secao("C10: alergia escondida no nome do prato")
ok(all(v(p, ["lactose"]) for p in ("Empadão goiano", "Strogonoff de frango", "Purê de batata",
                                   "Lasanha à bolonhesa", "Escondidinho de carne seca", "Pamonha de sal")),
   "lactose: empadão, strogonoff, purê, lasanha, escondidinho e pamonha são barrados pelo nome")
ok(not v("Purê de batata sem lactose", ["lactose"]) and not v("Strogonoff de frango zero lactose", ["lactose"]),
   "a versão 'sem lactose' escrita no nome é liberada")
ok(v("Feijoada simples", ["vegetariano"]) and v("Galinhada goiana", ["vegetariano"])
   and not v("Feijão tropeiro vegetariano", ["vegetariano"]), "vegetariano: feijoada e galinhada barradas; tropeiro vegetariano liberado")
ok(v("Sopa de legumes com frango", ["vegetariano"]), "'de legumes' não libera um prato com frango")
ok(v("Vatapá", ["amendoim"]) and v("Vatapá", ["frutos_do_mar"]) and v("Panqueca de carne", ["gluten"])
   and v("Quindim", ["ovo"]), "vatapá (castanha e camarão), panqueca (trigo) e quindim (ovo)")
ok(not v("Arroz com pequi", ["lactose", "gluten", "vegetariano"]) and not v("Couve manteiga refogada", ["lactose"]),
   "sem falso alarme em prato goiano sem o ingrediente")

secao("C10: repetir a semana anterior")
novo_banco()
perfil = criar_usuario()
calc = cesta.calcular(plano_valido(), {})
g, av = cardapio.conferir(plano_valido(), perfil, calc, 200, ["Arroz, feijão e carne moída"])
ok(not g and av, "1 prato repetido da semana passada: só aviso (coincidência comum)")
g, _ = cardapio.conferir(plano_valido(), perfil, calc, 200, ["Arroz, feijão e carne moída", "Feijão tropeiro com ovo"])
ok(any("semana passada" in x for x in g) and roteador.categoria(g) == "repetição",
   "2 ou mais pratos repetidos da semana passada: o plano é refeito")
banco.atualizar_perfil("u1", preferencias_pratos={"feijao tropeiro com ovo": {"prato": "Feijão tropeiro com ovo", "nota": 5}})
g, _ = cardapio.conferir(plano_valido(), banco.usuario("u1"), calc, 200,
                         ["Arroz, feijão e carne moída", "Feijão tropeiro com ovo"])
ok(not g, "favorito pode repetir (não conta para o limite)")

secao("C10 / lacuna 3: plano acima do orçamento é entregue com opções")
import atendimento  # noqa: E402

novo_banco()
gemini, claude = instalar_ias()
criar_usuario("o1", orcamento=100.0)
claude.fila = [para_ia(plano_valido()), para_ia(plano_valido())]
plano_o = asyncio.run(cardapio.gerar_plano("o1"))
ok(modelos(claude) == [SONNET, OPUS] and plano_o["cesta"]["total"] == 133.90 and cardapio.excesso(plano_o) == 33.90,
   "nenhum modelo fechou no orçamento: o melhor plano é entregue (passou R$ 33,90)")
r = telas.resultado(plano_o, banco.usuario("o1"))
acoes_r = [b.acao for linha in r.botoes for b in linha]
rotulos_r = [b.rotulo for linha in r.botoes for b in linha]
ok("R$ 33,90 acima do orçamento" in r.texto and "pl:ajo:orc" in acoes_r and "pl:ajo:simples" in acoes_r
   and "💰 Aumentar para R$ 140,00" in rotulos_r and "pl:ajo:lanches" not in acoes_r,
   "o resultado avisa quanto passou e oferece [Aumentar para R$ 140] e [Pratos mais simples] (sem lanches: sem o botão)")
s = asyncio.run(atendimento.acao("o1", "pl:ajo:simples"))
ok(s[0].tipo == "acao" and s[0].acao == "pl:montar" and "mais simples" in s[0].texto and "33.90" in s[0].texto,
   "[Pratos mais simples] monta de novo, pedindo pratos mais baratos e dizendo quanto passou")
s = asyncio.run(atendimento.acao("o1", "pl:ajo:orc"))
ok(banco.usuario("o1")["orcamento"] == 140.0 and banco.plano_atual("o1")["orcamento"] == 140.0
   and "Sobrou" in s[0].texto and "Orçamento atualizado para R$ 140,00" in s[0].texto and s[0].editar,
   "[Aumentar] sobe o orçamento do perfil e do plano, sem chamar a IA")
criar_usuario("o2", orcamento=500.0, periodo="mes", refeicoes=["almoco", "jantar", "lanche"])
com_lanche = para_ia(plano_valido())
com_lanche["refeicoes"].append({"dias": ["seg", "ter", "qua"], "tipo": "lanche", "prato": "Banana", "min": 1,
                                "equip": [], "ingr": [{"item": "banana", "qtd": 3}], "sobra": ""})
com_lanche["compras"].append({"item": "banana", "emb": "penca 12 un", "tam": 12, "un": "un", "preco": 6.0,
                              "secao": "Hortifrúti", "promo": 0})
claude.fila = [com_lanche, com_lanche]
claude.chamadas.clear()
plano_l = asyncio.run(cardapio.gerar_plano("o2"))
r = telas.resultado(plano_l, banco.usuario("o2"))
rotulos_r = [b.rotulo for linha in r.botoes for b in linha]
ok(plano_l["orcamento"] == round(500 / 4.3, 2) and "✂️ Tirar lanches" in rotulos_r
   and "💰 Aumentar para R$ 610,00/mês" in rotulos_r,
   "compra do mês: o botão mostra o valor por mês (R$ 140/semana x 4,3) e aparece [Tirar lanches]")
s = asyncio.run(atendimento.acao("o2", "pl:ajo:lanches"))
plano_l2 = banco.plano_atual("o2")
ok(not cardapio.tem_lanches(plano_l2) and "lanche" not in banco.usuario("o2")["refeicoes"]
   and plano_l2["cesta"]["total"] == 133.90 and "Tirei os lanches" in s[0].texto and not claude.chamadas[2:],
   "[Tirar lanches] tira do plano e do perfil e refaz a conta, sem chamar a IA")
banco.obter_ou_criar_usuario("c9")
banco.atualizar_perfil("c9", nome="Bia", adultos=2, criancas=0, refeicoes=["almoco", "jantar"],
                       dias=[d for d, _ in cardapio.DIAS], periodo="semana", orcamento=60.0, cadastro_passo="orcamento")
t_orc = cadastro.tela_do_passo(banco.usuario("c9"), "orcamento")
sug = cadastro.sugerir_orcamento(banco.usuario("c9"))
ok("bem abaixo" in t_orc.texto and any(b.acao == "cad:orc:sug" for linha in t_orc.botoes for b in linha),
   f"cadastro: orçamento muito abaixo da sugestão (R$ 60 x R$ {sug:.0f}) avisa já na escolha")
cadastro.acao("c9", "cad:orc:sug")
ok(banco.usuario("c9")["orcamento"] == sug and "bem abaixo" not in cadastro.tela_do_passo(banco.usuario("c9"), "orcamento").texto,
   "[Usar R$ sugerido] volta para a sugestão e o aviso some")

secao("C10: receita acompanha o tamanho da família")
novo_banco()
gemini, claude = instalar_ias()
criar_usuario()
claude.fila = [para_ia(plano_valido())]
asyncio.run(cardapio.gerar_plano("u1"))
receita_ia = {"ingredientes": ["arroz"], "passos": ["Cozinhe."], "tempo_min": 30, "dica": ""}
gemini.fila = [dict(receita_ia)]
rec1 = asyncio.run(cardapio.receita("u1", "seg", "almoco"))
ok(rec1["porcoes"] == 2.5 and "arroz 250 g" in gemini.chamadas[-1]["mensagens"][0]["texto"],
   "receita guarda para quantas porções foi escrita (2,5)")
banco.atualizar_perfil("u1", adultos=4)  # agora 4,5 porções
gemini.fila = [dict(receita_ia)]
rec2 = asyncio.run(cardapio.receita("u1", "seg", "almoco"))
briefing_r = gemini.chamadas[-1]["mensagens"][0]["texto"]
ok(len(gemini.chamadas) == 2 and rec2["porcoes"] == 4.5 and "arroz 450 g" in briefing_r and "cebola 2 un" in briefing_r
   and "2.5 -> 4.5" in briefing_r, "família mudou: a receita é refeita com as quantidades na nova proporção")
tela_rec = telas.receita(banco.plano_atual("u1"), banco.usuario("u1"), "seg", "almoco", rec2)
ok("Receita ajustada para 4,5 porções" in tela_rec.texto and "continua para 2,5 porções" in tela_rec.texto,
   "a tela da receita avisa que a lista de compras não mudou sozinha")
asyncio.run(cardapio.receita("u1", "seg", "almoco"))
ok(len(gemini.chamadas) == 2, "mesma família: a receita guardada é reaproveitada (sem nova chamada)")

# =======================================================================================
secao("C9: resultado e botões")
import mercado  # noqa: E402

novo_banco()
gemini, claude = instalar_ias()
criar_usuario("m1", mercados=["assai"])
claude.fila = [para_ia(plano_valido())]
plano_m = asyncio.run(cardapio.gerar_plano("m1"))
r = telas.resultado(plano_m, banco.usuario("m1"))
rotulos_r = [b.rotulo for linha in r.botoes for b in linha]
itens_m = len(mercado.linhas(plano_m))
ok("Sua semana está pronta, Ana!" in r.texto and f"Gasto *R$ 133,90* de R$ 200,00. Sobrou *R$ 66,10* · {itens_m} itens." in r.texto,
   "resultado no formato do C9: gasto, orçamento, sobra e número de itens")
ok(rotulos_r[:4] == ["📅 Ver cardápio", "🛒 Lista", "📄 PDF", "🔄 Refazer"] and "🛒 Modo mercado" in rotulos_r,
   "botões do C9 com os textos do pedido + [🛒 Modo mercado]")
ok(any(b.acao == "mm:ver" for linha in telas.lista(plano_m).botoes for b in linha), "a lista também tem [🛒 Modo mercado]")

secao("🛒 Modo mercado")
pid = plano_m["id"]
s = asyncio.run(atendimento.acao("m1", "mm:ver"))[0]
acoes_m = [b.acao for linha in s.botoes for b in linha]
ok(f"✅ 0 de {itens_m} itens · R$ 0,00 de R$ 133,90" in s.texto and f"mm:t:{pid}:0" in acoes_m and "mm:x" in acoes_m
   and acoes_m[0] == "mm:x", "abre com o topo '✅ 0 de N itens · R$ 0 de R$ total', seções e um botão por item")
primeira = mercado.linhas(plano_m)[0]
s = asyncio.run(atendimento.acao("m1", f"mm:t:{pid}:0"))[0]
rotulo_1 = next(b.rotulo for linha in s.botoes for b in linha if b.acao == f"mm:t:{pid}:0")
ok(s.editar and f"✅ 1 de {itens_m} itens · {telas.brl(primeira['custo'])} de R$ 133,90" in s.texto and rotulo_1.startswith("✅"),
   "tocar no item marca ✅ editando a mesma mensagem, e o total parcial sobe")
s = asyncio.run(atendimento.acao("m1", f"mm:t:{pid}:0"))[0]
ok(f"✅ 0 de {itens_m} itens" in s.texto and banco.plano_atual("m1")["mercado"]["comprados"] == [],
   "tocar de novo desmarca (⬜)")
asyncio.run(atendimento.acao("m1", f"mm:t:{pid}:1"))
asyncio.run(atendimento.acao("m1", f"mm:t:{pid}:2"))
duas = mercado.linhas(plano_m)[1:3]
s = asyncio.run(atendimento.acao("m1", "mm:ver"))[0]
ok(f"✅ 2 de {itens_m} itens · {telas.brl(duas[0]['custo'] + duas[1]['custo'])}" in s.texto
   and sorted(banco.plano_atual("m1")["mercado"]["comprados"]) == sorted(cesta.chave(l["item"]) for l in duas),
   "o progresso fica salvo no banco: fechar e abrir de novo continua de onde parou")
ok(asyncio.run(atendimento.acao("m1", "mm:x")) == [], "título de seção não faz nada")
s = asyncio.run(atendimento.acao("m1", f"mm:t:{pid + 99}:0"))[0]
ok("O plano mudou" in s.texto, "botão de um plano que já mudou não marca o item errado")
ok(mercado.ler_preco("23,90") == 23.9 and mercado.ler_preco("R$ 1.234,50") == 1234.5 and mercado.ler_preco("23.9") == 23.9
   and mercado.ler_preco("abc") is None and mercado.ler_preco("0") is None, "lê o preço escrito de vários jeitos")
s = asyncio.run(atendimento.acao("m1", "mm:p"))[0]
ok(any(b.acao == f"mm:pi:{pid}:3" for linha in s.botoes for b in linha), "[✏️ Paguei outro preço] mostra os itens para escolher")
quarta = mercado.linhas(plano_m)[3]
s = asyncio.run(atendimento.acao("m1", f"mm:pi:{pid}:3"))[0]
ok(quarta["embalagem"] in s.texto and "Escreva só o valor" in s.texto and banco.usuario("m1")["aguardando"] == f"preco:{pid}:3",
   "escolher o item pede o preço da embalagem e o Rende fica esperando o valor")
s = asyncio.run(atendimento.responder("m1", "R$ 15,50"))[0]
pago = banco.precos(produto=cesta.chave(quarta["item"]))
ok("Anotei" in s.texto and not s.editar and banco.usuario("m1")["aguardando"] is None
   and pago and pago[0]["origem"] == "usuario" and pago[0]["preco"] == 15.5 and pago[0]["mercado"] == "Assaí",
   "o preço informado alimenta a tabela de preços (origem 'usuario', mercado da pessoa)")
r_m = mercado.resumo(banco.plano_atual("m1"))
ok(r_m["marcados"] == 3 and r_m["valor_marcado"] == round(duas[0]["custo"] + duas[1]["custo"] + 15.5 * quarta["pacotes"], 2)
   and r_m["valor_total"] == round(133.90 - quarta["custo"] + 15.5 * quarta["pacotes"], 2),
   "o item com preço informado fica marcado e os totais usam o preço real")
gemini.chamadas.clear()
asyncio.run(atendimento.acao("m1", f"mm:pi:{pid}:4"))
s = asyncio.run(atendimento.responder("m1", "e aí, tudo bem?"))
ok(banco.usuario("m1")["aguardando"] is None and gemini.chamadas, "se a mensagem não for um preço, a espera acaba e vira conversa normal")
banco.atualizar_perfil("m1", restricoes=["vegetariano", "lactose"])
ok(mercado.substitutos("Frango coxa", banco.usuario("m1")) == ["ovo"]
   and mercado.substitutos("leite integral", banco.usuario("m1")) == ["leite sem lactose"],
   "substitutos respeitam as restrições (vegetariano: só ovo no lugar do frango; lactose: leite sem lactose)")
banco.atualizar_perfil("m1", restricoes=["lactose"])
s = asyncio.run(atendimento.acao("m1", "mm:fim"))[0]
plano_f = banco.plano_atual("m1")
casa = banco.usuario("m1")["despensa"]
comprados_f = set(plano_f["mercado"]["comprados"])
ok(plano_f["mercado"]["finalizado"] and len(plano_f["mercado"]["nao_encontrei"]) == itens_m - 3
   and all(cesta.chave(i) not in comprados_f for i in plano_f["mercado"]["nao_encontrei"]),
   "[🏁 Terminei] guarda o que ficou sem marcar na lista 'não encontrei'")
tamanhos_m = {cesta.chave(p["item"]): p["tamanho"] for p in plano_f["produtos"]}
ok(all(casa[k]["quantidade"] == round(l["pacotes"] * tamanhos_m[k]) for l in mercado.linhas(plano_f)
       for k in [cesta.chave(l["item"])] if k in comprados_f)
   and not any(cesta.chave(i) in casa for i in plano_f["mercado"]["nao_encontrei"]),
   "o que foi comprado vai para a despensa (o que ficou de fora, não)")
com_substituto = next(i for i in plano_f["mercado"]["nao_encontrei"] if mercado.substitutos(i, banco.usuario("m1")))
ok("Compras encerradas" in s.texto and "Não encontrei" in s.texto
   and f"• {com_substituto} → dá para usar {mercado.substitutos(com_substituto, banco.usuario('m1'))[0]}" in s.texto
   and any(b.acao.startswith("pl:tro:") for linha in s.botoes for b in linha),
   f"o Rende oferece substitutos ({com_substituto}) e a troca dos pratos afetados")
ok(not any(cesta.chave(i) in plano_f["cesta"]["despensa_final"] for i in plano_f["mercado"]["nao_encontrei"]
           if cesta.chave(i) not in (plano_f.get("despensa_inicial") or {})),
   "a despensa da semana seguinte não conta sobra do que não foi comprado")
ok(cardapio.despensa_base("m1", banco.usuario("m1")) == casa, "refazer o plano depois das compras parte do que tem em casa agora")
faltou_f = plano_f["mercado"]["nao_encontrei"][0]
afetada = mercado.pratos_afetados(plano_f, cesta.chave(faltou_f))[0]
claude.fila = [troca_ia(refeicao(afetada["dia"], afetada["tipo"], "Prato com o que faltou", [(faltou_f, 100, "g")]))] * 3
claude.chamadas.clear()
asyncio.run(atendimento.trocar_prato("m1", afetada["dia"], afetada["tipo"]))
ok(f"NÃO encontrou no mercado (não use): " in claude.chamadas[0]["mensagens"][0]["texto"]
   and "não encontrou no mercado" in claude.chamadas[1]["mensagens"][-1]["texto"],
   "a troca sabe o que faltou e reprova prato que usa o item não encontrado")

secao("C11: PDF com caixinhas clicáveis")
from pypdf import PdfReader  # noqa: E402

plano_pdf = banco.plano_atual("m1")
arquivo = pdf.gerar(plano_pdf, banco.usuario("m1"))
leitor = PdfReader(io.BytesIO(arquivo))
campos = leitor.get_fields() or {}
widgets = [a.get_object() for p in leitor.pages for a in (p.get("/Annots") or [])]
ok(len(campos) == itens_m and all(c.get("/FT") == "/Btn" for c in campos.values()),
   f"uma caixinha de formulário (AcroForm) por item ({len(campos)} de {itens_m})")
ok(all(int(w["/F"]) & 4 and set(w["/AP"]["/N"].keys()) == {"/Yes", "/Off"} for w in widgets),
   "caixinhas com aparência marcada/desmarcada e visíveis na impressão")
texto_pdf = " ".join(p.extract_text() for p in leitor.pages)
ok("estimado" in texto_pdf and "preço pago" in texto_pdf and "Dica: no Telegram, use o Modo mercado" in texto_pdf
   and telas.brl(r_m["valor_total"]).replace("R$ ", "") in texto_pdf,
   "cada item diz 'estimado' ou 'preço pago', o total usa o preço pago e a dica do Modo mercado vai no fim")
banco.adicionar_promocao(mercado="Assaí", produto="arroz", preco=22.9, validade="2099-12-31", cidade="Goiânia", origem="admin")
plano_promo = copy.deepcopy(plano_pdf)
plano_promo["promocoes"] = {"1": banco.promocao(1)}
for l in plano_promo["cesta"]["linhas"]:
    if l["item"] == "arroz":
        l["promocao_id"] = 1
texto_promo = PdfReader(io.BytesIO(pdf.gerar(plano_promo, banco.usuario("m1")))).pages[0].extract_text()
ok("PROMOÇÃO" in texto_promo and "(Assaí, até 31/12)" in texto_promo, "item em promoção: 'PROMOÇÃO (mercado, até dd/mm)'")
grande = copy.deepcopy(plano_pdf)
grande.pop("mercado", None)
base = grande["cesta"]["linhas"][0]
grande["cesta"]["linhas"] = [{**base, "item": f"item {n}", "nome": f"item {n}", "secao": cardapio.SECOES[n % 6]}
                             for n in range(70)]
grande["cesta"]["linhas"].sort(key=lambda l: l["secao"])
leitor_g = PdfReader(io.BytesIO(pdf.gerar(grande, banco.usuario("m1"))))
rects = [[float(v) for v in a.get_object()["/Rect"]] for p in leitor_g.pages for a in (p.get("/Annots") or [])]
ok(len(leitor_g.pages) >= 2 and len(rects) == 70 and all(r[1] > 30 and r[3] < 842 for r in rects),
   f"lista grande: {len(leitor_g.pages)} páginas, cada caixinha dentro da página do seu item")

# =======================================================================================
secao("C6: encarte, arquivo de áudio")
from datetime import timedelta  # noqa: E402

novo_banco()
gemini, claude = instalar_ias()
criar_usuario("e1")
amanha = (banco.agora().date() + timedelta(days=1)).isoformat()
ofertas = [{"produto": "arroz", "marca": "Tio João", "tamanho": "5 kg", "preco": 21.9, "preco_anterior": 27.9},
           {"produto": "feijão carioca", "tamanho": "1 kg", "preco": 6.49, "condicao": "leve 3 pague 2"},
           {"produto": "", "preco": 5}, {"produto": "óleo", "preco": 0}, {"produto": "carne", "preco": 99999}]
r_e = asyncio.run(ferramentas.executar(Chamada("e1", "salvar_promocoes_de_encarte",
                                               {"mercado": "Tático", "validade": amanha, "ofertas": ofertas}),
                                       ferramentas.Contexto(usuario="e1")))
promos_e = banco.promocoes_validas(cidade="Goiânia", mercado="Tático")
ok(r_e["salvas"] == 2 and r_e["ignoradas"] == 3 and {p["origem"] for p in promos_e} == {"usuario"}
   and promos_e[0]["validade"] == amanha,
   "encarte: ofertas legíveis salvas em promocoes (origem 'usuario'); sem nome, preço zero ou absurdo são ignorados")
arroz_e = next(p for p in promos_e if p["produto"] == "arroz")
feijao_e = next(p for p in promos_e if p["produto"] == "feijão carioca")
ok(arroz_e["marca"] == "Tio João" and arroz_e["preco_anterior"] == 27.9 and feijao_e["condicao"] == "leve 3 pague 2",
   "marca, preço anterior e condição ('leve 3 pague 2') são guardados")
r_e2 = asyncio.run(ferramentas.executar(Chamada("e2", "salvar_promocoes_de_encarte",
                                                {"mercado": "tático", "validade": amanha, "ofertas": ofertas[:2]}),
                                        ferramentas.Contexto(usuario="e1")))
ok(r_e2["salvas"] == 0 and len(banco.promocoes_validas(mercado="Tático")) == 2, "o mesmo encarte mandado de novo não duplica")
r_e3 = asyncio.run(ferramentas.executar(Chamada("e3", "salvar_promocoes_de_encarte",
                                                {"mercado": "Bretas", "ofertas": [{"produto": "café", "preco": 15.9}]}),
                                        ferramentas.Contexto(usuario="e1")))
ok(r_e3["salvas"] == 1 and r_e3["validade"] == (banco.agora().date() + timedelta(days=6)).isoformat() and "aviso" in r_e3,
   "encarte sem validade impressa vale 6 dias, com aviso")
r_e4 = asyncio.run(ferramentas.executar(Chamada("e4", "salvar_promocoes_de_encarte",
                                                {"mercado": "Barão", "validade": "2020-01-01",
                                                 "ofertas": [{"produto": "café", "preco": 15.9}]}),
                                        ferramentas.Contexto(usuario="e1")))
ok("erro" in r_e4 and not banco.promocoes_validas(mercado="Barão"), "encarte vencido não é salvo")
gemini.fila = [RespostaIA(chamadas=[Chamada("c9", "salvar_promocoes_de_encarte",
                                            {"mercado": "Assaí", "validade": amanha,
                                             "ofertas": [{"produto": "frango", "tamanho": "1 kg", "preco": 11.9}]})]),
               "🔥 Salvei 1 oferta do Assaí"]
foto_encarte = {"tipo": "imagem", "mime_type": "image/jpeg", "dados": b"jpg"}
s = asyncio.run(atendimento.responder("e1", "", anexo=foto_encarte))
ok(s[0].texto.startswith("🔥 Salvei") and banco.promocoes_validas(mercado="Assaí")[0]["produto"] == "frango"
   and gemini.chamadas[0]["mensagens"][-1]["anexo"]["mime_type"] == "image/jpeg"
   and any(d["nome"] == "salvar_promocoes_de_encarte" for d in gemini.chamadas[0]["ferramentas"]),
   "foto de encarte na conversa: o Gemini lê e a ferramenta salva as ofertas")
ok("Encarte" in cardapio.prompts.CONVERSA and "salvar_promocoes_de_encarte" in cardapio.prompts.CONVERSA,
   "as instruções da conversa explicam o que fazer com encarte")
ok(atendimento.mime_de_audio("audio/x-m4a") == "audio/mp4" and atendimento.mime_de_audio("audio/mpeg") == "audio/mpeg"
   and atendimento.mime_de_audio(None) == "audio/ogg", "arquivo de áudio: tipos ajustados para o Gemini (m4a -> mp4)")
claude.chamadas.clear()
gemini.chamadas.clear()
gemini.fila = ["🎤 Entendi: R$ 300 por semana"]
s = asyncio.run(atendimento.responder("e1", "", anexo={"tipo": "audio", "mime_type": "audio/mpeg", "dados": b"ID3"}))
ok(s[0].texto.startswith("🎤") and gemini.chamadas and not claude.chamadas,
   "arquivo de áudio (mp3) é entendido pelo Gemini e nunca vai para o Claude")
codigo_bot = (RAIZ / "bot_telegram.py").read_text(encoding="utf-8")
ok("filters.AUDIO | filters.Document.AUDIO, arquivo_de_audio" in codigo_bot,
   "o bot aceita áudio mandado como arquivo, além da mensagem de voz")

# =======================================================================================
secao("Cadastro com botões")
novo_banco()
banco.obter_ou_criar_usuario("c1")
s = cadastro.iniciar("c1")
ok("Como posso te chamar" in s[0].texto, "cadastro começa pelo nome")
s = cadastro.resposta_escrita("c1", "matheus")
ok(banco.usuario("c1")["nome"] == "Matheus" and "Quem vai comer" in s[0].texto, "nome salvo e passa para 'quem vai comer'")
cadastro.acao("c1", "cad:ad:+")
s = cadastro.acao("c1", "cad:cr:+")
ok("2,5" in s[0].texto.replace(".", ",") or "2.5" in s[0].texto, "adultos e crianças: = 2,5 porções (criança = meia)")
s = cadastro.acao("c1", "cad:ok")
s = cadastro.acao("c1", "cad:t:refeicoes:cafe")
ok(banco.usuario("c1")["refeicoes"] == ["almoco", "jantar", "cafe"], "múltipla escolha liga/desliga opções")
cadastro.acao("c1", "cad:ok")
cadastro.acao("c1", "cad:ok")  # dias (padrão: todos)
cadastro.acao("c1", "cad:s:vibe:rapido")
cadastro.acao("c1", "cad:t:restricoes:gluten")
s = cadastro.acao("c1", "cad:outro")
s = cadastro.resposta_escrita("c1", "coentro")
ok(banco.usuario("c1")["restricoes_outras"] == "coentro" and "Alergia" in s[0].texto or "restrição" in s[0].texto,
   "restrição 'outra' escrita e volta para a tela de restrições")
cadastro.acao("c1", "cad:ok")
cadastro.acao("c1", "cad:t:utensilios:pressao")
cadastro.acao("c1", "cad:ok")
cadastro.acao("c1", "cad:t:mercados:assai")
ok(banco.usuario("c1")["mercados"] == ["assai"], "escolher um mercado tira o 'Qualquer um'")
cadastro.acao("c1", "cad:ok")
s = cadastro.acao("c1", "cad:s:periodo:semana")
sugestao = banco.usuario("c1")["orcamento"]
ok(sugestao == cadastro.sugerir_orcamento(banco.usuario("c1")) and "porções na semana" in s[0].texto,
   f"orçamento sugerido para a família (R$ {sugestao:.0f}) com resumo")
s = cadastro.acao("c1", "cad:orc:+")
ok(banco.usuario("c1")["orcamento"] == sugestao + 20, "botão +R$ 20 ajusta o orçamento")
s = cadastro.acao("c1", "cad:ok")
ok(cadastro.concluido(banco.usuario("c1")) and s[-1].tipo == "acao" and s[-1].acao == "pl:montar",
   "cadastro concluído já pede para montar o plano")
s = cadastro.editar("c1", "pessoas")
cadastro.acao("c1", "cad:ad:+")
s = cadastro.acao("c1", "cad:ok")
ok(banco.usuario("c1")["adultos"] == 3 and "Seu perfil" in s[0].texto, "/perfil: muda um item e volta ao resumo")

# =======================================================================================
secao("Telas, botões e PDF")
novo_banco()
criar_usuario()
plano = plano_valido()
plano.update(cesta=cesta.calcular(plano, {}), orcamento=200.0, receitas={}, promocoes={})
plano["id"] = banco.salvar_plano("u1", plano)
plano = banco.plano_atual("u1")
r = telas.resultado(plano, banco.usuario("u1"))
ok("Sua semana está pronta, Ana" in r.texto and "R$ 133,90" in r.texto and "Sobrou *R$ 66,10*" in r.texto,
   "resultado: gasto, orçamento e sobra")
d = telas.dia(plano, "ter")
acoes = [b.acao for linha in d.botoes for b in linha]
ok("pl:tro:ter:almoco" in acoes and "pl:rec:ter:jantar" in acoes and "pl:dia:qua" in acoes, "dia: botões de receita, troca e navegação")
ok(all(len(a.encode()) <= 64 for a in acoes), "dados dos botões cabem no limite do Telegram (64 bytes)")
l = telas.lista(plano)
ok("1 pacote 5 kg" in l.texto and "Total: R$ 133,90" in l.texto, "lista por embalagem com total")
pr = telas.progresso(1, ajustando=True)
ok("✅ Vendo as promoções da semana" in pr and "⏳ Ajustando as receitas..." in pr, "texto da animação")
rec = {"ingredientes": ["a"], "passos": ["p1", "p2"], "tempo_min": 20, "dica": ""}
ok(telas.passo(rec, "seg", "almoco", 0).botoes[0][0].acao == "pl:pas:seg:almoco:1"
   and telas.passo(rec, "seg", "almoco", 1).botoes[0][0].acao == "pl:fiz:seg:almoco", "passo a passo termina no 'Fiz!'")
d2 = telas.dia(plano, "ter", aviso="🔁 Troquei! Jantar agora é *Sopa*.")
ok(d2.texto.startswith("🔁 Troquei!") and "📅 *Terça*" in d2.texto and d2.editar,
   "confirmação da troca vai no topo da tela do dia (sem mensagem extra)")
import atendimento as _at  # noqa: E402

os.environ["APAGAR_PDF_APOS_MIN"] = "5"
s_pdf = asyncio.run(_at.acao("u1", "pl:pdf"))[0]
ok(s_pdf.tipo == "documento" and s_pdf.apagar_apos == 300 and "some em 5 min" in s_pdf.texto,
   "PDF é enviado para sumir sozinho depois de 5 minutos (APAGAR_PDF_APOS_MIN)")
arquivo = pdf.gerar(plano, banco.usuario("u1"))
ok(arquivo.startswith(b"%PDF") and len(arquivo) > 1000, f"PDF gerado na memória ({len(arquivo)} bytes)")

# =======================================================================================
secao("Conversa com ferramentas (IAs simuladas)")
import atendimento  # noqa: E402

novo_banco()
gemini, claude = instalar_ias()
criar_usuario()
gemini.fila = [RespostaIA(chamadas=[Chamada("c1", "salvar_perfil", {"adultos": 4, "criancas": 0})]),
               "Anotado! Agora são 4 adultos 😊"]
s = asyncio.run(atendimento.responder("u1", "agora somos 4 em casa"))
ok(banco.usuario("u1")["adultos"] == 4 and s[0].texto.startswith("Anotado"), "'agora somos 4 em casa' atualiza o perfil")
ok(gemini.chamadas[1]["mensagens"][-1]["papel"] == "ferramenta", "resultado da ferramenta volta para a IA")
gemini.fila = [RespostaIA(chamadas=[Chamada("c2", "montar_plano", {})]), "Já vou montar seu plano!"]
s = asyncio.run(atendimento.responder("u1", "monta meu cardápio"))
ok(s[-1].tipo == "acao" and s[-1].acao == "pl:montar", "pedido de cardápio vira a ação com animação")
gemini.fila = [RespostaIA(chamadas=[Chamada("c3", "pedir_especialista", {"motivo": "complexo", "resumo_do_pedido": "X"})])]
claude.fila = ["Resposta caprichada do especialista"]
s = asyncio.run(atendimento.responder("u1", "otimiza minha compra entre 3 mercados sem glúten e sem lactose"))
ok(s[0].texto == "Resposta caprichada do especialista" and claude.chamadas, "pedido complexo é refeito pelo Claude")
ok(atendimento.motivo_para_recusar("u1", duracao_s=121) == atendimento.prompts.AUDIO_LONGO
   and atendimento.motivo_para_recusar("u1", tamanho_bytes=11 * 1024 * 1024) == atendimento.prompts.ARQUIVO_GRANDE,
   "áudio > 2 min e arquivo > 10 MB recusados")
for _ in range(30):
    banco.contar_mensagem("u1")
ok("limite" in asyncio.run(atendimento.responder("u1", "oi"))[0].texto, "limite diário (LIMITE_MSG_DIA)")
texto_custos = atendimento.custos()[0].texto
ok("Sonnet" in texto_custos and "Gemini" in texto_custos and "Subidas de nível hoje" in texto_custos
   and "Limites hoje: Haiku" in texto_custos and "pedido complexo: Sonnet" in texto_custos,
   "/custos: gasto por modelo, quem fez o quê, subidas e limites")
ok(atendimento.eh_admin("999") and not atendimento.eh_admin("u1"), "/custos só para ADMIN_IDS")

# =======================================================================================
secao("Troca de prato com o orçamento apertado (teste real de 24/11)")
novo_banco()
gemini, claude = instalar_ias()
criar_usuario()
claude.fila = [para_ia(plano_valido())]
plano = asyncio.run(cardapio.gerar_plano("u1"))
i_tj = cardapio.indice(plano, "ter", "jantar")
sem_prato = copy.deepcopy(plano)
del sem_prato["refeicoes"][i_tj]
calc_sem = cesta.calcular(sem_prato, plano.get("despensa_inicial") or {})
folga_exata = plano["orcamento"] - calc_sem["total"]

claude.chamadas.clear()
claude.fila = [troca_ia(refeicao("ter", "jantar", "Arroz carreteiro", [("arroz", 300, "g"), ("carne moída", 200, "g")]))]
asyncio.run(cardapio.trocar_prato("u1", "ter", "jantar"))
briefing = claude.chamadas[0]["mensagens"][0]["texto"]
ok(f"NO MÁXIMO R$ {folga_exata:.2f}" in briefing,
   f"troca: o modelo recebe a folga exata, calculada sem o prato antigo (R$ {folga_exata:.2f})")
ok("Sobras das embalagens já compradas" in briefing and "arroz" in briefing.split("Sobras das embalagens já compradas")[1],
   "troca: o modelo recebe as sobras das embalagens (usar não custa nada)")

atual = banco.plano_atual("u1")
apertado = {k: v for k, v in atual.items() if k not in ("id", "criado_em")}
apertado["orcamento"] = 50.0
banco.atualizar_plano(atual["id"], apertado)
claude.chamadas.clear()
s = asyncio.run(atendimento.trocar_prato("u1", "ter", "jantar"))
ok(not claude.chamadas and "orçamento" in s[0].texto and "tentar de novo" not in s[0].texto,
   "troca sem folga no orçamento: avisa a pessoa sem gastar com a IA")
banco.atualizar_plano(atual["id"], {k: v for k, v in atual.items() if k not in ("id", "criado_em")})

caro = troca_ia(refeicao("ter", "jantar", "Picanha na chapa", [("picanha", 1000, "g")]),
               [produto("picanha", "peça 1 kg", 1000, "g", 150.0, "Açougue e aves", True)])
claude.fila = [caro, caro, caro]
claude.chamadas.clear()
s = asyncio.run(atendimento.trocar_prato("u1", "ter", "jantar"))
ok(len(claude.chamadas) == 3 and "orçamento" in s[0].texto and "tentar de novo" not in s[0].texto,
   "troca que estoura o orçamento em todos os níveis explica o motivo, sem convidar a repetir")

secao("Privacidade do registro (log)")
textos_log = capturar_log("rende", lambda: asyncio.run(atendimento.trocar_prato("5550001112", "ter", "jantar")))
ok(textos_log and not any("5550001112" in t for t in textos_log), "o log de uma troca que falhou não grava o ID da conta")
suspeitos = [f"{arq.name}:{n}" for arq in sorted(RAIZ.glob("*.py"))
             for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1)
             if re.search(r"\blog\.\w+\(.*\busuario\b", linha)]
ok(not suspeitos, f"nenhuma linha de log do código grava o ID do usuário {suspeitos}")

# =======================================================================================
secao("Formato para cada IA")
msgs = [{"papel": "assistente", "texto": "oi"},
        {"papel": "usuario", "texto": "foto", "anexo": {"mime_type": "image/jpeg", "dados": b"jpg"}},
        {"papel": "assistente", "texto": "", "chamadas": [Chamada("abc", "mostrar", {"o_que": "lista"})]},
        {"papel": "ferramenta", "resultados": [{"id": "abc", "nome": "mostrar", "conteudo": {"ok": True}}]}]
c = ia_claude._para_claude(msgs)
ok(c[0]["role"] == "user" and c[2]["content"][0]["type"] == "image" and c[3]["content"][0]["type"] == "tool_use"
   and c[4]["content"][0]["type"] == "tool_result", "Claude: começa pela pessoa, imagem, tool_use e tool_result")
g = ia._para_gemini(msgs)
ok(g[0].role == "user" and g[3].parts[0].function_call.name == "mostrar" and g[4].parts[0].function_response.id == "abc",
   "Gemini: function_call e function_response com o mesmo id")
audio_claude = ia_claude._para_claude([{"papel": "usuario", "texto": "", "anexo": {"mime_type": "audio/ogg", "dados": b"x"}}])
ok("áudio" in audio_claude[0]["content"][0]["text"], "Claude: áudio vira aviso em texto (ele não ouve áudio)")

import bot_telegram  # noqa: E402

registro = logging.LogRecord("t", logging.ERROR, "", 0,
                             f"url bot{os.environ['TELEGRAM_BOT_TOKEN']}/x chave {os.environ['GEMINI_API_KEY']} sk-ant-api03-abcdefghijkl",
                             None, None)
saida = bot_telegram._FormatoSemSegredos("%(message)s").format(registro)
ok(saida.count("<segredo>") == 3, "log esconde token do Telegram e chaves das IAs")

print(f"\n{total - len(falhas)} de {total} testes OK" + (f"\nFALHARAM: {falhas}" if falhas else ""))
sys.exit(1 if falhas else 0)
