"""C15 "Onde comprar": quanto a lista atual sai em cada mercado, sem depender do Telegram.

- Cada item custa o preço da promoção daquele mercado (quando houver uma que combine com o
  item) ou o preço estimado do plano. A promoção é convertida para a quantidade que a lista
  precisa ("arroz 1 kg por R$ 5" para quem precisa de 5 kg = 5 pacotes).
- Os 3 mercados mais baratos, com total, distância (quando a pessoa mandou a localização) e
  quantos itens têm preço real.
- Dividir entre 2 mercados só aparece se economizar pelo menos R$ 15.
- Avisa as condições das promoções usadas (só sócio, só no app, leve X pague Y...).
"""
import math
import re
from dataclasses import dataclass, field

import banco
import cardapio
import cesta
import promocoes
import restricoes

ECONOMIA_MINIMA_DIVISAO = 15.0
_FATOR = {"kg": ("g", 1000), "g": ("g", 1), "ml": ("ml", 1), "L": ("ml", 1000), "un": ("un", 1)}


@dataclass
class Item:
    chave: str
    nome: str
    custo: float
    promocao: dict | None = None     # a promoção usada (None = estimado)


@dataclass
class Mercado:
    nome: str
    itens: list[Item] = field(default_factory=list)
    distancia_km: float | None = None

    @property
    def total(self) -> float:
        return round(sum(i.custo for i in self.itens), 2)

    @property
    def com_promocao(self) -> int:
        return sum(1 for i in self.itens if i.promocao)


def quantidade(tamanho: str | None) -> tuple[str, float] | None:
    """'5 kg' -> ('g', 5000); '1,5 L' -> ('ml', 1500); '30 un' -> ('un', 30)."""
    achado = re.match(r"^\s*(\d+(?:,\d+)?)\s*(kg|g|ml|L|un)\b", promocoes.tamanho(tamanho) or "")
    if not achado:
        return None
    unidade, fator = _FATOR[achado.group(2)]
    return unidade, float(achado.group(1).replace(",", ".")) * fator


def custo_com_promocao(linha: dict, promo: dict) -> float | None:
    """Quanto a linha custa comprando as embalagens da promoção. None = não dá para comparar."""
    precisa = max(0.0, float(linha.get("precisa") or 0) - float(linha.get("da_despensa") or 0))
    qtd = quantidade(promo.get("tamanho"))
    if qtd is None:
        if "kg" in (promo.get("condicao") or "").lower() and linha["unidade"] == "g":
            qtd = ("g", 1000.0)             # "preço por kg"
        else:
            return round(linha["pacotes"] * promo["preco"], 2)   # sem tamanho: a mesma embalagem da lista
    unidade, por_embalagem = qtd
    if unidade != linha["unidade"] or por_embalagem <= 0 or precisa <= 0:
        return None
    return round(math.ceil(precisa / por_embalagem - 1e-9) * promo["preco"], 2)


def _promos_por_mercado(perfil: dict) -> dict[str, list[dict]]:
    cidade = perfil.get("cidade") or promocoes.CIDADE_PADRAO
    restr, outras = perfil.get("restricoes") or [], perfil.get("restricoes_outras")
    grupos: dict[str, list[dict]] = {}
    for p in banco.promocoes_validas(cidade=cidade, limite=5000):
        if restricoes.violacoes(p["produto"], restr, outras):
            continue
        grupos.setdefault(restricoes.normalizar(p["mercado"]), []).append(p)
    return grupos


def _nomes_dos_mercados(perfil: dict, grupos: dict[str, list[dict]]) -> dict[str, str]:
    """chave -> nome para mostrar. Os mercados com promoção e os que a pessoa escolheu no cadastro."""
    nomes = {k: v[0]["mercado"] for k, v in grupos.items()}
    for m in perfil.get("mercados") or []:
        if m != "qualquer":
            nome = cardapio.MERCADOS.get(m, m).split("/")[0]
            chave = restricoes.normalizar(nome)
            if not any(chave in k or k in chave for k in nomes):
                nomes[chave] = nome
    return nomes


def comparar(plano: dict, perfil: dict, distancias: dict[str, float] | None = None) -> list[Mercado]:
    """Todos os mercados, do mais barato para o mais caro."""
    grupos = _promos_por_mercado(perfil)
    cesta_linhas = [l for l in plano["cesta"]["linhas"] if l["pacotes"] > 0]
    mercados = []
    for chave, nome in _nomes_dos_mercados(perfil, grupos).items():
        promos = grupos.get(chave, [])
        mercado = Mercado(nome=nome, distancia_km=(distancias or {}).get(chave))
        for linha in cesta_linhas:
            melhor: tuple[float, dict] | None = None
            for p in promos:
                if not promocoes.combina(linha["item"], p["produto"]):
                    continue
                custo = custo_com_promocao(linha, p)
                if custo is not None and (melhor is None or custo < melhor[0]):
                    melhor = (custo, p)
            if melhor:
                mercado.itens.append(Item(cesta.chave(linha["item"]), linha["nome"], melhor[0], melhor[1]))
            else:
                mercado.itens.append(Item(cesta.chave(linha["item"]), linha["nome"], linha["custo"]))
        mercados.append(mercado)
    return sorted(mercados, key=lambda m: (m.total, -m.com_promocao, m.nome))


@dataclass
class Divisao:
    mercados: tuple[str, str]
    itens: dict[str, str]          # chave do item -> nome do mercado
    total: float
    economia: float                # em relação ao melhor mercado sozinho


def melhor_divisao(mercados: list[Mercado]) -> Divisao | None:
    """O melhor par de mercados, só se economizar pelo menos R$ 15 sobre o melhor sozinho."""
    if len(mercados) < 2:
        return None
    melhor_sozinho = mercados[0].total
    escolhida = None
    for i, a in enumerate(mercados):
        for b in mercados[i + 1:]:
            custos_b = {item.chave: item for item in b.itens}
            itens, total = {}, 0.0
            for item_a in a.itens:
                item_b = custos_b.get(item_a.chave)
                if item_b is not None and item_b.custo < item_a.custo:
                    itens[item_a.chave], total = b.nome, total + item_b.custo
                else:
                    itens[item_a.chave], total = a.nome, total + item_a.custo
            total = round(total, 2)
            if escolhida is None or total < escolhida.total:
                escolhida = Divisao((a.nome, b.nome), itens, total, round(melhor_sozinho - total, 2))
    if escolhida is None or escolhida.economia < ECONOMIA_MINIMA_DIVISAO:
        return None
    if len(set(escolhida.itens.values())) < 2:
        return None
    return escolhida


def condicoes(mercados: list[Mercado]) -> list[str]:
    """Condições das promoções usadas nos 3 primeiros mercados ('arroz no Assaí: só no app')."""
    avisos = []
    for m in mercados[:3]:
        for item in m.itens:
            if item.promocao and item.promocao.get("condicao"):
                avisos.append(f"{item.nome} no {m.nome}: {item.promocao['condicao']}")
    return avisos


def porcentagem_real(mercado: Mercado) -> int:
    return round(100 * mercado.com_promocao / len(mercado.itens)) if mercado.itens else 0
