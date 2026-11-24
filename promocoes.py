"""Guardar ofertas na tabela `promocoes`, com as conferências em código, venham de onde vierem:
encarte mandado pela pessoa (origem "usuario"), coletor dos sites (origem "site") ou /promo
(origem "admin").

Conferências: produto com nome, preço plausível (entre R$ 0,01 e R$ 5.000), validade (vencida
não entra; sem data impressa vale DIAS_SEM_VALIDADE dias) e sem repetir a mesma oferta.
Também normaliza nome, marca e tamanho ("ARROZ TIO JOÃO 5KG" -> arroz / Tio João / 5 kg).
"""
import logging
import re
from datetime import date, timedelta

import banco
from restricoes import normalizar

log = logging.getLogger("rende.promocoes")

DIAS_SEM_VALIDADE = 6   # sem data impressa: vale até daqui a 6 dias (uma semana contando hoje)
PRECO_MAXIMO = 5000
CIDADE_PADRAO = "Goiânia"

_UNIDADES = {"kg": "kg", "g": "g", "gr": "g", "grs": "g", "grama": "g", "gramas": "g", "ml": "ml",
             "l": "L", "lt": "L", "lts": "L", "litro": "L", "litros": "L", "un": "un", "und": "un",
             "unid": "un", "unidade": "un", "unidades": "un"}
_RE_TAMANHO = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|grs?|gramas?|g|ml|lts?|litros?|l|unid(?:ades?)?|und|un)\b",
                         re.IGNORECASE)
_PALAVRAS_MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "com"}


def tamanho(texto: str | None) -> str | None:
    """'5KG' -> '5 kg'; '900ML' -> '900 ml'; '1,5L' -> '1,5 L'; 'bandeja 30 un' -> '30 un'."""
    achado = _RE_TAMANHO.search(texto or "")
    if not achado:
        return None
    numero = achado.group(1).replace(".", ",")
    return f"{numero} {_UNIDADES[achado.group(2).lower()]}"


def marca(texto: str | None) -> str | None:
    """'TIO JOÃO' -> 'Tio João'."""
    palavras = (texto or "").strip().split()
    if not palavras:
        return None
    return " ".join(p.lower() if p.lower() in _PALAVRAS_MINUSCULAS and i else p[:1].upper() + p[1:].lower()
                    for i, p in enumerate(palavras))[:60]


