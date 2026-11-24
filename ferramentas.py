"""Ferramentas que a IA de conversa pode pedir (function calling).

As definições são neutras (nome, descrição, JSON Schema); ia.py e ia_claude.py
convertem para o formato de cada modelo. Ações demoradas e com tela (montar o
plano com animação, trocar prato, mostrar cardápio) viram uma Saida do tipo 'acao',
que o canal executa depois de mandar a resposta da IA.
"""
import logging
from dataclasses import dataclass, field

import banco
import cardapio
import promocoes
from cardapio import DIAS, MERCADOS, REFEICOES, UTENSILIOS, VIBES
from cesta import chave
from ia_comum import Chamada
from restricoes import NOMES as NOMES_RESTRICOES
from telas import Saida

log = logging.getLogger("rende.ferramentas")

_DIAS = [d for d, _ in DIAS]
_TIPOS = [r for r, _, _ in REFEICOES]
_NOMES_DIA_SEMANA = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}


def _lista(enum: list[str], descricao: str) -> dict:
    return {"type": "array", "items": {"type": "string", "enum": enum}, "description": descricao}


SALVAR_PERFIL = {
    "nome": "salvar_perfil",
    "descricao": "Salva ou atualiza dados do perfil da pessoa. Envie só os campos que mudaram.",
    "parametros": {"type": "object", "properties": {
        "nome": {"type": "string", "description": "Como a pessoa quer ser chamada"},
        "adultos": {"type": "integer"}, "criancas": {"type": "integer"},
        "refeicoes": _lista(_TIPOS, "Refeições a planejar"),
        "dias": _lista(_DIAS, "Dias em que vai cozinhar"),
        "vibe": {"type": "string", "enum": list(VIBES)},
        "restricoes": _lista(list(NOMES_RESTRICOES), "Alergias e restrições (lista completa)"),
        "restricoes_outras": {"type": "string", "description": "Outras restrições em texto livre"},
        "utensilios": _lista(list(UTENSILIOS), "O que tem na cozinha (lista completa)"),
        "mercados": _lista(list(MERCADOS), "Mercados onde compra"),
        "periodo": {"type": "string", "enum": ["semana", "mes"]},
        "orcamento": {"type": "number", "description": "Valor em reais para o período"},
        "cidade": {"type": "string"},
        "preferencias": {"type": "string", "description": "Gostos e observações gerais"},
        "itens_em_casa": {"type": "array", "items": {"type": "string"},
                          "description": "Alimentos que a pessoa já tem em casa (ex.: vistos numa foto da geladeira)"},
    }},
}

DEFINICOES = [
    SALVAR_PERFIL,
    {"nome": "montar_plano",
     "descricao": "Monta (ou refaz) o plano da semana: cardápio e lista de compras por embalagem, "
                  "dentro do orçamento. Mostra uma animação e depois o resultado com botões.",
     "parametros": {"type": "object", "properties": {
         "pedido": {"type": "string", "description": "Pedido especial da pessoa para este plano, se houver"}}}},
    {"nome": "trocar_prato",
     "descricao": "Troca um prato específico do plano atual e recalcula o total.",
     "parametros": {"type": "object", "required": ["dia", "refeicao"], "properties": {
         "dia": {"type": "string", "enum": _DIAS}, "refeicao": {"type": "string", "enum": _TIPOS},
         "pedido": {"type": "string", "description": "O que a pessoa quer no lugar (ex.: 'algo sem carne')"}}}},
    {"nome": "mostrar",
     "descricao": "Mostra o resumo do plano, o cardápio (de um dia), a lista de compras, o PDF da lista, o "
                  "Modo mercado (marcar o que já foi para o carrinho, durante as compras) ou onde comprar "
                  "(quanto a lista sai em cada mercado).",
     "parametros": {"type": "object", "required": ["o_que"], "properties": {
         "o_que": {"type": "string", "enum": ["resumo", "cardapio", "lista", "pdf", "mercado", "onde_comprar"]},
         "dia": {"type": "string", "enum": _DIAS}}}},
    {"nome": "avaliar_prato",
     "descricao": "Guarda a nota (1 a 5) que a pessoa deu para um prato. 4-5 = favorito, 1-2 = não usar mais.",
     "parametros": {"type": "object", "required": ["prato", "nota"], "properties": {
         "prato": {"type": "string"}, "nota": {"type": "integer"}}}},
    {"nome": "listar_promocoes",
     "descricao": "Lista promoções cadastradas e válidas (mercado, produto, preço e validade).",
     "parametros": {"type": "object", "properties": {
         "produto": {"type": "string"}, "mercado": {"type": "string"}, "cidade": {"type": "string"}}}},
    {"nome": "salvar_promocoes_de_encarte",
     "descricao": "Salva as ofertas lidas numa foto ou PDF de encarte (folheto de ofertas de um mercado). "
                  "Mande TODAS as ofertas legíveis; nunca invente preço que não dá para ler.",
     "parametros": {"type": "object", "required": ["mercado", "ofertas"], "properties": {
         "mercado": {"type": "string", "description": "Rede do encarte (ex.: 'Tático', 'Assaí')"},
         "validade": {"type": "string", "description": "Último dia das ofertas, AAAA-MM-DD ('' se não aparece)"},
         "ofertas": {"type": "array", "items": {"type": "object", "required": ["produto", "preco"], "properties": {
             "produto": {"type": "string", "description": "O que é, curto: 'arroz', 'feijão carioca'"},
             "marca": {"type": "string"},
             "tamanho": {"type": "string", "description": "Embalagem: '5 kg', '900 ml', 'bandeja 30 un'"},
             "preco": {"type": "number", "description": "Preço da oferta, em reais"},
             "preco_anterior": {"type": "number", "description": "Preço 'de', se aparecer"},
             "condicao": {"type": "string", "description": "Ex.: 'leve 3 pague 2', 'só no app', 'cartão da loja'"},
         }}}}}},
    {"nome": "configurar_avisos",
     "descricao": "Liga ou desliga os avisos de promoção e muda o dia/horário do resumo semanal.",
     "parametros": {"type": "object", "required": ["ativo"], "properties": {
         "ativo": {"type": "boolean"},
         "dia_semana": {"type": "string", "enum": list(_NOMES_DIA_SEMANA)},
         "horario": {"type": "string", "description": "HH:MM, ex.: 09:00"}}}},
    {"nome": "pedir_especialista",
     "descricao": "Encaminha um pedido complexo SOBRE O RENDE (cardápio, compras, orçamento) para um modelo "
                  "mais forte responder neste turno. Nunca para assunto de fora.",
     "parametros": {"type": "object", "required": ["motivo", "resumo_do_pedido", "no_escopo"], "properties": {
         "no_escopo": {"type": "boolean", "description": "true só se o pedido é sobre o Rende"},
         "motivo": {"type": "string"},
         "resumo_do_pedido": {"type": "string", "description": "O pedido completo, com o que a pessoa disse"}}}},
]


