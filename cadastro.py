"""Cadastro do Rende: uma pergunta por mensagem, com botões, sem depender do Telegram.

O passo atual fica em banco (usuarios.cadastro_passo). Quando a pessoa edita pelo
/perfil, o passo fica como "perfil:<passo>" e, ao confirmar, volta para o resumo.
A pessoa também pode responder escrevendo ou por áudio (o atendimento manda para a IA).
"""
import banco
import cesta
from cardapio import DIAS, MERCADOS, REFEICOES, UTENSILIOS, VIBES
from restricoes import NOMES as NOMES_RESTRICOES
from telas import Botao, Saida, brl, tela

PASSOS = ["nome", "pessoas", "refeicoes", "dias", "vibe", "restricoes", "utensilios", "mercados",
          "periodo", "orcamento"]
PERGUNTAS = {
    "nome": "Como posso te chamar?",
    "pessoas": "Quem vai comer?",
    "refeicoes": "Quais refeições?",
    "dias": "Quais dias vai cozinhar?",
    "vibe": "Qual a vibe?",
    "restricoes": "Alergias ou restrições?",
    "utensilios": "O que tem na cozinha?",
    "mercados": "Onde você compra?",
    "periodo": "Compra da semana ou do mês?",
    "orcamento": "Quanto quer gastar?",
}
OPCOES = {"refeicoes": {k: f"{i} {n}" for k, n, i in REFEICOES},
          "dias": dict(DIAS),
          "restricoes": NOMES_RESTRICOES,
          "utensilios": UTENSILIOS,
          "mercados": MERCADOS}
PADROES = {"refeicoes": ["almoco", "jantar"], "dias": [d for d, _ in DIAS], "utensilios": ["fogao"],
           "mercados": ["qualquer"], "restricoes": []}
# Custo médio por porção em Goiânia (sugestão de orçamento, não é preço real)
CUSTO_PORCAO = {"cafe": 3.5, "almoco": 7.0, "jantar": 6.5, "lanche": 3.0, "marmita": 6.5}
PASSO_ORCAMENTO = 20.0
# Abaixo de 75% da sugestão, o cadastro avisa que talvez o plano não feche (Pedido I, lacuna 3)
ORCAMENTO_BAIXO = 0.75


def orcamento_baixo(perfil: dict) -> float | None:
    """A sugestão para a família, quando o orçamento escolhido está muito abaixo dela."""
    sugestao = sugerir_orcamento(perfil)
    return sugestao if (perfil.get("orcamento") or 0) < sugestao * ORCAMENTO_BAIXO else None


# --- estado ------------------------------------------------------------------------
def passo_atual(perfil: dict) -> str | None:
    passo = perfil.get("cadastro_passo")
    return passo.split(":", 1)[1] if passo and passo.startswith("perfil:") else passo


def editando_pelo_perfil(perfil: dict) -> bool:
    return bool(perfil.get("cadastro_passo", "") and perfil["cadastro_passo"].startswith("perfil:"))


def concluido(perfil: dict) -> bool:
    return not perfil.get("cadastro_passo") and bool(perfil.get("nome")) and bool(perfil.get("orcamento"))


def iniciar(usuario: str) -> list[Saida]:
    banco.atualizar_perfil(usuario, cadastro_passo="nome")
    return [Saida(texto="Oi! Eu sou o *Rende* 👋 Como posso te chamar?")]


def editar(usuario: str, passo: str) -> list[Saida]:
    perfil = banco.atualizar_perfil(usuario, cadastro_passo=f"perfil:{passo}")
    return [tela_do_passo(perfil, passo, editar_msg=True)]


# --- resumo e sugestão de orçamento --------------------------------------------------
def porcoes_semana(perfil: dict) -> float:
    return (cesta.porcoes(perfil.get("adultos"), perfil.get("criancas"))
            * len(perfil.get("refeicoes") or []) * len(perfil.get("dias") or []))


