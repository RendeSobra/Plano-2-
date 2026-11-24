"""Mede quanto custa gerar um cardápio no Sonnet (formato compacto, pedido de 24/11).

Dois modos:
  .venv\\Scripts\\python testes\\medir_cardapio.py            estimativa GRÁTIS
  .venv\\Scripts\\python testes\\medir_cardapio.py --real     UMA chamada paga ao Sonnet (até US$ 0,15)

Os dois usam o mesmo perfil do teste real de 23/11 (2 adultos + 1 criança, café/almoço/jantar,
7 dias, comida de vó, sem lactose, fogão + pressão, Assaí, R$ 300 por semana).

Estimativa: conta os tokens com a contagem da Anthropic (count_tokens, que não é cobrada) e
usa o cardápio real de 23/11 (testes/dados/plano_23_11.json) convertido para o formato
compacto. O raciocínio do modelo não aparece no texto: é estimado a partir do teste de 23/11.

Modo real: não grava nada no rende.db (usa um banco na memória), limita a resposta a
13 mil tokens (no pior caso, US$ 0,14) e mostra se o cardápio passou na conferência em código.
"""
import argparse
import asyncio
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / ".env")

import anthropic  # noqa: E402

import banco  # noqa: E402
import cardapio  # noqa: E402
import cesta  # noqa: E402
import ia_claude  # noqa: E402
import prompts  # noqa: E402
import roteador  # noqa: E402

SONNET = (os.getenv("CLAUDE_MODELO_PADRAO") or "claude-sonnet-5-5").strip()
TETO_REAL_USD = 0.15
MAX_TOKENS_REAL = 13_000

# Teste real de 23/11 (tabela uso_ia): Sonnet com effort "medium", formato antigo.
ANTES = {"entrada": 557, "cache_escrita": 2329, "saida": 12_444, "json_antigo": 7_446,
         "custo_sonnet": 0.131, "custo_com_opus": 0.334}
ANTES_24_11 = 0.357  # Sonnet cortado (16 mil tokens) + Opus refazendo
RACIOCINIO_MEDIUM = ANTES["saida"] - ANTES["json_antigo"]  # ~5 mil tokens
RACIOCINIO_LOW = (1_500, 2_500)  # suposição; a rodada real confirma

PERFIL = dict(nome="Teste", adultos=2, criancas=1, refeicoes=["cafe", "almoco", "jantar"],
              dias=[d for d, _ in cardapio.DIAS], vibe="vo", restricoes=["lactose"],
              utensilios=["fogao", "pressao"], mercados=["assai"], periodo="semana", orcamento=300.0,
              cidade="Goiânia", cadastro_passo=None)


def preparar() -> tuple[str, str]:
    """Banco na memória com o perfil de 23/11; devolve (usuário, briefing que a IA recebe)."""
    banco.conectar(":memory:")
    banco.obter_ou_criar_usuario("medicao")
    perfil = banco.atualizar_perfil("medicao", **PERFIL)
    briefing = cardapio._briefing_plano("medicao", perfil, {}, [], "")
    return "medicao", briefing


def compacto_do_plano_real() -> dict:
    """Converte o plano de 23/11 para o formato compacto, agrupando cafés iguais."""
    dados = json.loads((RAIZ / "testes" / "dados" / "plano_23_11.json").read_text(encoding="utf-8"))
    grupos: OrderedDict = OrderedDict()
    for r in dados["refeicoes"]:
        ingr = [{"item": i["item"], "qtd": i["quantidade"]} for i in r["ingredientes"]]
        sobra = r.get("sobra_planejada") or ""
        sobra = sobra if cardapio.sobra_util(sobra) else ""
        chave = ((r["tipo"], r["prato"], json.dumps(ingr)) if r["tipo"] not in cardapio.PRINCIPAIS
                 else (r["dia"], r["tipo"]))
        if chave in grupos:
            grupos[chave]["dias"].append(r["dia"])
        else:
            grupos[chave] = {"dias": [r["dia"]], "tipo": r["tipo"], "prato": r["prato"], "min": r["tempo_min"],
                             "equip": r["equipamentos"], "ingr": ingr, "sobra": sobra}
    compras = [{"item": p["item"], "emb": p["embalagem"], "tam": p["tamanho"], "un": p["unidade"],
                "preco": p["preco"], "secao": p["secao"], "promo": p["promocao_id"]} for p in dados["produtos"]]
    return {"refeicoes": list(grupos.values()), "compras": compras}


def contar(cliente: anthropic.Anthropic, texto: str) -> int:
    """Tokens de um texto (count_tokens não é cobrado)."""
    base = cliente.messages.count_tokens(model=SONNET, messages=[{"role": "user", "content": "x"}]).input_tokens
    com = cliente.messages.count_tokens(model=SONNET, messages=[{"role": "user", "content": "x" + texto}]).input_tokens
    return com - base


def usd(valor: float) -> str:
    return f"US$ {valor:.3f}"


