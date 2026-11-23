"""Toca um botão e registra cada estado diferente das mensagens até aparecer um texto final."""
import re
import sys
import time

sys.path.insert(0, sys.argv[1])
import cel  # noqa: E402
import rende_cel as r  # noqa: E402

padrao, fim, espera_max = sys.argv[2], sys.argv[3], float(sys.argv[4])
candidatos = [(rot, x, y) for rot, x, y in r.botoes() if re.search(padrao, rot, re.I)]
if not candidatos:
    sys.exit(f"botão não encontrado: {padrao}")
rot, x, y = max(candidatos, key=lambda c: c[2])
antes = set(r.mensagens())
cel.adb("shell", "input", "tap", str(x), str(y))
inicio = time.time()
print(f"tocado: {rot!r}")
vistos: list[str] = []
while time.time() - inicio < espera_max:
    lista = r.nos()
    for m in r.mensagens(lista):
        corpo = re.sub(r"\n(Recebido|Enviado|Editado) às.*$", "", m.strip(), flags=re.S)
        if m not in antes and corpo not in vistos:
            vistos.append(corpo)
            print(f"\n[{time.time() - inicio:5.1f}s]\n{corpo}")
    if any(re.search(fim, m) for m in r.mensagens(lista)):
        time.sleep(2)
        break
    time.sleep(0.7)
print("\n----- botões visíveis: " + " | ".join(rot for rot, _, _ in r.botoes()))
