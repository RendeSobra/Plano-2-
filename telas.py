"""Telas do Rende (texto + botões), sem depender do Telegram.

O canal (hoje bot_telegram.py) só desenha: Saida.texto vira a mensagem e
Saida.botoes vira o teclado de botões. `acao` é o que volta quando o botão é tocado
(curto: o Telegram aceita até 64 bytes).
"""
import math
from dataclasses import dataclass, field
from datetime import date

import cesta
import mercado
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


def _ou(itens: list[str]) -> str:
    """['a', 'b', 'c'] -> 'a, b ou c'."""
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " ou " + itens[-1]


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
    """Botões do C9 + [🛒 Modo mercado] (Pedido I)."""
    return [[Botao("📅 Ver cardápio", "pl:dia"), Botao("🛒 Lista", "pl:lista")],
            [Botao("📄 PDF", "pl:pdf"), Botao("🔄 Refazer", "pl:refazer")],
            [Botao("🏪 Onde comprar", "oc:ver"), Botao("🛒 Modo mercado", "mm:ver")]]


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
        gasto = f"Gasto *{brl(total)}* de {brl(orc)}. Sobrou *{brl(orc - total)}* · {itens} itens."
        t = "\n".join(topo + [f"*Sua semana está pronta, {nome}!* 🎉", "", gasto])
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
    escolhido = mercado.escolha(plano, linha)
    if escolhido is not None:  # C15: a pessoa escolheu onde comprar; vale a promoção daquele mercado
        return escolhido.get("promocao")
    if not linha.get("promocao_id"):
        return None
    return (plano.get("promocoes") or {}).get(str(linha["promocao_id"]))


def lista(plano: dict, editar: bool = True) -> Saida:
    linhas_txt = ["🛒 *Lista de compras*"]
    escolhidos = (plano.get("onde_comprar") or {}).get("mercados") or []
    if len(escolhidos) == 1:
        linhas_txt.append(f"🏪 Preços do {escolhidos[0]}")
    elif len(escolhidos) > 1:
        linhas_txt.append(f"✂️ Compra dividida: {' e '.join(escolhidos)}")
    secao_atual = None
    tem_promo = False
    for l in plano["cesta"]["linhas"]:
        if l["pacotes"] <= 0:
            continue
        if l["secao"] != secao_atual:
            secao_atual = l["secao"]
            linhas_txt += ["", f"*{secao_atual}*"]
        promo = promocao_da_linha(plano, l)
        marca = f" 🔥 {promo['mercado']} até {data_br(promo['validade'])}" if promo else ""
        if len(escolhidos) > 1 and not promo and mercado.escolha(plano, l):
            marca = f" · {mercado.escolha(plano, l)['mercado']}"
        tem_promo |= bool(promo)
        linhas_txt.append(f"• {l['nome']}, {cesta.texto_embalagem(l)}: {brl(mercado.custo_linha(plano, l))}{marca}")
    de_casa = [l for l in plano["cesta"]["linhas"] if l["da_despensa"] > 0]
    if de_casa:
        linhas_txt += ["", "🏠 *Já tem em casa:* " + ", ".join(
            f"{l['nome']} ({l['da_despensa']} {l['unidade']})" for l in de_casa)]
    total, orc = mercado.resumo(plano)["valor_total"], plano.get("orcamento") or 0  # com os preços pagos
    diferenca = f"Sobra {brl(orc - total)}" if total <= orc else f"Passou {brl(total - orc)}"
    linhas_txt += ["", f"*Total: {brl(total)}* · Orçamento {brl(orc)} · {diferenca}",
                   "≈ Preços estimados" + (", exceto os itens 🔥 em promoção cadastrada." if tem_promo else ".")]
    botoes = [[Botao("🛒 Modo mercado", "mm:ver")],
              [Botao("📄 PDF", "pl:pdf"), Botao("📅 Cardápio", "pl:dia")],
              [Botao("🏠 Resumo", "pl:res")]]
    return tela("\n".join(linhas_txt), botoes, editar)