def sugerir_orcamento(perfil: dict) -> float:
    porc = cesta.porcoes(perfil.get("adultos") or 1, perfil.get("criancas"))
    por_dia = sum(CUSTO_PORCAO.get(r, 6.0) for r in perfil.get("refeicoes") or ["almoco", "jantar"])
    semana = porc * por_dia * len(perfil.get("dias") or PADROES["dias"])
    if perfil.get("periodo") == "mes":
        semana *= 4.3
    return max(50.0, round(semana / 10) * 10)


def _familia(perfil: dict) -> str:
    a, c = perfil.get("adultos") or 0, perfil.get("criancas") or 0
    partes = [f"{a} adulto{'s' if a != 1 else ''}"]
    if c:
        partes.append(f"{c} criança{'s' if c != 1 else ''}")
    return " e ".join(partes)


def resumo(perfil: dict) -> str:
    periodo = "mês" if perfil.get("periodo") == "mes" else "semana"
    return (f"{_familia(perfil)} · {len(perfil.get('refeicoes') or [])} refeições/dia · "
            f"{porcoes_semana(perfil):.0f} porções na semana · {brl(perfil.get('orcamento') or 0)}/{periodo}")


# --- telas de cada passo --------------------------------------------------------------
def _multipla(perfil: dict, campo: str, colunas: int = 2) -> list[list[Botao]]:
    escolhidos = set(perfil.get(campo) or [])
    botoes = [Botao(("✅ " if k in escolhidos else "▫️ ") + rotulo, f"cad:t:{campo}:{k}")
              for k, rotulo in OPCOES[campo].items()]
    return [botoes[i:i + colunas] for i in range(0, len(botoes), colunas)]


def _rodape(perfil: dict, passo: str, rotulo: str = "Continuar ▶️") -> list[list[Botao]]:
    linha = [Botao(rotulo, "cad:ok")]
    if not editando_pelo_perfil(perfil) and PASSOS.index(passo) > 1:
        linha.insert(0, Botao("⬅️ Voltar", "cad:voltar"))
    return [linha]


