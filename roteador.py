"""Escada de modelos: cada tarefa começa no nível mais barato que dá conta e só sobe
quando é preciso. O resto do código chama só este arquivo.

Níveis (do mais barato ao mais caro):
  1. Gemini (principal e reserva): conversa, áudio, foto, receitas, encartes
     (o coletor diário de encartes usa SÓ o Gemini).
  2. Claude Haiku: trocar 1 prato; substituto do Gemini sem cota/fora do ar
     (conversa e foto; áudio fica só no Gemini); tarefas curtas e estruturadas.
  3. Claude Sonnet: gerar e refazer o cardápio da semana.
  4. Claude Opus: só por escalonamento (cardápio do Sonnet reprovado na conferência)
     ou caso complexo (3+ restrições, ou otimizar com promoções de vários mercados).

Subidas:
- resultado reprovado na conferência em código: tenta UMA vez o nível de cima,
  dizendo o motivo da reprovação; recusa ou erro: vai para o próximo nível;
- se todos os níveis do Claude falharem: usa o Gemini e avisa no log;
- limites diários por modelo (LIMITE_HAIKU_DIA, LIMITE_SONNET_DIA, LIMITE_OPUS_DIA):
  se o nível de cima está no limite, repete o atual uma vez e entrega o melhor resultado.

Cada chamada fica registrada (banco.uso_ia + log) com nível, modelo, motivo, tokens,
cache e custo estimado, sem o texto da conversa.
"""
import inspect
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import banco
import ia
import ia_claude
import restricoes
from ia_comum import ErroIA, RespostaIA

log = logging.getLogger("rende.roteador")


@dataclass(frozen=True)
class Nivel:
    nome: str       # 'gemini', 'gemini-reserva', 'haiku', 'sonnet', 'opus'
    provedor: str   # 'gemini' ou 'claude'
    modelo: str


# US$ por 1 milhão de tokens: (entrada, saída, leitura de cache). Preço de tabela, nov/2026.
# Gravar no cache custa 1,25x a entrada. No plano gratuito do Gemini o custo real é zero.
PRECOS = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "gemini-3.5-flash-lite": (0.30, 2.50, 0.03),
    "gemini-3.6-flash": (0.75, 3.75, 0.075),  # sobe para 1,50 / 7,50 em 01/01/2027
}
ESCRITA_CACHE = 1.25

# Effort "medium" nas tarefas que exigem conta de orçamento; o resto: "low". Na troca, o Haiku
# também usa "medium" (conferido em 24/11: o Haiku 5.5 aceita low a max e o padrão dele é medium;
# a troca custa ~US$ 0,001 nele, e nos testes reais ele estourou o orçamento por pouco).
TAREFAS_ESFORCO_MEDIO = {"troca", "cardapio", "complexo", "otimizar_lista"}
# Teto de tokens de saída por tarefa (só o Claude usa). Não muda o preço — paga-se o que o modelo
# escreve —, mas a Anthropic reserva o teto na conta de tokens por minuto: pedir 32 mil para
# responder "oi" tira folga de limite de todo mundo. O cardápio continua com o teto alto porque
# em 24/11 o Sonnet chegou a usar 16 mil (raciocínio + JSON) e a resposta saiu cortada.
# Mídia também tem teto alto: a foto de um encarte vira uma chamada de ferramenta com até 80
# ofertas, e 8 mil tokens (somados ao raciocínio) podiam cortar a lista no meio.
MAX_TOKENS_TAREFA = {"cardapio": 32000, "complexo": 16000, "otimizar_lista": 16000, "troca": 16000,
                     "midia": 16000}
MAX_TOKENS_PADRAO = 8000  # conversa, cadastro, receita
_CLAUDE = {"haiku": ("CLAUDE_MODELO_BARATO", "claude-haiku-5-5", "LIMITE_HAIKU_DIA", 500),
           "sonnet": ("CLAUDE_MODELO_PADRAO", "claude-sonnet-5-5", "LIMITE_SONNET_DIA", 100),
           "opus": ("CLAUDE_MODELO_FORTE", "claude-opus-5-5", "LIMITE_OPUS_DIA", 20)}

ADAPTADORES = {"gemini": ia, "claude": ia_claude}  # os testes trocam por simulações

Conferir = Callable[[RespostaIA], list[str] | Awaitable[list[str]]]


