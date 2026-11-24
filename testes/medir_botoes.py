"""Mede o caminho BOTÃO -> TEXTO: quanto tempo o Rende gasta do toque até a tela ficar pronta.

Não chama IA nem Telegram. Usa um banco em ARQUIVO (não na memória), porque boa parte do
custo são os commits do SQLite — num banco de memória eles somem e a medida mente.

    .venv\\Scripts\\python testes\\medir_botoes.py

O que NÃO entra aqui: a ida e volta até a API do Telegram (medida à parte, ~220 ms por
chamada a partir de Goiânia). O relatório soma as duas coisas.
"""
import asyncio
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456789:AAbbCCddEEffGGhhIIjjKKllMMnnOOppQQr")
os.environ.setdefault("GEMINI_API_KEY", "chave-de-teste")
os.environ.setdefault("GEMINI_MODEL", "gemini-3.5-flash-lite")
os.environ["LIMITE_MSG_DIA"] = "100000"

import atendimento  # noqa: E402
import banco  # noqa: E402
import cardapio  # noqa: E402
import cesta  # noqa: E402

USUARIO = "medidor"
REPETICOES = 25

COMPRAS = [
    ("Arroz", "pacote 5 kg", 5000, "g", 24.90, "Mercearia"),
    ("Feijão carioca", "pacote 1 kg", 1000, "g", 7.49, "Mercearia"),
    ("Frango", "bandeja 1 kg", 1000, "g", 14.90, "Açougue e aves"),
    ("Carne moída", "bandeja 500 g", 500, "g", 19.90, "Açougue e aves"),
    ("Ovo", "bandeja 30 un", 30, "un", 18.90, "Ovos e laticínios"),
    ("Macarrão", "pacote 500 g", 500, "g", 4.29, "Mercearia"),
    ("Batata", "saco 2 kg", 2000, "g", 9.90, "Hortifrúti"),
    ("Cebola", "kg", 1000, "g", 5.90, "Hortifrúti"),
    ("Tomate", "kg", 1000, "g", 8.90, "Hortifrúti"),
    ("Cenoura", "kg", 1000, "g", 5.49, "Hortifrúti"),
    ("Couve", "maço", 300, "g", 3.90, "Hortifrúti"),
    ("Abóbora", "kg", 1000, "g", 4.90, "Hortifrúti"),
    ("Pão francês", "kg", 1000, "g", 14.90, "Padaria"),
    ("Café", "pacote 500 g", 500, "g", 17.90, "Mercearia"),
    ("Açúcar", "pacote 1 kg", 1000, "g", 4.49, "Mercearia"),
    ("Óleo", "garrafa 900 ml", 900, "ml", 7.90, "Mercearia"),
    ("Farinha de mandioca", "pacote 500 g", 500, "g", 5.90, "Mercearia"),
    ("Banana", "kg", 1000, "g", 5.90, "Hortifrúti"),
    ("Alho", "pacote 200 g", 200, "g", 9.90, "Temperos e outros"),
    ("Sal", "pacote 1 kg", 1000, "g", 2.49, "Temperos e outros"),
]
PRATOS = [("Arroz, feijão e frango grelhado", [("Arroz", 400), ("Feijão carioca", 200), ("Frango", 600)]),
          ("Macarrão com carne moída", [("Macarrão", 400), ("Carne moída", 400), ("Tomate", 300)]),
          ("Galinhada goiana", [("Arroz", 400), ("Frango", 500), ("Cebola", 150)]),
          ("Ovos mexidos com couve", [("Ovo", 6), ("Couve", 150), ("Óleo", 30)]),
          ("Sopa de legumes", [("Batata", 400), ("Cenoura", 300), ("Abóbora", 400)]),
          ("Bife de panela com purê", [("Carne moída", 500), ("Batata", 600), ("Cebola", 100)]),
          ("Café com pão", [("Café", 50), ("Pão francês", 300), ("Açúcar", 60)])]


