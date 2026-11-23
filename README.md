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
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env      # e preencha as chaves (nunca vão para o Git)
.venv\Scripts\python bot_telegram.py
```

Chaves no `.env`: `TELEGRAM_BOT_TOKEN` (BotFather), `GEMINI_API_KEY` (Google AI Studio) e
`ANTHROPIC_API_KEY` (console da Anthropic). O resto já vem com valor padrão no `.env.example`.

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
