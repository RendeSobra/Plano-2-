"""PDF da lista de compras. O arquivo é gerado só na memória (nunca vai para o disco).

Conteúdo (C11): título "Rende", nome, data, itens por seção com caixinha para marcar,
embalagem, preço, marca "PROMOÇÃO (mercado, até dd/mm)" ou "≈ estimado" (ou "preço pago",
quando a pessoa informou no Modo mercado), total, orçamento e sobra, e a dica do Modo mercado.

Duas bibliotecas, cada uma no que faz bem:
- fpdf2 desenha a página toda, inclusive o quadradinho de cada item (sai na impressão
  mesmo em leitores que ignoram formulários);
- pypdf põe, em cima de cada quadradinho, uma caixinha de formulário (checkbox AcroForm)
  que se marca com um toque no Adobe Acrobat, no Google Drive e no leitor do navegador.
  A fpdf2 2.9 só cria campos de formulário para assinatura digital, não caixinhas; a pypdf
  é só Python (sem programa externo) e mexe só nessa parte. A marquinha ✓ é desenhada com
  linhas, sem depender de fonte, e a caixinha tem a opção "imprimir" ligada.

As fontes padrão do PDF (Helvetica) não têm emoji: os marcadores viram texto, e o "≈" é
desenhado com a fonte Symbol, que todo leitor de PDF tem.
"""
import io

from fpdf import FPDF
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject, FloatObject, NameObject,
                           NumberObject, TextStringObject)

import banco
import cesta
import mercado
from telas import brl, data_br, promocao_da_linha

VERDE = (22, 128, 61)
LARANJA = (214, 90, 0)
CINZA = (110, 110, 110)
LADO_CAIXA = 4.2          # mm
APROXIMADO_SYMBOL = "\xbb"  # "≈" na codificação da fonte Symbol
DICA = "Dica: no Telegram, use o Modo mercado para marcar direto no app."


def _txt(texto: str) -> str:
    """Mantém só caracteres que as fontes padrão do PDF conseguem desenhar."""
    trocas = {"–": "-", "—": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "•": "-"}
    for de, para in trocas.items():
        texto = texto.replace(de, para)
    return texto.encode("latin-1", "ignore").decode("latin-1")


def _marca(pdf: FPDF, plano: dict, linha: dict, promo: dict | None, largura: float) -> None:
    """A marca do item: PROMOÇÃO, preço pago ou ≈ estimado."""
    x = pdf.get_x()
    if promo:
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*LARANJA)
        pdf.cell(largura, 7, _txt("PROMOÇÃO"))
    elif cesta.chave(linha["item"]) in ((plano.get("mercado") or {}).get("precos") or {}):
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*VERDE)
        pdf.cell(largura, 7, _txt("preço pago"))
    else:
        pdf.set_text_color(*CINZA)
        pdf.set_font("Symbol", "", 9)
        pdf.cell(3, 7, APROXIMADO_SYMBOL)
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(largura - 3, 7, "estimado")
    pdf.set_x(x + largura)


def _pagina(plano: dict, perfil: dict) -> tuple[bytes, list[tuple], float]:
    """Desenha o PDF (fpdf2). Devolve (pdf, caixinhas [(página, x, y, nome)], altura da página em mm)."""
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

    caixas: list[tuple] = []
    secao = None
    for linha in mercado.linhas(plano):
        promo = promocao_da_linha(plano, linha)
        altura = 7 + (5 if promo else 0)
        if linha["secao"] != secao:
            altura += 10
        if pdf.will_page_break(altura):  # a caixinha e o item ficam na mesma página
            pdf.add_page()
        if linha["secao"] != secao:
            secao = linha["secao"]
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 8, _txt(secao), new_x="LMARGIN", new_y="NEXT")
        y = pdf.get_y()
        pdf.set_draw_color(*CINZA)
        pdf.rect(pdf.l_margin, y + 1.4, LADO_CAIXA, LADO_CAIXA)  # quadradinho (sai na impressão)
        caixas.append((pdf.page_no(), pdf.l_margin, y + 1.4, linha["nome"]))
        pdf.set_x(pdf.l_margin + 7)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(118, 7, _txt(f"{linha['nome']} - {cesta.texto_embalagem(linha)}"))
        _marca(pdf, plano, linha, promo, 24)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 7, _txt(brl(mercado.custo_linha(plano, linha))), align="R", new_x="LMARGIN", new_y="NEXT")
        if promo:
            pdf.set_x(pdf.l_margin + 7)
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(*LARANJA)
            pdf.cell(0, 5, _txt(f"({promo['mercado']}, até {data_br(promo['validade'])})"),
                     new_x="LMARGIN", new_y="NEXT")

    # soma o que aparece em cada linha (com o preço pago, quando a pessoa informou)
    total, orc = mercado.resumo(plano)["valor_total"], plano.get("orcamento") or 0
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
    pdf.multi_cell(0, 5, _txt("Preços marcados como estimado são uma média; PROMOÇÃO é oferta cadastrada, com "
                              "mercado e validade. Toque na caixinha para marcar o que já está no carrinho."))
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*VERDE)
    pdf.multi_cell(0, 5, _txt(DICA))
    return bytes(pdf.output()), caixas, pdf.h