# --- escopo e promoções ------------------------------------------------------------
def fora_do_escopo(texto_fixo: str) -> Saida:
    """C3: resposta fixa (o texto do modelo foi descartado) com os botões do pedido."""
    return tela(texto_fixo, [[Botao("📅 Meu cardápio", "pl:dia"), Botao("🔥 Promoções", "pr:ver"),
                              Botao("🛒 Lista", "pl:lista")]])


def promocoes(promos: list[dict], cidade: str, vazio: str, editar: bool = True) -> Saida:
    if not promos:
        return tela(vazio, [[Botao("📍 Mercados perto de mim", "lc:ver")], [Botao("🏠 Resumo", "pl:res")]], editar)
    linhas_txt = [f"🔥 *Promoções em {cidade}*", ""]
    for p in promos[:15]:
        descricao = " ".join(x for x in (p["produto"], p.get("marca"), p.get("tamanho")) if x)
        condicao = f" ({p['condicao']})" if p.get("condicao") else ""
        linhas_txt.append(f"• {descricao}: *{brl(p['preco'])}* no {p['mercado']} até {data_br(p['validade'])}{condicao}")
    if len(promos) > 15:
        linhas_txt += ["", f"...e mais {len(promos) - 15}. Pergunte por um produto que eu procuro."]
    return tela("\n".join(linhas_txt), [[Botao("📍 Mercados perto de mim", "lc:ver")], [Botao("🏠 Resumo", "pl:res")]], editar)


# --- 🛒 Modo mercado (Pedido I) ----------------------------------------------------
def _rotulo_item(plano: dict, linha: dict, marcado: bool) -> str:
    pago = (plano.get("mercado") or {}).get("precos", {}).get(cesta.chave(linha["item"]))
    preco = brl(mercado.custo_linha(plano, linha)) + (" ✏️" if pago is not None else "")
    return f"{'✅' if marcado else '⬜'} {linha['nome']} ({cesta.texto_embalagem(linha)}) {preco}"


def modo_mercado(plano: dict, editar: bool = True, aviso: str = "") -> Saida:
    """Lista por seção; cada item é um botão que alterna ⬜/✅ editando a mesma mensagem."""
    r = mercado.resumo(plano)
    estado = plano.get("mercado") or {}
    comprados = set(estado.get("comprados") or [])
    linhas_txt = ([aviso, ""] if aviso else []) + [
        "🛒 *Modo mercado*",
        f"✅ {r['marcados']} de {r['itens']} itens · {brl(r['valor_marcado'])} de {brl(r['valor_total'])}", "",
        "Toque no item quando ele for para o carrinho."]
    if estado.get("finalizado"):
        linhas_txt.append(f"🏁 Compras encerradas em {data_br(estado.get('terminado_em') or '')}.")
    botoes: list[list[Botao]] = []
    secao_atual = None
    for i, l in enumerate(mercado.linhas(plano)):
        if l["secao"] != secao_atual:
            secao_atual = l["secao"]
            botoes.append([Botao(f"· {secao_atual} ·", "mm:x")])
        marcado = cesta.chave(l["item"]) in comprados
        botoes.append([Botao(_rotulo_item(plano, l, marcado), f"mm:t:{plano['id']}:{i}")])
    botoes += [[Botao("✏️ Paguei outro preço", "mm:p"), Botao("🏁 Terminei as compras", "mm:fim")],
               [Botao("🏠 Resumo", "pl:res")]]
    return tela("\n".join(linhas_txt), botoes, editar)


def escolher_item_preco(plano: dict) -> Saida:
    botoes = [[Botao(f"{l['nome']} · {brl(mercado.custo_linha(plano, l) / max(1, l['pacotes']))}/{l['embalagem']}",
                     f"mm:pi:{plano['id']}:{i}")] for i, l in enumerate(mercado.linhas(plano))]
    botoes.append([Botao("⬅️ Voltar", "mm:ver")])
    return tela("✏️ Em qual item você pagou outro preço?", botoes, editar=True)


