"""Coletor de promoções de Goiânia (C13, Fase 2).

Um arquivo por rede (prezunic.py, atacadao.py, diaadia.py), todos com
`async def coletar(nav) -> list[Encarte]`. Este arquivo roda as redes, uma por vez:

1. pega a lista de encartes vigentes no site oficial (respeitando o robots.txt);
2. pula o que já foi lido (mesmo endereço ou mesmo arquivo, pelo hash sha256);
3. manda o encarte para o Gemini (extrair.py) e guarda as ofertas em `promocoes`
   (origem "site", com o link da fonte), com as conferências de promocoes.py;
4. o arquivo só existe na memória e é descartado logo depois da extrair.

Se uma rede quebrar, as outras seguem; o resultado diz o que falhou (o bot avisa o admin).
Rodar à mão (sem o bot):   .venv\\Scripts\\python -m coletor
"""
import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import date

import banco
import promocoes
from coletor import atacadao, diaadia, prezunic
from coletor import extrair as extrator
from coletor.encarte import Encarte
from coletor.web import ErroColeta, Navegador, Proibido
from ia_comum import ErroIA

log = logging.getLogger("rende.coletor")

REDES = {m.REDE: m for m in (prezunic, atacadao, diaadia)}
CIDADE = "Goiânia"
# Encartes que não interessam ao cardápio (não gastam a cota do Gemini)
TITULOS_FORA = ("bazar", "eletro", "utilidade", "brinquedo", "papelaria", "pet")


def max_encartes() -> int:
    return int(os.getenv("COLETOR_MAX_ENCARTES") or 8)


@dataclass
class ResultadoRede:
    rede: str
    mercado: str
    encartes: int = 0          # vigentes no site
    lidos: int = 0             # mandados para a IA agora
    repetidos: int = 0         # já lidos antes (mesmo endereço ou mesmo arquivo)
    ofertas_novas: int = 0
    ids: list[int] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)   # problema em um encarte (a rede seguiu)
    falha: str | None = None                         # a rede inteira falhou

    @property
    def exemplos(self) -> list[str]:
        saida = []
        for i in self.ids[:5]:
            p = banco.promocao(i)
            if p:
                nome = " ".join(x for x in (p["produto"], p.get("marca"), p.get("tamanho")) if x)
                saida.append(f"{nome}: R$ {p['preco']:.2f}".replace(".", ",") + f" até {p['validade'][8:10]}/{p['validade'][5:7]}")
        return saida


def _fora_do_cardapio(encarte: Encarte) -> bool:
    titulo = encarte.titulo.lower()
    return any(p in titulo for p in TITULOS_FORA)


def _data_lida(texto: str, hoje: date) -> date | None:
    """Data lida pela IA. Se ela errar o ano de um encarte que está no ar ('24/11' -> 2025-11-24),
    corrige para o ano atual."""
    try:
        lida = date.fromisoformat((texto or "")[:10])
    except ValueError:
        return None
    if lida < hoje:
        try:
            corrigida = lida.replace(year=hoje.year)
        except ValueError:
            return lida
        if corrigida >= hoje:
            return corrigida
    return lida


async def _ler_encarte(encarte: Encarte, nav: Navegador, resultado: ResultadoRede) -> None:
    if banco.encarte_lido(url=encarte.url):
        resultado.repetidos += 1
        return
    arquivo = await nav.baixar(encarte.url)
    dados = arquivo.dados
    hash_arquivo = hashlib.sha256(dados).hexdigest()
    if banco.encarte_lido(hash_arquivo=hash_arquivo):
        banco.registrar_encarte(hash_arquivo=hash_arquivo, rede=encarte.rede, url=encarte.url,
                                titulo=encarte.titulo, ofertas=0)
        resultado.repetidos += 1
        return
    mime_type = extrator.tipo_do_arquivo(arquivo.tipo, arquivo.url, dados)
    if mime_type is None:
        raise ErroColeta(f"'{encarte.titulo}': tipo de arquivo inesperado ({arquivo.tipo or 'sem tipo'})")
    try:
        lido = await extrator.extrair(encarte, dados, mime_type)
    finally:
        del dados, arquivo  # o encarte nunca vai para o disco e some da memória aqui
    resultado.lidos += 1
    hoje = banco.agora().date()
    fim = encarte.validade_fim or _data_lida(lido["validade_fim"], hoje)
    inicio = encarte.validade_inicio or _data_lida(lido["validade_inicio"], hoje)
    salvo = promocoes.salvar_ofertas(mercado=encarte.mercado, ofertas=lido["ofertas"], origem="site", cidade=CIDADE,
                                     validade=fim, validade_inicio=inicio, fonte_url=encarte.fonte_url,
                                     lojas=encarte.lojas, maximo=extrator.MAX_OFERTAS)
    novos = salvo.get("ids", [])
    resultado.ids += novos
    resultado.ofertas_novas += len(novos)
    if salvo.get("erro"):
        resultado.erros.append(f"'{encarte.titulo}': {salvo['erro']}")
    banco.registrar_encarte(hash_arquivo=hash_arquivo, rede=encarte.rede, url=encarte.url,
                            titulo=encarte.titulo, ofertas=len(novos))


