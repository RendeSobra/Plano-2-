"""C3: o Rende só responde sobre o Rende (cardápio, receitas do cardápio, lista, PDF, despensa,
orçamento, economia, promoções, mercados, perfil, avisos e como usar o Rende).

Três camadas, a principal em código:
1. filtro_rapido(): antes de chamar qualquer IA, barra o que é claramente de fora (futebol,
   política, "ignore suas regras"...) e não tem nenhuma palavra do Rende. Não gasta nada.
2. Toda resposta final da IA começa com a linha "no_escopo: sim" ou "no_escopo: nao"
   (separar() lê o campo). Com "nao", o código descarta o texto do modelo e manda uma
   mensagem fixa com botões. O formato é uma linha de texto, e não JSON forçado, para
   funcionar igual no Gemini e no Claude também quando a IA usa ferramentas.
3. A ferramenta que chama o especialista (Claude) exige no_escopo = true: fora do escopo
   nunca sobe para o Claude.
O log registra só "fora_do_escopo" (sem o texto e sem quem mandou).
"""
import random
import re

from restricoes import normalizar

# Palavras do Rende: se aparecer alguma, a mensagem vai para a IA (pode ser pergunta mista).
PALAVRAS_DO_RENDE = [
    "rende", "cardapio", "receita", "prato", "comida", "comer", "almoco", "jantar", "cafe", "lanche",
    "marmita", "lista", "compra", "compras", "mercado", "supermercado", "atacado", "feira", "preco",
    "precos", "promocao", "promocoes", "oferta", "ofertas", "encarte", "orcamento", "economizar",
    "economia", "gastar", "gasto", "barato", "despensa", "geladeira", "perfil", "aviso", "avisos", "pdf",
    "ingrediente", "ingredientes", "cozinhar", "cozinha", "semana", "arroz", "feijao", "frango", "carne",
    "ovo", "ovos", "legume", "legumes", "fruta", "verdura", "alergia", "lactose", "gluten", "vegetariano",
    "dieta", "nutricionista", "porcao", "porcoes", "embalagem", "sobra", "sobrou",
]

# Claramente de fora (só barra se não houver nenhuma palavra do Rende na mensagem)
_FORA = [
    # tentativas de mudar as regras, a personalidade ou de ver o prompt
    r"\bignor\w* (as |suas |todas as |tod\w* )?(instruc|regra)", r"\besquec\w* (as |suas )?(instruc|regra)",
    r"\b(revel|mostr|diga|conta|passa)\w* (o |seu |teu )?prompt", r"\bsystem prompt\b", r"\bprompt do sistema\b",
    r"\bmodo (desenvolvedor|developer|deus)\b", r"\bjailbreak\b", r"\bfing\w* (que|ser)\b", r"\baja como\b",
    r"\ba partir de agora (voce|vc) (e|sera)\b", r"\bmud\w* (a |sua |de )?personalidade\b",
    # temas de fora
    # (sem "Goiás", "Vila Nova" e "Atlético": também são estado, bairro de Goiânia e nome de rua)
    r"\bfutebol\b", r"\b(flamengo|corinthians|palmeiras|vasco|gremio|cruzeiro|fluminense|botafogo)\b",
    r"\b(brasileirao|copa do mundo|campeonato|libertadores)\b", r"\bpolitic", r"\beleic", r"\bpresidente\b",
    r"\b(deputad|senador|vereador|prefeit)", r"\bnoticia", r"\bprogram(ar|acao)\b", r"\bcodigo\b", r"\bpython\b",
    r"\bjavascript\b", r"\bhtml\b", r"\btraduz", r"\btraducao\b", r"\bem ingles\b", r"\bredacao\b",
    r"\b(dever|licao|trabalho) (de casa|da escola)\b", r"\bequacao\b", r"\bpiada\b", r"\bpoema\b", r"\bhoroscopo\b",
    r"\bsigno\b", r"\bprevisao do tempo\b", r"\bbitcoin\b", r"\bbolsa de valores\b", r"\bremedio\b",
    r"\bsintoma", r"\bdiagnostic", r"\bcapital d[aoe]\b", r"\bquem (foi|descobriu|inventou)\b",
    r"\bescrev\w* (um |uma )?(texto|poema|email|e-mail|artigo|carta|musica)\b",
]
_FORA_RE = [re.compile(p) for p in _FORA]
_TAG_RE = re.compile(r"^\W*no[_ ]escopo\W*[:=]\W*(sim|nao|não|true|false)\b\W*", re.IGNORECASE)


def filtro_rapido(texto: str) -> bool:
    """True = claramente fora do escopo (responder com a mensagem fixa, sem chamar IA)."""
    alvo = normalizar(texto)
    if not alvo or any(re.search(rf"\b{p}\b", alvo) for p in PALAVRAS_DO_RENDE):
        return False
    return any(p.search(alvo) for p in _FORA_RE)


def separar(texto: str) -> tuple[bool | None, str]:
    """'no_escopo: nao\\n...' -> (False, '...'). Sem o campo: (None, texto inteiro)."""
    texto = (texto or "").strip()
    primeira, _, resto = texto.partition("\n")
    achou = _TAG_RE.match(primeira)
    if not achou:
        return None, texto
    valor = achou.group(1).lower() in ("sim", "true")
    depois_da_tag = primeira[achou.end():].strip()
    return valor, "\n".join(p for p in (depois_da_tag, resto.strip()) if p).strip()


def mensagem_fixa(nome: str, mensagens: list[str]) -> str:
    return random.choice(mensagens).format(nome=nome or "amigo")
