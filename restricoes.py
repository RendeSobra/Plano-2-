"""Confere EM CÓDIGO se um prato ou ingrediente fere as alergias e restrições da pessoa.

A IA recebe as restrições, mas nunca confiamos só nela: depois de cada cardápio,
troca ou receita, tudo passa por aqui. Na dúvida, a regra é conservadora
(um falso alarme só faz o plano ser refeito; um ingrediente proibido pode fazer mal).
"""
import re
import unicodedata

# Rótulos mostrados nos botões do cadastro
NOMES = {
    "lactose": "Lactose",
    "gluten": "Glúten",
    "ovo": "Ovo",
    "amendoim": "Amendoim/castanhas",
    "frutos_do_mar": "Frutos do mar",
    "peixe": "Peixe",
    "soja": "Soja",
    "vegetariano": "Vegetariano",
}

_PEIXES = ["peixe", "tilapia", "sardinha", "atum", "bacalhau", "salmao", "merluza", "pescada",
           "pintado", "tambaqui", "cacao", "anchova", "pacu", "surubim", "linguado", "truta"]
_FRUTOS_DO_MAR = ["camarao", "lula", "polvo", "marisco", "mexilhao", "ostra", "caranguejo", "siri",
                  "lagosta", "vieira", "frutos do mar", "sururu"]

PROIBIDOS: dict[str, list[str]] = {
    "lactose": ["leite", "queijo", "manteiga", "requeijao", "creme de leite", "nata", "iogurte",
                "coalhada", "leite condensado", "doce de leite", "mucarela", "mussarela", "parmesao",
                "catupiry", "cream cheese", "chantilly", "soro de leite", "whey", "ricota", "coalho"],
    "gluten": ["trigo", "farinha de trigo", "farinha de rosca", "pao", "paes", "macarrao", "espaguete",
               "talharim", "lasanha", "nhoque", "biscoito", "bolacha", "cevada", "centeio", "malte",
               "cerveja", "empanado", "empanada", "cuscuz marroquino", "torrada", "pizza", "bolo",
               "aveia", "semolina", "pastel", "esfiha", "coxinha", "empadao", "empada", "kibe", "quibe"],
    "ovo": ["ovo", "ovos", "gema", "clara de ovo", "maionese", "omelete", "fritada"],
    "amendoim": ["amendoim", "castanha", "castanhas", "nozes", "noz", "amendoa", "amendoas", "pistache",
                 "avela", "macadamia", "pacoca", "pe de moleque"],
    "frutos_do_mar": _FRUTOS_DO_MAR,
    "peixe": _PEIXES,
    "soja": ["soja", "tofu", "shoyu", "molho de soja", "misso", "pts", "edamame", "proteina texturizada"],
    "vegetariano": ["carne", "carnes", "frango", "galinha", "porco", "suino", "pernil", "lombo", "bacon",
                    "linguica", "calabresa", "salsicha", "presunto", "mortadela", "salame", "peito de peru",
                    "costela", "acem", "patinho", "musculo", "figado", "coxa", "sobrecoxa", "picanha",
                    "alcatra", "file mignon", "cupim", "charque", "toucinho", "banha", "torresmo",
                    "caldo de carne", "caldo de galinha", "gelatina", "moela", "coracao de frango",
                    *_PEIXES, *_FRUTOS_DO_MAR],
}

# Marcadores que liberam o ingrediente INTEIRO para aquela restrição ("creme de leite sem lactose")
MARCADORES: dict[str, list[str]] = {
    "lactose": ["sem lactose", "zero lactose"],
    "gluten": ["sem gluten"],
    "ovo": ["sem ovo"],
}

# Expressões seguras que são apagadas antes da busca ("leite de coco" não é leite de vaca)
EXCECOES: dict[str, list[str]] = {
    "lactose": ["leite de coco", "leite vegetal", "leite de soja", "leite de amendoa", "leite de aveia",
                "leite de arroz", "manteiga de amendoim", "manteiga de cacau",
                # verduras e grãos com "manteiga" no nome (não têm leite)
                "couve manteiga", "alface manteiga", "feijao manteiga"],
    "gluten": ["pao de queijo", "macarrao de arroz", "polvilho", "tapioca"],
    "soja": ["oleo de soja"],  # óleo refinado de soja não costuma causar reação; mantenha se o médico liberou
    "vegetariano": ["carne vegetal", "carne de soja", "carne de jaca", "proteina vegetal"],
}


def normalizar(texto: str) -> str:
    """minúsculas, sem acentos e sem pontuação: 'Pão-de-Queijo!' -> 'pao de queijo'."""
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()


def _contem(texto_norm: str, termo: str) -> bool:
    return re.search(rf"\b{re.escape(termo)}\b", texto_norm) is not None


def termos_proibidos(restricoes: list[str], outras: str | None = None) -> dict[str, list[str]]:
    """Restrição -> termos proibidos. 'outras' (texto livre) vira termos extras: 'coentro, pimenta'."""
    termos = {r: PROIBIDOS[r] for r in restricoes if r in PROIBIDOS}
    extras = [normalizar(t) for t in re.split(r",|;|\be\b|\n", outras or "") if normalizar(t)]
    if extras:
        termos["outro"] = extras
    return termos


def violacoes(texto: str, restricoes: list[str], outras: str | None = None) -> list[str]:
    """Lista de problemas encontrados no texto (nome de prato ou ingrediente)."""
    alvo = normalizar(texto)
    encontrados = []
    for restricao, termos in termos_proibidos(restricoes, outras).items():
        if any(_contem(alvo, m) for m in MARCADORES.get(restricao, [])):
            continue
        seguro = alvo
        for excecao in EXCECOES.get(restricao, []):
            seguro = re.sub(rf"\b{re.escape(excecao)}\b", " ", seguro)
        for termo in termos:
            if _contem(seguro, termo):
                encontrados.append(f"'{texto}' tem '{termo}' ({NOMES.get(restricao, restricao)})")
                break
    return encontrados


def violacoes_em(textos: list[str], restricoes: list[str], outras: str | None = None) -> list[str]:
    problemas = []
    for texto in textos:
        problemas += violacoes(texto, restricoes, outras)
    return problemas