def pedir_preco(linha: dict) -> Saida:
    cada = "cada " if linha["pacotes"] > 1 else ""
    return tela(f"Quanto custou {cada}*{linha['embalagem']}* de *{linha['nome']}*?\n\n"
                f"Escreva só o valor (ex.: 23,90).", [[Botao("❌ Cancelar", "mm:ver")]], editar=True)


def compras_encerradas(plano: dict, perfil: dict) -> Saida:
    r = mercado.resumo(plano)
    estado = plano.get("mercado") or {}
    linhas_txt = ["🏁 *Compras encerradas!*",
                  f"✅ {r['marcados']} de {r['itens']} itens · {brl(r['valor_marcado'])}",
                  "🏠 O que você comprou foi para a despensa."]
    botoes: list[list[Botao]] = []
    faltou = estado.get("nao_encontrei") or []
    if not faltou:
        linhas_txt += ["", "Achou tudo! 🎉"]
    else:
        linhas_txt += ["", "❓ *Não encontrei:*"]
        afetadas: list[dict] = []
        for item in faltou:
            subs = mercado.substitutos(item, perfil)
            pratos = mercado.pratos_afetados(plano, cesta.chave(item))
            afetadas += [p for p in pratos if p not in afetadas]
            onde = ", ".join(f"{NOME_REFEICAO[p['tipo']]} de {NOME_DIA[p['dia']].lower()}" for p in pratos)
            linhas_txt.append(f"• {item}" + (f" → dá para usar {_ou(subs)}" if subs else "")
                              + (f". Afeta: {onde}." if onde else "."))
        if afetadas:
            linhas_txt += ["", "Quer que eu troque os pratos afetados? Eu evito o que você não encontrou."]
            botoes += [[Botao(f"🔁 Trocar {NOME_REFEICAO[p['tipo']].lower()} de {NOME_DIA[p['dia']][:3].lower()}",
                              f"pl:tro:{p['dia']}:{p['tipo']}")] for p in afetadas[:6]]
    botoes += [[Botao("🛒 Modo mercado", "mm:ver"), Botao("🏠 Resumo", "pl:res")]]
    return tela("\n".join(linhas_txt), botoes, editar=True)


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


# --- 🏪 Onde comprar (C15) ---------------------------------------------------------------
MEDALHAS = ["🥇", "🥈", "🥉"]


def chave_mercado(nome: str) -> str:
    """Nome curto para o botão (o Telegram aceita até 64 bytes no botão)."""
    from restricoes import normalizar
    return normalizar(nome).replace(" ", "")[:24]


def _km(distancia: float | None) -> str:
    if distancia is None:
        return ""
    return f" · {distancia:.1f} km".replace(".", ",") if distancia >= 1 else f" · {round(distancia * 1000)} m"


