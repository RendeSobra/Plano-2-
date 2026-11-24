"""C12: supermercados perto da pessoa, pela API Overpass do OpenStreetMap (gratuita).

- Raio padrão de 3 km (RAIO_MERCADOS_M no .env), até 8 mercados, do mais perto ao mais longe,
  com link do Google Maps.
- Boa conduta com a Overpass: User-Agent do app, uma consulta por vez, timeout, e o
  resultado fica guardado por 24 h para o mesmo lugar (não repete a consulta).
- Privacidade: a localização vai arredondada (~100 m) e sem nenhum dado da pessoa.
"""
import asyncio
import math
import os
import time
from dataclasses import dataclass

import httpx

import restricoes

# Servidor principal e um espelho público (o espelho só é usado se o principal responder erro na hora)
OVERPASS_URLS = "https://overpass-api.de/api/interpreter,https://overpass.kumi.systems/api/interpreter"
USER_AGENT = "RendeBot/1.0 (assistente de cardapio e mercado)"
TEMPO = 65.0   # a Overpass costuma ter fila: em 24/11 uma consulta pequena levou 39 s
MAX_MERCADOS = 8
CACHE_SEGUNDOS = 24 * 3600
# Redes conhecidas (do nome mais específico para o mais geral): "Atacadão Dia a Dia" é Dia a Dia
REDES = [("dia a dia", "Dia a Dia"), ("assai", "Assaí"), ("atacadao", "Atacadão"), ("prezunic", "Prezunic"),
         ("bretas", "Bretas"), ("tatico", "Tático"), ("barao", "Barão"), ("carrefour", "Carrefour"),
         ("pao de acucar", "Pão de Açúcar"), ("sam s club", "Sam's Club"), ("sams club", "Sam's Club"),
         ("cerrado", "Cerrado"), ("super vi", "Super Vi")]

ESPERA_NOVA_TENTATIVA = 3.0   # segundos antes de repetir quando o servidor está lotado

_cache: dict[tuple, tuple[float, list]] = {}
_trava = asyncio.Lock()
transporte: httpx.AsyncBaseTransport | None = None   # os testes trocam por um simulado
dormir = asyncio.sleep                                # os testes trocam para não esperar


class ErroMapa(Exception):
    """A Overpass não respondeu (fora do ar, ocupada ou demorou)."""


@dataclass
class MercadoProximo:
    nome: str
    rede: str | None          # rede conhecida ("Atacadão"), se o nome bater
    distancia_km: float
    latitude: float
    longitude: float

    @property
    def link(self) -> str:
        return f"https://www.google.com/maps/search/?api=1&query={self.latitude:.6f},{self.longitude:.6f}"


def raio_m() -> int:
    return int(os.getenv("RAIO_MERCADOS_M") or 3000)


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em linha reta (fórmula de haversine)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def rede_do_nome(*nomes: str | None) -> str | None:
    alvo = " ".join(restricoes.normalizar(n or "") for n in nomes)
    for chave, rede in REDES:
        if f" {chave} " in f" {alvo} ":
            return rede
    return None


def consulta(lat: float, lon: float, raio: int) -> str:
    """Supermercados e atacarejos (ponto ou prédio) no raio. Sem expressão regular: mais leve."""
    perto = f"(around:{raio},{lat},{lon})"
    partes = "".join(f'{tipo}["shop"="{loja}"]{perto};' for loja in ("supermarket", "wholesale")
                     for tipo in ("node", "way"))
    return f"[out:json][timeout:60];({partes});out center tags;"