def produto(nome: str | None, nome_marca: str | None = None) -> str:
    """Nome genérico, curto e em minúsculas, sem marca nem tamanho: 'ARROZ TIO JOÃO 5KG' -> 'arroz'
    (se a marca vier separada). Mantém acentos para a pessoa ler."""
    texto = _RE_TAMANHO.sub(" ", nome or "")
    if nome_marca:
        texto = re.sub(re.escape(nome_marca.strip()), " ", texto, flags=re.IGNORECASE)
    texto = re.sub(r"[^\wÀ-ÿ%,.\- ]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip(" -,.").lower()[:80]


def _data(texto) -> date | None:
    if isinstance(texto, date):
        return texto
    try:
        return date.fromisoformat(str(texto or "").strip()[:10])
    except ValueError:
        return None


def _preco(valor) -> float:
    if isinstance(valor, str):
        valor = valor.replace("R$", "").replace(".", "").replace(",", ".").strip() if "," in valor else valor
    try:
        return round(float(valor or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def assinatura(mercado: str, nome: str, tam: str | None, preco: float) -> tuple:
    return normalizar(mercado), normalizar(nome), normalizar(tam or ""), round(preco, 2)


def salvar_ofertas(*, mercado: str, ofertas: list[dict], origem: str, cidade: str | None = None,
                   validade: str | date | None = None, validade_inicio: str | date | None = None,
                   fonte_url: str | None = None, lojas: str | None = None, maximo: int = 80) -> dict:
    """Grava as ofertas novas e devolve {"ids", "salvas", "ignoradas", "validade", "aviso"} ou {"erro"}.
    `validade` vale para todas; uma oferta pode trazer a própria ("validade": AAAA-MM-DD)."""
    mercado = (mercado or "").strip()[:60]
    if not mercado:
        return {"erro": "diga de qual mercado é o encarte"}
    hoje = banco.agora().date()
    aviso = ""
    fim_geral = _data(validade)
    if fim_geral is None:
        fim_geral = hoje + timedelta(days=DIAS_SEM_VALIDADE)
        aviso = f"o encarte não mostra a validade: guardei até {fim_geral.strftime('%d/%m')}"
    if fim_geral < hoje:
        return {"erro": f"essas ofertas já venceram ({fim_geral.strftime('%d/%m')}); nada foi salvo"}
    cidade = cidade or CIDADE_PADRAO
    inicio_geral = _data(validade_inicio)
    existentes = {assinatura(p["mercado"], p["produto"], p.get("tamanho"), p["preco"])
                  for p in banco.promocoes_validas(cidade=cidade, mercado=mercado, limite=2000)}
    ids, ignoradas = [], 0
    for oferta in (ofertas or [])[:maximo]:
        nome_marca = marca(oferta.get("marca"))
        nome = produto(oferta.get("produto"), nome_marca)
        preco = _preco(oferta.get("preco"))
        tam = tamanho(oferta.get("tamanho")) or (str(oferta.get("tamanho") or "").strip()[:40] or None)
        fim = _data(oferta.get("validade")) or fim_geral
        if fim < hoje or not nome or not 0 < preco < PRECO_MAXIMO:
            ignoradas += 1
            continue
        chave = assinatura(mercado, nome, tam, preco)
        if chave in existentes:
            ignoradas += 1
            continue
        existentes.add(chave)
        anterior = _preco(oferta.get("preco_anterior"))
        ids.append(banco.adicionar_promocao(
            mercado=mercado, produto=nome, preco=preco, validade=fim.isoformat(), cidade=cidade, origem=origem,
            marca=nome_marca, tamanho=tam, preco_anterior=anterior if anterior > preco else None,
            condicao=str(oferta.get("condicao") or "").strip()[:80] or None,
            validade_inicio=(_data(oferta.get("validade_inicio")) or inicio_geral or hoje).isoformat(),
            lojas=(lojas or "")[:200] or None, fonte_url=fonte_url))
    log.info("Promoções (%s, %s): %d novas, %d ignoradas.", origem, mercado, len(ids), ignoradas)
    return {"ok": True, "ids": ids, "salvas": len(ids), "ignoradas": ignoradas, "mercado": mercado,
            "validade": fim_geral.isoformat(), **({"aviso": aviso} if aviso else {})}


# --- comparar itens da lista com promoções (avisos, cardápio e "onde comprar") ---------
NAO_COMIDA = ("detergente", "sabao", "amaciante", "desinfetante", "agua sanitaria", "alvejante", "limpador",
              "multiuso", "esponja", "papel higienico", "papel toalha", "guardanapo", "shampoo", "xampu",
              "condicionador", "sabonete", "creme dental", "pasta de dente", "escova de dente", "desodorante",
              "fralda", "absorvente", "inseticida", "saco de lixo", "lustra moveis", "cera", "racao",
              "lenco umedecido", "fio dental", "aparelho de barbear", "hidratante", "protetor solar", "tintura")
_PALAVRAS_VAZIAS = {"de", "da", "do", "das", "dos", "com", "e", "em", "tipo", "o", "a"}


def eh_comida(nome: str) -> bool:
    alvo = normalizar(nome)
    return not any(re.search(rf"\b{re.escape(p)}", alvo) for p in NAO_COMIDA)


def _singular(palavra: str) -> str:
    if len(palavra) > 3 and palavra.endswith("oes"):
        return palavra[:-3] + "ao"
    if len(palavra) > 3 and palavra.endswith("s") and not palavra.endswith("ss"):
        return palavra[:-1]
    return palavra


def termos(texto: str) -> str:
    """'Ovos brancos' -> 'ovo branco' (minúsculas, sem acento, no singular, sem palavras vazias)."""
    return " ".join(_singular(p) for p in normalizar(texto).split() if p not in _PALAVRAS_VAZIAS)


def combina(item: str, nome_promocao: str) -> bool:
    """O item da lista e a promoção falam da mesma coisa? 'feijão' x 'feijão carioca' = sim;
    'frango' x 'peito de frango' = sim; 'arroz' x 'farinha de arroz'... também (aceitável)."""
    a, b = termos(item), termos(nome_promocao)
    if not a or not b:
        return False
    return bool(re.search(rf"\b{re.escape(a)}\b", b) or re.search(rf"\b{re.escape(b)}\b", a))
