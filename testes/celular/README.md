# Ajudantes do teste pelo celular (adb)

Scripts usados para testar o Rende no Telegram de um celular Android ligado ao computador
por cabo (depuração USB ligada e autorizada). Eles leem a tela como texto (uiautomator),
tocam nos botões pelo nome e esperam a resposta. Qualquer coisa com cara de token de bot
aparece mascarada.

Combine antes com o dono do celular: se ele usar o aparelho ao mesmo tempo, um toque pode
cair em outro app.

Todos recebem a pasta destes scripts como primeiro argumento:

```powershell
$C = "testes\celular"
python -I -X utf8 $C\rende_cel.py $C abrir                # abre a conversa com o bot
python -I -X utf8 $C\rende_cel.py $C enviar "/start" 30   # manda texto e espera até 30 s
python -I -X utf8 $C\rende_cel.py $C tocar "Continuar" 20 # toca um botão (regex do rótulo)
python -I -X utf8 $C\rende_cel.py $C tela                 # últimas mensagens e botões visíveis
python -I -X utf8 $C\observar.py $C "Confirmar" "Sua semana est" 360  # registra a "animação"
python -I -X utf8 $C\trocar.py $C "Almoço" 240            # toca o 🔁 da refeição e mostra o resultado
```

- `cel.py`: base (adb, leitura da tela, toque, digitação ASCII, extração do token do
  BotFather direto para o `.env`).
- `rende_cel.py`: comandos do teste do Rende.
- `observar.py` / `trocar.py`: registram mensagens editadas (plano e troca de prato).

Limitação: o `adb shell input text` não digita acentos.
