"""Única parte do Rende que conversa com o Claude (Anthropic).

Mesma interface do ia.py: `gerar(...)` recebe sistema, mensagens, ferramentas e
(opcional) um esquema JSON, e devolve uma RespostaIA.

Regras da API atual (conferidas em platform.claude.com/docs, nov/2026):
- SDK oficial `anthropic`, cliente AsyncAnthropic (lê ANTHROPIC_API_KEY do ambiente);
- modelo exatamente como está no .env (CLAUDE_MODEL), sem data no final;
- não enviamos temperature, top_p, top_k nem thinking com budget_tokens (dão erro 400);
  nesses modelos o raciocínio é sempre adaptativo e o controle é o `effort`;
- não enviamos thinking (nem "disabled"): o parâmetro é omitido;
- ferramentas só com tool_choice "auto" ("any"/"tool" dão erro 400);
- effort sempre explícito em output_config (o roteador escolhe por tarefa);
- prompt caching: as instruções fixas (e as ferramentas, que vêm antes delas)
  vão com cache_control; a parte que muda vai num bloco separado, sem cache;
- sempre conferimos stop_reason: "refusal" vira RespostaIA(recusou=True); "max_tokens"
  (resposta cortada) fica no log e a conferência reprova, o que sobe de nível;
- a resposta vem por streaming (messages.stream + get_final_message): o SDK exige isso
  para limites de saída grandes, e o raciocínio do modelo também conta nesse limite.
O Claude não entende áudio; áudio fica com o Gemini (o roteador cuida disso).
"""
import base64
import json
import logging
import os
import uuid

import anthropic

from ia_comum import Chamada, ErroIA, RespostaIA

log = logging.getLogger("rende.ia_claude")

TEMPO_MAXIMO = 120  # segundos (por leitura do streaming)
# Em 24/11 o Sonnet usou os 16 mil tokens inteiros (raciocínio + JSON) e o cardápio saiu
# cortado. Só se paga o que o modelo usa; o limite maior evita refazer tudo no Opus.
# Quem chama escolhe o teto por tarefa (roteador.MAX_TOKENS_TAREFA): a Anthropic reserva
# esse valor na conta de tokens por minuto, então pedir 32 mil numa conversa curta gasta
# folga de limite à toa. Este é o padrão de quem não escolher.
MAX_TOKENS = 32000

_cliente: anthropic.AsyncAnthropic | None = None


def disponivel() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _obter_cliente() -> anthropic.AsyncAnthropic:
    global _cliente
    if _cliente is None:
        _cliente = anthropic.AsyncAnthropic(timeout=TEMPO_MAXIMO, max_retries=1)
    return _cliente


def _bloco_anexo(anexo: dict) -> dict:
    mime = anexo["mime_type"]
    dados = base64.standard_b64encode(bytes(anexo["dados"])).decode("ascii")
    if mime.startswith("image/"):
        return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": dados}}
    if mime == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": mime, "data": dados}}
    return {"type": "text", "text": "(a pessoa mandou um áudio, que não está disponível aqui)"}


def _id_valido(id_: str | None) -> str:
    return id_ if id_ and all(c.isalnum() or c in "_-" for c in id_) else f"toolu_{uuid.uuid4().hex}"


