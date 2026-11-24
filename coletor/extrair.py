"""Manda um encarte (PDF ou imagem) para o Gemini e recebe as ofertas em JSON.

A normalização dos nomes e as conferências (preço, validade, repetição) ficam em
promocoes.py, iguais para todas as origens.
"""
import json

import prompts
import roteador
from coletor.encarte import Encarte
from ia_comum import ErroIA

TEMPO = 180  # segundos: um encarte de várias páginas demora
MAX_OFERTAS = 300

_OFERTA = {"type": "object", "additionalProperties": False, "required": ["produto", "preco"], "properties": {
    "produto": {"type": "string"}, "marca": {"type": "string"}, "tamanho": {"type": "string"},
    "preco": {"type": "number"}, "preco_anterior": {"type": "number"}, "condicao": {"type": "string"},
    "validade": {"type": "string", "description": "AAAA-MM-DD, só se a oferta tiver data própria"}}}
ESQUEMA = {"type": "object", "additionalProperties": False, "required": ["ofertas"], "properties": {
    "validade_inicio": {"type": "string", "description": "AAAA-MM-DD ou vazio"},
    "validade_fim": {"type": "string", "description": "AAAA-MM-DD ou vazio"},
    "ofertas": {"type": "array", "items": _OFERTA}}}

TIPOS_ACEITOS = {"application/pdf": "pdf", "image/jpeg": "imagem", "image/png": "imagem", "image/webp": "imagem"}


def tipo_do_arquivo(tipo: str, url: str, dados: bytes) -> str | None:
    """O mime_type que vai para o Gemini, olhando o cabeçalho, a extensão e os primeiros bytes."""
    if tipo in TIPOS_ACEITOS:
        return tipo
    if dados[:5] == b"%PDF-" or url.lower().split("?")[0].endswith(".pdf"):
        return "application/pdf"
    if dados[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return None


async def extrair(encarte: Encarte, dados: bytes, mime_type: str) -> dict:
    """{"validade_inicio", "validade_fim", "ofertas": [...]} lidos do encarte."""
    validade = ""
    if encarte.validade_fim:
        validade = f" O site informa validade de {encarte.validade_inicio or '?'} até {encarte.validade_fim}."
    pedido = (f"Encarte da rede {encarte.mercado} ({encarte.titulo}), lojas: {encarte.lojas or 'Goiânia'}.{validade} "
              "Extraia as ofertas.")
    mensagem = {"papel": "usuario", "texto": pedido,
                "anexo": {"tipo": TIPOS_ACEITOS[mime_type], "mime_type": mime_type, "dados": dados}}
    resposta = await roteador.gerar("coletor", sistema=prompts.EXTRAIR_ENCARTE, mensagens=[mensagem],
                                    esquema_json=ESQUEMA, tempo=TEMPO)
    try:
        lido = json.loads(resposta.texto)
    except ValueError as erro:
        raise ErroIA(f"o Gemini não devolveu JSON para o encarte '{encarte.titulo}'") from erro
    ofertas = [o for o in (lido.get("ofertas") or []) if isinstance(o, dict)][:MAX_OFERTAS]
    return {"validade_inicio": lido.get("validade_inicio") or "", "validade_fim": lido.get("validade_fim") or "",
            "ofertas": ofertas}
