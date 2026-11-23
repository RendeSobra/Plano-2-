# Contexto do projeto Rende (para retomar o trabalho)

Última atualização: 23/11/2026. Tudo foi feito numa conversa longa com o Claude Code
(Opus 5.5), com o celular do dono do projeto ligado ao computador por cabo (adb) para os
testes no Telegram. O texto de cada pedido está em [docs/PEDIDOS.md](docs/PEDIDOS.md).

> **Para retomar com o Claude Code:** peça "leia o CONTEXTO.md, o PLANO.md e o
> docs/PEDIDOS.md e continue pelos próximos passos". Rode os testes antes de mexer.

---

## 1. O que é

Bot de Telegram em Python que virou um **assistente de mercado** chamado **Rende**:
cadastro com botões, plano da semana (cardápio + lista de compras por embalagem) dentro do
orçamento, troca de pratos, receita passo a passo com nota, PDF da lista, conversa livre
por texto, áudio e foto, e uma escada de modelos de IA que sobe de nível só quando precisa.

- Bot: `@cesta_cardapio_bot`. Nasceu como "Cesta" e foi renomeado para "Rende" pela API.
- Pasta local: `C:\Users\Matheus Duarte\cesta-bot` (ambiente virtual em `.venv`).
- Por enquanto roda **só no computador local** (polling). Desligou o computador, o bot para.

## 2. Linha do tempo (23/11/2026)

1. **Bot "Cesta" (pedido 0):** bot criado pelo @BotFather pelo celular via adb. O token foi
   lido da tela por um script que o gravou direto no `.env`, sem nunca aparecer na conversa.
   A descrição e os comandos foram configurados pela API do Telegram, porque o adb não
   digita acentos. Python + python-telegram-bot 22.8 + Gemini (google-genai). Testado no
   celular: R$ 300/semana, 3 pessoas, Goiânia.
   - Defeito achado no teste: **a IA errou a soma da lista** (disse R$ 297,50; o certo era
     R$ 288,00). Solução: o total passou a ser calculado **em código**, sempre.
   - O Gemini esteve **sobrecarregado (503)** o dia todo. Solução: retentativa, modelo
     reserva (`gemini-3.6-flash`), aviso "⏳ A IA está mais lenta…" após 25 s e `/novo`
     que vale na hora (descarta resposta atrasada).
2. **Áudio e foto (pedido A):** download só na memória (nada no disco), limites de 2 min e
   10 MB, áudio e foto contam no limite diário. Testado no celular: o áudio funcionou
   ("🎤 Entendi: R$ 300 por semana…"). **Foto de geladeira e de nota fiscal ainda não
   foram testadas no celular.**
3. **Rende (pedido B) + roteador (D) + experiência com botões (E):** construídos juntos,
   porque o pedido E mudou o formato do cardápio. SQLite (`banco.py`), function calling,
   cadastro de 10 passos com botões, "Montando seu plano" com etapas reais, cardápio por dia,
   troca de prato, receita passo a passo, nota 1–5, PDF (fpdf2), `/perfil`, `/novo`,
   `/esquecer` (LGPD, com confirmação), `/custos` (admin).
4. **Escada de modelos (pedido F):** substituiu o roteador do pedido D. Gemini → Haiku →
   Sonnet → Opus, limites diários por modelo, prompt caching e `/custos` com subidas de nível.
5. **Teste completo no celular** (cadastro, animação, plano, 2 trocas, receita, nota, PDF,
   `/custos`). Resultados na seção 6.
6. **Ajustes pedidos depois do teste:** a confirmação de troca virou uma linha no topo da
   tela do dia (sem mensagem extra). O PDF some sozinho depois de `APAGAR_PDF_APOS_MIN`
   minutos (padrão 5), e gerar um novo apaga o anterior. Os dois foram testados no celular.

## 3. Arquitetura (cada arquivo com um papel)

