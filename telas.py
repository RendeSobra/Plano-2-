"""Telas do Rende (texto + botões), sem depender do Telegram.

O canal (hoje bot_telegram.py) só desenha: Saida.texto vira a mensagem e
Saida.botoes vira o teclado de botões. `acao` é o que volta quando o botão é tocado
(curto: o Telegram aceita até 64 bytes).
"""
import math
from dataclasses import dataclass, field
from datetime import date

import cesta
from cardapio import DIAS, ETAPAS, ICONE_REFEICAO, NOME_DIA, NOME_REFEICAO, REFEICOES, sobra_util


@dataclass
class Botao:
    rotulo: str
    acao: str


@dataclass
class Saida:
    tipo: str = "texto"          # 'texto' | 'documento' | 'pedir_localizacao' | 'acao'
    texto: str = ""
    botoes: list[list[Botao]] = field(default_factory=list)
    editar: bool = False         # substitui a mensagem do botão tocado (navegação)
    dados: bytes | None = None   # documento (ex.: PDF), só na memória
    nome_arquivo: str = ""
    apagar_apos: float = 0       # segundos até a mensagem sumir sozinha (0 = fica)
    acao: str = ""               # tipo 'acao': o canal executa (ex.: montar o plano com animação)


def texto(t: str) -> Saida:
    return Saida(texto=t)


def tela(t: str, botoes: list[list[Botao]], editar: bool = False) -> Saida:
    return Saida(texto=t, botoes=botoes, editar=editar)


