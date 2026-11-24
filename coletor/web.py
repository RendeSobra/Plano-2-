"""Acesso aos sites das redes com as regras de boa conduta do C13:

- respeita o robots.txt (página proibida = a rede é pulada e fica no log);
- no máximo 1 requisição a cada 5 segundos por site (o robots.txt também conta);
- timeout em toda requisição e User-Agent genérico do app (sem dados pessoais);
- baixa só o que foi pedido (encarte ou página de ofertas), com limite de tamanho,
  e devolve os bytes na memória: nada é gravado no disco.
"""
import asyncio
import json
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger("rende.coletor")

USER_AGENT = "Mozilla/5.0 (compatible; RendeColetor/1.0; assistente de cardapio e mercado)"
NOME_ROBO = "RendeColetor"     # o nome que o robots.txt pode citar
INTERVALO = 5.0                # segundos entre duas requisições ao mesmo site
TEMPO = 40.0                   # timeout de cada requisição
TAMANHO_MAXIMO = 18 * 1024 * 1024   # 18 MB (o Gemini recebe até ~20 MB por pedido)


class Proibido(Exception):
    """O robots.txt do site não permite esta página."""


class ErroColeta(Exception):
    """O site respondeu com erro, demorou demais ou mandou algo inesperado."""


@dataclass
class _Resposta:
    status: int
    tipo: str
    conteudo: bytes
    url: str

    @property
    def texto(self) -> str:
        return self.conteudo.decode("utf-8", errors="replace")


@dataclass
class Arquivo:
    dados: bytes
    tipo: str      # content-type sem parâmetros ("application/pdf", "image/jpeg", "text/html"...)
    url: str


class Navegador:
    """Um navegador educado. Use um por coleta (ele lembra o robots.txt e a hora do último acesso)."""

    def __init__(self, intervalo: float = INTERVALO, transporte: httpx.AsyncBaseTransport | None = None,
                 dormir=asyncio.sleep, relogio=time.monotonic):
        self.intervalo = intervalo
        self._cliente = httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=TEMPO,
                                          follow_redirects=True, transport=transporte)
        self._robots: dict[str, RobotFileParser] = {}
        self._ultimo: dict[str, float] = {}
        self._travas: dict[str, asyncio.Lock] = {}
        self._dormir, self._relogio = dormir, relogio
        self.requisicoes = 0

    async def __aenter__(self) -> "Navegador":
        return self

    async def __aexit__(self, *_) -> None:
        await self.fechar()

    async def fechar(self) -> None:
        await self._cliente.aclose()

    # --- ritmo e robots.txt -----------------------------------------------------------
    async def _get(self, url: str) -> _Resposta:
        site = urlsplit(url).netloc
        trava = self._travas.setdefault(site, asyncio.Lock())
        async with trava:
            espera = self.intervalo - (self._relogio() - self._ultimo.get(site, -1e9))
            if espera > 0:
                await self._dormir(espera)
            try:
                self.requisicoes += 1
                async with self._cliente.stream("GET", url) as resposta:
                    tamanho = int(resposta.headers.get("content-length") or 0)
                    if tamanho > TAMANHO_MAXIMO:
                        raise ErroColeta(f"{url}: arquivo grande demais ({tamanho // 1_000_000} MB)")
                    corpo = bytearray()
                    async for pedaco in resposta.aiter_bytes():
                        corpo += pedaco
                        if len(corpo) > TAMANHO_MAXIMO:
                            raise ErroColeta(f"{url}: arquivo grande demais (mais de 18 MB)")
                    tipo = (resposta.headers.get("content-type") or "").split(";")[0].strip().lower()
                    return _Resposta(resposta.status_code, tipo, bytes(corpo), str(resposta.url))
            except httpx.HTTPError as erro:
                raise ErroColeta(f"{url}: {type(erro).__name__}") from erro
            finally:
                self._ultimo[site] = self._relogio()

    async def _regras(self, url: str) -> RobotFileParser:
        partes = urlsplit(url)
        site = f"{partes.scheme}://{partes.netloc}"
        if site not in self._robots:
            regras = RobotFileParser(f"{site}/robots.txt")
            try:
                resposta = await self._get(f"{site}/robots.txt")
            except ErroColeta as erro:
                # sem conseguir ler o robots.txt, não arriscamos: o site fica para outro dia
                raise ErroColeta(f"não consegui ler o robots.txt de {partes.netloc} ({erro})") from erro
            if resposta.status in (401, 403):
                regras.disallow_all = True       # mesma regra da biblioteca padrão do Python
            elif resposta.status >= 500:
                raise ErroColeta(f"robots.txt de {partes.netloc} respondeu {resposta.status}")
            elif resposta.status >= 400:
                regras.allow_all = True          # 404: o site não tem regras
            else:
                regras.parse(resposta.texto.splitlines())
            self._robots[site] = regras
        return self._robots[site]

    async def permitido(self, url: str) -> bool:
        regras = await self._regras(url)
        return regras.can_fetch(NOME_ROBO, url) and regras.can_fetch(USER_AGENT, url)

    # --- downloads --------------------------------------------------------------------
    async def baixar(self, url: str) -> Arquivo:
        if not await self.permitido(url):
            raise Proibido(f"o robots.txt de {urlsplit(url).netloc} não permite {urlsplit(url).path}")
        resposta = await self._get(url)
        if resposta.status != 200:
            raise ErroColeta(f"{url}: respondeu {resposta.status}")
        return Arquivo(dados=resposta.conteudo, tipo=resposta.tipo, url=resposta.url)

    async def texto(self, url: str) -> str:
        arquivo = await self.baixar(url)
        return arquivo.dados.decode("utf-8", errors="replace")

    async def json(self, url: str):
        try:
            return json.loads(await self.texto(url))
        except ValueError as erro:
            raise ErroColeta(f"{url}: a resposta não é JSON") from erro
