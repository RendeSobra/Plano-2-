"""Única parte do Rende que conversa com o Google Gemini.

Mesma interface do ia_claude.py: `gerar(...)` recebe sistema, mensagens,
ferramentas e (opcional) um esquema JSON, e devolve uma RespostaIA.
Quem escolhe o modelo é o roteador.py.
"""
import asyncio
import os
import uuid

from google import genai
from google.genai import errors, types

from ia_comum import Chamada, ErroIA, RespostaIA

TEMPO_MAXIMO = 45  # segundos por chamada (o cardápio pede mais, ver `tempo`)
_BLOQUEIOS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_SAFETY"}

_cliente: genai.Client | None = None


def _obter_cliente() -> genai.Client:
    global _cliente
    if _cliente is None:
        _cliente = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            # Erros passageiros (503 sobrecarga, 429 muitos pedidos) são tentados de
            # novo uma vez, 2 s depois. Se ainda falhar, o roteador passa para outro modelo.
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(attempts=2, initial_delay=2, max_delay=5)
            ),
        )
    return _cliente


def _ferramentas(definicoes: list[dict]) -> list[types.Tool]:
    return [types.Tool(function_declarations=[
        types.FunctionDeclaration(name=d["nome"], description=d["descricao"],
                                  parameters_json_schema=d["parametros"])
        for d in definicoes
    ])]


def _para_gemini(mensagens: list[dict]) -> list[types.Content]:
    conteudos: list[types.Content] = []
    for msg in mensagens:
        if msg["papel"] == "usuario":
            partes = []
            anexo = msg.get("anexo")
            if anexo:  # áudio, foto ou PDF: o Gemini entende direto
                partes.append(types.Part.from_bytes(data=bytes(anexo["dados"]), mime_type=anexo["mime_type"]))
            if msg.get("texto") or not partes:
                partes.append(types.Part.from_text(text=msg.get("texto") or ""))
            conteudos.append(types.Content(role="user", parts=partes))

        elif msg["papel"] == "assistente":
            bruto = msg.get("bruto")
            if isinstance(bruto, dict) and bruto.get("provedor") == "gemini":
                conteudos.append(bruto["conteudo"])  # devolve intacto (assinaturas de pensamento)
                continue
            partes = [types.Part.from_text(text=msg["texto"])] if msg.get("texto") else []
            for c in msg.get("chamadas", []):
                partes.append(types.Part(function_call=types.FunctionCall(id=c.id, name=c.nome, args=c.args)))
            if partes:
                conteudos.append(types.Content(role="model", parts=partes))

        elif msg["papel"] == "ferramenta":
            conteudos.append(types.Content(role="user", parts=[
                types.Part(function_response=types.FunctionResponse(
                    id=r["id"], name=r["nome"], response={"resultado": r["conteudo"]}))
                for r in msg["resultados"]
            ]))

    # O Gemini espera que a conversa comece pela pessoa (o histórico pode ter sido cortado).
    if conteudos and conteudos[0].role == "model":
        conteudos.insert(0, types.Content(role="user", parts=[types.Part.from_text(text="(continuação da conversa)")]))
    return conteudos


async def gerar(*, modelo: str, sistema: str, mensagens: list[dict], sistema_extra: str = "",
                ferramentas: list[dict] | None = None, esquema_json: dict | None = None,
                esforco: str | None = None, tempo: float = TEMPO_MAXIMO) -> RespostaIA:
    # o Gemini faz cache sozinho de prefixos repetidos: as instruções fixas vão primeiro
    config = types.GenerateContentConfig(system_instruction=f"{sistema}\n\n{sistema_extra}".strip())
    if ferramentas:
        config.tools = _ferramentas(ferramentas)
        # nós rodamos as ferramentas (o SDK não deve tentar rodar sozinho)
        config.automatic_function_calling = types.AutomaticFunctionCallingConfig(disable=True)
    if esquema_json:
        config.response_mime_type = "application/json"
        config.response_json_schema = esquema_json

    try:
        resposta = await asyncio.wait_for(
            _obter_cliente().aio.models.generate_content(
                model=modelo, contents=_para_gemini(mensagens), config=config),
            timeout=tempo,
        )
    except errors.APIError as erro:
        raise ErroIA(f"{modelo}: {erro.code} {erro.status}", cota=erro.code == 429) from erro
    except TimeoutError as erro:
        raise ErroIA(f"{modelo}: passou de {tempo:.0f} s sem responder") from erro
    except Exception as erro:
        raise ErroIA(f"{modelo}: {type(erro).__name__}: {erro}") from erro

    uso = resposta.usage_metadata
    em_cache = (uso.cached_content_token_count or 0) if uso else 0
    entrada = ((uso.prompt_token_count or 0) - em_cache) if uso else 0
    saida = ((uso.candidates_token_count or 0) + (uso.thoughts_token_count or 0)) if uso else 0
    base = dict(provedor="gemini", modelo=modelo, tokens_entrada=max(0, entrada), tokens_saida=saida,
                cache_leitura=em_cache)

    candidato = resposta.candidates[0] if resposta.candidates else None
    if candidato is None or not candidato.content or not candidato.content.parts:
        bloqueio = resposta.prompt_feedback.block_reason if resposta.prompt_feedback else None
        motivo = str(getattr(candidato, "finish_reason", None) or bloqueio or "")
        if bloqueio or any(b in motivo for b in _BLOQUEIOS):
            return RespostaIA(recusou=True, **base)
        raise ErroIA(f"{modelo}: resposta vazia ({motivo or 'sem candidatos'})")

    texto = "".join(p.text for p in candidato.content.parts if p.text and not p.thought).strip()
    chamadas = [Chamada(id=fc.id or uuid.uuid4().hex, nome=fc.name, args=dict(fc.args or {}))
                for fc in (resposta.function_calls or [])]
    if not texto and not chamadas:
        raise ErroIA(f"{modelo}: resposta sem texto")
    return RespostaIA(texto=texto, chamadas=chamadas,
                      bruto={"provedor": "gemini", "conteudo": candidato.content}, **base)
