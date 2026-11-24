# Contexto do projeto Rende (para retomar o trabalho)

Última atualização: 24/11/2026. Os pedidos 0 a G foram feitos em 23/11 numa conversa longa
com o Claude Code (Opus 5.5), com o celular do dono do projeto ligado ao computador por cabo
(adb) para os testes no Telegram. Em 24/11 o trabalho foi retomado em outro computador com a
especificação completa (Pedido H). O texto de cada pedido está em [docs/PEDIDOS.md](docs/PEDIDOS.md).

> **Para retomar com o Claude Code:** peça "leia o CONTEXTO.md, o PLANO.md e o
> docs/PEDIDOS.md (Pedido H) e continue pela ordem de trabalho do PLANO.md".
> Rode os testes antes de mexer.

---

## 1. O que é

Bot de Telegram em Python que virou um **assistente de mercado** chamado **Rende**:
cadastro com botões, plano da semana (cardápio + lista de compras por embalagem) dentro do
orçamento, troca de pratos, receita passo a passo com nota, PDF da lista, conversa livre
por texto, áudio e foto, e uma escada de modelos de IA que sobe de nível só quando precisa.

- Bot: `@cesta_cardapio_bot`. Nasceu como "Cesta" e foi renomeado para "Rende" pela API.
- Pastas locais (o dono usa dois computadores; **sempre `git fetch` antes de começar**):
  - `C:\Users\Matheus Duarte\cesta-bot`: o computador onde tudo começou (23/11). O `rende.db`
    daqui tem o perfil e os custos do teste de 23/11. Desde a tarde de 24/11 (Pedido I) é
    neste que o trabalho e os testes reais acontecem; o bot do outro fica desligado.
  - `C:\Users\mathe\Plano-2-`: usado na manhã de 24/11 (Pedido H, PARTE A). O `rende.db`
    de lá começou vazio.
  - O `rende.db` nunca vai pelo Git. Só uma cópia do bot pode estar ligada por vez.
- Por enquanto roda **só no computador local** (polling). Desligou o computador, o bot para.

## 2. Linha do tempo

**23/11/2026**

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

**24/11/2026**

7. **Retomada (Pedido H, PARTE A):** projeto baixado do GitHub em outro computador, todo o
   código lido, testes 101 de 101 OK, comparação com a especificação completa (resultado na
   tabela "situação de cada item" do [PLANO.md](PLANO.md)). Nenhum código foi alterado.
8. **Incidente de segurança:** o `.env` com as 3 chaves estava no primeiro commit e tinha ido
   para o GitHub. Com autorização do dono, o commit foi retirado da história e o GitHub foi
   atualizado (force push protegido); o `.env` local foi mantido. **Pendente: o dono trocar as
   3 chaves.** Detalhes na seção "Segurança" do PLANO.md.
9. **Teste real no celular (parcial) e 3 correções:** robô ligado neste computador, cadastro
   novo com orçamento de R$ 140. Resultado e correções na seção 6 e 7.
10. **Pedido I (tarde de 24/11, no computador `cesta-bot`):** a cópia antiga foi alinhada com
    o GitHub e o commit com o `.env` sumiu também do registro local; anthropic 2.13. O dono
    mandou executar todos os pendentes do H sem parar entre as etapas, com decisões novas
    (PLANO.md, "Decisões do Pedido I"). Primeira etapa, **custo do cardápio**: JSON compacto
    sem modo de preparo e Sonnet com effort "low". Rodada real: US$ 0,053 (antes US$ 0,131
    só no Sonnet), mas o plano estourou o orçamento por escolher embalagens grandes demais;
    regras corrigidas, nova medição pendente (tabela "Custo do cardápio" no PLANO.md).

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
- **API do Claude:** SDK `anthropic` 2.13 (instalado em 24/11), IDs sem data; sem temperature/top_p/top_k/
  budget_tokens/thinking; `tool_choice` "auto"; effort explícito ("low" na conversa,
  "medium" em troca e cardápio); `stop_reason` "refusal" sobe de nível; prompt caching nas
  instruções fixas (conferido na API real: 3.699 tokens lidos do cache, custo ~7x menor).
  O "fallback no servidor" da Anthropic **não** foi ativado (a regra manda recusa para o próximo nível).
- **Botões e telas neutras** (`telas.py`) para facilitar um canal futuro (WhatsApp).
- Receita gerada só quando a pessoa abre o prato (Gemini, barato) e guardada no plano.
- "Compra do mês" ainda gera plano semanal com orçamento mensal ÷ 4,3.
- Segredos: `.env` e qualquer `*.db` ficam fora do Git (o `.env` chegou a ser enviado por
  engano e foi retirado da história em 24/11); o log mascara tokens e chaves.

## 5. Como rodar e testar

