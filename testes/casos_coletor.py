"""Testes do C13 (coletor de promoções), chamados pelo testar.py. Sem internet: os sites são
simulados com httpx.MockTransport e o Gemini é a IA falsa do testar.py."""
import asyncio
import hashlib
import json
from datetime import timedelta

import httpx

import banco
import coletor
import promocoes
import roteador
from coletor import atacadao, diaadia, prezunic
from coletor.web import Navegador, Proibido, USER_AGENT


def _datas():
    hoje = banco.agora().date()
    return hoje, (hoje + timedelta(days=3)).isoformat(), (hoje - timedelta(days=3)).isoformat()


def pagina_prezunic() -> str:
    hoje, futuro, passado = _datas()
    objs = [
        {"title": "Ofertas da semana", "validityText": "Válidas até domingo", "active": True, "state": "GO",
         "startAt": f"{hoje}T03:00:00.000Z", "endAt": f"{futuro}T02:59:00.000Z",
         "pdfUrl": "https:\\u002F\\u002Fprezunic.vteximg.com.br\\u002Farquivos\\u002Fgo1.pdf"},
        {"title": "Ofertas da semana", "active": True, "state": "GO", "startAt": f"{hoje}T03:00:00.000Z",
         "endAt": f"{futuro}T02:59:00.000Z", "pdfUrl": "https:\\u002F\\u002Fprezunic.vteximg.com.br\\u002Farquivos\\u002Fgo1.pdf"},
        {"title": "Feirinha RJ", "active": True, "state": "RJ", "endAt": f"{futuro}T02:59:00.000Z",
         "pdfUrl": "https:\\u002F\\u002Fprezunic.vteximg.com.br\\u002Farquivos\\u002Frj.pdf"},
        {"title": "Carnaval", "active": True, "state": "GO", "endAt": f"{passado}T02:59:00.000Z",
         "pdfUrl": "https:\\u002F\\u002Fprezunic.vteximg.com.br\\u002Farquivos\\u002Fvelho.pdf"},
        {"title": "Inativo", "active": False, "state": "GO", "endAt": f"{futuro}T02:59:00.000Z",
         "pdfUrl": "https:\\u002F\\u002Fprezunic.vteximg.com.br\\u002Farquivos\\u002Finativo.pdf"},
    ]
    return "<html><script>window.__STATE__ = {\"a\": [" + ",".join(
        json.dumps(o, ensure_ascii=False).replace("\\\\u002F", "\\u002F") for o in objs) + "]}</script></html>"