def _aparencia(writer: PdfWriter, lado: float, conteudo: bytes):
    fluxo = DecodedStreamObject()
    fluxo.set_data(conteudo)
    fluxo.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Form"),
                  NameObject("/BBox"): ArrayObject([FloatObject(0), FloatObject(0), FloatObject(lado),
                                                    FloatObject(lado)]),
                  NameObject("/Resources"): DictionaryObject()})
    return writer._add_object(fluxo)


def _caixinhas(pdf_bytes: bytes, caixas: list[tuple], altura_mm: float) -> bytes:
    """Põe uma caixinha de formulário (AcroForm) em cima de cada quadradinho desenhado."""
    escala = 72 / 25.4  # mm -> pontos (o PDF mede de baixo para cima)
    lado = LADO_CAIXA * escala
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_bytes)))
    marcado = _aparencia(writer, lado, (
        f"q 0.09 0.50 0.24 RG {lado * 0.14:.2f} w 1 J 1 j {lado * 0.2:.2f} {lado * 0.52:.2f} m "
        f"{lado * 0.42:.2f} {lado * 0.22:.2f} l {lado * 0.84:.2f} {lado * 0.84:.2f} l S Q").encode())
    vazio = _aparencia(writer, lado, b"")
    campos = ArrayObject()
    for n, (pagina, x, y, nome) in enumerate(caixas, 1):
        pagina_pdf = writer.pages[pagina - 1]
        x0, y0 = x * escala, (altura_mm - y - LADO_CAIXA) * escala
        widget = DictionaryObject({
            NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/FT"): NameObject("/Btn"), NameObject("/T"): TextStringObject(f"item_{n:03d}"),
            NameObject("/TU"): TextStringObject(nome),
            NameObject("/Rect"): ArrayObject([FloatObject(round(x0, 2)), FloatObject(round(y0, 2)),
                                              FloatObject(round(x0 + lado, 2)), FloatObject(round(y0 + lado, 2))]),
            NameObject("/F"): NumberObject(4),  # 4 = imprimir: a marquinha sai no papel
            NameObject("/V"): NameObject("/Off"), NameObject("/AS"): NameObject("/Off"),
            NameObject("/DA"): TextStringObject("/ZaDb 0 Tf 0.09 0.5 0.24 rg"),
            NameObject("/MK"): DictionaryObject({NameObject("/CA"): TextStringObject("4")}),
            NameObject("/AP"): DictionaryObject({NameObject("/N"): DictionaryObject({
                NameObject("/Yes"): marcado, NameObject("/Off"): vazio})}),
            NameObject("/P"): pagina_pdf.indirect_reference,
        })
        ref = writer._add_object(widget)
        if "/Annots" not in pagina_pdf:
            pagina_pdf[NameObject("/Annots")] = ArrayObject()
        pagina_pdf["/Annots"].get_object().append(ref)
        campos.append(ref)
    fonte_zadb = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                                   NameObject("/BaseFont"): NameObject("/ZapfDingbats")})
    writer.root_object[NameObject("/AcroForm")] = DictionaryObject({
        NameObject("/Fields"): campos,
        NameObject("/DA"): TextStringObject("/ZaDb 0 Tf 0 g"),
        NameObject("/DR"): DictionaryObject({NameObject("/Font"): DictionaryObject({
            NameObject("/ZaDb"): writer._add_object(fonte_zadb)})}),
    })
    saida = io.BytesIO()
    writer.write(saida)
    return saida.getvalue()


def gerar(plano: dict, perfil: dict) -> bytes:
    pdf_bytes, caixas, altura = _pagina(plano, perfil)
    return _caixinhas(pdf_bytes, caixas, altura) if caixas else pdf_bytes


def nome_arquivo(perfil: dict) -> str:
    return f"lista-rende-{banco.agora().strftime('%Y-%m-%d')}.pdf"
