"""Toca o '🔁 Trocar' da mesma linha de um '📖 <Refeição>' e registra o resultado."""
import re
import sys
import time

sys.path.insert(0, sys.argv[1])
import cel  # noqa: E402
import rende_cel as r  # noqa: E402

refeicao, espera_max = sys.argv[2], float(sys.argv[3])
botoes = r.botoes()
y_ref = max(y for rot, x, y in botoes if rot == f"📖 {refeicao}")
x, y = next((x, y) for rot, x, y in botoes if "Trocar" in rot and abs(y - y_ref) < 20)
antes = set(r.mensagens())
cel.adb("shell", "input", "tap", str(x), str(y))
inicio = time.time()
print(f"tocado: 🔁 Trocar ({refeicao})")
vistos = []
while time.time() - inicio < espera_max:
    msgs = r.mensagens()
    for m in msgs:
        corpo = re.sub(r"\n(Recebido|Enviado|Editado) às.*$", "", m.strip(), flags=re.S)
        if m not in antes and corpo not in vistos:
            vistos.append(corpo)
            print(f"\n[{time.time() - inicio:5.1f}s]\n{corpo}")
    if any(re.search(r"Troquei|Não consegui trocar", m) for m in msgs):
        break
    time.sleep(1)