# --- preços e limites ------------------------------------------------------------
def custo_usd(modelo: str, entrada: int, saida: int, cache_leitura: int = 0, cache_escrita: int = 0) -> float:
    preco = PRECOS.get(modelo)
    if not preco:
        return 0.0
    p_entrada, p_saida, p_cache = preco
    return (entrada * p_entrada + cache_escrita * p_entrada * ESCRITA_CACHE
            + cache_leitura * p_cache + saida * p_saida) / 1_000_000


def saldo_cache(modelo: str, cache_leitura: int, cache_escrita: int) -> float:
    """Quanto o cache economizou, em US$ (negativo: custou mais do que economizou).
    Gravar custa ESCRITA_CACHE vezes a entrada (o que passa de 1x é o custo extra); cada token
    lido do cache custa o preço de cache em vez do de entrada. Compensa quando as leituras
    passam de ~27% das gravações, não só quando lê mais do que grava."""
    preco = PRECOS.get(modelo)
    if not preco:
        return 0.0
    p_entrada, _, p_cache = preco
    return (cache_leitura * (p_entrada - p_cache) - cache_escrita * p_entrada * (ESCRITA_CACHE - 1)) / 1_000_000


def claude(nome: str) -> Nivel:
    variavel, padrao, _, _ = _CLAUDE[nome]
    return Nivel(nome, "claude", (os.getenv(variavel) or padrao).strip())


