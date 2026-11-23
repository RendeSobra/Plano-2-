"""Ajudante do teste do Rende pelo celular (adb), lendo a tela como texto (tokens mascarados).

  python rende_cel.py abrir
  python rende_cel.py tela
  python rende_cel.py enviar "texto" [espera_max]
  python rende_cel.py tocar "regex do botão" [espera_max]
"""
import re
import sys
import time

sys.path.insert(0, sys.argv[1])
import cel  # noqa: E402


def nos():
    """[(texto, desc, x, y, classe, clicavel, bounds)]"""
    import xml.etree.ElementTree as ET
    xml = cel.dump_xml()
    raiz = ET.fromstring(xml[xml.find("<?xml"):] if "<?xml" in xml else xml)
    saida = []
    for n in raiz.iter("node"):
        m = re.findall(r"\d+", n.get("bounds", ""))
        if len(m) != 4:
            continue
        x1, y1, x2, y2 = map(int, m)
        saida.append((n.get("text") or "", n.get("content-desc") or "", (x1 + x2) // 2, (y1 + y2) // 2,
                      n.get("class", "").split(".")[-1], n.get("clickable") == "true", (x1, y1, x2, y2)))
    return saida


def mensagens(lista=None):
    lista = lista or nos()
    return [cel.mask(t or d) for t, d, x, y, c, k, b in lista
            if c == "ViewGroup" and re.search(r"(Recebido|Enviado|Editado) às|editad", t or d)]


def digitando(lista=None):
    lista = lista or nos()
    return any(re.search(r"typing|digitando", (t + d), re.I) for t, d, *_ in lista)


def botoes(lista=None):
    """Botões do bot visíveis (nós clicáveis com rótulo, fora da barra de cima e do campo de texto)."""
    lista = lista or nos()
    campo_y = next((y for t, d, x, y, c, k, b in lista if c == "EditText"), 2300)
    vistos = []
    for t, d, x, y, c, k, b in lista:
        rotulo = (t or d).strip()
        if not rotulo or c in ("EditText", "ViewGroup") or y < 300 or y > campo_y - 40:
            continue
        if rotulo in ("Voltar", "More options", "Foto de perfil", "Bot menu", "Enviar", "Attach media"):
            continue
        if k or c in ("View", "Button", "TextView"):
            vistos.append((rotulo, x, y))
    return vistos


def esperar(antes: list[str], espera_max: float) -> None:
    inicio = time.time()
    ultimo, estavel = None, 0
    while time.time() - inicio < espera_max:
        time.sleep(1.5)
        lista = nos()
        atual = mensagens(lista)
        if atual != antes and not digitando(lista):
            estavel = estavel + 1 if atual == ultimo else 0
            if estavel >= 2:
                break
        ultimo = atual
    lista = nos()
    atual = mensagens(lista)
    novas = [m for m in atual if m not in antes]
    print(f"[{time.time() - inicio:.0f}s] {len(novas)} mensagem(ns) nova(s)/editada(s):")
    for m in novas:
        print("-----\n" + m.strip())
    print("----- botões visíveis: " + " | ".join(r for r, _, _ in botoes(lista)))


def enviar(texto: str, espera_max: float) -> None:
    antes = mensagens()
    lista = nos()
    x, y = next((x, y) for t, d, x, y, c, k, b in lista if c == "EditText")
    cel.adb("shell", "input", "tap", str(x), str(y))
    time.sleep(0.8)
    cel.adb("shell", "input", "text", re.sub(r"([\\'\"`$&|;<>()])", r"\\\1", texto.replace(" ", "%s")))
    time.sleep(1.2)
    y_enviar = next(y for t, d, x, y, c, k, b in nos() if d == "Enviar")
    cel.adb("shell", "input", "tap", "1010", str(y_enviar))
    esperar(antes, espera_max)


def tocar(padrao: str, espera_max: float) -> None:
    antes = mensagens()
    candidatos = [(r, x, y) for r, x, y in botoes() if re.search(padrao, r, re.I)]
    if not candidatos:
        print("botão não encontrado:", padrao, "| visíveis:", " | ".join(r for r, _, _ in botoes()))
        sys.exit(1)
    rotulo, x, y = max(candidatos, key=lambda c: c[2])  # o mais de baixo (mensagem mais recente)
    cel.adb("shell", "input", "tap", str(x), str(y))
    print(f"tocado: {rotulo!r}")
    esperar(antes, espera_max)


if __name__ == "__main__":
    comando = sys.argv[2]
    if comando == "abrir":
        cel.adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d",
                "tg://resolve?domain=cesta_cardapio_bot", "org.telegram.messenger")
        time.sleep(3)
        print("\n-----\n".join(mensagens()[-3:]))
    elif comando == "tela":
        lista = nos()
        print("\n-----\n".join(mensagens(lista)[-3:]))
        print("----- botões: " + " | ".join(f"{r}@{y}" for r, _, y in botoes(lista)))
    elif comando == "enviar":
        enviar(sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else 60)
    elif comando == "tocar":
        tocar(sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else 60)