def ler_resposta(dados: dict, lat: float, lon: float) -> list[MercadoProximo]:
    mercados, vistos = [], set()
    for el in dados.get("elements") or []:
        tags = el.get("tags") or {}
        mlat = el.get("lat", (el.get("center") or {}).get("lat"))
        mlon = el.get("lon", (el.get("center") or {}).get("lon"))
        if mlat is None or mlon is None:
            continue
        nome = (tags.get("name") or tags.get("brand") or "").strip()
        if not nome:
            continue  # sem nome não ajuda a pessoa a achar
        chave = (restricoes.normalizar(nome), round(mlat, 3), round(mlon, 3))
        if chave in vistos:  # o mesmo mercado mapeado como ponto e como prédio
            continue
        vistos.add(chave)
        mercados.append(MercadoProximo(nome=nome, rede=rede_do_nome(nome, tags.get("brand")),
                                       distancia_km=round(distancia_km(lat, lon, mlat, mlon), 2),
                                       latitude=mlat, longitude=mlon))
    mercados.sort(key=lambda m: m.distancia_km)
    return mercados  # todos: o "Onde comprar" precisa da loja de cada rede, mesmo fora das 8 mais perto


def escolher(mercados: list[MercadoProximo], redes_com_promo: set[str],
             maximo: int = MAX_MERCADOS) -> list[MercadoProximo]:
    """Os que vão para a tela: a loja mais perto de cada rede com promoção (mesmo que não esteja
    entre as 8 mais perto) e o resto pelos mais perto, até `maximo`, do mais perto ao mais longe."""
    escolhidos, redes = [], set()
    for m in mercados:  # já vêm do mais perto ao mais longe
        rede = restricoes.normalizar(m.rede) if m.rede else None
        if rede in redes_com_promo and rede not in redes:
            redes.add(rede)
            escolhidos.append(m)
    escolhidos = escolhidos[:maximo]
    ja = {id(m) for m in escolhidos}
    for m in mercados:
        if len(escolhidos) >= maximo:
            break
        if id(m) not in ja:
            escolhidos.append(m)
    return sorted(escolhidos, key=lambda m: m.distancia_km)


async def buscar(latitude: float, longitude: float, raio: int | None = None) -> list[MercadoProximo]:
    """Todos os mercados no raio, do mais perto ao mais longe (a tela usa `escolher`).
    Levanta ErroMapa se a Overpass falhar."""
    raio = raio or raio_m()
    lat, lon = round(latitude, 3), round(longitude, 3)  # ~100 m: não manda o ponto exato da pessoa
    chave = (lat, lon, raio)
    guardado = _cache.get(chave)
    if guardado and time.monotonic() - guardado[0] < CACHE_SEGUNDOS:
        return guardado[1]
    urls = [u.strip() for u in (os.getenv("OVERPASS_URL") or OVERPASS_URLS).split(",") if u.strip()]
    async with _trava:  # uma consulta por vez (a Overpass limita consultas simultâneas)
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=TEMPO,
                                     transport=transporte) as cliente:
            tentativas = [(url, espera) for url in urls for espera in (0, ESPERA_NOVA_TENTATIVA)]
            for i, (url, espera) in enumerate(tentativas):
                if espera:  # o servidor pediu calma (lotado): espera um pouco antes de tentar de novo
                    await dormir(espera)
                try:
                    resposta = await cliente.post(url, data={"data": consulta(lat, lon, raio)})
                except httpx.TimeoutException as erro:  # já esperamos muito: não emenda outra espera
                    raise ErroMapa("Overpass: demorou demais") from erro
                except httpx.HTTPError as erro:
                    if i == len(tentativas) - 1:
                        raise ErroMapa(f"Overpass: {type(erro).__name__}") from erro
                    continue
                if resposta.status_code == 200:
                    break
                if i == len(tentativas) - 1:  # 429 (muitas consultas), 502/504 (lotado)...
                    raise ErroMapa(f"Overpass respondeu {resposta.status_code}")
        try:
            mercados = ler_resposta(resposta.json(), latitude, longitude)
        except ValueError as erro:
            raise ErroMapa("Overpass mandou uma resposta inválida") from erro
    _cache[chave] = (time.monotonic(), mercados)
    return mercados


def distancias_por_rede(mercados: list[MercadoProximo]) -> dict[str, float]:
    """Rede (nome normalizado, igual ao das promoções) -> distância da loja mais perto."""
    saida: dict[str, float] = {}
    for m in mercados:
        if m.rede:
            chave = restricoes.normalizar(m.rede)
            saida[chave] = min(saida.get(chave, m.distancia_km), m.distancia_km)
    return saida
