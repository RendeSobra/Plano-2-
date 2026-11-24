"""🛒 Modo mercado: marcar o que já foi para o carrinho (Pedido I, 24/11/2026).

Sem IA e sem depender do Telegram. O progresso fica guardado dentro do próprio plano
(campo "mercado"), então fechar e abrir de novo continua de onde parou, e o /esquecer
apaga junto com o plano.

    plano["mercado"] = {
        "comprados": ["arroz", ...],        # chaves (nome normalizado) dos itens marcados
        "precos": {"arroz": 23.9, ...},     # preço real de UMA embalagem, quando a pessoa informou
        "finalizado": False,                # tocou em "Terminei as compras"
        "nao_encontrei": ["frango coxa"],   # o que ficou sem marcar ao terminar
    }
"""
import banco
import cardapio
import cesta
import restricoes

# Substitutos simples para o que a pessoa não encontrou (sem IA). A chave é procurada no
# nome do item; as sugestões que ferem as restrições da pessoa são tiradas.
SUBSTITUTOS = {
    "frango": ["peito de frango", "ovo", "carne moída"],
    "carne moida": ["frango desfiado", "ovo", "linguiça"],
    "carne": ["frango", "ovo", "carne moída"],
    "linguica": ["frango", "carne moída", "ovo"],
    "peixe": ["frango", "ovo", "sardinha em lata"],
    "tilapia": ["outro peixe", "frango", "ovo"],
    "ovo": ["frango desfiado", "carne moída"],
    "feijao": ["outro tipo de feijão", "lentilha", "grão-de-bico"],
    "arroz": ["macarrão", "cuscuz de milho", "batata"],
    "macarrao": ["arroz", "batata"],
    "batata": ["mandioca", "batata-doce", "inhame"],
    "mandioca": ["batata", "batata-doce", "inhame"],
    "tomate": ["molho de tomate pronto", "extrato de tomate"],
    "cebola": ["cebolinha", "alho a mais"],
    "leite": ["leite em pó", "leite sem lactose"],
    "queijo": ["requeijão", "ovo"],
    "pao": ["cuscuz de milho", "tapioca", "bolacha de água e sal"],
    "flocao": ["tapioca", "pão"],
    "couve": ["repolho", "espinafre", "acelga"],
    "abobora": ["cenoura", "chuchu"],
    "cenoura": ["abóbora", "chuchu", "beterraba"],
    "chuchu": ["abobrinha", "cenoura"],
    "pequi": ["açafrão-da-terra (para a cor)", "milho"],
}


def _estado(plano: dict) -> dict:
    estado = plano.setdefault("mercado", {})
    estado.setdefault("comprados", [])
    estado.setdefault("precos", {})
    estado.setdefault("finalizado", False)
    estado.setdefault("nao_encontrei", [])
    return estado


def linhas(plano: dict) -> list[dict]:
    """Os itens da lista (embalagens a comprar), na ordem das seções do mercado."""
    return [l for l in plano["cesta"]["linhas"] if l["pacotes"] > 0]


def custo_linha(plano: dict, linha: dict) -> float:
    """Custo da linha: preço informado pela pessoa (se houver) ou o estimado."""
    preco = (plano.get("mercado") or {}).get("precos", {}).get(cesta.chave(linha["item"]))
    return round(linha["pacotes"] * preco, 2) if preco is not None else linha["custo"]


def resumo(plano: dict) -> dict:
    """{"marcados": n, "itens": n, "valor_marcado": R$, "valor_total": R$} para o topo da tela."""
    estado = plano.get("mercado") or {}
    comprados = set(estado.get("comprados") or [])
    todas = linhas(plano)
    marcadas = [l for l in todas if cesta.chave(l["item"]) in comprados]
    return {"marcados": len(marcadas), "itens": len(todas),
            "valor_marcado": round(sum(custo_linha(plano, l) for l in marcadas), 2),
            "valor_total": round(sum(custo_linha(plano, l) for l in todas), 2)}


def linha_por_indice(plano: dict, indice: int) -> dict | None:
    todas = linhas(plano)
    return todas[indice] if 0 <= indice < len(todas) else None


def _salvar(plano: dict) -> dict:
    banco.atualizar_plano(plano["id"], {k: v for k, v in plano.items() if k not in ("id", "criado_em")})
    return plano


def alternar(usuario: str, indice: int) -> dict:
    """Marca ou desmarca um item (⬜ <-> ✅) e guarda no banco."""
    plano = banco.plano_atual(usuario)
    linha = linha_por_indice(plano, indice)
    if linha is None:
        return plano
    estado = _estado(plano)
    chave = cesta.chave(linha["item"])
    if chave in estado["comprados"]:
        estado["comprados"].remove(chave)
    else:
        estado["comprados"].append(chave)
    return _salvar(plano)