def pagina_atacadao() -> str:
    _, futuro, passado = _datas()
    flyers = [{"id": "f1", "name": "Super Ofertas", "exclude": False, "validity": {"initial": f"{passado}T00:00:00Z",
               "final": f"{futuro}T00:00:00Z"}, "urlFinalDocument": "https://apigw.cloud.carrefour.com.br/flyer?id=f1"},
              {"id": "f2", "name": "Velho", "exclude": False, "validity": {"final": f"{passado}T00:00:00Z"},
               "urlFinalDocument": "https://apigw.cloud.carrefour.com.br/flyer?id=f2"},
              {"id": "f3", "name": "Escondido", "exclude": True, "validity": {"final": f"{futuro}T00:00:00Z"},
               "urlFinalDocument": "https://apigw.cloud.carrefour.com.br/flyer?id=f3"}]
    dados = {"props": {"pageProps": {"storeInfo": {"name": "Goiânia Av. Independência", "flyers": flyers}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(dados)}</script></html>'


PAGINA_DIAADIA = ('<select id="uf"><option value="go">Goiás</option></select>'
                  '<select id="campanha" name="campanha"><option value="" disabled>Escolha</option>'
                  '<option value="11">Dia da Limpeza</option><option value="12">Festival de Bazar</option></select>')


def campanha_diaadia(i: int, nome: str, pdf: str) -> dict:
    return {"id": i, "link": f"https://ofertas.diaadiaatacadista.com.br/ofertas/c{i}/",
            "title": {"rendered": nome}, "acf": {"nome_da_campanha": nome, "tipo_de_oferta": "Tabloide",
                                                 "tabloide": [{"pdf_do_tabloide": pdf, "paginas_do_tabloide": []}],
                                                 "segmentacao_go": ["Aparecida de Goiânia", "Goiânia Balneário"]}}


class SitesFalsos:
    """Responde como os sites das redes. `quebrado` = redes cujo site está fora do ar."""

    def __init__(self, quebrado: set[str] | None = None, robots_prezunic: str = "User-agent: *\nAllow: /\n"):
        self.quebrado = quebrado or set()
        self.robots_prezunic = robots_prezunic
        self.pedidos: list[httpx.Request] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        host, caminho = pedido.url.host, pedido.url.path
        if caminho == "/robots.txt":
            if host == "www.prezunic.com.br":
                return httpx.Response(200, text=self.robots_prezunic)
            if host == "apigw.cloud.carrefour.com.br":
                return httpx.Response(404)
            return httpx.Response(200, text="User-agent: *\nDisallow: /checkout\n")
        if host == "www.atacadao.com.br":
            if "atacadao" in self.quebrado:
                return httpx.Response(500, text="erro")
            return httpx.Response(200, text=pagina_atacadao(), headers={"content-type": "text/html"})
        if host == "www.prezunic.com.br":
            return httpx.Response(200, text=pagina_prezunic(), headers={"content-type": "text/html"})
        if host == "ofertas.diaadiaatacadista.com.br":
            if caminho.startswith("/ofertas/go/"):
                return httpx.Response(200, text=PAGINA_DIAADIA, headers={"content-type": "text/html"})
            if caminho.endswith("/ofertas/11"):
                return httpx.Response(200, json=campanha_diaadia(11, "Dia da Limpeza",
                                                                 "https://ofertas.diaadiaatacadista.com.br/up/limpeza.pdf"))
            if caminho.endswith("/ofertas/12"):
                return httpx.Response(200, json=campanha_diaadia(12, "Festival de Bazar",
                                                                 "https://ofertas.diaadiaatacadista.com.br/up/bazar.pdf"))
            if caminho.endswith(".pdf"):
                return httpx.Response(200, content=b"%PDF-1.4 tabloide limpeza", headers={"content-type": "application/pdf"})
        if host == "prezunic.vteximg.com.br":
            return httpx.Response(200, content=b"%PDF-1.4 encarte prezunic go1", headers={"content-type": "application/pdf"})
        if host == "apigw.cloud.carrefour.com.br":
            return httpx.Response(200, content=b"%PDF-1.4 folheto atacadao f1",
                                  headers={"content-type": "application/pdf"})
        return httpx.Response(404)


class Relogio:
    """Tempo falso: dormir avança o relógio na hora (os testes não esperam 5 s de verdade)."""

    def __init__(self):
        self.agora, self.esperas = 1000.0, []

    def __call__(self) -> float:
        return self.agora

    async def dormir(self, segundos: float) -> None:
        self.esperas.append(segundos)
        self.agora += segundos


def navegador(sites: SitesFalsos, relogio: Relogio | None = None) -> Navegador:
    relogio = relogio or Relogio()
    return Navegador(transporte=httpx.MockTransport(sites), dormir=relogio.dormir, relogio=relogio)


def oferta_json(*ofertas, fim="") -> str:
    return json.dumps({"validade_inicio": "", "validade_fim": fim, "ofertas": list(ofertas)}, ensure_ascii=False)


def rodar(ok, secao, novo_banco, instalar_ias) -> None:
    secao("C13: coletor de promoções (sites e Gemini simulados)")
    hoje, futuro, _ = _datas()

    # normalização
    ok(promocoes.tamanho("ARROZ TIO JOÃO 5KG") == "5 kg" and promocoes.tamanho("leite 1L") == "1 L"
       and promocoes.tamanho("óleo 900ML") == "900 ml" and promocoes.tamanho("ovos c/ 30 un") == "30 un",
       "normaliza tamanhos: 5KG -> 5 kg, 1L -> 1 L, 900ML -> 900 ml, 30 un")
    ok(promocoes.marca("TIO JOÃO") == "Tio João" and promocoes.produto("ARROZ TIO JOÃO 5KG", "Tio João") == "arroz"
       and promocoes.produto("Feijão Carioca") == "feijão carioca",
       "normaliza nomes: 'ARROZ TIO JOÃO 5KG' -> arroz / Tio João / 5 kg")

    # leitura das páginas de cada rede
    encs = prezunic.ler_pagina(pagina_prezunic())
    ok(len(encs) == 1 and encs[0].url.endswith("/arquivos/go1.pdf") and encs[0].validade_fim.isoformat() < futuro,
       "Prezunic: só encartes de GO, ativos e válidos, sem repetir (fim em UTC vira o dia de Brasília)")
    encs = atacadao.ler_loja(pagina_atacadao(), "https://www.atacadao.com.br/loja/x", "x")
    ok([e.titulo for e in encs] == ["Super Ofertas"] and encs[0].validade_fim.isoformat() == futuro
       and encs[0].lojas == "Goiânia Av. Independência", "Atacadão: folhetos da loja, sem os vencidos e os escondidos")
    try:
        atacadao.ler_loja("<html>site novo</html>", "u", "x")
        mudou = False
    except ValueError:
        mudou = True
    ok(mudou, "Atacadão: se a página mudar, o coletor percebe (erro claro em vez de 0 ofertas calado)")
    encs = diaadia.encartes_da_campanha(campanha_diaadia(11, "Dia da Limpeza", "https://x/limpeza.pdf"), "loja")
    ok(diaadia.campanhas_da_pagina(PAGINA_DIAADIA) == ["11", "12"] and encs[0].url == "https://x/limpeza.pdf"
       and "Goiânia Balneário" in encs[0].lojas and "Aparecida" not in encs[0].lojas,
       "Dia a Dia: campanhas da loja e o PDF de cada tabloide pela API do site")

    # boa conduta
    sites, relogio = SitesFalsos(robots_prezunic="User-agent: *\nDisallow: /encartes\n"), Relogio()

    async def _proibido():
        async with navegador(sites, relogio) as nav:
            try:
                await nav.texto(prezunic.PAGINA)
                return False
            except Proibido:
                return True
    ok(asyncio.run(_proibido()) and not any(p.url.path == "/encartes" for p in sites.pedidos),
       "robots.txt proibindo a página: o coletor nem pede a página")

    sites, relogio = SitesFalsos(), Relogio()

    async def _ritmo():
        async with navegador(sites, relogio) as nav:
            await nav.texto("https://www.atacadao.com.br/loja/a")
            await nav.texto("https://www.atacadao.com.br/loja/b")
            await nav.texto("https://www.prezunic.com.br/encartes")
    asyncio.run(_ritmo())
    ok(sites.pedidos and all(p.headers["user-agent"] == USER_AGENT for p in sites.pedidos)
       and "RendeColetor" in USER_AGENT and "@" not in USER_AGENT,
       "User-Agent genérico do app em todas as requisições (sem dados pessoais)")
    ok(len(relogio.esperas) == 3 and all(abs(e - 5.0) < 0.01 for e in relogio.esperas),
       "no máximo 1 requisição a cada 5 s por site (o robots.txt também conta; sites diferentes não esperam)")

    # coleta completa: uma rede quebrada, as outras seguem
    novo_banco()
    gemini, claude = instalar_ias()
    ofertas_prezunic = oferta_json({"produto": "ARROZ TIO JOÃO 5KG", "marca": "TIO JOÃO", "tamanho": "5KG", "preco": 21.9,
                                    "preco_anterior": 27.9},
                                   {"produto": "feijão carioca", "tamanho": "1 kg", "preco": 6.49,
                                    "condicao": "no cartão da loja"},
                                   {"produto": "café", "preco": 0})
    ofertas_diaadia = oferta_json({"produto": "detergente", "marca": "Ypê", "tamanho": "500 ml", "preco": 1.99}, fim=futuro)
    gemini.fila = [ofertas_prezunic, ofertas_diaadia]
    sites = SitesFalsos(quebrado={"atacadao"})
    resultados = asyncio.run(coletor.coletar(nav=navegador(sites)))
    por_rede = {r.rede: r for r in resultados}
    ok(por_rede["atacadao"].falha and por_rede["prezunic"].ofertas_novas == 2 and por_rede["diaadia"].ofertas_novas == 1,
       "uma rede quebrada (Atacadão fora do ar) não derruba as outras")
    ok(any("Atacadão" in f for f in coletor.falhas(resultados)), "o resultado diz qual rede falhou (o bot avisa o admin)")
    arroz = banco.promocoes_validas(mercado="Prezunic", produto="arroz")[0]
    ok(arroz["origem"] == "site" and arroz["marca"] == "Tio João" and arroz["tamanho"] == "5 kg"
       and arroz["preco_anterior"] == 27.9 and arroz["fonte_url"] == prezunic.PAGINA and arroz["cidade"] == "Goiânia",
       "oferta do site salva normalizada, com origem 'site' e o link da fonte")
    ok(len(gemini.chamadas) == 2 and not claude.chamadas
       and gemini.chamadas[0]["mensagens"][0]["anexo"]["mime_type"] == "application/pdf"
       and gemini.chamadas[0]["esquema"] is not None,
       "cada encarte vai para o Gemini como PDF, com JSON estruturado (nunca para o Claude)")
    ok(not any(p.url.path.endswith("bazar.pdf") for p in sites.pedidos),
       "encarte que não interessa ao cardápio (bazar) nem é baixado")
    detergente = banco.promocoes_validas(mercado="Dia a Dia")[0]
    ok(detergente["validade"] == futuro, "sem validade no site, vale a data lida no tabloide")
    texto = coletor.texto_resultado(resultados)
    ok("Prezunic*: 2 ofertas novas" in texto and "arroz Tio João 5 kg" in texto and "❌ *Atacadão*" in texto,
       "/coletar mostra o resultado por rede, com exemplos e erros")

    # de novo: nada é reprocessado
    gemini.chamadas.clear()
    gemini.fila = [oferta_json({"produto": "leite integral", "marca": "Italac", "tamanho": "1 L", "preco": 4.79,
                                "condicao": "a partir de 12 un R$ 4,59"})]
    resultados = asyncio.run(coletor.coletar(nav=navegador(SitesFalsos())))
    por_rede = {r.rede: r for r in resultados}
    ok(por_rede["prezunic"].repetidos == 1 and por_rede["prezunic"].ofertas_novas == 0
       and por_rede["atacadao"].lidos == 1 and len(gemini.chamadas) == 1,
       "encarte já lido não vai de novo para a IA (só o do Atacadão, que voltou ao ar)")

    # mesmo arquivo publicado em outro endereço: o hash pega
    hash_go1 = hashlib.sha256(b"%PDF-1.4 encarte prezunic go1").hexdigest()
    ok(banco.encarte_lido(hash_arquivo=hash_go1), "o hash de cada encarte lido fica guardado")
    banco.registrar_encarte(hash_arquivo=hash_go1, rede="prezunic", url="https://outro/endereco.pdf",
                            titulo="cópia", ofertas=0)
    ok(banco.encarte_lido(url="https://outro/endereco.pdf"), "mesmo arquivo em outro endereço também conta como lido")

    # erro da IA num encarte: não marca como lido (tenta de novo amanhã)
    novo_banco()
    gemini, _ = instalar_ias()
    from ia_comum import ErroIA
    gemini.fila = [ErroIA("sem cota", cota=True), ErroIA("sem cota", cota=True), ofertas_diaadia]
    resultados = asyncio.run(coletor.coletar(["prezunic", "diaadia"], nav=navegador(SitesFalsos())))
    por_rede = {r.rede: r for r in resultados}
    ok(por_rede["prezunic"].erros and not banco.encarte_lido(url="https://prezunic.vteximg.com.br/arquivos/go1.pdf")
       and por_rede["diaadia"].ofertas_novas == 1,
       "Gemini sem cota num encarte: ele fica para a próxima coleta e as outras redes seguem")
    ok([n.provedor for n in roteador.escada("coletor")] == ["gemini", "gemini"], "o coletor usa só o Gemini")

    # o ano errado lido pela IA é corrigido para um encarte que está no ar
    ok(coletor._data_lida(f"{hoje.year - 1}-{futuro[5:]}", hoje).isoformat() == futuro,
       "data lida com o ano errado ('24/11' -> ano passado) é corrigida")
