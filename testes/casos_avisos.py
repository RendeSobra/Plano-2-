"""Testes do C14 (promoções e avisos), chamados pelo testar.py. Sem Telegram: só as decisões."""
from datetime import datetime, timedelta

import atendimento
import avisos
import banco
import cardapio
import cesta


def _quando(dia_semana: int, hora: int, minuto: int = 0) -> datetime:
    """Próxima data (a partir de hoje) com esse dia da semana, na hora pedida, em Brasília."""
    hoje = banco.agora()
    dias = (dia_semana - hoje.weekday()) % 7
    return (hoje + timedelta(days=dias)).replace(hour=hora, minute=minuto, second=0, microsecond=0)


def rodar(ok, secao, novo_banco, criar_usuario, plano_valido) -> None:
    secao("C14: promoções e avisos")
    novo_banco()
    validade = (banco.agora().date() + timedelta(days=5)).isoformat()

    def com_plano(uid: str, **perfil) -> None:
        criar_usuario(uid, **perfil)
        plano = plano_valido()
        plano["cesta"] = cesta.calcular(plano, {})
        plano["orcamento"] = 200.0
        banco.salvar_plano(uid, plano)

    com_plano("a1", preferencias="tomo leite integral todo dia")  # Ana: lista com arroz, feijão...; sem lactose
    com_plano("a2", nome="Bia", avisos_ativos=0)        # avisos desligados
    com_plano("a3", nome="Caio", cidade="Anápolis")     # outra cidade
    criar_usuario("a4", nome="Duda", cadastro_passo="pessoas")  # cadastro pela metade
    com_plano("a5", nome="Edu", aviso_dia_semana=0)     # resumo na segunda

    terca_10h = _quando(1, 10)
    ok(avisos.avisos_de_promocoes(terca_10h) == [], "primeira rodada só marca onde parou (não avisa do que já existia)")
    banco.adicionar_promocao(mercado="Prezunic", produto="arroz", marca="Tio João", tamanho="5 kg", preco=21.9,
                             preco_anterior=27.9, validade=validade, cidade="Goiânia", origem="site")
    banco.adicionar_promocao(mercado="Prezunic", produto="leite integral", preco=4.49, validade=validade,
                             cidade="Goiânia", origem="site")
    banco.adicionar_promocao(mercado="Atacadão", produto="picanha", preco=59.9, validade=validade,
                             cidade="Goiânia", origem="site")
    ok(avisos.avisos_de_promocoes(_quando(1, 22)) == [], "fora do horário (22h) ninguém é avisado")
    saidas = dict(avisos.avisos_de_promocoes(terca_10h))
    ok(set(saidas) == {"a1", "a5"}, "avisa só quem tem avisos ligados, cadastro pronto, mora na cidade e tem o produto na lista")
    texto = saidas["a1"].texto
    ok("arroz Tio João 5 kg" in texto and "R$ 21,90" in texto and "Prezunic" in texto and "picanha" not in texto,
       "o aviso traz só o que está na lista da pessoa, com preço, mercado e validade")
    ok("leite" not in texto, "nunca avisa de algo que a pessoa não pode comer (leite para quem não come lactose)")
    ok(any(b.acao == "pr:ver" for linha in saidas["a1"].botoes for b in linha), "o aviso tem o botão [🔥 Promoções]")
    banco.adicionar_promocao(mercado="Atacadão", produto="feijão carioca", preco=6.49, validade=validade,
                             cidade="Goiânia", origem="site")
    ok(avisos.avisos_de_promocoes(terca_10h) == [], "no máximo 1 aviso por dia por pessoa")

    banco.atualizar_perfil("a1", preferencias="adoro picanha no domingo, não gosto de peixe",
                           ultimo_aviso_dia=None)
    banco.adicionar_promocao(mercado="Atacadão", produto="peixe", preco=19.9, validade=validade,
                             cidade="Goiânia", origem="site")
    banco.adicionar_promocao(mercado="Atacadão", produto="picanha", preco=55.9, validade=validade,
                             cidade="Goiânia", origem="site")
    saidas = dict(avisos.avisos_de_promocoes(terca_10h))
    ok("a1" in saidas and "picanha" in saidas["a1"].texto and "peixe" not in saidas["a1"].texto,
       "preferências contam ('adoro picanha'), mas não o que a pessoa disse que não gosta ('não gosto de peixe')")

    # resumo semanal: dia e hora de cada um; nunca aviso de promoção no dia do resumo
    sabado_8h, sabado_9h = _quando(5, 8), _quando(5, 9, 5)
    ok(avisos.resumos_semanais(sabado_8h) == [], "resumo não sai antes da hora escolhida (padrão sábado 9h)")
    resumos = dict(avisos.resumos_semanais(sabado_9h))
    ok(set(resumos) == {"a1", "a3"}, "resumo no dia e hora escolhidos, só para quem tem avisos ligados")
    r = resumos["a1"].texto
    ok("sobrou" in r and "promoções em Goiânia" in r and "arroz" in r and "leite" not in r
       and any(b.acao == "pl:montar" for linha in resumos["a1"].botoes for b in linha),
       "resumo comemora a sobra, mostra as promoções (sem as proibidas) e oferece montar o cardápio")
    ok("Ainda não tenho promoções" in resumos["a3"].texto, "resumo de quem é de outra cidade não mostra as de Goiânia")
    ok(avisos.resumos_semanais(_quando(5, 15)) == [], "o resumo sai uma vez só no dia")
    banco.adicionar_promocao(mercado="Prezunic", produto="frango", preco=9.9, validade=validade,
                             cidade="Goiânia", origem="site")
    banco.atualizar_perfil("a1", ultimo_aviso_dia=None)
    ok("a1" not in dict(avisos.avisos_de_promocoes(_quando(5, 10))),
       "no dia do resumo não sai aviso de promoção (o resumo já trouxe)")
    ok(set(dict(avisos.resumos_semanais(_quando(0, 9, 30)))) == {"a5"}, "quem escolheu segunda recebe na segunda")

    # /avisos liga e desliga
    tela = avisos.alternar("a1")
    ok(banco.usuario("a1")["avisos_ativos"] == 0 and "desligados" in tela.texto and tela.botoes[0][0].acao == "av:on",
       "/avisos desliga (e mostra o botão para ligar de novo)")
    tela = avisos.alternar("a1")
    ok(banco.usuario("a1")["avisos_ativos"] == 1 and "todo sábado às 09:00" in tela.texto,
       "/avisos liga de novo e diz quando sai o resumo")
    avisos.desligar_por_bloqueio("a5")
    ok(banco.usuario("a5")["avisos_ativos"] == 0, "quem bloqueou o bot para de receber avisos")

    # /promo
    s, nova = atendimento.cadastrar_promocao("a1", "Assaí; café 500 g; 15,90; 30/12")
    ok(not nova and "administradores" in s[0].texto, "/promo só para administradores")
    s, nova = atendimento.cadastrar_promocao("999", "")
    ok(not nova and "/promo mercado; produto; preço; validade" in s[0].texto, "/promo sem dados mostra como usar")
    fim = (banco.agora().date() + timedelta(days=10)).strftime("%d/%m/%Y")
    s, nova = atendimento.cadastrar_promocao("999", f"Assaí; Café 500g; 15,90; {fim}; marca=Pilão; condicao=no app")
    cafe = banco.promocoes_validas(mercado="Assaí", produto="café")
    ok(nova and cafe and cafe[0]["preco"] == 15.9 and cafe[0]["tamanho"] == "500 g" and cafe[0]["marca"] == "Pilão"
       and cafe[0]["origem"] == "admin" and cafe[0]["condicao"] == "no app" and cafe[0]["cidade"] == "Goiânia",
       "/promo cadastra a oferta (preço com vírgula, tamanho, marca, condição; cidade padrão Goiânia)")
    s, nova = atendimento.cadastrar_promocao("999", "Assaí; café 500g; 15,90; 01/01/2020")
    ok(not nova and "venceram" in s[0].texto, "/promo vencida não entra")
    s, nova = atendimento.cadastrar_promocao("999", "Assaí; café 500g; 15,90; amanhã")
    ok(not nova and "validade" in s[0].texto, "/promo com data que não dá para ler explica o formato")

    # cardápio: dá preferência a promoções de comida que a pessoa pode comer
    banco.adicionar_promocao(mercado="Prezunic", produto="detergente", preco=1.99, validade=validade,
                             cidade="Goiânia", origem="site")
    promos = cardapio._promos_do_perfil(banco.usuario("a1"))
    nomes = [p["produto"] for p in promos]
    ok("detergente" not in nomes and "leite integral" not in nomes and nomes[0] == "arroz",
       "cardápio recebe só promoções de comida que a pessoa pode comer, maior desconto primeiro")
    ok("Dê preferência aos ingredientes em promoção" in cardapio.prompts.PLANO,
       "as instruções do cardápio pedem preferência às promoções, sem quebrar orçamento e restrições")

    # vencidas somem
    banco.adicionar_promocao(mercado="Prezunic", produto="arroz", preco=1.0, validade="2020-01-01",
                             cidade="Goiânia", origem="site")
    ok(banco.apagar_promocoes_vencidas() == 1, "promoções vencidas são apagadas na limpeza diária")
