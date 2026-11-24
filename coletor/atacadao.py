"""Atacadão (grupo Carrefour).

Onde ficam as ofertas: a página de cada loja (ex.: /loja/goiania-avenida-independencia)
traz, no JSON da página (__NEXT_DATA__), os folhetos daquela loja com nome, validade
e o link do PDF (servido por apigw.cloud.carrefour.com.br, que não tem robots.txt).
robots.txt do atacadao.com.br: /loja/ liberada (proíbe só carrinho, busca, conta etc.).
Termos de uso: não proíbem coleta automática; dizem que o conteúdo é do Atacadão
("vedado o uso não autorizado"). Por isso guardamos só produto e preço, com o link da
fonte, e nunca republicamos o folheto.
Atacado: o folheto costuma ter "preço varejo" e "preço atacado a partir de X unidades";
a IA guarda o preço de 1 unidade e põe o de atacado na condição.
"""
import json
import os
import re

from coletor.encarte import Encarte, data_iso, vigente

REDE, MERCADO = "atacadao", "Atacadão"
SITE = "https://www.atacadao.com.br"
LOJAS_PADRAO = "goiania-avenida-independencia"


def lojas() -> list[str]:
    return [l.strip() for l in (os.getenv("COLETOR_ATACADAO_LOJAS") or LOJAS_PADRAO).split(",") if l.strip()]


def ler_loja(html: str, pagina: str, loja: str) -> list[Encarte]:
    achado = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not achado:
        raise ValueError("a página da loja mudou: não achei o __NEXT_DATA__")
    dados = json.loads(achado.group(1))
    info = (dados.get("props", {}).get("pageProps", {}).get("storeInfo") or {})
    if "flyers" not in info:
        raise ValueError("a página da loja mudou: não achei a lista de folhetos")
    encartes = []
    for f in info.get("flyers") or []:
        if f.get("exclude") or not f.get("urlFinalDocument"):
            continue
        validade = f.get("validity") or {}
        encarte = Encarte(rede=REDE, mercado=MERCADO, titulo=str(f.get("name") or "Folheto").strip(),
                          url=str(f["urlFinalDocument"]).strip(), fonte_url=pagina,
                          validade_inicio=data_iso((validade.get("initial") or "")[:10]),
                          validade_fim=data_iso((validade.get("final") or "")[:10]),
                          lojas=info.get("name") or loja)
        if vigente(encarte):
            encartes.append(encarte)
    return encartes


async def coletar(nav) -> list[Encarte]:
    vistos: dict[str, Encarte] = {}
    for loja in lojas():
        pagina = f"{SITE}/loja/{loja}"
        for encarte in ler_loja(await nav.texto(pagina), pagina, loja):
            vistos.setdefault(encarte.url, encarte)
    return list(vistos.values())