| Arquivo | Papel |
|---|---|
| `bot_telegram.py` | Só Telegram: recebe mensagens/botões, baixa arquivos para a memória, desenha telas, anima o plano, agenda a remoção do PDF |
| `atendimento.py` | "Cérebro" neutro: cadastro, conversa com IA + ferramentas, botões, plano, troca, `/custos` |
| `roteador.py` | Escada de modelos, conferência com subida de nível, limites diários, registro de custo |
| `ia.py` / `ia_claude.py` | Adaptadores do Gemini e do Claude (mesma interface; `ia_comum.py` tem os tipos) |
| `ferramentas.py` | Ferramentas da IA: salvar_perfil, montar_plano, trocar_prato, mostrar, avaliar_prato, listar_promocoes, configurar_avisos, pedir_especialista |
| `cardapio.py` | Gera/confere/troca o plano, receitas (geradas ao abrir e guardadas), notas |
| `cesta.py` | Compra por embalagem inteira, despensa, custo por refeição e total (em código) |
| `restricoes.py` | Alergias/restrições conferidas em código (com exceções como "leite de coco", "pão de queijo", "couve-manteiga") |
| `cadastro.py` | Cadastro com botões e edição pelo `/perfil` |
| `telas.py` | Telas neutras (texto + botões); o canal só desenha |
| `pdf.py` | PDF da lista, só na memória |
| `banco.py` | Único acesso a dados. SQLite `rende.db` (fora do Git). Para ir ao Supabase, reescrever só ele |
| `prompts.py` | Personalidade (a mesma para Gemini e Claude), instruções de plano/troca/receita, mensagens fixas |

Tabelas: `usuarios`, `historico` (30 últimas), `planos` (3 últimos; o mais novo é o atual),
`promocoes`, `uso_diario`, `uso_ia` (custo por chamada, sem texto de conversa nem usuário).

## 4. Decisões importantes

- **Nunca confiar só na IA:** soma, embalagens, despensa, alergias, utensílios, repetição de
  pratos e orçamento são conferidos em código. Reprovou → o nível de cima refaz, recebendo o motivo.
- **Escada de modelos:** conversa/áudio/foto/receitas/encartes no Gemini (reserva e depois
  Haiku como substitutos; **áudio nunca vai para o Claude**). Trocar prato: Haiku → Sonnet → Opus.
  Gerar cardápio: Sonnet → Opus. Opus só por escalonamento ou caso complexo (3+ restrições,
  ou otimizar promoções de vários mercados). Todos os níveis do Claude falharam → Gemini.
  Pedido complexo vindo da conversa ("pedir_especialista") vai para o Sonnet.
- **API do Claude:** SDK `anthropic` 2.12, IDs sem data; sem temperature/top_p/top_k/
  budget_tokens/thinking; `tool_choice` "auto"; effort explícito ("low" na conversa,
  "medium" em troca e cardápio); `stop_reason` "refusal" sobe de nível; prompt caching nas
  instruções fixas (conferido na API real: 3.699 tokens lidos do cache, custo ~7x menor).
  O "fallback no servidor" da Anthropic **não** foi ativado (a regra manda recusa para o próximo nível).
- **Botões e telas neutras** (`telas.py`) para facilitar um canal futuro (WhatsApp).
- Receita gerada só quando a pessoa abre o prato (Gemini, barato) e guardada no plano.
- "Compra do mês" ainda gera plano semanal com orçamento mensal ÷ 4,3.
- Segredos: `.env` e `rende.db` ficam fora do Git; o log mascara tokens e chaves.

## 5. Como rodar e testar

Veja o [README](README.md). Testes automáticos: `.venv\Scripts\python testes\testar.py`
(**101 de 101 OK** em 23/11/2026). Ajudantes do teste pelo celular em `testes/celular/`.

## 6. Resultado do teste real no celular (23/11/2026)