def tela_do_passo(perfil: dict, passo: str, editar_msg: bool = False) -> Saida:
    nome = perfil.get("nome") or ""
    if passo == "nome":
        return Saida(texto="Como posso te chamar?")
    if passo == "restricoes_outro":
        return Saida(texto="✏️ Escreva as outras restrições (ex.: coentro, pimenta, carne de porco):")

    if passo == "pessoas":
        a, c = perfil.get("adultos") or 1, perfil.get("criancas") or 0
        porc = cesta.porcoes(a, c)
        t = (f"Prazer, *{nome}*! 😊 Quem vai comer?\n\n👤 Adultos: *{a}*\n🧒 Crianças: *{c}* (meia porção)\n\n"
             f"= *{cesta.porcoes_txt(porc)}* por refeição")
        botoes = [[Botao("➖ Adulto", "cad:ad:-"), Botao("➕ Adulto", "cad:ad:+")],
                  [Botao("➖ Criança", "cad:cr:-"), Botao("➕ Criança", "cad:cr:+")]] + _rodape(perfil, passo)
        return tela(t, botoes, editar_msg)

    if passo in ("refeicoes", "dias", "restricoes", "utensilios", "mercados"):
        textos = {
            "refeicoes": "🍽️ Quais refeições vou planejar? (pode marcar várias)",
            "dias": "📅 Em quais dias você vai cozinhar?",
            "restricoes": "⚠️ Alguma alergia ou restrição? Eu confiro cada ingrediente.",
            "utensilios": "🍳 O que tem na sua cozinha? As receitas só vão usar isso.",
            "mercados": "🛒 Onde você costuma comprar?",
        }
        t = textos[passo]
        if passo == "restricoes" and perfil.get("restricoes_outras"):
            t += f"\n\nOutras: {perfil['restricoes_outras']}"
        botoes = _multipla(perfil, passo, 3 if passo == "dias" else 2)
        if passo == "dias":
            botoes.append([Botao("Todos os dias", "cad:todos:dias")])
        if passo == "restricoes":
            botoes.append([Botao("✏️ Outra (escrever)", "cad:outro"), Botao("🚫 Nenhuma", "cad:nenhuma")])
        return tela(t, botoes + _rodape(perfil, passo), editar_msg)

    if passo == "vibe":
        atual = perfil.get("vibe")
        botoes = [[Botao(("✅ " if k == atual else "") + rotulo, f"cad:s:vibe:{k}")] for k, rotulo in VIBES.items()]
        if not editando_pelo_perfil(perfil):
            botoes.append([Botao("⬅️ Voltar", "cad:voltar")])
        return tela("✨ Qual a vibe da sua cozinha?", botoes, editar_msg)

    if passo == "periodo":
        botoes = [[Botao("🗓️ Da semana", "cad:s:periodo:semana"), Botao("📆 Do mês", "cad:s:periodo:mes")]]
        if not editando_pelo_perfil(perfil):
            botoes.append([Botao("⬅️ Voltar", "cad:voltar")])
        return tela("🛍️ Você faz a compra da semana ou do mês?", botoes, editar_msg)

    if passo == "orcamento":
        periodo = "mês" if perfil.get("periodo") == "mes" else "semana"
        t = (f"💰 Quanto quer gastar por {periodo}?\n\nSugeri um valor realista para a sua família. "
             f"Ajuste se quiser:\n\n*{brl(perfil.get('orcamento') or 0)}*\n\n{resumo(perfil)}")
        botoes = [[Botao(f"− {brl(PASSO_ORCAMENTO)}", "cad:orc:-"), Botao(f"+ {brl(PASSO_ORCAMENTO)}", "cad:orc:+")],
                  [Botao("✅ Confirmar", "cad:ok")]]
        sugestao = orcamento_baixo(perfil)
        if sugestao:
            t += (f"\n\n⚠️ Esse valor fica bem abaixo do que costuma custar para a sua família "
                  f"(uns {brl(sugestao)} por {periodo}). Posso tentar, mas talvez o plano não feche nele.")
            botoes.insert(1, [Botao(f"↩️ Usar {brl(sugestao)}", "cad:orc:sug")])
        return tela(t, botoes, editar_msg)
    raise ValueError(f"passo desconhecido: {passo}")


# --- avanço ------------------------------------------------------------------------------
def _preparar(usuario: str, perfil: dict, passo: str) -> dict:
    """Preenche os valores padrão de um passo antes de mostrá-lo."""
    campos = {}
    if passo == "pessoas" and not perfil.get("adultos"):
        campos.update(adultos=1, criancas=perfil.get("criancas") or 0)
    if passo in PADROES and not perfil.get(passo) and passo != "restricoes":
        campos[passo] = PADROES[passo]
    if passo == "orcamento" and not perfil.get("orcamento"):
        campos["orcamento"] = sugerir_orcamento(perfil)
    return banco.atualizar_perfil(usuario, **campos) if campos else perfil


def ir_para(usuario: str, passo: str, editar_msg: bool = False) -> list[Saida]:
    perfil = banco.atualizar_perfil(usuario, cadastro_passo=passo)
    perfil = _preparar(usuario, perfil, passo)
    return [tela_do_passo(perfil, passo, editar_msg)]


