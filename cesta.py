"""Calcula a cesta EM CÓDIGO: compra por embalagem, despensa, custo por refeição e total.

A IA escolhe os pratos, as quantidades que cada prato usa e as embalagens que
existem no mercado (com preço). Daqui em diante é só conta:
- soma o que a semana precisa de cada item;
- desconta o que já está na despensa;
- compra embalagens inteiras ("1 pacote de 5 kg", nunca "350 g de arroz");
- o que sobrar de item não perecível vai para a despensa da semana seguinte.
"""
import math

from restricoes import normalizar

# Porção: adulto = 1, criança = meia porção
def porcoes(adultos: int | None, criancas: int | None) -> float:
    return float(adultos or 0) + 0.5 * float(criancas or 0)


def porcoes_txt(valor: float) -> str:
    """2.5 -> '2,5 porções'; 1 -> '1 porção'."""
    numero = f"{valor:g}".replace(".", ",")
    return f"{numero} porção" if valor == 1 else f"{numero} porções"


def chave(item: str) -> str:
    return normalizar(item)


def _arredondar(valor: float) -> float:
    return round(valor + 1e-9, 2)


def calcular(plano: dict, despensa: dict | None = None) -> dict:
    """Recebe o plano da IA (refeicoes + produtos) e a despensa, e devolve:
    {"linhas": [...], "total": float, "custo_refeicoes": [float por refeição],
     "despensa_final": {...}, "sem_produto": [itens sem embalagem], "unidade_errada": [...]}"""
    despensa = {chave(k): dict(v) for k, v in (despensa or {}).items()}
    produtos = {}
    for p in plano.get("produtos", []):
        produtos.setdefault(chave(p["item"]), p)  # se a IA repetir o item, vale o primeiro

    necessidade: dict[str, float] = {}
    sem_produto, unidade_errada = [], []
    for ref in plano.get("refeicoes", []):
        for ing in ref.get("ingredientes", []):
            k = chave(ing["item"])
            produto = produtos.get(k)
            if produto is None:
                sem_produto.append(ing["item"])
                continue
            if ing.get("unidade") != produto.get("unidade"):
                unidade_errada.append(f"{ing['item']} ({ing.get('unidade')} x {produto.get('unidade')})")
                continue
            necessidade[k] = necessidade.get(k, 0.0) + float(ing.get("quantidade") or 0)

    linhas, total = [], 0.0
    despensa_final = {k: dict(v) for k, v in despensa.items()}
    for k, precisa in necessidade.items():
        p = produtos[k]
        tamanho, preco = float(p["tamanho"]), float(p["preco"])
        em_casa = despensa.get(k, {})
        mesma_unidade = em_casa.get("unidade") == p["unidade"]
        qtd_casa = float(em_casa.get("quantidade", 0)) if mesma_unidade else 0.0
        usa_de_casa = min(precisa, qtd_casa)
        comprar = max(0.0, precisa - usa_de_casa)
        pacotes = math.ceil(comprar / tamanho - 1e-9) if comprar > 0 else 0
        custo = _arredondar(pacotes * preco)
        sobra = pacotes * tamanho - comprar
        total += custo

        # despensa da semana seguinte: o que estava em casa menos o que foi usado,
        # mais o que sobrar das embalagens (só itens que não estragam).
        # Se a unidade em casa for outra (ex.: "un" x "g"), o item de casa fica como está.
        if mesma_unidade or not em_casa:
            restante = qtd_casa - usa_de_casa + (sobra if not p.get("perecivel", True) else 0.0)
            if restante > 0.5:
                despensa_final[k] = {"item": p["item"], "quantidade": round(restante), "unidade": p["unidade"]}
            else:
                despensa_final.pop(k, None)

        linhas.append({
            "item": p["item"], "nome": p.get("nome") or p["item"], "embalagem": p["embalagem"],
            "pacotes": pacotes, "preco_embalagem": preco, "custo": custo, "secao": p.get("secao", "Outros"),
            "promocao_id": int(p.get("promocao_id") or 0), "perecivel": bool(p.get("perecivel", True)),
            "precisa": round(precisa), "da_despensa": round(usa_de_casa), "unidade": p["unidade"],
        })

    custo_refeicoes = []  # na mesma ordem de plano["refeicoes"]
    for ref in plano.get("refeicoes", []):
        custo = 0.0
        for ing in ref.get("ingredientes", []):
            p = produtos.get(chave(ing["item"]))
            if p and ing.get("unidade") == p.get("unidade") and float(p["tamanho"]) > 0:
                custo += float(ing.get("quantidade") or 0) * float(p["preco"]) / float(p["tamanho"])
        custo_refeicoes.append(_arredondar(custo))

    linhas.sort(key=lambda l: (l["secao"], normalizar(l["nome"])))
    return {"linhas": linhas, "total": _arredondar(total), "custo_refeicoes": custo_refeicoes,
            "despensa_final": despensa_final, "sem_produto": sorted(set(sem_produto)),
            "unidade_errada": sorted(set(unidade_errada))}


def texto_embalagem(linha: dict) -> str:
    """'1 pacote 5 kg', '2 x bandeja 30 ovos'."""
    if linha["pacotes"] <= 1:
        return f"1 {linha['embalagem']}"
    return f"{linha['pacotes']} x {linha['embalagem']}"
