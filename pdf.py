"""PDF da lista de compras (biblioteca fpdf2). O arquivo é gerado só na memória.

Conteúdo: título "Rende", nome, data, itens por seção com caixinha para marcar,
embalagem, preço, itens em promoção marcados com o mercado, total, orçamento e sobra.
Usa as fontes padrão do PDF (Helvetica), que cobrem os acentos do português; emojis
e símbolos fora do Latin-1 são trocados por texto.
"""
from fpdf import FPDF

import banco
import cesta
from telas import brl, data_br, promocao_da_linha

VERDE = (22, 128, 61)
CINZA = (110, 110, 110)


def _txt(texto: str) -> str:
    """Mantém só caracteres que as fontes padrão do PDF conseguem desenhar."""
    trocas = {"–": "-", "—": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "•": "-"}
    for de, para in trocas.items():
        texto = texto.replace(de, para)
    return texto.encode("latin-1", "ignore").decode("latin-1")


def gerar(plano: dict, perfil: dict) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(*VERDE)
    pdf.cell(0, 12, "Rende", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*CINZA)
    nome = perfil.get("nome") or ""
    pdf.cell(0, 6, _txt(f"Lista de compras de {nome} - {banco.agora().strftime('%d/%m/%Y')}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    secao = None
    for linha in plano["cesta"]["linhas"]:
        if linha["pacotes"] <= 0:
            continue
        if linha["secao"] != secao:
            secao = linha["secao"]
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 8, _txt(secao), new_x="LMARGIN", new_y="NEXT")
        y = pdf.get_y()
        pdf.set_draw_color(*CINZA)
        pdf.rect(pdf.l_margin, y + 1.5, 4, 4)  # caixinha para marcar
        pdf.set_x(pdf.l_margin + 7)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(0, 0, 0)
        promo = promocao_da_linha(plano, linha)
        descricao = f"{linha['nome']} - {cesta.texto_embalagem(linha)}"
        pdf.cell(130, 7, _txt(descricao))
        pdf.cell(0, 7, _txt(brl(linha["custo"])), align="R", new_x="LMARGIN", new_y="NEXT")
        if promo:
            pdf.set_x(pdf.l_margin + 7)
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(*VERDE)
            pdf.cell(0, 5, _txt(f"PROMOÇÃO no {promo['mercado']} até {data_br(promo['validade'])}"),
                     new_x="LMARGIN", new_y="NEXT")

    total, orc = plano["cesta"]["total"], plano.get("orcamento") or 0
    pdf.ln(6)
    pdf.set_draw_color(0, 0, 0)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, _txt(f"Total: {brl(total)}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    resto = f"Sobra: {brl(orc - total)}" if total <= orc else f"Passou do orçamento: {brl(total - orc)}"
    pdf.cell(0, 6, _txt(f"Orçamento: {brl(orc)}   |   {resto}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*CINZA)
    pdf.multi_cell(0, 5, _txt("Preços estimados, exceto os itens marcados como promoção cadastrada. "
                              "Gerado pelo Rende."))
    return bytes(pdf.output())


def nome_arquivo(perfil: dict) -> str:
    return f"lista-rende-{banco.agora().strftime('%Y-%m-%d')}.pdf"
