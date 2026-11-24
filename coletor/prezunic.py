"""Prezunic (grupo Cencosud; assumiu as lojas do Bretas em Goiânia).

Onde ficam as ofertas: https://www.prezunic.com.br/encartes, com um seletor RJ/GO.
A página já traz, num JSON embutido, todos os encartes com título, estado, início,
fim e o link do PDF. Pegamos só os de GO, ativos e ainda válidos.
robots.txt: /encartes liberada; os PDFs ficam em /arquivos (liberado) ou na vtexassets (liberado).
"""
import json
import re

from coletor.encarte import Encarte, data_iso, vigente

REDE, MERCADO = "prezunic", "Prezunic"
PAGINA = "https://www.prezunic.com.br/encartes"
ESTADO = "GO"


def ler_pagina(html: str) -> list[Encarte]:
    """Acha os objetos {"title": ..., "pdfUrl": ..., "state": ...} do JSON embutido na página."""
    texto = html.replace("\\u002F", "/")
    decodificador = json.JSONDecoder()
    vistos: dict[str, Encarte] = {}
    for inicio in (m.start() for m in re.finditer(r'\{"title":', texto)):
        try:
            obj, _ = decodificador.raw_decode(texto, inicio)
        except ValueError:
            continue
        if not isinstance(obj, dict) or obj.get("state") != ESTADO or not obj.get("pdfUrl"):
            continue
        if obj.get("active") is False:
            continue
        url = str(obj["pdfUrl"]).strip()
        encarte = Encarte(rede=REDE, mercado=MERCADO, titulo=str(obj.get("title") or "Encarte").strip(),
                          url=url, fonte_url=PAGINA, validade_inicio=data_iso(obj.get("startAt")),
                          validade_fim=data_iso(obj.get("endAt")),
                          lojas=str(obj.get("validityText") or "").strip() or None)
        if vigente(encarte):
            vistos.setdefault(url, encarte)
    return list(vistos.values())


async def coletar(nav) -> list[Encarte]:
    return ler_pagina(await nav.texto(PAGINA))