def niveis_gemini() -> list[Nivel]:
    niveis = [Nivel("gemini", "gemini", (os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite").strip())]
    reserva = (os.getenv("GEMINI_MODEL_RESERVA") or "").strip()
    if reserva and reserva != niveis[0].modelo:
        niveis.append(Nivel("gemini-reserva", "gemini", reserva))
    return niveis


def limite(nome: str) -> int:
    _, _, variavel, padrao = _CLAUDE[nome]
    return int(os.getenv(variavel) or padrao)


def liberado(nivel: Nivel) -> tuple[bool, str]:
    if nivel.provedor == "gemini":
        return True, ""
    if not ADAPTADORES["claude"].disponivel():
        return False, "sem ANTHROPIC_API_KEY"
    if banco.chamadas_modelo_hoje(nivel.modelo) >= limite(nivel.nome):
        return False, f"limite diário do {nivel.nome} atingido ({limite(nivel.nome)} chamadas)"
    return True, ""


def _tem_audio(mensagens: list[dict]) -> bool:
    return any(str((m.get("anexo") or {}).get("mime_type", "")).startswith("audio/") for m in mensagens)


def escada(tarefa: str, *, complexo: bool = False, tem_audio: bool = False) -> list[Nivel]:
    """Níveis em ordem de tentativa para a tarefa."""
    if tarefa == "troca":
        niveis = [claude("haiku"), claude("sonnet"), claude("opus")]
    elif tarefa == "cardapio":
        niveis = [claude("opus")] if complexo else [claude("sonnet"), claude("opus")]
    elif tarefa in ("complexo", "otimizar_lista"):
        niveis = [claude("sonnet"), claude("opus")]
    elif tarefa == "coletor":  # robô diário: só o Gemini (nunca gasta o Claude pago)
        niveis = niveis_gemini()
    else:  # conversa, midia, cadastro, receita, encarte...
        niveis = niveis_gemini() + [claude("haiku")]
    if tem_audio:  # o Claude não ouve áudio
        niveis = [n for n in niveis if n.provedor == "gemini"] or niveis_gemini()
    return niveis


def categoria(problemas: list[str]) -> str:
    """Resumo do motivo de uma reprovação, para o log e o /custos."""
    # Nomes de pratos e itens aparecem em vários problemas ("Feijão tropeiro com ovo" repetido,
    # "ovo R$ 40,00" na dica de orçamento). Alergia é reconhecida pelo rótulo que a conferência
    # escreve, "(Lactose)", "(Ovo)"..., e as outras regras não olham o problema de orçamento.
    orcamento = any("orçamento" in p.lower() for p in problemas)
    texto = " ".join(p for p in problemas if "orçamento" not in p.lower()).lower()
    rotulos_alergia = tuple(f"({n.lower()})" for n in restricoes.NOMES.values()) + ("(outro)",)
    regras = [("alergia/restrição", rotulos_alergia),
              ("orçamento", ()),
              ("repetição", ("mais de uma vez", "rejeitado", "igual ao antigo", "semana passada")),
              ("utensílios", ("não tem",)),
              ("JSON inválido", ("json",)),
              ("estrutura", ("faltam", "sem ingredientes", "embalagem", "unidade", "não foram pedidas",
                             "quantidade"))]
    for nome, palavras in regras:
        if (nome == "orçamento" and orcamento) or any(p in texto for p in palavras):
            return nome
    return "outros"


def _so_orcamento(problemas: list[str]) -> bool:
    return bool(problemas) and all("orçamento" in p for p in problemas)


# --- registro -----------------------------------------------------------------------
def _registrar(nivel: Nivel, tarefa: str, motivo: str, resposta: RespostaIA | None, escalonou_por: str | None) -> None:
    r = resposta or RespostaIA()
    custo = custo_usd(nivel.modelo, r.tokens_entrada, r.tokens_saida, r.cache_leitura, r.cache_escrita)
    banco.registrar_uso_ia(provedor=nivel.provedor, nivel=nivel.nome, modelo=nivel.modelo, tarefa=tarefa,
                           motivo=motivo, tokens_entrada=r.tokens_entrada, tokens_saida=r.tokens_saida,
                           cache_leitura=r.cache_leitura, cache_escrita=r.cache_escrita, custo_usd=custo,
                           cobrada=resposta is not None, escalonou_por=escalonou_por)
    log.info("IA: nivel=%s modelo=%s tarefa=%s motivo=%s tokens=%d/%d cache=%d lidos/%d gravados custo=US$ %.5f%s",
             nivel.nome, nivel.modelo, tarefa, motivo, r.tokens_entrada, r.tokens_saida, r.cache_leitura,
             r.cache_escrita, custo, "" if resposta else " (falhou)")


ESFORCOS = ("low", "medium", "high")


def esforco(nivel: Nivel, tarefa: str) -> str | None:
    """Effort do Claude por tarefa (o Gemini não usa). O cardápio no Sonnet usa ESFORCO_CARDAPIO
    (padrão "low", decisão de 24/11 para o custo ficar abaixo de US$ 0,08: o raciocínio é cobrado
    como saída e era ~5 mil dos 12 mil tokens). Quando o Opus refaz um cardápio reprovado, ele
    pensa mais ("medium")."""
    if nivel.provedor != "claude":
        return None
    if tarefa == "cardapio" and nivel.nome == "sonnet":
        escolhido = (os.getenv("ESFORCO_CARDAPIO") or "low").strip().lower()
        return escolhido if escolhido in ESFORCOS else "low"
    return "medium" if tarefa in TAREFAS_ESFORCO_MEDIO else "low"


def max_tokens(tarefa: str) -> int:
    """Teto de tokens de saída da tarefa (ver MAX_TOKENS_TAREFA)."""
    return MAX_TOKENS_TAREFA.get(tarefa, MAX_TOKENS_PADRAO)


async def _chamar(nivel: Nivel, tarefa: str, **kwargs) -> RespostaIA:
    resposta = await ADAPTADORES[nivel.provedor].gerar(modelo=nivel.modelo, esforco=esforco(nivel, tarefa),
                                                        max_tokens=max_tokens(tarefa), **kwargs)
    resposta.nivel = nivel.nome
    return resposta


async def _conferir(conferir: Conferir, resposta: RespostaIA) -> list[str]:
    resultado = conferir(resposta)
    return await resultado if inspect.isawaitable(resultado) else resultado


def _mensagem_de_correcao(problemas: list[str]) -> str:
    return ("O sistema conferiu sua resposta em código e reprovou. Corrija TODOS estes problemas e devolva "
            "a resposta completa no mesmo formato: " + "; ".join(problemas))


# --- a escada -----------------------------------------------------------------------
async def gerar(tarefa: str, *, sistema: str, mensagens: list[dict], sistema_extra: str = "",
                ferramentas: list[dict] | None = None, esquema_json: dict | None = None,
                tempo: float | None = None, conferir: Conferir | None = None, complexo: bool = False,
                ao_tentar: Callable[[int], Awaitable[None]] | None = None) -> RespostaIA:
    """Sobe a escada até um resultado aprovado.

    conferir(resposta) -> problemas (vazio = aprovado). Reprovado: o nível de cima recebe
    a resposta reprovada e o motivo. Sem nenhum aprovado, devolve o melhor resultado com
    .problemas preenchido (quem chamou decide se aceita). ao_tentar(n) avisa cada tentativa.
    """
    niveis = escada(tarefa, complexo=complexo, tem_audio=_tem_audio(mensagens))
    args = dict(sistema=sistema, sistema_extra=sistema_extra, ferramentas=ferramentas, esquema_json=esquema_json,
                **({"tempo": tempo} if tempo else {}))
    primeiro = niveis[0]
    motivo = f"padrão: '{tarefa}' começa no {primeiro.nome}" + (" (caso complexo)" if complexo else "")
    escalonou_por: str | None = None
    correcao: list[dict] = []
    reprovados: list[RespostaIA] = []
    falhas: list[str] = []
    repetiu_nivel = False
    tentativa = 0
    i = 0
    while i < len(niveis):
        nivel = niveis[i]
        ok, por_que = liberado(nivel)
        if not ok:
            falhas.append(f"{nivel.nome}: {por_que}")
            log.info("IA: pulando %s para '%s' (%s)", nivel.nome, tarefa, por_que)
            algum_acima = any(liberado(n)[0] for n in niveis[i + 1:])
            if reprovados and not algum_acima and not repetiu_nivel and i > 0 and liberado(niveis[i - 1])[0]:
                # nenhum nível de cima liberado: fica no atual mais uma vez, com a correção
                repetiu_nivel = True
                i -= 1
                motivo = f"repetindo {niveis[i].nome} ({por_que})"
                continue
            if i == 0:
                motivo = f"{nivel.nome} indisponível ({por_que})"
            i += 1
            continue

        if ao_tentar:
            await ao_tentar(tentativa)
        tentativa += 1
        try:
            resposta = await _chamar(nivel, tarefa, mensagens=mensagens + correcao, **args)
        except ErroIA as erro:
            _registrar(nivel, tarefa, motivo, None, escalonou_por)
            falhas.append(f"{nivel.nome}: {'sem cota' if erro.cota else 'erro'} ({erro})")
            log.warning("IA: %s falhou em '%s': %s", nivel.nome, tarefa, erro)
            motivo, escalonou_por = f"subiu: {nivel.nome} {'sem cota' if erro.cota else 'com erro'}", "erro"
            i += 1
            continue

        _registrar(nivel, tarefa, motivo, resposta, escalonou_por)
        if resposta.recusou:
            falhas.append(f"{nivel.nome}: recusou")
            log.warning("IA: %s recusou a tarefa '%s'", nivel.nome, tarefa)
            motivo, escalonou_por = f"subiu: {nivel.nome} recusou", "recusa"
            i += 1
            continue

        resposta.motivo = motivo
        if conferir is None:
            return resposta
        resposta.problemas = await _conferir(conferir, resposta)
        if not resposta.problemas:
            return resposta

        reprovados.append(resposta)
        escalonou_por = categoria(resposta.problemas)
        log.info("IA: %s reprovado na conferência de '%s' (%s): %s", nivel.nome, tarefa, escalonou_por,
                 "; ".join(resposta.problemas)[:300])
        correcao = [{"papel": "assistente", "texto": resposta.texto},
                    {"papel": "usuario", "texto": _mensagem_de_correcao(resposta.problemas)}]
        motivo = f"escalonamento: {nivel.nome} reprovado ({escalonou_por})"
        i += 1

    if reprovados:  # nenhum aprovado: o melhor resultado (só orçamento é o menos grave)
        return min(reprovados, key=lambda r: (not _so_orcamento(r.problemas), len(r.problemas)))

    if primeiro.provedor == "claude":  # todos os níveis do Claude falharam: último recurso, Gemini
        log.warning("IA: nenhum nível do Claude respondeu '%s' (%s); usando o Gemini", tarefa, " | ".join(falhas))
        for nivel in niveis_gemini():
            motivo_g = f"último recurso: Claude indisponível ({' | '.join(falhas)[:150]})"
            if ao_tentar:
                await ao_tentar(tentativa)
            tentativa += 1
            try:
                resposta = await _chamar(nivel, tarefa, mensagens=mensagens, **args)
            except ErroIA as erro:
                _registrar(nivel, tarefa, motivo_g, None, "erro")
                falhas.append(f"{nivel.nome}: erro ({erro})")
                continue
            _registrar(nivel, tarefa, motivo_g, resposta, "erro")
            if resposta.recusou:
                falhas.append(f"{nivel.nome}: recusou")
                continue
            resposta.motivo = motivo_g
            if conferir is not None:
                resposta.problemas = await _conferir(conferir, resposta)
            return resposta

    raise ErroIA(" | ".join(falhas) or "nenhum modelo disponível")
