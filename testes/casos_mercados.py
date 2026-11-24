"""Testes do C12 (mercados próximos), chamados pelo testar.py. A Overpass é simulada."""
import asyncio
from datetime import timedelta
from urllib.parse import parse_qs

import httpx

import atendimento
import banco
import cesta
import mercados_proximos as mp

PRACA_CIVICA = (-16.67993, -49.25504)   # ponto público de Goiânia (não é a casa de ninguém)


def _elementos():
    return {"elements": [
        {"type": "node", "lat": -16.6746, "lon": -49.2476, "tags": {"name": "Mercadinho Pratiko", "shop": "supermarket"}},
        {"type": "way", "center": {"lat": -16.6890, "lon": -49.2600},
         "tags": {"name": "Atacadão", "brand": "Atacadão", "shop": "wholesale"}},
        {"type": "node", "lat": -16.68901, "lon": -49.26001, "tags": {"name": "Atacadão", "shop": "wholesale"}},
        {"type": "node", "lat": -16.6700, "lon": -49.2500, "tags": {"shop": "supermarket"}},   # sem nome
        {"type": "way", "center": {"lat": -16.7000, "lon": -49.2700},
         "tags": {"name": "Atacadão Dia a Dia", "shop": "wholesale"}},
        *[{"type": "node", "lat": -16.66 - i / 1000, "lon": -49.24, "tags": {"name": f"Mercado {i}"}} for i in range(8)],
    ]}


class OverpassFalsa:
    def __init__(self, respostas):
        self.respostas, self.pedidos = list(respostas), []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        item = self.respostas.pop(0) if self.respostas else 200
        if item == 200:
            return httpx.Response(200, json=_elementos())
        return httpx.Response(item, text="lotado")


def _instalar(respostas) -> OverpassFalsa:
    falsa = OverpassFalsa(respostas)
    mp.transporte, mp._cache = httpx.MockTransport(falsa), {}
    esperas = []

    async def dormir(segundos):
        esperas.append(segundos)
    mp.dormir = dormir
    falsa.esperas = esperas
    return falsa


def rodar(ok, secao, novo_banco, criar_usuario, plano_valido) -> None:
    secao("C12: mercados próximos (Overpass simulada)")
    os_padrao = mp.transporte, mp.dormir
    try:
        _rodar(ok, novo_banco, criar_usuario, plano_valido)
    finally:
        mp.transporte, mp.dormir, mp._cache = os_padrao[0], os_padrao[1], {}


def _rodar(ok, novo_banco, criar_usuario, plano_valido) -> None:
    ok(mp.rede_do_nome("Atacadão Dia a Dia") == "Dia a Dia" and mp.rede_do_nome("ATACADÃO") == "Atacadão"
       and mp.rede_do_nome("Assaí Atacadista") == "Assaí" and mp.rede_do_nome("Mercadinho Pratiko") is None,
       "reconhece a rede pelo nome ('Atacadão Dia a Dia' é Dia a Dia, não Atacadão)")
    ok(abs(mp.distancia_km(-16.68, -49.255, -16.69, -49.255) - 1.11) < 0.01, "distância em km (haversine)")

    falsa = _instalar([200])
    achados = asyncio.run(mp.buscar(*PRACA_CIVICA))
    corpo = parse_qs(falsa.pedidos[0].content.decode())["data"][0]
    ok(len(achados) == 8 and achados == sorted(achados, key=lambda m: m.distancia_km),
       "até 8 mercados, do mais perto ao mais longe")
    nomes = [m.nome for m in achados]
    ok(nomes.count("Atacadão") == 1 and all(n for n in nomes), "sem repetir o mesmo mercado e sem os sem nome")
    ok("around:3000,-16.68,-49.255" in corpo and "-16.67993" not in corpo and '"shop"="wholesale"' in corpo,
       "consulta no raio de 3 km, com a localização arredondada (~100 m), incluindo atacarejos")
    ok(falsa.pedidos[0].headers["user-agent"] == mp.USER_AGENT and "RendeBot" in mp.USER_AGENT,
       "User-Agent genérico do app")
    ok(achados[0].link.startswith("https://www.google.com/maps/search/?api=1&query="), "link do Google Maps")
    asyncio.run(mp.buscar(*PRACA_CIVICA))
    ok(len(falsa.pedidos) == 1, "mesmo lugar de novo: usa o resultado guardado (não consulta a Overpass outra vez)")

    falsa = _instalar([502, 200])
    asyncio.run(mp.buscar(*PRACA_CIVICA))
    ok(len(falsa.pedidos) == 2 and falsa.esperas == [mp.ESPERA_NOVA_TENTATIVA],
       "servidor lotado (502): espera um pouco e tenta de novo")
    falsa = _instalar([502, 502, 200])
    asyncio.run(mp.buscar(*PRACA_CIVICA))
    ok(len(falsa.pedidos) == 3 and "kumi" in str(falsa.pedidos[2].url), "ainda lotado: tenta o espelho público")

    # no bot
    novo_banco()
    criar_usuario("m1")
    validade = (banco.agora().date() + timedelta(days=3)).isoformat()
    banco.adicionar_promocao(mercado="Atacadão", produto="arroz", tamanho="5 kg", preco=20.99, validade=validade,
                             cidade="Goiânia", origem="site")
    s = asyncio.run(atendimento.acao("m1", "lc:ver"))
    ok(s[0].tipo == "pedir_localizacao", "sem localização: o bot mostra o botão '📍 Enviar minha localização'")
    _instalar([200])
    s = asyncio.run(atendimento.receber_localizacao("m1", *PRACA_CIVICA))
    perfil = banco.usuario("m1")
    tela = s[-1].texto
    ok(perfil["latitude"] == PRACA_CIVICA[0] and "Mercados perto de você" in tela and "*Atacadão* · 1," in tela
       and "🔥 *tem promoções*" in tela.split("Atacadão*")[1].split("\n")[0] and "google.com/maps" in tela,
       "localização: guarda e mostra os mercados com distância, link e 🔥 nos que têm promoção")
    ok("tem promoções" not in tela.split("Mercadinho Pratiko*")[1].split("\n")[0],
       "mercado sem promoção cadastrada não leva o 🔥")

    plano = plano_valido()
    plano["cesta"], plano["orcamento"] = cesta.calcular(plano, {}), 200.0
    banco.salvar_plano("m1", plano)
    s = asyncio.run(atendimento.acao("m1", "oc:ver"))
    ok("*Atacadão*: " in s[0].texto and " km" in s[0].texto.split("*Atacadão*:")[1].split("\n")[0]
       and "Mande sua localização" not in s[0].texto, "'Onde comprar' mostra a distância da loja mais perto")

    _instalar([502, 502, 502, 502])
    mp._cache = {}
    s = asyncio.run(atendimento.acao("m1", "lc:ver"))
    ok("ocupado" in s[0].texto and s[0].botoes[0][0].acao == "lc:ver", "Overpass fora do ar: avisa e oferece tentar de novo")
    s = asyncio.run(atendimento.acao("m1", "oc:ver"))
    ok("Onde comprar" in s[0].texto, "'Onde comprar' funciona mesmo sem a Overpass (só sem distância)")