@dataclass
class Contexto:
    usuario: str
    saidas: list[Saida] = field(default_factory=list)
    especialista: str | None = None   # resumo do pedido, quando a IA pede o especialista
    perfil_salvo: bool = False


def definicoes(cadastro: bool = False, com_especialista: bool = True) -> list[dict]:
    if cadastro:
        return [SALVAR_PERFIL]
    return [d for d in DEFINICOES if com_especialista or d["nome"] != "pedir_especialista"]


# --- implementações ------------------------------------------------------------------
def _salvar_perfil(ctx: Contexto, **args) -> dict:
    campos = {}
    for campo in ("nome", "vibe", "restricoes_outras", "periodo", "cidade", "preferencias"):
        if isinstance(args.get(campo), str) and args[campo].strip():
            campos[campo] = args[campo].strip()[:300]
    for campo in ("adultos", "criancas"):
        if args.get(campo) is not None:
            campos[campo] = max(0, min(15, int(args[campo])))
    if campos.get("adultos") == 0:
        campos["adultos"] = 1
    if args.get("orcamento") is not None and float(args["orcamento"]) > 0:
        campos["orcamento"] = round(float(args["orcamento"]), 2)
    validos = {"refeicoes": _TIPOS, "dias": _DIAS, "restricoes": list(NOMES_RESTRICOES),
               "utensilios": list(UTENSILIOS), "mercados": list(MERCADOS)}
    for campo, permitidos in validos.items():
        if isinstance(args.get(campo), list):
            campos[campo] = [v for v in args[campo] if v in permitidos]
    if campos.get("vibe") not in (None, *VIBES):
        campos.pop("vibe")
    if campos.get("periodo") not in (None, "semana", "mes"):
        campos.pop("periodo")
    if args.get("itens_em_casa"):
        despensa = dict(banco.usuario(ctx.usuario).get("despensa") or {})
        for item in args["itens_em_casa"][:40]:
            despensa.setdefault(chave(item), {"item": item, "quantidade": 0, "unidade": "?"})
        campos["despensa"] = despensa
    perfil = banco.atualizar_perfil(ctx.usuario, **campos)
    ctx.perfil_salvo = bool(campos)
    return {"ok": True, "salvo": sorted(campos), "perfil": {k: perfil.get(k) for k in (
        "nome", "adultos", "criancas", "refeicoes", "dias", "vibe", "restricoes", "orcamento", "periodo")}}


def _montar_plano(ctx: Contexto, pedido: str = "") -> dict:
    ctx.saidas.append(Saida(tipo="acao", acao="pl:montar", texto=pedido or ""))
    return {"ok": True, "info": "O plano vai ser montado logo depois da sua resposta, com animação. "
                                "Responda só uma frase curta avisando."}


