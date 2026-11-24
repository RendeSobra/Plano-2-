"""Roda a coleta uma vez, sem o bot:

    .venv\\Scripts\\python -m coletor                 (todas as redes)
    .venv\\Scripts\\python -m coletor prezunic diaadia --max 2 --banco teste.db

--max N: no máximo N encartes por rede; --banco: outro arquivo de banco (para teste);
--listar: só lista os encartes vigentes de cada rede (não baixa os arquivos nem chama a IA).
Usa o GEMINI_API_KEY do .env (só o Gemini; o coletor nunca chama o Claude).
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import banco  # noqa: E402
import coletor  # noqa: E402
from bot_telegram import sem_formatacao  # noqa: E402


async def listar(redes: list[str]) -> None:
    async with coletor.Navegador() as nav:
        for nome in redes:
            try:
                encartes = await coletor.REDES[nome].coletar(nav)
            except Exception as erro:
                print(f"\n{nome}: ERRO {type(erro).__name__}: {erro}")
                continue
            print(f"\n{nome}: {len(encartes)} encartes vigentes")
            for e in encartes:
                fora = " (fora do cardápio: não seria lido)" if coletor._fora_do_cardapio(e) else ""
                print(f"  - {e.titulo} | {e.validade_inicio or '?'} a {e.validade_fim or '?'} | {e.url}{fora}")
        print(f"\nrequisições feitas: {nav.requisicoes}")


def main() -> None:
    args = argparse.ArgumentParser(description="Coleta as promoções dos sites das redes de Goiânia.")
    args.add_argument("redes", nargs="*", help=f"redes: {', '.join(coletor.REDES)} (padrão: todas)")
    args.add_argument("--max", type=int, help="máximo de encartes por rede")
    args.add_argument("--banco", help="arquivo do banco (padrão: o do .env)")
    args.add_argument("--listar", action="store_true", help="só lista os encartes (sem IA)")
    opcoes = args.parse_args()
    desconhecidas = [r for r in opcoes.redes if r not in coletor.REDES]
    if desconhecidas:
        args.error(f"rede desconhecida: {', '.join(desconhecidas)}")
    if opcoes.max:
        os.environ["COLETOR_MAX_ENCARTES"] = str(opcoes.max)
    logging.getLogger("rende").setLevel(logging.INFO)
    if opcoes.listar:
        asyncio.run(listar(opcoes.redes or list(coletor.REDES)))
        return
    banco.conectar(opcoes.banco)
    resultados = asyncio.run(coletor.coletar(opcoes.redes or None))
    print(sem_formatacao(coletor.texto_resultado(resultados)))
    for linha in coletor.falhas(resultados):
        print("ERRO:", linha)


if __name__ == "__main__":
    main()
