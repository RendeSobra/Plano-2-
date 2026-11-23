"""Formatos comuns aos adaptadores de IA (ia.py = Gemini, ia_claude.py = Claude).

Os dois recebem a mesma entrada e devolvem uma RespostaIA. Assim o roteador
troca de modelo sem que o resto do código perceba.

sistema = instruções fixas (iguais em toda chamada: o Claude guarda em cache);
sistema_extra = parte que muda (perfil, plano atual, data).

Mensagens (lista de dicts, em ordem):
  {"papel": "usuario", "texto": "...", "anexo": {"mime_type": "...", "dados": b"..."}}  (anexo opcional)
  {"papel": "assistente", "texto": "...", "chamadas": [Chamada...], "bruto": {...}}      (chamadas/bruto opcionais)
  {"papel": "ferramenta", "resultados": [{"id": "...", "nome": "...", "conteudo": {...}}]}

Ferramentas (lista de dicts): {"nome": "...", "descricao": "...", "parametros": <JSON Schema>}
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chamada:
    """A IA pediu para rodar uma ferramenta."""
    id: str
    nome: str
    args: dict


@dataclass
class RespostaIA:
    texto: str = ""
    chamadas: list[Chamada] = field(default_factory=list)
    provedor: str = ""          # 'gemini' ou 'claude'
    modelo: str = ""
    tokens_entrada: int = 0     # entrada sem cache
    tokens_saida: int = 0       # inclui os tokens de "raciocínio", que também são cobrados
    cache_leitura: int = 0      # tokens lidos do cache (bem mais baratos)
    cache_escrita: int = 0      # tokens gravados no cache nesta chamada
    nivel: str = ""             # preenchido pelo roteador: 'gemini', 'haiku', 'sonnet', 'opus'...
    recusou: bool = False       # o modelo se recusou a responder (vai para o fallback)
    # Resposta original do provedor. No mesmo turno, ela volta intacta para o mesmo
    # provedor (o Claude exige os blocos de raciocínio; o Gemini 3, as assinaturas).
    bruto: Any = None
    motivo: str = ""            # preenchido pelo roteador: por que este modelo foi usado
    problemas: list[str] = field(default_factory=list)  # preenchido pelo roteador na validação


class ErroIA(Exception):
    """A IA não conseguiu responder (rede, sobrecarga, chave inválida, cota...)."""

    def __init__(self, mensagem: str, *, cota: bool = False):
        super().__init__(mensagem)
        self.cota = cota  # True quando o erro foi de cota/limite de uso (HTTP 429)