def estimar() -> None:
    cliente = anthropic.Anthropic()
    _, briefing = preparar()
    sistema = contar(cliente, prompts.PLANO) + contar(cliente, json.dumps(cardapio.ESQUEMA_PLANO, ensure_ascii=False))
    entrada = contar(cliente, briefing)
    json_novo = contar(cliente, json.dumps(compacto_do_plano_real(), ensure_ascii=False, separators=(",", ":")))
    preco_e, preco_s, _ = roteador.PRECOS[SONNET]
    custo_entrada = (sistema * preco_e * roteador.ESCRITA_CACHE + entrada * preco_e) / 1e6

    def custo(raciocinio: int) -> float:
        return custo_entrada + (json_novo + raciocinio) * preco_s / 1e6

    print("ANTES (teste real de 23/11, formato antigo, Sonnet effort medium)")
    print(f"  saída {ANTES['saida']:,} tokens (JSON ~{ANTES['json_antigo']:,} + raciocínio ~{RACIOCINIO_MEDIUM:,})")
    print(f"  Sonnet {usd(ANTES['custo_sonnet'])}; com o Opus refazendo {usd(ANTES['custo_com_opus'])}"
          f" (24/11: {usd(ANTES_24_11)})")
    print("\nDEPOIS (estimativa, formato compacto)")
    print(f"  instruções fixas ~{sistema:,} tokens (cache) · pedido ~{entrada:,} tokens")
    print(f"  JSON do cardápio ~{json_novo:,} tokens ({1 - json_novo / ANTES['json_antigo']:.0%} menor)")
    print(f"  effort medium: raciocínio ~{RACIOCINIO_MEDIUM:,} -> {usd(custo(RACIOCINIO_MEDIUM))}")
    lo, hi = RACIOCINIO_LOW
    print(f"  effort low:    raciocínio ~{lo:,}-{hi:,} (suposição) -> {usd(custo(lo))} a {usd(custo(hi))}")
    print("  meta: Sonnet sozinho abaixo de US$ 0,080")


async def real(salvar: str | None) -> None:
    if not ia_claude.disponivel():
        sys.exit("Falta ANTHROPIC_API_KEY no .env")
    usuario, briefing = preparar()
    perfil = banco.usuario(usuario)
    esforco = roteador.esforco(roteador.claude("sonnet"), "cardapio")
    preco_e, preco_s, _ = roteador.PRECOS[SONNET]
    teto = (3_000 * preco_e * roteador.ESCRITA_CACHE + 1_000 * preco_e + MAX_TOKENS_REAL * preco_s) / 1e6
    if teto > TETO_REAL_USD:
        sys.exit(f"Pior caso {usd(teto)} passa do teto combinado ({usd(TETO_REAL_USD)})")
    print(f"Chamando {SONNET} (effort {esforco}, até {MAX_TOKENS_REAL:,} tokens; pior caso {usd(teto)})...")
    ia_claude.MAX_TOKENS = MAX_TOKENS_REAL
    resposta = await ia_claude.gerar(modelo=SONNET, sistema=prompts.PLANO,
                                     mensagens=[{"papel": "usuario", "texto": briefing}],
                                     esquema_json=cardapio.ESQUEMA_PLANO, esforco=esforco, tempo=300)
    custo = roteador.custo_usd(SONNET, resposta.tokens_entrada, resposta.tokens_saida,
                               resposta.cache_leitura, resposta.cache_escrita)
    json_tokens = contar(anthropic.Anthropic(), resposta.texto)
    print(f"tokens: entrada {resposta.tokens_entrada:,} · cache gravado {resposta.cache_escrita:,} · "
          f"lido {resposta.cache_leitura:,} · saída {resposta.tokens_saida:,} "
          f"(JSON ~{json_tokens:,} + raciocínio ~{resposta.tokens_saida - json_tokens:,})")
    print(f"custo: {usd(custo)}  (antes: Sonnet {usd(ANTES['custo_sonnet'])}; com Opus {usd(ANTES['custo_com_opus'])})")
    try:
        plano = cardapio.expandir(cardapio.ler_json(resposta.texto))
    except (ValueError, KeyError, TypeError) as erro:
        print(f"JSON inválido: {erro}")
        return
    calc = cesta.calcular(plano, {})
    graves, avisos = cardapio.conferir(plano, perfil, calc, cardapio.orcamento_semanal(perfil))
    print(f"cardápio: {len(plano['refeicoes'])} refeições, {len(plano['produtos'])} compras, "
          f"total R$ {calc['total']:.2f} de R$ {cardapio.orcamento_semanal(perfil):.2f}")
    print("conferência em código: " + ("APROVADO (o Opus não seria chamado)" if not graves
                                       else "REPROVADO (o Opus refaria): " + "; ".join(graves)))
    if avisos:
        print("avisos: " + "; ".join(avisos))
    if salvar:
        Path(salvar).write_text(json.dumps({"texto": resposta.texto, "custo_usd": custo,
                                            "tokens_saida": resposta.tokens_saida, "graves": graves},
                                           ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"resposta salva em {salvar}")


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("--real", action="store_true", help="faz UMA chamada paga ao Sonnet (até US$ 0,15)")
    args.add_argument("--salvar", help="arquivo para guardar a resposta do modo real")
    a = args.parse_args()
    asyncio.run(real(a.salvar)) if a.real else estimar()