def brl(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def data_br(iso: str) -> str:
    try:
        return date.fromisoformat(iso[:10]).strftime("%d/%m")
    except ValueError:
        return iso


# --- "Montando seu plano" ------------------------------------------------------
def progresso(atual: int, ajustando: bool = False, concluido: bool = False) -> str:
    linhas = ["✨ *Montando seu plano*", ""]
    for i, etapa in enumerate(ETAPAS):
        if concluido or i < atual:
            linhas.append(f"✅ {etapa}")
        elif i == atual:
            rotulo = "Ajustando as receitas" if (ajustando and i == 1) else etapa
            linhas.append(f"⏳ {rotulo}...")
    return "\n".join(linhas)


# --- resultado ------------------------------------------------------------------
def _botoes_resultado() -> list[list[Botao]]:
    return [[Botao("📅 Ver cardápio", "pl:dia"), Botao("🛒 Lista de compras", "pl:lista")],
            [Botao("📄 PDF da lista", "pl:pdf"), Botao("🔄 Refazer tudo", "pl:refazer")]]


def _botoes_acima_do_orcamento(plano: dict, perfil: dict) -> list[list[Botao]]:
    """Lacuna 3 (Pedido I): o plano passou do orçamento; a pessoa escolhe como resolver."""
    semanal = math.ceil(plano["cesta"]["total"] / 10 - 1e-9) * 10
    if perfil.get("periodo") == "mes":
        rotulo = f"💰 Aumentar para {brl(math.ceil(semanal * 4.3 / 10) * 10)}/mês"
    else:
        rotulo = f"💰 Aumentar para {brl(semanal)}"
    linha = [Botao(rotulo, "pl:ajo:orc")]
    if any(r["tipo"] == "lanche" for r in plano["refeicoes"]):
        linha.insert(0, Botao("✂️ Tirar lanches", "pl:ajo:lanches"))
    return [linha, [Botao("🥘 Pratos mais simples", "pl:ajo:simples")]]


def resultado(plano: dict, perfil: dict, editar: bool = False, aviso: str = "") -> Saida:
    total, orc = plano["cesta"]["total"], plano.get("orcamento") or 0
    itens = sum(1 for l in plano["cesta"]["linhas"] if l["pacotes"] > 0)
    nome = perfil.get("nome") or "você"
    topo = [aviso, ""] if aviso else []
    if total <= orc + 0.009:
        gasto = f"Gasto: *{brl(total)}* de {brl(orc)}. Sobrou *{brl(orc - total)}* 💰"
        t = "\n".join(topo + [f"*Sua semana está pronta, {nome}!* 🎉", "", gasto, f"🛒 {itens} itens na lista"])
        return tela(t, _botoes_resultado(), editar)
    t = "\n".join(topo + [
        f"*Sua semana está pronta, {nome}!*", "",
        f"⚠️ Não consegui fechar em {brl(orc)}: o melhor plano que achei ficou em *{brl(total)}*, "
        f"{brl(total - orc)} acima do orçamento.", f"🛒 {itens} itens na lista", "",
        "Como prefere resolver?"])
    return tela(t, _botoes_acima_do_orcamento(plano, perfil) + _botoes_resultado(), editar)


# --- cardápio por dia ------------------------------------------------------------
def dias_do_plano(plano: dict) -> list[str]:
    presentes = {r["dia"] for r in plano["refeicoes"]}
    return [d for d, _ in DIAS if d in presentes]


def dia(plano: dict, d: str | None = None, editar: bool = True, aviso: str = "") -> Saida:
    """Cardápio de um dia. `aviso` aparece no topo (ex.: confirmação de troca) e some ao navegar."""
    dias = dias_do_plano(plano)
    d = d if d in dias else dias[0]
    ordem = [r for r, _, _ in REFEICOES]
    refeicoes = sorted([(i, r) for i, r in enumerate(plano["refeicoes"]) if r["dia"] == d],
                       key=lambda par: ordem.index(par[1]["tipo"]))
    custos = plano["cesta"]["custo_refeicoes"]
    linhas = ([aviso, ""] if aviso else []) + [f"📅 *{NOME_DIA[d]}*", ""]
    botoes: list[list[Botao]] = []
    for i, r in refeicoes:
        linhas.append(f"{ICONE_REFEICAO[r['tipo']]} *{NOME_REFEICAO[r['tipo']]}* · "
                      f"{r.get('tempo_min', '?')} min · {brl(custos[i])}")
        linhas.append(r["prato"])
        if sobra_util(r.get("sobra_planejada")):
            linhas.append(f"♻️ {r['sobra_planejada']}")
        linhas.append("")
        botoes.append([Botao(f"📖 {NOME_REFEICAO[r['tipo']]}", f"pl:rec:{d}:{r['tipo']}"),
                       Botao("🔁 Trocar", f"pl:tro:{d}:{r['tipo']}")])
    pos = dias.index(d)
    anterior, proximo = dias[pos - 1], dias[(pos + 1) % len(dias)]
    if len(dias) > 1:
        botoes.append([Botao(f"◀️ {NOME_DIA[anterior][:3]}", f"pl:dia:{anterior}"),
                       Botao(f"{NOME_DIA[proximo][:3]} ▶️", f"pl:dia:{proximo}")])
    botoes.append([Botao("🛒 Lista", "pl:lista"), Botao("🏠 Resumo", "pl:res")])
    return tela("\n".join(linhas).strip(), botoes, editar)


# --- lista de compras ------------------------------------------------------------
def promocao_da_linha(plano: dict, linha: dict) -> dict | None:
    if not linha.get("promocao_id"):
        return None
    return (plano.get("promocoes") or {}).get(str(linha["promocao_id"]))


def lista(plano: dict, editar: bool = True) -> Saida:
    linhas_txt = ["🛒 *Lista de compras*"]
    secao_atual = None
    tem_promo = False
    for l in plano["cesta"]["linhas"]:
        if l["pacotes"] <= 0:
            continue
        if l["secao"] != secao_atual:
            secao_atual = l["secao"]
            linhas_txt += ["", f"*{secao_atual}*"]
        promo = promocao_da_linha(plano, l)
        marca = f" 🏷️ {promo['mercado']} até {data_br(promo['validade'])}" if promo else ""
        tem_promo |= bool(promo)
        linhas_txt.append(f"• {l['nome']}, {cesta.texto_embalagem(l)}: {brl(l['custo'])}{marca}")
    de_casa = [l for l in plano["cesta"]["linhas"] if l["da_despensa"] > 0]
    if de_casa:
        linhas_txt += ["", "🏠 *Já tem em casa:* " + ", ".join(
            f"{l['nome']} ({l['da_despensa']} {l['unidade']})" for l in de_casa)]
    total, orc = plano["cesta"]["total"], plano.get("orcamento") or 0
    diferenca = f"Sobra {brl(orc - total)}" if total <= orc else f"Passou {brl(total - orc)}"
    linhas_txt += ["", f"*Total: {brl(total)}* · Orçamento {brl(orc)} · {diferenca}",
                   "⚠️ Preços estimados" + (", exceto os itens 🏷️ em promoção cadastrada." if tem_promo else ".")]
    botoes = [[Botao("📄 PDF da lista", "pl:pdf"), Botao("📅 Cardápio", "pl:dia")],
              [Botao("🏠 Resumo", "pl:res")]]
    return tela("\n".join(linhas_txt), botoes, editar)


# --- receita e passo a passo -----------------------------------------------------
def receita(plano: dict, perfil: dict, d: str, t: str, rec: dict, editar: bool = True) -> Saida:
    i = next(j for j, r in enumerate(plano["refeicoes"]) if r["dia"] == d and r["tipo"] == t)
    ref = plano["refeicoes"][i]
    porc = cesta.porcoes(perfil.get("adultos"), perfil.get("criancas"))
    linhas = [f"📖 *{ref['prato']}*",
              f"⏱️ {rec.get('tempo_min') or ref.get('tempo_min')} min · 🍽️ {cesta.porcoes_txt(porc)} · "
              f"💰 {brl(plano['cesta']['custo_refeicoes'][i])}", "", "*Ingredientes*"]
    linhas += [f"• {ing}" for ing in rec["ingredientes"]]
    if rec.get("dica"):
        linhas += ["", f"💡 {rec['dica']}"]
    if rec.get("porcoes_plano") and rec.get("porcoes") and rec["porcoes_plano"] != rec["porcoes"]:
        linhas += ["", f"ℹ️ Receita ajustada para {cesta.porcoes_txt(rec['porcoes'])}. A lista de compras "
                       f"continua para {cesta.porcoes_txt(rec['porcoes_plano'])}: use 🔄 Refazer se quiser outra."]
    botoes = [[Botao("👩‍🍳 Cozinhar passo a passo", f"pl:pas:{d}:{t}:0")],
              [Botao("🔁 Trocar", f"pl:tro:{d}:{t}"), Botao(f"⬅️ {NOME_DIA[d]}", f"pl:dia:{d}")]]
    return tela("\n".join(linhas), botoes, editar)


def passo(rec: dict, d: str, t: str, n: int, editar: bool = True) -> Saida:
    passos = rec["passos"]
    n = max(0, min(n, len(passos) - 1))
    t_txt = f"👩‍🍳 *Passo {n + 1} de {len(passos)}*\n\n{passos[n]}"
    if n + 1 < len(passos):
        botoes = [[Botao("Próximo ▶️", f"pl:pas:{d}:{t}:{n + 1}")]]
    else:
        botoes = [[Botao("✅ Fiz!", f"pl:fiz:{d}:{t}")]]
    botoes.append([Botao("📖 Receita", f"pl:rec:{d}:{t}")])
    return tela(t_txt, botoes, editar)


def pedir_nota(prato: str, d: str, t: str) -> Saida:
    estrelas = [Botao("⭐" * n, f"pl:not:{d}:{t}:{n}") for n in range(1, 6)]
    return tela(f"Que delícia! 🎉 Que nota você dá para *{prato}*?",
                [estrelas[:3], estrelas[3:]], editar=True)


def nota_salva(prato: str, nota: int) -> Saida:
    if nota >= 4:
        extra = "Vou lembrar que vocês gostaram e repetir de vez em quando 💚"
    elif nota <= 2:
        extra = "Beleza, não coloco mais esse prato no seu plano."
    else:
        extra = "Anotado!"
    return tela(f"{'⭐' * nota} para *{prato}*. {extra}", [[Botao("🏠 Resumo", "pl:res")]], editar=True)


def confirmar_refazer() -> Saida:
    return tela("Refazer o plano inteiro? Monto tudo de novo, do zero.",
                [[Botao("✅ Sim, refazer", "pl:montar"), Botao("❌ Cancelar", "pl:res")]], editar=True)
