"""Atacadão Dia a Dia.

Onde ficam as ofertas: https://ofertas.diaadiaatacadista.com.br/ofertas/go/<loja> lista
as campanhas da loja; cada campanha está na API pública do WordPress do site
(/wp-json/wp/v2/ofertas/<id>), com o PDF do tabloide e as lojas onde vale.
Lojas em Goiânia: Setor Novo Horizonte e Balneário (as campanhas costumam ser as mesmas).
robots.txt: liberado para todos (bloqueia só robôs de treino de IA, como GPTBot e
ClaudeBot; o coletor não treina IA e se identifica como RendeColetor).
O site não informa a validade na API: a IA lê no próprio tabloide.
"""
import html as html_lib
import os
import re

from coletor.encarte import Encarte
from restricoes import normalizar

REDE, MERCADO = "diaadia", "Dia a Dia"
SITE = "https://ofertas.diaadiaatacadista.com.br"
LOJAS_PADRAO = "goiania-setor-novo-horizonte,goiania-balneario"
MAX_CAMPANHAS = 12


def lojas() -> list[str]:
    return [l.strip() for l in (os.getenv("COLETOR_DIAADIA_LOJAS") or LOJAS_PADRAO).split(",") if l.strip()]


def campanhas_da_pagina(html: str) -> list[str]:
    """Os ids numéricos do seletor de campanhas (<select id="campanha">)."""
    seletor = re.search(r'<select[^>]*id="campanha"[^>]*>(.*?)</select>', html, re.S)
    if not seletor:
        raise ValueError("a página da loja mudou: não achei o seletor de campanhas")
    return re.findall(r'<option value="(\d+)"', seletor.group(1))


def encartes_da_campanha(dados: dict, loja: str) -> list[Encarte]:
    acf = dados.get("acf") or {}
    titulo = html_lib.unescape(acf.get("nome_da_campanha") or (dados.get("title") or {}).get("rendered") or "Tabloide")
    fonte = dados.get("link") or SITE
    # só as lojas da cidade de Goiânia ("Aparecida de Goiânia" é outra cidade)
    lojas_go = [l for l in (acf.get("segmentacao_go") or []) if normalizar(l).startswith("goiania")]
    encartes = []
    for tab in acf.get("tabloide") or []:
        pdf = (tab or {}).get("pdf_do_tabloide")
        paginas = [p for p in ((tab or {}).get("paginas_do_tabloide") or []) if p][:6]
        alvos = [pdf] if pdf else paginas  # o PDF tem tudo; sem PDF, as páginas em imagem
        for url in alvos:
            encartes.append(Encarte(rede=REDE, mercado=MERCADO, titulo=titulo.strip(), url=url, fonte_url=fonte,
                                    lojas=", ".join(lojas_go) or loja))
    return encartes


async def coletar(nav) -> list[Encarte]:
    ids: list[str] = []
    for loja in lojas():
        for i in campanhas_da_pagina(await nav.texto(f"{SITE}/ofertas/go/{loja}")):
            if i not in ids:
                ids.append(i)
    vistos: dict[str, Encarte] = {}
    for i in ids[:MAX_CAMPANHAS]:
        dados = await nav.json(f"{SITE}/wp-json/wp/v2/ofertas/{i}?_fields=id,link,acf,title,slug")
        for encarte in encartes_da_campanha(dados, lojas()[0]):
            vistos.setdefault(encarte.url, encarte)
    return list(vistos.values())