def montar_plano_realista() -> dict:
    """Um plano do tamanho de um real: 7 dias x 3 refeições = 21 refeições, 20 produtos."""
    compras = [{"item": i, "emb": e, "tam": t, "un": u, "preco": p, "secao": s, "promo": 0}
               for i, e, t, u, p, s in COMPRAS]
    refeicoes = []
    for n, (prato, ingredientes) in enumerate(PRATOS):
        tipo = ("cafe", "almoco", "jantar")[n % 3]
        refeicoes.append({"dias": [cardapio.DIAS[n][0]], "tipo": tipo, "prato": prato, "min": 30,
                          "equip": ["fogao"], "sobra": "",
                          "ingr": [{"item": i, "qtd": q} for i, q in ingredientes]})
    # completa os 21 horários da semana
    for d, _ in cardapio.DIAS:
        for tipo in ("cafe", "almoco", "jantar"):
            if not any(r["dias"] == [d] and r["tipo"] == tipo for r in refeicoes):
                base = PRATOS[(len(refeicoes)) % len(PRATOS)]
                refeicoes.append({"dias": [d], "tipo": tipo, "prato": base[0], "min": 30,
                                  "equip": ["fogao"], "sobra": "",
                                  "ingr": [{"item": i, "qtd": q} for i, q in base[1]]})
    plano = cardapio.expandir({"refeicoes": refeicoes, "compras": compras})
    calc = cesta.calcular(plano, {})
    return {**plano, "cesta": calc, "orcamento": 400.0, "porcoes": 2.5, "despensa_inicial": {},
            "receitas": {}, "promocoes": {}, "modelo": "medicao", "nivel": "sonnet",
            "semana": banco.semana_atual()}


def preparar(caminho: str) -> dict:
    banco.conectar(caminho)
    banco.atualizar_perfil(USUARIO, nome="Medidor", adultos=2, criancas=1,
                           refeicoes=["cafe", "almoco", "jantar"], dias=[d for d, _ in cardapio.DIAS],
                           vibe="vo", restricoes=[], utensilios=["fogao", "pressao"], mercados=["assai"],
                           periodo="semana", orcamento=400.0, cidade="Goiânia", cadastro_passo=None)
    conteudo = montar_plano_realista()
    conteudo["id"] = banco.salvar_plano(USUARIO, conteudo)
    return conteudo


def medir(nome: str, acao: str) -> float:
    tempos = []
    for _ in range(REPETICOES):
        inicio = time.perf_counter()
        asyncio.run(atendimento.acao(USUARIO, acao))
        tempos.append((time.perf_counter() - inicio) * 1000)
    mediana = statistics.median(tempos)
    print(f"  {nome:<34} {mediana:6.1f} ms   (min {min(tempos):5.1f} / max {max(tempos):6.1f})")
    return mediana


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as pasta:
        plano = preparar(os.path.join(pasta, "medicao.db"))
        print(f"Plano de teste: {len(plano['refeicoes'])} refeições, {len(plano['produtos'])} produtos, "
              f"{len(plano['cesta']['linhas'])} itens na lista\n")
        print(f"Trabalho do Rende por toque de botão (sem rede), mediana de {REPETICOES} execuções:")
        total = 0.0
        total += medir("Resumo do plano (pl:res)", "pl:res")
        total += medir("Cardápio de um dia (pl:dia)", "pl:dia:seg")
        total += medir("Lista de compras (pl:lista)", "pl:lista")
        total += medir("Perfil (per:ver)", "per:ver")
        total += medir("Modo mercado: abrir (mm:ver)", "mm:ver")
        total += medir("Modo mercado: marcar item (mm:t)", f"mm:t:{plano['id']}:0")
        print(f"\n  média por botão: {total / 6:.1f} ms")
        print("\nPara comparar: UMA chamada à API do Telegram custa ~220 ms a partir de Goiânia.")
        if banco._conexao is not None:  # o Windows não apaga a pasta com o arquivo ainda aberto
            banco._conexao.close()
            banco._conexao = None


if __name__ == "__main__":
    main()