| Etapa | Resultado | Quem fez / custo (tabela) |
|---|---|---|
| Cadastro (nome, 2 adultos + 1 criança, café/almoço/jantar, 7 dias, comida de vó, lactose, fogão + pressão, Assaí, semana, R$ 300 sugeridos) | ✅ | Sem IA |
| "Montando seu plano" (5 etapas, com "Ajustando as receitas") | ✅ 146 s | Sonnet US$ 0,131 → Opus US$ 0,203 |
| Resultado: R$ 289,50 de R$ 300, sobra R$ 10,50, 23 itens | ✅ | n/a |
| Troca 1 (almoço de segunda) | ✅ 29 s | Haiku US$ 0,001 (reprovado: +R$ 15) → Sonnet US$ 0,019 |
| Troca 2 (jantar de terça), total R$ 291,00 | ✅ | Haiku US$ 0,001 (reprovado: +R$ 13) → Sonnet US$ 0,013 |
| Receita com medidas brasileiras, para 2,5 porções | ✅ | Gemini US$ 0,001 |
| Passo a passo (9 passos) → Fiz! → ⭐⭐⭐⭐⭐ salvo no perfil | ✅ | Sem IA |
| PDF da lista (e sumindo sozinho) | ✅ | Sem IA |
| `/custos` | ✅ total do teste **US$ 0,37** | n/a |

## 7. Defeitos achados nos testes reais (todos corrigidos)

- Soma da lista errada pela IA → total em código.
- "Couve manteiga" barrada como lactose (falso alarme) → exceção; custou uma subida
  desnecessária ao Opus (US$ 0,20).
- Troca de prato quebrava sobras planejadas (o jantar dependia do frango do almoço) → a IA
  é avisada da sobra e o código confere.
- "♻️ Sem sobra" aparecendo na tela; "1 porções"; "2.5"; "1 chamadas"; "0.5 min" → corrigidos.
- `/novo` esperava a resposta anterior terminar → agora vale na hora.

## 8. Próximos passos (pendentes)

Em ordem sugerida:

1. **Melhorar o Haiku nas trocas:** nas 2 trocas reais ele estourou o orçamento e precisou
   do Sonnet. Passar a ele a folga exata e os itens com sobra na lista para reaproveitar.
2. **Estimativa de custo:** um plano de 21 refeições gerou 12,4 mil tokens de saída no
   Sonnet (~US$ 0,13), acima do estimado. Avaliar `effort` "low" ou dividir a geração.
3. **Pedido A, teste no celular:** foto de geladeira e de nota fiscal (o dono grava/fotografa).
4. **B2 (entender qualquer mensagem):** foto de **encarte** → extrair ofertas e chamar
   `salvar_promocoes_de_encarte` (ferramenta ainda não criada). Texto, voz, foto, PDF,
   localização (só salva) e figurinha já funcionam.
5. **B4 (mercados próximos):** botão "📍 Enviar minha localização", busca no Overpass
   (OpenStreetMap) num raio de 3 km, até 8 mercados com distância e link do Google Maps,
   destacando os que têm promoção. Teste com um ponto público de Goiânia (não o GPS do dono).
6. **B5 (promoções e avisos):** `/promo` (admin), JobQueue: aviso de promoção nova para quem
   tem o produto na lista ou nas preferências (máx. 1 por dia), resumo semanal (padrão
   sábado 9h), `/avisos`, apagar promoções vencidas.
7. **Teste final no celular dos pedidos B/E** que faltam: áudio pedindo o cardápio, mandar
   localização, `/promo` e ver o aviso chegar, foto de encarte, `/esquecer`.
8. **Pedido C (coletor de promoções de Goiânia), Fase 1:** pesquisa das redes (loja em
   Goiânia, onde ficam os encartes, robots.txt e termos). **Parar e esperar aprovação**
   antes da Fase 2.
9. **Colocar no ar 24h** (Railway ou Render, como *Background Worker*; uma só cópia do bot
   rodando) e **guardar dados no Supabase** (reescrever só o `banco.py`; LGPD: avisar no
   `/start`, prazo de retenção, `/esquecer` já existe).
10. Revisar a lista de exceções de alergia com casos reais e o PDF em celulares pequenos.

## 9. Observações

- O dono testa com o próprio celular; durante os testes ele também usava o aparelho, então
  combine antes de rodar testes automáticos de tela.
- Gemini no plano gratuito: o `/custos` mostra preço de tabela, mas o custo real é zero.
- Preços de tabela usados (US$/1M tokens, entrada/saída): Opus 5.5 4/20, Sonnet 5.5 2/10,
  Haiku 5.5 0,10/0,50, Gemini 3.5 Flash-Lite 0,30/2,50, Gemini 3.6 Flash 0,75/3,75.
