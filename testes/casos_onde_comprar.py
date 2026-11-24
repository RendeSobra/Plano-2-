"""Testes do C15 ("Onde comprar"), chamados pelo testar.py."""
import asyncio
import io
from datetime import timedelta

from pypdf import PdfReader

import atendimento
import banco
import cesta
import mercado
import onde_comprar
import pdf
import telas


def rodar(ok, secao, novo_banco, criar_usuario, refeicao, produto) -> None:
    secao("C15: onde comprar")
    novo_banco()
    validade = (banco.agora().date() + timedelta(days=4)).isoformat()
    criar_usuario("w1")
    plano = {
        "refeicoes": [refeicao("seg", "almoco", "Arroz, feijão e frango",
                               [("arroz", 2000, "g"), ("feijão", 1500, "g"), ("frango", 900, "g"), ("cebola", 3, "un")]),
                      refeicao("ter", "almoco", "Macarrão com carne moída", [("carne moída", 2000, "g")])],
        "produtos": [produto("arroz", "pacote 5 kg", 5000, "g", 25.0, "Mercearia", False),
                     produto("feijão", "pacote 1 kg", 1000, "g", 8.0, "Mercearia", False),
                     produto("frango", "bandeja 1 kg", 1000, "g", 15.0, "Açougue e aves", True),
                     produto("cebola", "unidade", 1, "un", 1.0, "Hortifrúti", True),
                     produto("carne moída", "pacote 500 g", 500, "g", 20.0, "Açougue e aves", True)],
    }
    plano["cesta"], plano["orcamento"] = cesta.calcular(plano, {}), 200.0
    banco.salvar_plano("w1", plano)

    def promo(mercado_nome, nome, tamanho, preco, condicao=None):
        banco.adicionar_promocao(mercado=mercado_nome, produto=nome, tamanho=tamanho, preco=preco, validade=validade,
                                 cidade="Goiânia", origem="site", condicao=condicao)
    promo("Prezunic", "arroz", "5 kg", 19.90, "com clube")
    promo("Prezunic", "feijão carioca", "1 kg", 6.59)
    promo("Prezunic", "carne moída", "500 g", 14.0)
    promo("Atacadão", "arroz agulhinha", "1 kg", 5.00)
    promo("Atacadão", "coxa de frango", "1 kg", 6.99)
    promo("Dia a Dia", "detergente", "500 ml", 1.99)

    ok(onde_comprar.quantidade("5 kg") == ("g", 5000) and onde_comprar.quantidade("1,5 L") == ("ml", 1500)
       and onde_comprar.quantidade("30 un") == ("un", 30) and onde_comprar.quantidade("") is None,
       "lê o tamanho da promoção (5 kg = 5000 g; 1,5 L = 1500 ml)")
    perfil = banco.usuario("w1")
    atual = banco.plano_atual("w1")
    mercados = onde_comprar.comparar(atual, perfil)
    totais = [(m.nome, m.total) for m in mercados]
    ok(totais == [("Prezunic", 107.08), ("Atacadão", 115.99), ("Dia a Dia", 139.0)],
       f"total da lista em cada mercado: promoção quando há, senão o estimado {totais}")
    atacadao = mercados[1]
    arroz = next(i for i in atacadao.itens if i.chave == "arroz")
    ok(arroz.custo == 10.0 and arroz.promocao["produto"] == "arroz agulhinha",
       "promoção convertida para o que a lista precisa (2 kg = 2 pacotes de 1 kg por R$ 5)")
    ok(onde_comprar.porcentagem_real(mercados[0]) == 60, "mostra o % da lista com preço real (3 de 5 itens)")
    ok(onde_comprar.condicoes(mercados) == ["Arroz no Prezunic: com clube"],
       "avisa as condições das promoções usadas (clube, app, leve X pague Y)")
    divisao = onde_comprar.melhor_divisao(mercados)
    ok(divisao and divisao.mercados == ("Prezunic", "Atacadão") and divisao.economia == 17.91
       and divisao.itens["arroz"] == "Atacadão" and divisao.itens["carne moida"] == "Prezunic",
       "dividir entre 2 mercados quando economiza R$ 15 ou mais (aqui, R$ 17,91)")
    sem_carne = [onde_comprar.Mercado(m.nome, [i for i in m.itens if i.chave != "carne moida"]) for m in mercados]
    ok(onde_comprar.melhor_divisao(sorted(sem_carne, key=lambda m: m.total)) is None,
       "não sugere dividir quando a economia é menor que R$ 15")
    vegetariano = {**perfil, "restricoes": ["vegetariano"]}
    frango_v = next(i for m in onde_comprar.comparar(atual, vegetariano) if m.nome == "Atacadão"
                    for i in m.itens if i.chave == "frango")
    ok(frango_v.promocao is None, "promoção de algo que a pessoa não pode comer não entra na conta")

    # telas e escolha
    s = asyncio.run(atendimento.acao("w1", "oc:ver"))
    t = s[0].texto
    ok("🥇 *Prezunic*: R$ 107,08" in t and "🥈 *Atacadão*: R$ 115,99" in t and "🥉 *Dia a Dia*: R$ 139,00" in t
       and "economiza *R$ 17,91*" in t and "60% da lista tem preço real" in t and "com clube" in t
       and "📍 Mande sua localização" in t, "tela: os 3 melhores, divisão, % com preço real, condições e pedido de localização")
    s = asyncio.run(atendimento.acao("w1", "oc:m:prezunic"))
    ok("🔥 promoção (até" in s[0].texto and "com clube" in s[0].texto and "≈ R$ 15,00 estimado" in s[0].texto,
       "itens de um mercado: '🔥 promoção (até dd/mm)' ou '≈ estimado'")
    asyncio.run(atendimento.acao("w1", "oc:div"))
    dividido = banco.plano_atual("w1")
    ok(mercado.resumo(dividido)["valor_total"] == 89.17 and "✂️ Compra dividida: Prezunic e Atacadão"
       in telas.lista(dividido).texto, "dividir: a lista passa a usar os preços de cada mercado (total R$ 89,17)")
    texto_pdf = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.gerar(dividido, perfil))).pages)
    ok("Comprar no Prezunic" in texto_pdf and "Comprar no Atacadão" in texto_pdf,
       "PDF da compra dividida separa os itens por mercado")
    asyncio.run(atendimento.acao("w1", "oc:e:atacadao"))
    um = banco.plano_atual("w1")
    ok(mercado.resumo(um)["valor_total"] == 115.99 and "🏪 Preços do Atacadão" in telas.lista(um).texto,
       "'Vou comprar aqui': lista e total com os preços daquele mercado")
    asyncio.run(atendimento.acao("w1", "oc:limpar"))
    ok("onde_comprar" not in banco.plano_atual("w1") and mercado.resumo(banco.plano_atual("w1"))["valor_total"] == 139.0,
       "desfazer a escolha volta aos preços estimados")
    ok(any(b.acao == "oc:ver" for linha in telas.resultado(dividido, perfil).botoes for b in linha),
       "resultado do plano tem o botão [🏪 Onde comprar]")