def onde_comprar(plano: dict, mercados: list, divisao, tem_localizacao: bool, condicoes: list[str],
                 editar: bool = True) -> Saida:
    import onde_comprar as oc
    voltar = [[Botao("🛒 Lista", "pl:lista"), Botao("🏠 Resumo", "pl:res")]]
    if not mercados:
        return tela("🏪 Ainda não tenho preços de mercados para comparar 😕\n\nEscolha seus mercados no /perfil "
                    "ou me mande a foto de um encarte que eu guardo as ofertas.", voltar, editar)
    itens = len(mercados[0].itens)
    linhas_txt = ["🏪 *Onde comprar sua lista*", f"{itens} itens. O total em cada mercado:", ""]
    for i, m in enumerate(mercados[:3]):
        promo = f" · 🔥 {m.com_promocao} em promoção" if m.com_promocao else " · ≈ só estimado"
        linhas_txt.append(f"{MEDALHAS[i]} *{m.nome}*: {brl(m.total)}{_km(m.distancia_km)}{promo}")
    if divisao:
        a, b = divisao.mercados
        linhas_txt += ["", f"💡 Dividindo entre *{a}* e *{b}* você economiza *{brl(divisao.economia)}* "
                           f"(total {brl(divisao.total)})."]
    melhor = mercados[0]
    linhas_txt += ["", f"📊 No {melhor.nome}, {oc.porcentagem_real(melhor)}% da lista tem preço real (🔥 promoção); "
                       "o resto é ≈ estimado."]
    if condicoes:
        linhas_txt += ["", "⚠️ *Condições das promoções:*"] + [f"• {c}" for c in condicoes[:6]]
    if not tem_localizacao:
        linhas_txt += ["", "📍 Mande sua localização para eu mostrar a distância de cada um."]
    escolhida = (plano.get("onde_comprar") or {}).get("mercados")
    if escolhida:
        linhas_txt += ["", f"✅ Sua escolha: {' + '.join(escolhida)}."]
    botoes = [[Botao(f"📋 {m.nome}", f"oc:m:{chave_mercado(m.nome)}") for m in mercados[:3]]]
    if divisao:
        botoes.append([Botao(f"✂️ Dividir: {divisao.mercados[0]} + {divisao.mercados[1]}", "oc:div")])
    if escolhida:
        botoes.append([Botao("↩️ Desfazer a escolha", "oc:limpar")])
    if not tem_localizacao:
        botoes.append([Botao("📍 Mercados perto de mim", "lc:pedir")])
    return tela("\n".join(linhas_txt), botoes + voltar, editar)


def onde_comprar_mercado(m, editar: bool = True) -> Saida:
    """Os itens da lista num mercado: '🔥 promoção (até dd/mm)' ou '≈ estimado'."""
    linhas_txt = [f"🏪 *{m.nome}*: {brl(m.total)}{_km(m.distancia_km)}", ""]
    for item in m.itens:
        if item.promocao:
            p = item.promocao
            condicao = f", {p['condicao']}" if p.get("condicao") else ""
            linhas_txt.append(f"• {item.nome}: {brl(item.custo)} 🔥 promoção (até {data_br(p['validade'])}{condicao})")
        else:
            linhas_txt.append(f"• {item.nome}: ≈ {brl(item.custo)} estimado")
    botoes = [[Botao(f"✅ Vou comprar no {m.nome}", f"oc:e:{chave_mercado(m.nome)}")],
              [Botao("⬅️ Voltar", "oc:ver")]]
    return tela("\n".join(linhas_txt), botoes, editar)


# --- 📍 Mercados próximos (C12) ------------------------------------------------------------
def pedir_localizacao() -> Saida:
    return Saida(tipo="pedir_localizacao",
                 texto="Toque no botão *📍 Enviar minha localização* aqui embaixo. Uso só para achar os "
                       "mercados perto de você (e dá para apagar tudo com /esquecer).")


def mercados_proximos(mercados: list, redes_com_promo: set[str], raio_m: int, tem_plano: bool) -> Saida:
    from restricoes import normalizar
    raio = f"{raio_m / 1000:g}".replace(".", ",")
    botoes = ([[Botao("🏪 Onde comprar", "oc:ver")]] if tem_plano else []) + [[Botao("🔥 Promoções", "pr:ver")]]
    if not mercados:
        return tela(f"📍 Não achei supermercados num raio de {raio} km 😕 O mapa (OpenStreetMap) é feito pelas "
                    "pessoas e pode estar incompleto.", botoes)
    linhas_txt = [f"📍 *Mercados perto de você* (até {raio} km)", ""]
    for i, m in enumerate(mercados, 1):
        promo = " · 🔥 *tem promoções*" if m.rede and normalizar(m.rede) in redes_com_promo else ""
        linhas_txt += [f"{i}. *{m.nome}*{_km(m.distancia_km)}{promo}", f"   {m.link}"]
    linhas_txt += ["", "Distância em linha reta. Mapa: © colaboradores do OpenStreetMap."]
    return tela("\n".join(linhas_txt), botoes)
