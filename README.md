# Plano-2-

**Rende**: assistente de mercado no Telegram, em Python. Monta o cardápio da semana e a
lista de compras **por embalagem**, dentro do orçamento, para famílias brasileiras (foco em
Goiânia). Entende texto, áudio, foto e PDF, tem cadastro com botões, receita passo a passo,
PDF da lista e uma **escada de modelos de IA** (Gemini → Claude Haiku → Sonnet → Opus) que só
sobe de nível quando precisa.

Bot no Telegram: `@cesta_cardapio_bot` (nome de exibição "Rende").

- **Contexto completo, decisões e próximos passos:** [CONTEXTO.md](CONTEXTO.md)
- **Situação de cada pedido:** [PLANO.md](PLANO.md)
- **Texto de todos os pedidos:** [docs/PEDIDOS.md](docs/PEDIDOS.md)

## Como rodar

Precisa de Python 3.11 ou mais novo.

```powershell
py -3 -m venv .venv          # qualquer Python 3.11+ instalado serve
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env      # e preencha as chaves (nunca vão para o Git)
.venv\Scripts\python bot_telegram.py
```

Chaves no `.env`: `TELEGRAM_BOT_TOKEN` (BotFather), `GEMINI_API_KEY` (Google AI Studio) e
`ANTHROPIC_API_KEY` (console da Anthropic). O resto já vem com valor padrão no `.env.example`.

Sem `ANTHROPIC_API_KEY` o bot liga assim mesmo e faz o cardápio no Gemini (o roteador avisa no
log). Sem `TELEGRAM_BOT_TOKEN` ou `GEMINI_API_KEY` ele para na hora, dizendo o que falta.

## Colocar no ar (Railway, Render ou qualquer contêiner)

Duas regras que, se forem esquecidas, só dão problema depois de já estar no ar:

**1. Uma cópia só.** O bot usa *long polling* (`run_polling`). Duas cópias com o mesmo token
brigam pelas mensagens e o Telegram recusa uma delas. Suba como **Background Worker** com
exatamente 1 réplica — nunca aumente a escala horizontal.

**2. O banco precisa de disco que sobreviva ao deploy.** O `rende.db` é um arquivo SQLite. Nos
contêineres do Railway/Render o sistema de arquivos é apagado a cada deploy ou reinício: sem
cuidado, todos os perfis, planos e despensas somem. Escolha uma:

- anexar um volume (Railway Volume / Render Disk) e apontar `BANCO_ARQUIVO` para dentro dele,
  por exemplo `BANCO_ARQUIVO=/dados/rende.db`;
- ou trocar o SQLite pelo Supabase, reescrevendo **só** o `banco.py` (nenhum outro arquivo
  fala SQL).

As chaves vão nas variáveis de ambiente do serviço, nunca num arquivo enviado para o Git.

## Testes automáticos

Não chamam nenhuma IA de verdade (são simuladas) nem o Telegram:

```powershell
.venv\Scripts\python testes\testar.py
```

## Arquivos

| Arquivo | Papel |
|---|---|
| `bot_telegram.py` | Única parte que fala com o Telegram (mensagens, botões, arquivos, animação) |
| `atendimento.py` | O "cérebro": junta perfil, histórico, IA, ferramentas e telas |
| `roteador.py` | Escada de modelos: escolhe o modelo, sobe de nível, limites diários, custos |
| `ia.py` / `ia_claude.py` / `ia_comum.py` | Falam com o Gemini / Claude, com a mesma interface |
| `ferramentas.py` | Ações que a IA de conversa pode pedir (function calling) |
| `cardapio.py` | Gera, confere e troca o plano; receitas; notas dos pratos |
| `cesta.py` | Conta por embalagem, despensa e custo por refeição (sempre em código) |
| `restricoes.py` | Alergias e restrições conferidas em código |
| `cadastro.py` | Cadastro com botões (10 passos) e /perfil |
| `telas.py` | Telas (texto + botões) sem depender do Telegram |
| `pdf.py` | PDF da lista (fpdf2), só na memória |
| `banco.py` | Único acesso a dados (SQLite `rende.db`; trocar por Supabase mexendo só nele) |
| `prompts.py` | Personalidade e instruções das IAs; mensagens fixas |
| `testes/` | Testes automáticos e ajudantes do teste pelo celular |