def _para_claude(mensagens: list[dict]) -> list[dict]:
    saida: list[dict] = []
    for msg in mensagens:
        if msg["papel"] == "usuario":
            blocos = [_bloco_anexo(msg["anexo"])] if msg.get("anexo") else []
            blocos.append({"type": "text", "text": msg.get("texto") or "(sem texto)"})
            saida.append({"role": "user", "content": blocos})

        elif msg["papel"] == "assistente":
            bruto = msg.get("bruto")
            if isinstance(bruto, dict) and bruto.get("provedor") == "claude":
                # devolve intacto: os blocos de raciocínio precisam voltar sem mudança
                saida.append({"role": "assistant", "content": bruto["conteudo"]})
                continue
            blocos = [{"type": "text", "text": msg["texto"]}] if msg.get("texto") else []
            for c in msg.get("chamadas", []):
                blocos.append({"type": "tool_use", "id": _id_valido(c.id), "name": c.nome, "input": c.args})
            if blocos:
                saida.append({"role": "assistant", "content": blocos})

        elif msg["papel"] == "ferramenta":
            saida.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": _id_valido(r["id"]),
                 "content": json.dumps(r["conteudo"], ensure_ascii=False, default=str)}
                for r in msg["resultados"]
            ]})

    if saida and saida[0]["role"] != "user":  # a conversa precisa começar pela pessoa
        saida.insert(0, {"role": "user", "content": "(continuação da conversa)"})
    return saida


def _sistema(sistema: str, sistema_extra: str) -> list[dict]:
    blocos = [{"type": "text", "text": sistema, "cache_control": {"type": "ephemeral"}}]
    if sistema_extra:
        blocos.append({"type": "text", "text": sistema_extra})
    return blocos


async def gerar(*, modelo: str, sistema: str, mensagens: list[dict], sistema_extra: str = "",
                ferramentas: list[dict] | None = None, esquema_json: dict | None = None,
                esforco: str | None = None, tempo: float = TEMPO_MAXIMO,
                max_tokens: int = MAX_TOKENS) -> RespostaIA:
    if not disponivel():
        raise ErroIA("Claude: falta ANTHROPIC_API_KEY no .env")

    parametros: dict = {
        "model": modelo,
        "max_tokens": max_tokens,
        "system": _sistema(sistema, sistema_extra),
        "messages": _para_claude(mensagens),
    }
    config_saida: dict = {}
    if esforco:
        config_saida["effort"] = esforco
    if esquema_json:
        config_saida["format"] = {"type": "json_schema", "schema": esquema_json}
    if config_saida:
        parametros["output_config"] = config_saida
    if ferramentas:
        parametros["tools"] = [{"name": d["nome"], "description": d["descricao"],
                                "input_schema": d["parametros"]} for d in ferramentas]
        parametros["tool_choice"] = {"type": "auto"}

    try:
        async with _obter_cliente().with_options(timeout=tempo).messages.stream(**parametros) as fluxo:
            resposta = await fluxo.get_final_message()
    except anthropic.RateLimitError as erro:
        raise ErroIA(f"{modelo}: limite de uso (429)", cota=True) from erro
    except anthropic.APIStatusError as erro:
        raise ErroIA(f"{modelo}: erro {erro.status_code}") from erro
    except (anthropic.APIConnectionError, anthropic.APITimeoutError) as erro:
        raise ErroIA(f"{modelo}: sem conexão ou demorou demais ({type(erro).__name__})") from erro

    uso = resposta.usage
    base = dict(provedor="claude", modelo=modelo, tokens_entrada=uso.input_tokens or 0,
                tokens_saida=uso.output_tokens or 0, cache_leitura=uso.cache_read_input_tokens or 0,
                cache_escrita=uso.cache_creation_input_tokens or 0)

    if resposta.stop_reason == "refusal":  # sempre conferido antes de ler o conteúdo
        return RespostaIA(recusou=True, **base)
    if resposta.stop_reason == "max_tokens":
        log.warning("Claude: resposta de %s cortada no limite de %d tokens de saída", modelo, max_tokens)

    texto = "".join(b.text for b in resposta.content if b.type == "text").strip()
    chamadas = [Chamada(id=b.id, nome=b.name, args=dict(b.input or {}))
                for b in resposta.content if b.type == "tool_use"]
    if not texto and not chamadas:
        raise ErroIA(f"{modelo}: resposta sem texto (stop_reason={resposta.stop_reason})")
    return RespostaIA(texto=texto, chamadas=chamadas,
                      bruto={"provedor": "claude", "conteudo": resposta.content}, **base)