async def coletar_rede(nome: str, nav: Navegador) -> ResultadoRede:
    modulo = REDES[nome]
    resultado = ResultadoRede(rede=nome, mercado=modulo.MERCADO)
    try:
        encartes = [e for e in await modulo.coletar(nav) if not _fora_do_cardapio(e)]
    except Proibido as erro:
        resultado.falha = f"pulada: {erro}"
        log.warning("Coletor %s: %s", nome, resultado.falha)
        return resultado
    except Exception as erro:  # o site mudou, caiu ou demorou: as outras redes seguem
        resultado.falha = f"{type(erro).__name__}: {erro}"[:300]
        log.error("Coletor %s falhou ao listar os encartes: %s", nome, resultado.falha)
        return resultado
    resultado.encartes = len(encartes)
    for encarte in encartes[:max_encartes()]:
        try:
            await _ler_encarte(encarte, nav, resultado)
        except (Proibido, ErroColeta, ErroIA) as erro:
            resultado.erros.append(f"'{encarte.titulo}': {erro}"[:300])
            log.warning("Coletor %s: encarte '%s' não lido: %s", nome, encarte.titulo, erro)
        except Exception as erro:
            resultado.erros.append(f"'{encarte.titulo}': {type(erro).__name__}: {erro}"[:300])
            log.exception("Coletor %s: erro inesperado no encarte '%s'", nome, encarte.titulo)
    if resultado.encartes and resultado.erros and not resultado.lidos and not resultado.repetidos:
        resultado.falha = "nenhum encarte pôde ser lido"
    log.info("Coletor %s: %d encartes, %d lidos, %d já vistos, %d ofertas novas, %d erros.", nome,
             resultado.encartes, resultado.lidos, resultado.repetidos, resultado.ofertas_novas, len(resultado.erros))
    return resultado


async def coletar(redes: list[str] | None = None, nav: Navegador | None = None) -> list[ResultadoRede]:
    """Roda a coleta de todas as redes (ou das escolhidas). Uma rede quebrada não derruba as outras."""
    proprio = nav is None
    nav = nav or Navegador()
    try:
        resultados = [await coletar_rede(nome, nav) for nome in (redes or list(REDES))]
    finally:
        if proprio:
            await nav.fechar()
    banco.apagar_promocoes_vencidas()
    banco.gravar_estado("ultima_coleta", banco.agora().isoformat(timespec="seconds"))
    return resultados


def falhas(resultados: list[ResultadoRede]) -> list[str]:
    """O que o admin precisa saber: redes que falharam inteiras e encartes que não foram lidos."""
    linhas = [f"{r.mercado}: {r.falha}" for r in resultados if r.falha]
    linhas += [f"{r.mercado}: {e}" for r in resultados if not r.falha for e in r.erros]
    return linhas


def texto_resultado(resultados: list[ResultadoRede]) -> str:
    linhas = ["🔎 *Coleta de promoções*", ""]
    for r in resultados:
        if r.falha:
            linhas.append(f"❌ *{r.mercado}*: {r.falha}")
            continue
        linhas.append(f"✅ *{r.mercado}*: {r.ofertas_novas} ofertas novas · {r.encartes} encartes no ar "
                      f"({r.lidos} lidos agora, {r.repetidos} já vistos)")
        linhas += [f"   • {e}" for e in r.exemplos]
        linhas += [f"   ⚠️ {e}" for e in r.erros[:3]]
    total = sum(r.ofertas_novas for r in resultados)
    linhas += ["", f"Total: {total} ofertas novas."]
    return "\n".join(linhas)