def avancar(usuario: str, editar_msg: bool = True) -> list[Saida]:
    """Passo confirmado: vai para o próximo, volta ao perfil ou termina o cadastro."""
    perfil = banco.usuario(usuario)
    passo = passo_atual(perfil)
    if passo == "restricoes_outro":
        passo = "restricoes"
    if editando_pelo_perfil(perfil):
        banco.atualizar_perfil(usuario, cadastro_passo=None)
        return [resumo_perfil(banco.usuario(usuario), editar_msg)]
    proximo = PASSOS.index(passo) + 1
    if proximo >= len(PASSOS):
        banco.atualizar_perfil(usuario, cadastro_passo=None, cidade=perfil.get("cidade") or "Goiânia")
        return [Saida(texto=f"Tudo pronto, *{perfil.get('nome')}*! 🙌\n\n{resumo(perfil)}", editar=editar_msg),
                Saida(tipo="acao", acao="pl:montar")]
    return ir_para(usuario, PASSOS[proximo], editar_msg)


def acao(usuario: str, acao_txt: str) -> list[Saida]:
    """Trata os botões 'cad:...'. Devolve as telas a mostrar."""
    perfil = banco.usuario(usuario)
    passo = passo_atual(perfil)
    partes = acao_txt.split(":")
    tipo = partes[1]
    if passo is None:
        return [Saida(texto="Esse cadastro já terminou. Use /perfil para mudar alguma coisa.")]
    if passo == "restricoes_outro":  # tocou num botão em vez de escrever: volta para a tela de restrições
        prefixo = "perfil:" if editando_pelo_perfil(perfil) else ""
        perfil = banco.atualizar_perfil(usuario, cadastro_passo=prefixo + "restricoes")
        passo = "restricoes"

    if tipo in ("ad", "cr"):
        campo = "adultos" if tipo == "ad" else "criancas"
        minimo = 1 if campo == "adultos" else 0
        valor = (perfil.get(campo) or minimo) + (1 if partes[2] == "+" else -1)
        perfil = banco.atualizar_perfil(usuario, **{campo: max(minimo, min(15, valor))})
        return [tela_do_passo(perfil, passo, True)]

    if tipo == "t":  # liga/desliga uma opção de múltipla escolha
        campo, valor = partes[2], partes[3]
        escolhidos = list(perfil.get(campo) or [])
        if valor in escolhidos:
            escolhidos.remove(valor)
        else:
            escolhidos.append(valor)
        if campo == "mercados":  # "Qualquer um" não combina com os outros
            escolhidos = ["qualquer"] if valor == "qualquer" and "qualquer" in escolhidos else \
                [m for m in escolhidos if m != "qualquer"]
        perfil = banco.atualizar_perfil(usuario, **{campo: escolhidos})
        return [tela_do_passo(perfil, passo, True)]

    if tipo == "todos":
        perfil = banco.atualizar_perfil(usuario, dias=[d for d, _ in DIAS])
        return [tela_do_passo(perfil, passo, True)]

    if tipo == "nenhuma":
        banco.atualizar_perfil(usuario, restricoes=[], restricoes_outras=None)
        return avancar(usuario)

    if tipo == "outro":
        banco.atualizar_perfil(usuario, cadastro_passo=("perfil:" if editando_pelo_perfil(perfil) else "")
                               + "restricoes_outro")
        return [Saida(texto="✏️ Escreva as outras restrições (ex.: coentro, pimenta, carne de porco):",
                      editar=True)]

    if tipo == "s":  # escolha única: salva e avança
        banco.atualizar_perfil(usuario, **{partes[2]: partes[3]})
        if partes[2] == "periodo":  # mudar semana/mês muda a sugestão de orçamento
            p = banco.usuario(usuario)
            banco.atualizar_perfil(usuario, orcamento=sugerir_orcamento(p))
        return avancar(usuario)

    if tipo == "orc":
        if partes[2] == "sug":
            perfil = banco.atualizar_perfil(usuario, orcamento=sugerir_orcamento(perfil))
            return [tela_do_passo(perfil, passo, True)]
        if partes[2] in ("+", "-"):
            delta = PASSO_ORCAMENTO if partes[2] == "+" else -PASSO_ORCAMENTO
            perfil = banco.atualizar_perfil(usuario, orcamento=max(PASSO_ORCAMENTO, (perfil.get("orcamento") or 0) + delta))
            return [tela_do_passo(perfil, passo, True)]

    if tipo == "ok":
        faltando = {"refeicoes": "Escolha pelo menos uma refeição 🙂", "dias": "Escolha pelo menos um dia 🙂",
                    "utensilios": "Marque pelo menos um item da cozinha 🙂", "mercados": "Escolha um mercado ou 'Qualquer um' 🙂"}
        if passo in faltando and not perfil.get(passo):
            return [Saida(texto=faltando[passo])]
        if passo in ("refeicoes", "dias") and not editando_pelo_perfil(perfil):
            banco.atualizar_perfil(usuario, orcamento=None)  # recalcula a sugestão lá no fim
        return avancar(usuario)

    if tipo == "voltar":
        anterior = max(1, PASSOS.index(passo) - 1)
        return ir_para(usuario, PASSOS[anterior], editar_msg=True)

    return [Saida(texto="Não entendi esse botão 🤔")]