def _trocar_prato(ctx: Contexto, dia: str, refeicao: str, pedido: str = "") -> dict:
    plano = banco.plano_atual(ctx.usuario)
    if not plano:
        return {"erro": "a pessoa ainda não tem plano"}
    try:
        cardapio.indice(plano, dia, refeicao)
    except KeyError:
        return {"erro": f"não existe {refeicao} de {dia} no plano"}
    ctx.saidas.append(Saida(tipo="acao", acao=f"pl:tro:{dia}:{refeicao}", texto=pedido or ""))
    return {"ok": True, "info": "A troca vai ser feita logo depois da sua resposta. Responda só uma frase curta."}


def _mostrar(ctx: Contexto, o_que: str, dia: str | None = None) -> dict:
    if not banco.plano_atual(ctx.usuario):
        return {"erro": "a pessoa ainda não tem plano; ofereça montar um"}
    acao = {"resumo": "pl:res", "lista": "pl:lista", "pdf": "pl:pdf", "mercado": "mm:ver", "onde_comprar": "oc:ver",
            "cardapio": f"pl:dia:{dia}" if dia else "pl:dia"}[o_que]
    ctx.saidas.append(Saida(tipo="acao", acao=acao))
    return {"ok": True}


def _avaliar_prato(ctx: Contexto, prato: str, nota: int) -> dict:
    cardapio.avaliar(ctx.usuario, prato, nota)
    return {"ok": True}


def _listar_promocoes(ctx: Contexto, produto: str = "", mercado: str = "", cidade: str = "") -> dict:
    perfil = banco.usuario(ctx.usuario)
    promos = banco.promocoes_validas(cidade=cidade or perfil.get("cidade") or "Goiânia",
                                     mercado=mercado or None, produto=produto or None, limite=20)
    return {"promocoes": [{k: p.get(k) for k in ("mercado", "produto", "marca", "tamanho", "preco",
                                                 "condicao", "validade")} for p in promos],
            "observacao": "Preços de promoção cadastrada (não são estimativa)." if promos
            else "Não há promoção cadastrada para isso agora."}


MAX_OFERTAS_ENCARTE = 80


def _salvar_promocoes_de_encarte(ctx: Contexto, mercado: str, ofertas: list, validade: str = "") -> dict:
    """C6: oferta lida de um encarte vai para `promocoes` com origem 'usuario' (conferências em promocoes.py)."""
    perfil = banco.usuario(ctx.usuario) or {}
    resultado = promocoes.salvar_ofertas(mercado=mercado, ofertas=ofertas, origem="usuario",
                                         cidade=perfil.get("cidade"), validade=validade or None,
                                         maximo=MAX_OFERTAS_ENCARTE)
    resultado.pop("ids", None)
    return resultado


def _configurar_avisos(ctx: Contexto, ativo: bool, dia_semana: str = "", horario: str = "") -> dict:
    campos: dict = {"avisos_ativos": int(bool(ativo))}
    if dia_semana in _NOMES_DIA_SEMANA:
        campos["aviso_dia_semana"] = _NOMES_DIA_SEMANA[dia_semana]
    if horario and len(horario) == 5 and horario[2] == ":" and horario.replace(":", "").isdigit():
        campos["aviso_horario"] = horario
    banco.atualizar_perfil(ctx.usuario, **campos)
    return {"ok": True, **campos}


def _pedir_especialista(ctx: Contexto, motivo: str, resumo_do_pedido: str, no_escopo: bool = False) -> dict:
    if not no_escopo:  # C3: assunto de fora nunca sobe para o Claude
        return {"erro": "fora do escopo: não encaminhe; responda com no_escopo: nao"}
    ctx.especialista = resumo_do_pedido
    log.info("Pedido marcado como complexo: %s", motivo[:120])
    return {"ok": True}


_IMPLEMENTACOES = {
    "salvar_perfil": _salvar_perfil, "montar_plano": _montar_plano, "trocar_prato": _trocar_prato,
    "mostrar": _mostrar, "avaliar_prato": _avaliar_prato, "listar_promocoes": _listar_promocoes,
    "configurar_avisos": _configurar_avisos, "pedir_especialista": _pedir_especialista,
    "salvar_promocoes_de_encarte": _salvar_promocoes_de_encarte,
}


async def executar(chamada: Chamada, ctx: Contexto) -> dict:
    funcao = _IMPLEMENTACOES.get(chamada.nome)
    if funcao is None:
        return {"erro": f"ferramenta desconhecida: {chamada.nome}"}
    try:
        return funcao(ctx, **(chamada.args or {}))
    except TypeError as erro:
        return {"erro": f"parâmetros inválidos: {erro}"}
    except Exception:
        log.exception("Falha na ferramenta %s", chamada.nome)
        return {"erro": "falha interna ao executar a ferramenta"}