def ler_preco(texto: str) -> float | None:
    """'23,90', 'R$ 23.90', '23' -> 23.9. Qualquer outra coisa -> None."""
    limpo = (texto or "").lower().replace("r$", "").replace(" ", "").strip()
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        valor = float(limpo)
    except ValueError:
        return None
    return round(valor, 2) if 0 < valor < 10_000 else None


def informar_preco(usuario: str, indice: int, preco: float) -> tuple[dict, dict | None]:
    """A pessoa pagou outro preço numa embalagem: guarda no plano (o total parcial usa o preço real),
    marca o item como comprado e alimenta a tabela de preços (origem 'usuario')."""
    plano = banco.plano_atual(usuario)
    linha = linha_por_indice(plano, indice)
    if linha is None:
        return plano, None
    estado = _estado(plano)
    chave = cesta.chave(linha["item"])
    estado["precos"][chave] = preco
    if chave not in estado["comprados"]:
        estado["comprados"].append(chave)
    perfil = banco.usuario(usuario) or {}
    mercados = [m for m in perfil.get("mercados") or [] if m != "qualquer"]
    tamanho = next((float(p["tamanho"]) for p in plano.get("produtos", []) if cesta.chave(p["item"]) == chave), None)
    banco.adicionar_preco(produto=chave, nome=linha["nome"], preco=preco, origem="usuario",
                          embalagem=linha["embalagem"], tamanho=tamanho, unidade=linha["unidade"],
                          mercado=cardapio.MERCADOS.get(mercados[0]) if len(mercados) == 1 else None,
                          cidade=perfil.get("cidade") or "Goiânia")
    return _salvar(plano), linha


def substitutos(item: str, perfil: dict) -> list[str]:
    alvo = restricoes.normalizar(item)
    for chave, opcoes in SUBSTITUTOS.items():
        if chave in alvo:
            return [o for o in opcoes if not restricoes.violacoes(o, perfil.get("restricoes") or [],
                                                                  perfil.get("restricoes_outras"))]
    return []


def pratos_afetados(plano: dict, chave: str) -> list[dict]:
    """Refeições do plano que usam um item."""
    return [r for r in plano["refeicoes"]
            if any(cesta.chave(i["item"]) == chave for i in r.get("ingredientes", []))]


def _somar(despensa: dict, chave: str, item: str, quantidade: float, unidade: str) -> None:
    atual = despensa.get(chave)
    if atual and atual.get("unidade") == unidade:
        atual["quantidade"] = round(float(atual.get("quantidade") or 0) + quantidade)
    else:
        despensa[chave] = {"item": item, "quantidade": round(quantidade), "unidade": unidade}


def terminar(usuario: str) -> dict:
    """🏁 Terminei as compras: o que foi comprado vai para a despensa (o que a pessoa tem em casa
    agora); o que faltou vira a lista "não encontrei". A despensa da semana seguinte passa a
    contar só o que foi comprado de verdade."""
    plano = banco.plano_atual(usuario)
    estado = _estado(plano)
    comprados = set(estado["comprados"])
    tamanhos = {cesta.chave(p["item"]): float(p["tamanho"]) for p in plano.get("produtos", [])}
    em_casa = {k: dict(v) for k, v in (plano.get("despensa_inicial") or {}).items()}
    for l in linhas(plano):
        chave = cesta.chave(l["item"])
        if chave in comprados:
            _somar(em_casa, chave, l["item"], l["pacotes"] * tamanhos.get(chave, 0), l["unidade"])
    # semana seguinte: o que não foi comprado não deixa sobra de embalagem (os itens que já
    # vinham inteiros da despensa, sem nada a comprar, continuam na conta)
    faltaram = {cesta.chave(l["item"]) for l in linhas(plano)} - comprados
    so_o_comprado = {**plano, "produtos": [p for p in plano.get("produtos", [])
                                           if cesta.chave(p["item"]) not in faltaram]}
    calc_real = cesta.calcular(so_o_comprado, plano.get("despensa_inicial") or {})
    plano["cesta"]["despensa_final"] = calc_real["despensa_final"]
    estado["nao_encontrei"] = [l["item"] for l in linhas(plano) if cesta.chave(l["item"]) not in comprados]
    estado["finalizado"] = True
    estado["terminado_em"] = banco.agora().isoformat(timespec="seconds")
    banco.atualizar_perfil(usuario, despensa=em_casa)
    return _salvar(plano)