Veja o [README](README.md). Testes automáticos: `.venv\Scripts\python testes\testar.py`
(**124 de 124 OK** em 24/11/2026). Ajudantes do teste pelo celular em `testes/celular/`.

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

**Teste real de 24/11/2026 (parcial, orçamento R$ 140):**

| Etapa | Resultado | Quem fez / custo (tabela) |
|---|---|---|
| Cardápio | ✅, mas caro | Sonnet US$ 0,167 (bateu nos 16 mil tokens; JSON cortado) → Opus US$ 0,190 |
| Conversa (12 mensagens) | ✅ | Gemini, ~US$ 0,001 cada |
| Troca de prato | ❌ | Haiku (+R$ 1,00) → Sonnet (+R$ 14,50) → Opus (+R$ 1,50): todos acima do orçamento, US$ 0,06 |

Gasto até a correção: cerca de US$ 0,43.

## 7. Defeitos achados nos testes reais (todos corrigidos)

Em 24/11 (corrigidos no mesmo dia, com testes automáticos novos):

- Cardápio cortado no limite de 16 mil tokens → limite de 32 mil com streaming.
- Troca recebia uma folga "proporcional" maior que a real e não sabia das sobras das
  embalagens → folga exata e lista de sobras; sem folga, avisa sem gastar; falha por
  orçamento explica o motivo em vez de convidar a repetir.
- O log gravava o ID da conta do Telegram → removido de todas as linhas.

Em 23/11:

- Soma da lista errada pela IA → total em código.
- "Couve manteiga" barrada como lactose (falso alarme) → exceção; custou uma subida
  desnecessária ao Opus (US$ 0,20).
- Troca de prato quebrava sobras planejadas (o jantar dependia do frango do almoço) → a IA
  é avisada da sobra e o código confere.
- "♻️ Sem sobra" aparecendo na tela; "1 porções"; "2.5"; "1 chamadas"; "0.5 min" → corrigidos.
- `/novo` esperava a resposta anterior terminar → agora vale na hora.

## 8. Próximos passos (pendentes)

**Antes de tudo (só o dono):** trocar as 3 chaves e colar as novas no `.env` local.

A ordem agora é a da PARTE D do Pedido H (lista completa e situação de cada item no
[PLANO.md](PLANO.md)). As pendências antigas entram assim:

1. **C1, C4–C11 (próximo):** fechar as lacunas de alergia escondida no nome do prato (C10),
   repetição da semana anterior, "≈ estimado" e "🔥 promoção" no PDF (C11). Foto de
   **encarte** → extrair ofertas e salvar em `promocoes` com origem "usuario" (C6; a
   ferramenta `salvar_promocoes_de_encarte` ainda não existe). Revisar as exceções de
   alergia com casos reais e o PDF em celulares pequenos.
2. **C2:** a troca já recebe a folga exata e as sobras (24/11); conferir no próximo teste
   real se o Haiku acerta de primeira. Rever o custo do cardápio (o Sonnet chegou a usar
   16 mil tokens de saída; agora o limite é 32 mil). `/custos` com escalonamentos também no mês.
3. **C3:** escopo conferido em código (`no_escopo`), com teste de 40 mensagens.
4. **C13 Fase 1:** pesquisa das redes de Goiânia. **Parar e esperar aprovação.**
5. **C13 Fase 2 + C14:** coletor das redes aprovadas; `/promo`, `/avisos`, avisos pelo
   JobQueue (máx. 1 por dia), resumo semanal (padrão sábado 9h), apagar promoções vencidas.
6. **C15:** "Onde comprar" (total por mercado, 3 melhores, divisão só se economizar R$ 15+).
7. **C12:** mercados próximos pelo Overpass (OpenStreetMap), raio de 3 km, até 8 mercados.
   Teste com um ponto público de Goiânia (não o GPS do dono).
8. **Testes no celular (PARTE E)**, com o custo estimado avisado antes. Inclui o que ficou
   do Pedido A: foto de geladeira e de nota fiscal.
9. **Relatório final (PARTE F).** Depois: colocar no ar 24h (Railway ou Render, como
   *Background Worker*, uma só cópia do bot) e guardar dados no Supabase (reescrever só o
   `banco.py`; LGPD: avisar no `/start`, prazo de retenção, `/esquecer` já existe).

## 9. Observações

- O dono testa com o próprio celular; durante os testes ele também usava o aparelho, então
  combine antes de rodar testes automáticos de tela.
- Gemini no plano gratuito: o `/custos` mostra preço de tabela, mas o custo real é zero.
- Preços de tabela usados (US$/1M tokens, entrada/saída): Opus 5.5 4/20, Sonnet 5.5 2/10,
  Haiku 5.5 0,10/0,50, Gemini 3.5 Flash-Lite 0,30/2,50, Gemini 3.6 Flash 0,75/3,75.
  Conferir na documentação atual antes de usar esses valores em estimativas de custo.