def resposta_escrita(usuario: str, texto: str) -> list[Saida] | None:
    """Respostas que não precisam de IA (nome curto, 'outras restrições').
    Devolve None quando é preciso perguntar à IA."""
    perfil = banco.usuario(usuario)
    passo = passo_atual(perfil)
    if passo == "nome":
        palavras = texto.strip().split()
        if 1 <= len(palavras) <= 3 and not any(ch.isdigit() for ch in texto) and len(texto) <= 40:
            banco.atualizar_perfil(usuario, nome=" ".join(p.capitalize() for p in palavras))
            return avancar(usuario, editar_msg=False)  # no /perfil, volta ao resumo
        return None
    if passo == "restricoes_outro":
        banco.atualizar_perfil(usuario, restricoes_outras=texto.strip()[:200],
                               cadastro_passo=("perfil:" if editando_pelo_perfil(perfil) else "") + "restricoes")
        return [tela_do_passo(banco.usuario(usuario), "restricoes")]
    return None


# --- /perfil ------------------------------------------------------------------------------
def resumo_perfil(perfil: dict, editar_msg: bool = False) -> Saida:
    restr = [NOMES_RESTRICOES.get(r, r) for r in perfil.get("restricoes") or []]
    if perfil.get("restricoes_outras"):
        restr.append(perfil["restricoes_outras"])
    t = "\n".join([
        f"👤 *Seu perfil, {perfil.get('nome') or ''}*", "",
        f"👥 {_familia(perfil)}",
        "🍽️ " + ", ".join(OPCOES["refeicoes"][r].split(" ", 1)[1] for r in perfil.get("refeicoes") or []),
        "📅 " + ", ".join(dict(DIAS)[d][:3] for d in perfil.get("dias") or []),
        f"✨ {VIBES.get(perfil.get('vibe'), '-')}",
        f"⚠️ {', '.join(restr) or 'Nenhuma restrição'}",
        "🍳 " + ", ".join(UTENSILIOS[u] for u in perfil.get("utensilios") or []),
        "🛒 " + ", ".join(MERCADOS.get(m, m) for m in perfil.get("mercados") or []),
        f"💰 {brl(perfil.get('orcamento') or 0)} por {'mês' if perfil.get('periodo') == 'mes' else 'semana'}",
    ])
    botoes = [[Botao("✏️ Nome", "per:nome"), Botao("👥 Pessoas", "per:pessoas"), Botao("🍽️ Refeições", "per:refeicoes")],
              [Botao("📅 Dias", "per:dias"), Botao("✨ Vibe", "per:vibe"), Botao("⚠️ Restrições", "per:restricoes")],
              [Botao("🍳 Cozinha", "per:utensilios"), Botao("🛒 Mercados", "per:mercados"), Botao("💰 Orçamento", "per:orcamento")],
              [Botao("🗓️ Semana/mês", "per:periodo")]]
    return tela(t, botoes, editar_msg)
