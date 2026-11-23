"""Ajudante para controlar o celular por adb sem nunca exibir o token do bot.

Uso:
  python cel.py dump [filtro]      -> lista os elementos visíveis (texto/descrição/centro), tokens mascarados
  python cel.py tap X Y
  python cel.py tapdesc REGEX      -> toca no primeiro elemento cujo texto/descrição casa com REGEX
  python cel.py type TEXTO         -> digita texto ASCII no campo focado
  python cel.py token ARQUIVO_ENV  -> extrai o token da tela e grava TELEGRAM_BOT_TOKEN no .env (só mostra mascarado)
  python cel.py shot ARQUIVO.png   -> captura de tela (recusa se houver token visível)
"""
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")
TMP = tempfile.gettempdir()


def adb(*args, binary=False):
    r = subprocess.run(["adb", *args], capture_output=True)
    if r.returncode != 0:
        raise SystemExit(f"adb falhou: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout if binary else r.stdout.decode("utf-8", errors="replace")


def mask(s: str) -> str:
    return TOKEN_RE.sub("<TOKEN-OCULTO>", s)


def dump_xml() -> str:
    import time
    for _ in range(4):  # às vezes o uiautomator falha uma vez (tela em transição)
        subprocess.run(["adb", "shell", "uiautomator", "dump", "/sdcard/cesta_ui.xml"], capture_output=True)
        xml = adb("exec-out", "cat", "/sdcard/cesta_ui.xml")
        adb("shell", "rm", "-f", "/sdcard/cesta_ui.xml")
        if "<hierarchy" in xml:
            return xml
        time.sleep(1)
    raise SystemExit("não consegui ler a tela do celular")


def nodes(xml: str):
    root = ET.fromstring(xml[xml.find("<?xml"):] if "<?xml" in xml else xml)
    for n in root.iter("node"):
        txt = n.get("text") or ""
        desc = n.get("content-desc") or ""
        if not (txt or desc):
            continue
        m = re.findall(r"\d+", n.get("bounds", ""))
        if len(m) != 4:
            continue
        x1, y1, x2, y2 = map(int, m)
        yield txt, desc, (x1 + x2) // 2, (y1 + y2) // 2, n.get("class", "").split(".")[-1]


def main():
    cmd = sys.argv[1]
    if cmd == "dump":
        filtro = re.compile(sys.argv[2], re.I) if len(sys.argv) > 2 else None
        for txt, desc, x, y, cls in nodes(dump_xml()):
            linha = f"[{x},{y}] {cls} | text={txt!r} | desc={desc!r}"
            linha = mask(linha)
            if filtro and not filtro.search(linha):
                continue
            print(linha[:400])
    elif cmd == "tap":
        adb("shell", "input", "tap", sys.argv[2], sys.argv[3])
    elif cmd == "tapdesc":
        rx = re.compile(sys.argv[2], re.I)
        for txt, desc, x, y, cls in nodes(dump_xml()):
            if rx.search(txt) or rx.search(desc):
                adb("shell", "input", "tap", str(x), str(y))
                print(f"tocado em [{x},{y}] ({mask((txt or desc)[:60])!r})")
                return
        raise SystemExit("elemento não encontrado")
    elif cmd == "type":
        texto = sys.argv[2]
        if not texto.isascii():
            raise SystemExit("só texto ASCII (adb não digita acentos)")
        esc = texto.replace(" ", "%s")
        esc = re.sub(r"([\\'\"`$&|;<>()])", r"\\\1", esc)
        adb("shell", "input", "text", esc)
    elif cmd == "token":
        env_path, usuario = sys.argv[2], sys.argv[3].lower()
        achados = []
        for txt, desc, *_ in nodes(dump_xml()):
            for s in (txt, desc):
                # só a mensagem de sucesso do bot pedido (t.me/<usuario>), nunca a de outro bot
                if f"t.me/{usuario}" in s.lower():
                    achados += TOKEN_RE.findall(s)
        achados = list(dict.fromkeys(achados))
        if len(achados) != 1:
            raise SystemExit(f"esperava 1 token do @{usuario}, achei {len(achados)}")
        token = achados[0]
        linhas = []
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
                linhas = [l.rstrip("\n") for l in f if not l.startswith("TELEGRAM_BOT_TOKEN=")]
        linhas.insert(0, f"TELEGRAM_BOT_TOKEN={token}")
        with open(env_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(linhas) + "\n")
        print(f"token gravado em {env_path}: {token.split(':')[0][:3]}…:{'*' * 6} "
              f"(tokens vistos na tela: {len(achados)})")
    elif cmd == "shot":
        xml = dump_xml()
        if TOKEN_RE.search(xml):
            raise SystemExit("recusado: há um token visível na tela")
        png = adb("exec-out", "screencap", "-p", binary=True)
        with open(sys.argv[2], "wb") as f:
            f.write(png)
        print("ok")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
