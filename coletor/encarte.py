"""O que cada rede devolve: a lista de encartes (PDF ou imagem) vigentes em Goiânia."""
from dataclasses import dataclass
from datetime import date, datetime

from banco import FUSO_BRASILIA, agora


@dataclass
class Encarte:
    rede: str                        # chave da rede ("prezunic")
    mercado: str                     # nome que aparece para a pessoa ("Prezunic")
    titulo: str
    url: str                         # o arquivo do encarte (PDF ou imagem)
    fonte_url: str                   # a página oficial onde o encarte aparece (vai junto com a oferta)
    validade_inicio: date | None = None
    validade_fim: date | None = None  # None: o site não informa (a IA lê no próprio encarte)
    lojas: str | None = None          # lojas ou região, quando o site informa


def data_iso(texto: str | None) -> date | None:
    """'2026-11-26T02:59:00.000Z' -> data em Brasília (25/11); '2026-11-30' -> 30/11; inválida -> None."""
    if not texto:
        return None
    try:
        momento = datetime.fromisoformat(str(texto).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if momento.tzinfo is not None:
        momento = momento.astimezone(FUSO_BRASILIA)
    return momento.date()


def vigente(encarte: Encarte, hoje: date | None = None) -> bool:
    hoje = hoje or agora().date()
    return encarte.validade_fim is None or encarte.validade_fim >= hoje
