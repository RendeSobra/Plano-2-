# Pedidos (texto original, em ordem)

Pedidos 0 a G: feitos em 23/11/2026. Pedido H (24/11/2026): especificação em vigor. Pedido I (24/11/2026): execução dos itens pendentes do H, em andamento. Situação de cada um: [PLANO.md](../PLANO.md) e [CONTEXTO.md](../CONTEXTO.md).

---

## Pedido 0: bot "Cesta" (cardápio por orçamento)

Quero que você crie, do zero, um bot de Telegram em Python. Você tem acesso ao meu celular, então pode fazer a parte do Telegram por mim. Sou iniciante, então me explique em português simples o que está fazendo em cada etapa.

### Etapa 1: criar o bot no Telegram (pelo meu celular)
1. Abra o Telegram e procure o @BotFather. Confira que é o oficial, com o selo azul de verificado.
2. Mande /newbot.
3. Nome do bot: "Cesta". Usuário: "cesta_cardapio_bot". Se já existir, tente variações (cesta_cardapio_br_bot, cestinha_cardapio_bot...) e me diga qual ficou.
4. Mande /setdescription e escreva: "Me diga quanto pode gastar no mercado e eu monto o cardápio da semana e a lista de compras com preço."
5. Mande /setcommands com:
   start - Começar
   novo - Recomeçar o cardápio do zero
6. O BotFather vai responder com um TOKEN. Regras para o token:
   - Grave o token direto no arquivo .env do projeto (TELEGRAM_BOT_TOKEN=...).
   - Não escreva o token na conversa, no código, em nenhum outro arquivo nem em commits.
   - Não mande o token para nenhum contato ou grupo.
7. Não mexa em mais nada no meu celular além do necessário para isso. Antes de qualquer ação fora dessas (enviar mensagem a alguém, instalar app, pagar algo), me pergunte.

### Etapa 2: o que o bot faz
É um planejador de refeições focado em orçamento, para famílias brasileiras. A pessoa diz quanto pode gastar no mercado, e o bot devolve o cardápio da semana e a lista de compras com preço estimado, cabendo nesse valor.

Fluxo da conversa:
1. No /start, o bot se apresenta em uma frase e pergunta quanto a pessoa quer gastar no mercado e se é por semana ou por mês.
2. Depois pergunta, UMA pergunta por vez: quantas pessoas comem em casa, restrições ou coisas que não comem, cidade, e (opcional) o que já tem em casa.
3. Com essas informações, manda numa mensagem só:
   - cardápio de segunda a domingo (almoço e jantar), com comida do dia a dia brasileiro: arroz e feijão, ovo, frango, carne moída, macarrão, legumes, cuscuz, tapioca, sopas;
   - ingredientes reaproveitados entre os dias (ex.: o frango de um dia vira recheio no outro);
   - lista de compras agrupada por seção do mercado, com quantidade e preço estimado de cada item;
   - total estimado e quanto sobra ou falta em relação ao orçamento. Se passar do orçamento, a IA ajusta o cardápio antes de responder;
   - um aviso, no final, de que os preços são estimativas.
4. Depois disso a pessoa pode pedir para trocar pratos, sempre mantendo o orçamento.
5. O comando /novo recomeça a conversa do zero.
O bot só fala de alimentação, receitas e compras de mercado.

### Etapa 3: o código
Tecnologia:
- Python 3.11+
- python-telegram-bot (versão 22 ou mais nova, com async e run_polling)
- IA: Gemini, pela biblioteca oficial google-genai. O nome do modelo fica numa variável de ambiente (GEMINI_MODEL).
- python-dotenv para ler o .env

Requisitos:
- Separe o código em arquivos:
  - prompts.py: as instruções (system prompt) da IA, em português, com as regras da Etapa 2;
  - ia.py: a única parte que fala com o Gemini (recebe o histórico e devolve o texto);
  - bot_telegram.py: a única parte que fala com o Telegram. No futuro quero trocar de IA mexendo só no ia.py e ir para o WhatsApp sem mexer no ia.py.
- Guarde o histórico de cada usuário (na memória, por enquanto), limitado às últimas 30 mensagens.
- Limite de mensagens por usuário por dia, configurável no .env (LIMITE_MSG_DIA, padrão 30). Ao passar do limite, responda com educação que amanhã continua.
- Mostre "digitando..." enquanto a IA pensa.
- Divida mensagens maiores que 4000 caracteres.
- Use negrito simples do Telegram. Se a formatação der erro, mande o texto sem formatação.
- Se a IA der erro, avise o usuário para mandar de novo e registre no log, sem derrubar o bot.
- Chaves só no .env. Crie também .env.example (sem valores reais) e .gitignore ignorando o .env.
- Antes de escrever, confira na documentação atual os nomes das funções das bibliotecas e um modelo Gemini disponível hoje.

### Etapa 4: chave do Gemini
Eu vou pegar a chave do Gemini no Google AI Studio e colocar no .env (GEMINI_API_KEY) eu mesmo. Quando chegar nessa hora, me avise e espere. Não peça para eu colar a chave na conversa.

### Etapa 5: testar
1. Instale as bibliotecas e rode o bot.
2. Pelo meu celular, abra o bot no Telegram e faça uma conversa de teste completa: /start, orçamento de R$ 300 por semana, 3 pessoas, sem restrições, cidade Goiânia.
3. Confira se o cardápio veio completo, com a lista, os preços e o total dentro do orçamento. Se algo falhar, corrija e teste de novo.
4. No final, me mande:
   - o @ do bot;
   - um resumo do que foi feito;
   - o que ainda falta para ele ficar ligado 24h (Railway ou Render) e guardar as conversas (Supabase). Só explique, não faça ainda.

---

## Pedido A: áudio e foto

Agora quero que o bot entenda ÁUDIO e FOTO, além de texto.

1. Áudio (mensagens de voz do Telegram):
   - Baixe o arquivo de voz (.ogg) e mande direto para o Gemini junto com o histórico, que ele entende áudio.
   - O bot responde normalmente, como se a pessoa tivesse escrito.

2. Foto:
   - Baixe a foto (a maior resolução) e mande para o Gemini junto com a legenda, se houver.
   - Se for foto de geladeira, despensa ou alimentos: identificar o que tem e usar no cardápio.
   - Se for foto de nota fiscal ou cupom de mercado: listar os itens com preço e dizer o total. Por enquanto só responder, não precisa salvar.
   - Se for outra coisa, responder com educação que só entende fotos de comida ou de notas de mercado.

3. Regras:
   - Áudio e foto contam no limite diário de mensagens, igual texto.
   - Limite de tamanho: recusar áudio maior que 2 minutos e arquivos maiores que 10 MB, com uma mensagem amigável.
   - Mostrar "digitando..." enquanto processa.
   - Não guardar os arquivos no computador depois de mandar para a IA.
   - Atualize o prompts.py para a IA saber que pode receber áudio e fotos.
   - Mantenha a separação: o download fica no bot_telegram.py, e o envio para o Gemini fica no ia.py.

4. Teste mandando pelo meu celular: um áudio com orçamento e número de pessoas, uma foto de geladeira e uma foto de nota fiscal. Me mostre como o bot respondeu cada um.

---

## Pedido B: assistente "Rende"

Quero transformar o bot em um ASSISTENTE pessoal de mercado chamado "Rende". Ele não deve seguir um roteiro fixo: deve entender qualquer mensagem e decidir sozinho o que fazer.

### 1. Arquitetura: assistente com ferramentas
- Use o "function calling" (ferramentas) do Gemini. A IA recebe a mensagem, o perfil do usuário e o histórico, e decide se responde direto ou se chama uma ferramenta.
- Ferramentas que a IA pode chamar:
  - salvar_perfil(nome, orcamento, periodo, pessoas, restricoes, cidade, preferencias)
  - gerar_cardapio(): monta o cardápio da semana com lista de compras e preços estimados, dentro do orçamento
  - gerar_pdf_lista(): cria o PDF da lista de compras atual e manda no chat
  - buscar_mercados_proximos(lat, lon, raio_km): busca supermercados perto
  - listar_promocoes(cidade ou mercados): ofertas cadastradas e válidas
  - salvar_promocoes_de_encarte(itens): guarda ofertas lidas de uma foto de encarte
  - configurar_avisos(ativo, dia_semana, horario)
- Mantenha a separação: bot_telegram.py só fala com o Telegram; ia.py só fala com o Gemini; crie ferramentas.py (as funções), banco.py (dados) e pdf.py.

### 2. Memória (banco de dados)
- Use SQLite agora (arquivo rende.db, no .gitignore), mas com o acesso isolado em banco.py para trocar por Supabase depois.
- Tabelas: usuarios (telegram_id, nome, orçamento, período, pessoas, restrições, cidade, última localização, preferências, avisos ativos), historico (últimas 30 mensagens por usuário), listas (lista de compras atual), promocoes (mercado, produto, preço, validade, cidade, origem: admin ou encarte).
- No /start, se for usuário novo, pergunte o nome primeiro e depois o resto aos poucos, de forma natural. Se já for conhecido, cumprimente pelo nome.
- O usuário pode atualizar qualquer dado conversando ("agora somos 4 em casa").
- Comando /esquecer: apaga todos os dados do usuário (LGPD).

### 3. Entender qualquer mensagem
- Texto, áudio (voz), foto (geladeira, despensa, nota fiscal, encarte de promoção), documento PDF ou imagem, e localização.
- Foto de encarte: extrair produtos, preços, mercado e validade, e chamar salvar_promocoes_de_encarte.
- Localização: salvar no perfil e oferecer os mercados próximos.
- Figurinha ou algo sem sentido: responder com simpatia e puxar a conversa de volta.
- Limites: áudio até 2 min, arquivos até 10 MB; tudo conta no limite diário (LIMITE_MSG_DIA). Não guardar arquivos depois de processar.

### 4. PDF da lista de compras
- Use a biblioteca fpdf2.
- Conteúdo: logo/título "Rende", nome do usuário, data, itens agrupados por seção do mercado com caixinha para marcar, quantidade, preço estimado, total, orçamento e quanto sobra. Marcar os itens que estão em promoção.
- Enviar como documento no Telegram e apagar o arquivo local depois.

### 5. Mercados próximos
- O usuário manda a localização pelo botão do Telegram (ofereça um botão "📍 Enviar minha localização").
- Buscar supermercados num raio de 3 km (configurável) pela API Overpass do OpenStreetMap (gratuita). Respeite os limites de uso e coloque um User-Agent genérico do app.
- Mostrar nome, distância e um link do Google Maps para cada um (até 8), destacando os que têm promoções cadastradas.

### 6. Promoções e avisos automáticos
- Comando de administrador /promo (só para os IDs em ADMIN_IDS no .env) para cadastrar ofertas: mercado, produto, preço, validade, cidade.
- Usar o JobQueue do python-telegram-bot:
  - Toda vez que entrar promoção nova, avisar os usuários da mesma cidade que têm avisos ativos e que têm aquele produto na lista ou nas preferências.
  - Um resumo semanal (dia e horário escolhidos pelo usuário, padrão sábado 9h): promoções da semana + oferta de montar o cardápio.
  - No máximo 1 aviso por dia por usuário, e o usuário pode desligar com /avisos.
- Promoções vencidas não aparecem e são apagadas automaticamente.

### 7. Personalidade
- Atualize o prompts.py: o Rende é um assistente simpático e direto, que fala português do Brasil, chama a pessoa pelo nome, lembra das preferências dela e sempre pensa em economizar. Só trata de comida, receitas, mercado, promoções e orçamento.
- Respostas curtas, com exceção do cardápio. Deixar claro que os preços são estimativas, exceto quando vierem de promoção cadastrada.

### 8. Testes
- Testes automáticos para o banco, o PDF, a busca de mercados (simulada) e os avisos.
- Depois, pelo meu celular:
  1. /start como usuário novo e passar nome e dados;
  2. mandar um áudio pedindo o cardápio;
  3. pedir o PDF da lista;
  4. mandar a localização e ver os mercados;
  5. cadastrar uma promoção com /promo e ver o aviso chegar;
  6. mandar uma foto de encarte;
  7. /esquecer.
- Me mostre o resultado de cada passo e me diga o que ainda falta ou o que não deu certo.

Faça por partes, nesta ordem: memória → entender qualquer mensagem → PDF → mercados → promoções e avisos. Teste cada parte antes de passar para a próxima e me dê um resumo a cada etapa.

---

## Pedido C: coletor de promoções de Goiânia

Quero um COLETOR DE PROMOÇÕES para o Rende, focado em GOIÂNIA. Ele lê os encartes ou tabloides de ofertas que os supermercados publicam nos sites oficiais e salva as promoções no banco do assistente.

Redes candidatas: Tático, Bretas, Prezunic, Assaí, Dia a Dia (atacarejo), Carrefour/Atacadão, Supermercado Barão, Pão de Açúcar, Sam's Club, Supermercado Cerrado.

### FASE 1: Pesquisa (NÃO programe nada ainda)
Para cada rede, descubra e me mostre numa tabela:
1. Se tem loja em Goiânia hoje (confirme no site oficial da rede).
2. Onde ficam as ofertas: página de encartes ou tabloides (imagem ou PDF), página de ofertas em HTML, loja online com preço por produto, ou só no app.
3. Se as ofertas mudam por loja ou região, e como escolher Goiânia (CEP, seletor de loja etc.).
4. O que diz o robots.txt do site e se os termos de uso proíbem coleta automática.
5. Observações, por exemplo: preço só para sócio (Sam's Club), preço só no app (Meu Assaí), preço de atacado a partir de X unidades.
Depois recomende as 3 a 5 melhores redes para começar (as que têm loja em Goiânia, encarte acessível e não proíbem a coleta) e ESPERE minha aprovação.

### FASE 2: Coletor (só das redes aprovadas)
Arquitetura:
- Pasta coletor/, com um arquivo por rede (ex.: coletor/tatico.py), todos com a mesma função: coletar() -> lista de encartes ou ofertas.
- coletor/extrair.py: manda cada imagem ou PDF de encarte para o Gemini (ia.py) e recebe JSON estruturado por oferta: rede, produto, marca, tamanho/peso, preço, preço anterior (se houver), condição (ex.: "no cartão", "leve 3", "só no app", "sócio"), validade início/fim, lojas ou região.
- Salva na tabela promocoes do banco (banco.py), com origem = "site" e o link da fonte.
- Normaliza os nomes dos produtos (ex.: "ARROZ TIO JOÃO 5KG" -> produto "arroz", marca "Tio João", tamanho "5 kg") para o assistente conseguir comparar e montar cardápios.

Regras de boa conduta (obrigatórias):
- Rodar no máximo 1 vez por dia (padrão 6h), pelo JobQueue do bot ou por um script separado.
- Respeitar o robots.txt; se uma página for proibida, pular a rede e registrar no log.
- No máximo 1 requisição a cada 5 segundos por site, com timeout, e User-Agent genérico do app (sem dados pessoais).
- Guardar um hash de cada encarte já processado e não mandar o mesmo encarte para a IA de novo (economiza a cota do Gemini).
- Se o site de uma rede mudar e o coletor quebrar, as outras redes continuam funcionando, e o administrador (ADMIN_IDS) recebe um aviso no Telegram.
- Não baixar nada além das ofertas. Apagar as imagens e PDFs depois de extrair.

Integração com o assistente:
- Promoções novas disparam os avisos que já existem (usuários de Goiânia com avisos ativos e produto na lista ou nas preferências; máximo de 1 aviso por dia).
- Quando montar cardápio ou lista, a IA usa o preço da promoção quando houver, diz em qual mercado está e até quando vale.
- No PDF, marcar os itens em promoção com o nome do mercado.
- Comando de administrador /coletar: roda a coleta na hora e mostra quantas ofertas novas entraram por rede.

### FASE 3: Testes
- Testes automáticos com encartes de exemplo salvos (sem acessar a internet): extração, normalização, deduplicação e falha de uma rede sem derrubar as outras.
- Depois, uma coleta real das redes aprovadas. Me mostre, por rede: quantas ofertas, 5 exemplos e qualquer erro.
- Pelo meu celular: pergunte ao Rende "quais as promoções de arroz em Goiânia essa semana?" e depois peça o PDF da lista.

Faça uma fase de cada vez e me dê um resumo ao final de cada uma.

---

## Pedido D: roteador Gemini/Claude e personalidade amigável

Quero duas melhorias no Rende: (1) um roteador que escolhe entre Gemini e Claude (Anthropic) conforme a tarefa e (2) uma personalidade mais amigável.

### 1. Roteador de modelos
- Crie roteador.py, que decide qual modelo usar. O resto do código chama só o roteador, nunca um modelo direto.
- Mantenha ia.py para o Gemini e crie ia_claude.py para o Claude, os dois com a mesma interface (recebem histórico, perfil e ferramentas; devolvem texto e/ou chamadas de ferramenta).
- Regras:
  a) GEMINI (padrão): conversa, dúvidas simples, salvar perfil, entender áudio e foto, extrair ofertas de encartes, buscar mercados.
  b) CLAUDE: gerar_cardapio, refazer cardápio com restrições, otimizar a lista usando promoções de vários mercados, e qualquer pedido que o Gemini marque como complexo.
  c) ESCALONAMENTO: depois de um cardápio gerado pelo Gemini, valide em código (o total cabe no orçamento? tem os 7 dias? o JSON é válido?). Se falhar, refaça com o Claude.
  d) FALLBACK: se o Claude der erro ou recusar, use o Gemini e registre no log; se o Gemini estourar a cota, use o Claude.
- Configuração no .env: ANTHROPIC_API_KEY, CLAUDE_MODEL=claude-opus-5-5 (alternativa mais barata: claude-sonnet-5-5), e um limite de gasto diário com Claude (LIMITE_CLAUDE_DIA, ex.: 50 chamadas). Quando passar do limite, use só o Gemini.
- Log (sem o texto das conversas): qual modelo foi usado, por quê, tokens de entrada e saída e o custo estimado. Comando de administrador /custos: gasto do dia e do mês por modelo.

Regras técnicas para o Claude (a API mudou recentemente; siga exatamente):
- Use o SDK oficial em Python, o pacote "anthropic" (client = anthropic.AsyncAnthropic(), que lê ANTHROPIC_API_KEY do ambiente), e client.messages.create.
- Use o ID do modelo exatamente como está no .env, sem data no final.
- NÃO envie temperature, top_p, top_k nem thinking com budget_tokens: nesses modelos isso dá erro 400.
- NÃO force ferramenta com tool_choice "any" ou "tool" (dá erro 400). Use tool_choice "auto" e diga no system prompt qual ferramenta usar.
- Para o cardápio, use output_config={"effort": "medium"} e max_tokens=16000.
- Sempre confira response.stop_reason antes de ler o conteúdo: se for "refusal", vá para o fallback do Gemini.
- Antes de escrever o código, confira a documentação oficial atual em platform.claude.com/docs.

### 2. Personalidade (assistente amigável)
Atualize o prompts.py (vale para os dois modelos, para o Rende ter a mesma "voz" com qualquer um):
- O Rende é um amigo que entende de mercado: simpático, leve, usa o nome da pessoa e fala português do Brasil do dia a dia, sem ser forçado. Emojis com moderação.
- Lembra das coisas: usa o perfil salvo (nome, família, restrições, mercado preferido, pratos de que gostou ou não gostou) sem perguntar de novo.
- Comemora conquistas ("Essa semana você economizou R$ 42 em relação ao orçamento! 🎉").
- Toma iniciativa com moderação: no resumo semanal, sugere algo com base no histórico ("semana passada você gostou do escondidinho; quer repetir?").
- Se não souber algo, admite e não inventa preço.
- Depois de cada cardápio, pergunte o que a pessoa achou e salve os pratos aprovados e rejeitados no perfil (nova coluna: preferencias_pratos).

### 3. Testes
- Testes automáticos do roteador: qual modelo cada tipo de tarefa usa, escalonamento quando o cardápio passa do orçamento, fallback quando um modelo falha e respeito ao LIMITE_CLAUDE_DIA. Simule os modelos, sem chamar as APIs.
- Pelo meu celular: uma conversa simples (deve usar Gemini), pedir o cardápio (deve usar Claude) e /custos. Me mostre qual modelo respondeu em cada passo e quanto custou.

Quando precisar da ANTHROPIC_API_KEY, me avise e espere: eu mesmo coloco no .env. Não peça a chave na conversa.

---

## Pedido E: experiência com botões (estilo NeatEat)

Quero que o Rende tenha a experiência do app NeatEat (mostrada num vídeo), adaptada ao Telegram e ao Brasil, e mais amigável. O assistente continua entendendo qualquer mensagem (texto, áudio, foto), mas os passos principais devem ter BOTÕES (inline keyboard) para ser rápido e bonito.

### 1. Onboarding (primeira vez)
Uma pergunta por mensagem, com botões e sempre aceitando resposta livre ou por áudio:
1. "Oi! Eu sou o Rende 👋 Como posso te chamar?" (salvar o nome e usá-lo sempre)
2. Quem vai comer? Botões de + e − para Adultos e Crianças (criança = meia porção). Mostrar: "= X porções por refeição".
3. Quais refeições? Seleção múltipla: Café da manhã, Almoço, Jantar, Lanches, Marmita para o trabalho.
4. Quais dias vai cozinhar? Seleção múltipla dos dias da semana.
5. Qual a vibe? Rápido e fácil, Cozinhar no domingo para a semana, Uma panela só, Comida de vó, Leve/saudável, Fitness (mais proteína).
6. Alergias ou restrições? Seleção múltipla: lactose, glúten, ovo, amendoim/castanhas, frutos do mar, peixe, soja, vegetariano, outro (texto livre).
7. O que tem na cozinha? Seleção múltipla: fogão, forno, micro-ondas, airfryer, panela de pressão, panela elétrica. As receitas só usam o que a pessoa tem.
8. Onde você compra? Mercados de Goiânia (Assaí, Atacadão/Carrefour, Tático, Barão, Cerrado, Dia a Dia...) ou "Qualquer um".
9. Compra da semana ou do mês?
10. Orçamento: sugira um valor realista para o tamanho da família e mostre botões −R$ 20 / +R$ 20 / Confirmar, com o resumo: "2 adultos e 1 criança · 3 refeições/dia · X porções na semana · R$ Y".
Salve tudo no perfil. Depois, a pessoa pode mudar qualquer coisa conversando ou com /perfil.

### 2. "Montando seu plano" (o momento mágico)
- Mande UMA mensagem e vá EDITANDO ela a cada etapa, como uma animação:
  ⏳ Vendo as promoções da semana...
  ✅ Vendo as promoções da semana
  ⏳ Escolhendo as receitas...
  ... (Calculando a cesta, Conferindo o orçamento, Finalizando)
- As etapas devem corresponder ao processamento real (não é só enfeite).

### 3. Resultado
- "Sua semana está pronta, {nome}! 🎉 Gasto: R$ X de R$ Y. Sobrou R$ Z 💰 · N itens na lista."
- Botões: [📅 Ver cardápio] [🛒 Lista de compras] [📄 PDF da lista] [🔄 Refazer tudo]
- Cardápio: uma mensagem por dia (ou botões Seg, Ter, Qua...), cada refeição com tempo de preparo e custo.
- Cada refeição tem um botão [🔁 Trocar]. Troca só aquele prato e recalcula o total, sempre dentro do orçamento.

### 4. Receita
Ao tocar num prato: ingredientes já na quantidade da família, tempo e passo a passo.
- Botão [👩‍🍳 Cozinhar passo a passo]: um passo por mensagem com o botão [Próximo ▶️].
- No final: [✅ Fiz!] com nota de 1 a 5 estrelas. Salve no perfil (pratos aprovados e rejeitados) e use nos próximos cardápios.
- Sem imagens geradas por IA.

### 5. Corrigir os defeitos do NeatEat (obrigatório)
- PREÇO POR EMBALAGEM: a lista compra o que existe no mercado ("1 pacote de arroz 5 kg", "1 bandeja de 30 ovos"), nunca "350 g de arroz". O total usa o preço da embalagem. O que sobrar vai para a despensa do usuário e é usado nas semanas seguintes.
- ALERGIAS: depois que a IA gerar o cardápio, valide EM CÓDIGO que nenhum ingrediente proibido aparece. Se aparecer, refaça. Nunca confie só na IA para isso.
- VARIEDADE: o mesmo prato no máximo 1 vez por semana, e evite repetir pratos da semana anterior, salvo os favoritos.
- QUANTIDADES: ao escalar as porções, ajuste também o texto do modo de preparo. Use medidas brasileiras (xícara, colher de sopa, kg, g, unidade).
- O plano nunca muda sozinho. Só muda quando o usuário pede.
- Comida brasileira de verdade: arroz e feijão, PF, marmita, comida regional goiana (arroz com pequi, empadão, pamonha), sobras planejadas (o feijão de segunda vira tropeiro na quarta).

### 6. Jeito de falar
Português do Brasil (nunca de Portugal: "você", não "tu"; "economizou", não "poupaste"). Chama a pessoa pelo nome, comemora a economia e lembra das preferências.

### 7. Testes
- Testes automáticos: validação de alergias, cálculo por embalagem, sem repetição e o total dentro do orçamento.
- Pelo meu celular: onboarding completo, ver a "animação", trocar 2 pratos, abrir uma receita no modo passo a passo, dar uma nota e gerar o PDF. Me mostre prints ou o texto de cada etapa.

Use o roteador de modelos: Claude para gerar e trocar o cardápio; Gemini para o resto.

---

## Pedido F: escada de modelos

Quero mudar o roteador para usar uma ESCADA de modelos, do mais barato para o mais caro. Subir de nível só quando necessário.

### Níveis
1. GEMINI (padrão para o resto): conversa, áudio, foto, receitas, extração de encartes.
2. CLAUDE HAIKU (claude-haiku-5-5):
   - trocar 1 prato do cardápio;
   - substituto do Gemini quando ele estiver sem cota ou fora do ar (conversa e foto; áudio continua só no Gemini);
   - tarefas curtas e estruturadas.
3. CLAUDE SONNET (claude-sonnet-5-5): gerar o cardápio da semana (padrão) e refazer o cardápio inteiro.
4. CLAUDE OPUS (claude-opus-5-5): só por escalonamento:
   - o cardápio do Sonnet foi reprovado na conferência em código (orçamento, alergia, repetição, utensílios), ou
   - o caso é complexo: 3 ou mais restrições ao mesmo tempo, ou otimização com promoções de vários mercados.

### Escalonamento
- Cada tarefa começa no nível indicado. Se a conferência em código reprovar o resultado, tente de novo UMA vez no nível de cima, passando o motivo da reprovação ("passou R$ 23 do orçamento", "tinha leite no cardápio de quem tem alergia a lactose").
- Trocar prato: Haiku -> Sonnet -> Opus. Gerar cardápio: Sonnet -> Opus.
- Recusa (stop_reason "refusal") ou erro: tente o próximo nível. Se todos falharem, use o Gemini e avise no log.
- Respeite os limites diários por modelo no .env: LIMITE_OPUS_DIA (ex.: 20), LIMITE_SONNET_DIA (ex.: 100), LIMITE_HAIKU_DIA (ex.: 500). Se o Opus estiver no limite, fique no Sonnet e entregue o melhor resultado aprovado.

### Configuração no .env
CLAUDE_MODELO_BARATO=claude-haiku-5-5
CLAUDE_MODELO_PADRAO=claude-sonnet-5-5
CLAUDE_MODELO_FORTE=claude-opus-5-5
Os IDs vão exatamente assim, sem data no final.

### Regras técnicas da API do Claude (para os 3 modelos)
- Não enviar temperature, top_p, top_k nem budget_tokens (dá erro 400).
- Não enviar thinking {"type": "disabled"}; simplesmente omita o parâmetro thinking.
- tool_choice sempre "auto" (forçar "any" ou "tool" dá erro 400 no Sonnet 5.5 e no Opus 5.5).
- effort em output_config: "low" para conversa no Haiku; "medium" para trocar prato e gerar cardápio no Sonnet e no Opus. Defina sempre de forma explícita.
- Use prompt caching (cache_control) no system prompt e nas instruções fixas, que se repetem em toda chamada, para baratear. Confirme pelo usage.cache_read_input_tokens que o cache está funcionando.
- Sempre confira stop_reason antes de ler a resposta.

### /custos e log
- Mostrar o gasto por modelo (Gemini, Haiku, Sonnet, Opus) no dia e no mês, e quantas vezes houve escalonamento e por quê.

### Testes
- Testes automáticos (com modelos simulados): cada tarefa começa no nível certo; a reprovação sobe um nível; a recusa sobe um nível; os limites diários são respeitados; o áudio nunca vai para o Claude.
- Teste real no celular: gerar 1 cardápio, trocar 2 pratos e mostrar no /custos qual modelo fez cada coisa e quanto custou.

---

## Pedido G: mensagens que somem e GitHub

> As mensagens de PDF e de troca de refeição ficam fixadas? Elas podem sumir, ou o PDF não
> aparecer aqui, somente baixar ele?

Feito: a confirmação de troca virou uma linha no topo da tela do dia; o PDF some sozinho
depois de `APAGAR_PDF_APOS_MIN` minutos (padrão 5) e o anterior é apagado ao gerar um novo.
(O Telegram não permite que um bot entregue um arquivo sem mandar uma mensagem.)

> Suba no meu GitHub, quero o contexto de toda essa mensagem e tudo o que fizemos e os
> próximos passos pendentes. Repositório: `Matheus-Ceciliano/Plano-2-`.

---

## Pedido H: retomada com a especificação completa (24/11/2026)

Texto original colado na conversa. Substitui os pedidos anteriores onde eles discordarem.
Situação e ordem de trabalho: [PLANO.md](../PLANO.md).

Você vai continuar o desenvolvimento do Rende: um assistente de Telegram que monta o cardápio da semana e a lista de compras dentro do orçamento da família, mostra promoções e diz onde comprar mais barato. Foco inicial: Goiânia. Público: famílias brasileiras de baixa e média renda.

Eu sou iniciante em programação. Explique em português simples o que você faz em cada etapa.

### PARTE A — PEGAR O PROJETO E ENTENDER O CONTEXTO

#### A1. Clonar

- Repositório: https://github.com/Matheus-Ceciliano/Plano-2-.git
- Se a pasta já existir, faça git pull em vez de clonar de novo.

#### A2. Ler tudo antes de mexer

Leia nesta ordem:

- PLANO.md (o que foi feito, o que falta e as decisões);
- README.md;
- o código: bot_telegram.py, roteador.py, ia.py, ia_claude.py, ferramentas.py, banco.py, pdf.py, prompts.py, coletor/ e testes;
- git log;
- .env.example.
- Rode os testes automáticos e anote quantos passam.

#### A3. Segurança (verificar primeiro)

- Confira se .env, `*.db` ou qualquer token ou chave foi enviado ao repositório, inclusive no histórico do git. Se encontrar, me avise IMEDIATAMENTE e pare. Não apague o histórico sem me perguntar.
- Garanta que o .gitignore tenha: .env, `*.db`, `__pycache__/`, `.venv/`.
- Nunca escreva chaves, tokens, CPF ou dados de usuários no código, nos commits, nos logs ou na conversa.

#### A4. Resumo para mim — PARE AQUI

Mostre:

- o que o Rende já faz;
- como os modelos estão organizados;
- o que falta (comparando com a PARTE C abaixo);
- testes que passam e falham;
- problemas ou diferenças entre o código e o PLANO.md.
- Espere minha confirmação antes de alterar qualquer coisa.

#### A5. Ambiente

- Crie um ambiente virtual e instale o requirements.txt.
- Crie o .env a partir do .env.example.
- As chaves (TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, ANTHROPIC_API_KEY) quem coloca sou eu. Quando precisar, me avise e espere. Nunca peça uma chave na conversa.

### PARTE B — REGRAS DE TRABALHO (valem para tudo)

- Uma etapa por vez, na ordem da PARTE C.
- Ao terminar cada etapa: testes automáticos passando + resumo para mim + PLANO.md atualizado (feito, decisões, pendências), para outra pessoa ou IA conseguir continuar.
- Commits pequenos, com mensagens claras em português. Não faça push sem me perguntar.
- Antes de qualquer teste real que gaste dinheiro (chamadas ao Claude), me diga o custo estimado.
- Antes de qualquer ação no meu celular fora do roteiro (mandar mensagem a alguém, instalar app, pagar), me pergunte.
- Se algo do que eu pedi não for possível ou for arriscado, explique e proponha uma alternativa em vez de improvisar.
- Confira sempre a documentação atual das bibliotecas e APIs antes de escrever o código.

### PARTE C — O QUE O RENDE DEVE SER (especificação completa)

- Para cada item, verifique se já existe e está correto. Se já existir, só teste e siga. Se faltar ou estiver errado, implemente.

#### C1. Arquitetura

- Python 3.11+, python-telegram-bot 22+ (async), SQLite agora (acesso isolado em banco.py, para trocar por Supabase depois), fpdf2 para PDF, python-dotenv.

Separação obrigatória:

- bot_telegram.py: só fala com o Telegram;
- roteador.py: decide o modelo; o resto do código chama só o roteador;
- ia.py (Gemini) e ia_claude.py (Claude): mesma interface;
- ferramentas.py: funções que a IA pode chamar;
- banco.py, pdf.py, prompts.py, coletor/.
- No futuro o bot vai para o WhatsApp: trocar o mensageiro não pode exigir mexer na IA.

#### C2. Escada de modelos (roteador)

- Começar no mais barato e subir só quando necessário.

| Nível | Modelo | Usar para |
|---|---|---|
| 1 | Gemini (GEMINI_MODEL) | conversa, áudio, foto, receitas, extração de encartes e notas |
| 2 | Claude Haiku (claude-haiku-5-5) | trocar 1 prato; substituto do Gemini sem cota ou fora do ar (conversa e foto; áudio continua só no Gemini) |
| 3 | Claude Sonnet (claude-sonnet-5-5) | gerar e refazer o cardápio da semana (padrão) |
| 4 | Claude Opus (claude-opus-5-5) | só por escalonamento: o Sonnet foi reprovado na conferência, ou o caso é complexo (3+ restrições, otimização com vários mercados) |

- Escalonamento: se a conferência em código reprovar, tente de novo UMA vez no nível de cima, passando o motivo ("passou R$ 23 do orçamento", "tinha leite para alérgico a lactose"). Trocar prato: Haiku → Sonnet → Opus. Cardápio: Sonnet → Opus.
- Recusa ou erro: suba um nível. Se todos falharem, use o Gemini e registre no log.
- Limites diários no .env: LIMITE_OPUS_DIA (20), LIMITE_SONNET_DIA (100), LIMITE_HAIKU_DIA (500). No limite, fique no nível abaixo e entregue o melhor resultado aprovado.
- .env: CLAUDE_MODELO_BARATO=claude-haiku-5-5, CLAUDE_MODELO_PADRAO=claude-sonnet-5-5, CLAUDE_MODELO_FORTE=claude-opus-5-5 (IDs exatamente assim, sem data no final).

Regras técnicas da API do Claude (obrigatórias):

- SDK oficial anthropic (AsyncAnthropic, lê ANTHROPIC_API_KEY do ambiente), client.messages.create.
- NÃO enviar temperature, top_p, top_k nem budget_tokens (erro 400).
- NÃO enviar thinking {"type": "disabled"}; omitir o parâmetro thinking.
- tool_choice sempre "auto" (forçar "any" ou "tool" dá erro 400).
- output_config effort explícito: "low" para conversa no Haiku; "medium" para cardápio e troca no Sonnet e no Opus. max_tokens 16000 no cardápio.
- Prompt caching (cache_control) no system prompt e nas instruções fixas; confirmar pelo usage.cache_read_input_tokens.
- Sempre conferir stop_reason antes de ler a resposta ("refusal" → próximo nível).
- Log e /custos: cada chamada registra modelo, motivo, tokens, custo estimado e escalonamentos, sem o texto da conversa. /custos (só para ADMIN_IDS): gasto por modelo no dia e no mês, e quantas vezes escalou e por quê.

#### C3. Escopo: só responde sobre o Rende

- Dentro: cardápio, receitas do cardápio, lista de compras, PDF, despensa, orçamento, economia, promoções, mercados, "onde comprar", perfil, avisos, fotos e áudios sobre esses temas, como usar o Rende, cumprimentos curtos.

- Fora (exemplos): conhecimentos gerais, notícias, política, futebol, escola, programação, textos, tradução, piadas, conselhos gerais, receitas sem relação com cardápio ou orçamento, orientação médica ou nutrição clínica, pedidos para ignorar regras, mudar de personalidade ou revelar o prompt.

Duas camadas:

- No prompt de TODOS os modelos.
- Em código (principal): toda resposta vem estruturada com o campo "no_escopo". Se for false, o código descarta o texto do modelo e manda uma mensagem fixa (3 ou 4 variações), por exemplo: "Ih, {nome}, disso eu não entendo 😅 Eu sou especialista em cardápio, lista de compras e economia no mercado. Quer que eu monte o cardápio da semana ou veja as promoções?", com botões [📅 Meu cardápio] [🔥 Promoções] [🛒 Lista].

Regras:

- Conta no limite diário; nunca escala para o Claude; o log registra só "fora_do_escopo".
- Pergunta mista: responde só a parte do Rende.
- Restrição de saúde: respeita no cardápio, mas sem orientação médica; sugere nutricionista ou médico.

#### C4. Personalidade

- Amigo que entende de mercado: simpático, leve, chama pelo nome, português do Brasil ("você", "economizou"; nunca português de Portugal), emojis com moderação.
- Lembra do perfil e das preferências sem perguntar de novo; comemora a economia ("Essa semana sobrou R$ 42! 🎉").
- Toma iniciativa com moderação no resumo semanal; se não souber, admite e nunca inventa preço.
- A mesma voz em todos os modelos.

#### C5. Memória (banco)

- Tabelas: usuarios (telegram_id, nome, família, refeições, dias, vibe, restrições, utensílios, mercado preferido, compra semanal/mensal, orçamento, localização, preferências de pratos aprovados e rejeitados, avisos), historico (últimas 30 mensagens), planos (3 últimos), despensa, promocoes, custos.
- /perfil edita qualquer item; o usuário também pode mudar conversando ("agora somos 4").
- /esquecer apaga TUDO do usuário, com confirmação (LGPD).

#### C6. Entender qualquer mensagem

- Texto, áudio (até 2 min), foto, PDF ou imagem (até 10 MB), localização, figurinha.
- Foto de geladeira ou despensa → identifica e usa no cardápio.
- Foto de nota fiscal → lista itens e preços.
- Foto de encarte → extrai ofertas e salva em promocoes (origem "usuario").
- Localização → salva e oferece mercados próximos.
- Tudo conta no LIMITE_MSG_DIA. Arquivos são apagados depois de processar.

#### C7. Cadastro com botões (primeira vez)

Uma pergunta por mensagem, com botões, aceitando também texto e áudio:

- Nome.
- Adultos e crianças (+/−; criança = meia porção; mostrar "= X porções por refeição").
- Refeições (café, almoço, jantar, lanches, marmita).
- Dias da semana em que cozinha.
- Vibe (rápido, cozinhar no domingo para a semana, uma panela só, comida de vó, leve, fitness).
- Alergias e restrições (lactose, glúten, ovo, amendoim/castanhas, frutos do mar, peixe, soja, vegetariano, outro).
- Utensílios (fogão, forno, micro-ondas, airfryer, panela de pressão, panela elétrica).
- Mercado (redes de Goiânia ou "qualquer um").
- Compra da semana ou do mês.
- Orçamento: sugestão realista + botões −R$ 20 / +R$ 20 / Confirmar, com o resumo de porções e valor.

#### C8. "Montando seu plano"

- Uma mensagem só, editada a cada etapa REAL: promoções → receitas → cesta → orçamento → finalizando. Se reprovar na conferência: "⏳ Ajustando as receitas…".

#### C9. Resultado, cardápio e receitas

- "Sua semana está pronta, {nome}! 🎉 Gasto R$ X de R$ Y. Sobrou R$ Z · N itens."
- Botões: [📅 Ver cardápio] [🛒 Lista] [📄 PDF] [🔄 Refazer] [🏪 Onde comprar].
- Cada dia mostra as refeições com tempo e custo, e os botões [📖 Receita] e [🔁 Trocar]. A troca recalcula dentro do orçamento.
- Receita: quantidades da família, medidas brasileiras, passo a passo (um passo por mensagem, botão [Próximo ▶️]), fim com [✅ Fiz!] e nota de 1 a 5 (salva no perfil e usada nos próximos cardápios). Sem imagens geradas por IA.

#### C10. Conferências em código (nunca confiar só na IA)

- Compra por embalagem real ("1 pacote 5 kg"); a sobra não perecível vai para a despensa.
- Alergias, incluindo casos escondidos (leite de coco, pão de queijo etc.).
- Mesmo prato no máximo 1 vez por semana; evitar repetir a semana anterior (salvo favoritos).
- Só receitas com os utensílios que a pessoa tem.
- Total dentro do orçamento.
- Ao escalar porções, ajustar também o modo de preparo.
- Comida brasileira de verdade, incluindo a goiana (arroz com pequi, empadão, pamonha) e sobras planejadas.
- O plano nunca muda sozinho.

#### C11. PDF da lista

- Título "Rende", nome, data, itens por seção com caixinha, quantidade, preço, marca "🔥 promoção (mercado, até dd/mm)" ou "≈ estimado", total, orçamento e sobra. Se a compra for dividida, separar por mercado. Apagar o arquivo local depois de enviar.

#### C12. Mercados próximos

- Botão "📍 Enviar minha localização".
- API Overpass (OpenStreetMap), raio de 3 km configurável, até 8 mercados com distância e link do Google Maps, destacando os que têm promoção.
- Respeitar os limites de uso e usar um User-Agent genérico do app.

#### C13. Coletor de promoções (Goiânia)

FASE 1 (pesquisa, sem código): para Tático, Bretas, Prezunic, Assaí, Dia a Dia, Carrefour/Atacadão, Barão, Pão de Açúcar, Sam's Club e Cerrado, faça uma tabela com:

- se tem loja em Goiânia hoje;
- onde ficam as ofertas (encarte em imagem ou PDF, HTML, loja online, só no app);
- se varia por loja ou região;
- robots.txt e termos de uso;
- observações (preço só para sócio, só no app, atacado).
- Recomende 3 a 5 redes. PARE e espere minha aprovação.

FASE 2 (só as redes aprovadas):

- Um arquivo por rede em coletor/.
- extrair.py manda o encarte para o Gemini e recebe JSON por oferta (rede, produto, marca, tamanho, preço, preço anterior, condição, validade, região).
- Normalizar nomes ("ARROZ TIO JOÃO 5KG" → arroz / Tio João / 5 kg) e salvar em promocoes (origem "site", com link da fonte).

Boa conduta (obrigatória):

- 1 coleta por dia (6h);
- respeitar o robots.txt;
- 1 requisição a cada 5 s por site, com timeout e User-Agent genérico;
- hash para não reprocessar o mesmo encarte;
- se uma rede quebrar, as outras seguem e o admin recebe um aviso;
- apagar os arquivos depois de extrair.
- /coletar (admin) roda na hora e mostra o resultado por rede.

#### C14. Promoções e avisos

- /promo (só ADMIN_IDS) para cadastrar ofertas manualmente.

JobQueue:

- promoção nova avisa os usuários da cidade com avisos ativos e o produto na lista ou nas preferências;
- resumo semanal (dia e hora escolhidos; padrão sábado 9h);
- no máximo 1 aviso por dia;
- /avisos liga e desliga.
- Promoções vencidas somem e são apagadas.
- O cardápio dá preferência a ingredientes em promoção no mercado escolhido, sem quebrar orçamento, alergias e variedade.

#### C15. "Onde comprar"

- Total da lista atual em cada mercado (promoção quando houver; senão, estimado).
- Os 3 melhores com total e distância; a opção de dividir entre 2 mercados só se economizar pelo menos R$ 15.
- Marcar cada item como "🔥 promoção (até dd/mm)" ou "≈ estimado" e mostrar o % da lista com preço real.
- Avisar condições: só para sócio, só no app, leve X pague Y.

### PARTE D — ORDEM DE EXECUÇÃO

### PARTE A completa (clonar, ler, segurança, resumo) → esperar confirmação.

- Conferir e completar C1, C4, C5, C6, C7, C8, C9, C10 e C11 (o que já existe: só testar).
- C2 (escada de modelos).
- C3 (escopo).
- C13 FASE 1 → esperar aprovação das redes.
- C13 FASE 2 + C14.
- C15.
- C12.
- Testes no celular (PARTE E).
- Relatório final e PLANO.md atualizado.

### PARTE E — TESTES

Automáticos (sem chamar APIs reais; modelos simulados):

- roteador: nível inicial, escalonamento, recusa, limites, áudio nunca no Claude;
- escopo: 40 mensagens (20 dentro, 20 fora, incluindo mistas e tentativas de manipulação);
- conferências: embalagem, alergias escondidas, repetição, utensílios, orçamento;
- coletor: extração, normalização, deduplicação, falha de uma rede;
- "onde comprar": total por mercado e divisão;
- PDF, banco, /esquecer, avisos.

No celular (me avise o custo antes):

- /start como usuário novo e cadastro completo;
- ver a "animação" e o resultado;
- trocar 2 pratos;
- abrir uma receita no passo a passo e dar uma nota;
- gerar o PDF;
- mandar um áudio e uma foto de geladeira;
- mandar a localização e ver os mercados;
- "Onde comprar";
- /promo e ver o aviso chegar;
- 5 perguntas fora do escopo;
- /custos;
- /esquecer.
- Mostre o texto de cada resposta, qual modelo respondeu e o custo.

### PARTE F — RELATÓRIO FINAL

- O que funciona, o que não funciona e por quê.
- Custo médio por cardápio e % de escalonamento para o Opus.
- Próximos passos recomendados (servidor 24h no Railway ou Render, Supabase, WhatsApp, política de privacidade).
- PLANO.md atualizado.

---

## Pedido I: executar os itens pendentes do Pedido H + Modo mercado (24/11/2026)

Texto original colado na conversa (no computador `C:\Users\Matheus Duarte\cesta-bot`).
Ajustes que vieram nas mensagens seguintes estão logo depois do texto.

Decisão: execute AGORA todos os itens pendentes do PLANO.md (C2, C3, C6, C9, C10, C11, C12, C13, C14 e C15), sem esperar minha aprovação entre as etapas. Continue seguindo as regras da PARTE B (testes, PLANO.md e commits a cada etapa), e me mande um resumo curto ao final de cada C.

#### Restrições enquanto eu não troco as chaves

- As 3 chaves (Telegram, Gemini, Anthropic) vazaram e ainda não foram trocadas. Até eu avisar que troquei:
  - não faça chamadas PAGAS ao Claude; use modelos simulados nos testes;
  - não faça push para o GitHub;
  - não apague a cópia de segurança.
- A pesquisa na internet (C13 Fase 1) pode ser feita normalmente.

#### Decisões que já tomei

1. Lacuna 3 do C10: quando nenhum modelo acerta o orçamento, ENTREGAR o melhor plano, avisando quanto passou e oferecendo opções com botões: [Tirar lanches] [Aumentar para R$ X] [Pratos mais simples]. Se o orçamento escolhido estiver muito abaixo do sugerido no cadastro, avisar já no cadastro.
2. Custo do cardápio (fazer ANTES do resto do C10):
   - ao gerar o cardápio, o modelo devolve só JSON compacto: pratos, ingredientes com quantidades e lista de compras, SEM modo de preparo;
   - o modo de preparo é gerado só quando o usuário toca em [📖 Receita], pelo modelo mais barato que der conta (Gemini ou Haiku), e fica salvo;
   - meça tokens e custo antes e depois com o mesmo perfil (simulado ou estimado). Meta: Sonnet sozinho, menos de US$ 0,08 por cardápio.
3. C13 Fase 1: faça a pesquisa das redes de Goiânia e ESCOLHA VOCÊ as redes, seguindo estes critérios:
   - tem loja em Goiânia hoje;
   - ofertas acessíveis sem login;
   - robots.txt e termos de uso não proíbem a coleta.
   Implemente a Fase 2 para até 5 redes que passarem. As que não passarem ficam documentadas no PLANO.md como "candidatas a parceria". Me mostre a tabela no resumo.

#### Nova funcionalidade: marcar o que já foi comprado

1. "🛒 Modo mercado" no Telegram:
   - botão [🛒 Modo mercado] no resultado e na lista;
   - mostra a lista por seção do mercado; cada item é um botão; tocar alterna entre ⬜ e ✅ (editando a mesma mensagem, sem mandar várias);
   - no topo: "✅ 12 de 34 itens · R$ 145 de R$ 287";
   - botão [✏️ Paguei outro preço]: o usuário informa o preço real do item, que alimenta a tabela de preços (origem "usuario");
   - botão [🏁 Terminei as compras]: o que foi comprado vai para a despensa; o que faltou fica numa lista "não encontrei" e o Rende oferece substitutos;
   - o progresso fica salvo no banco: se fechar e abrir de novo, continua de onde parou.
2. PDF com caixinhas clicáveis:
   - use campos de formulário (checkbox AcroForm) em cada item, que funcionam em leitores como Adobe Acrobat e Google Drive;
   - mantenha as caixinhas visíveis também na impressão;
   - no fim do PDF, uma nota: "Dica: no Telegram, use 🛒 Modo mercado para marcar direto no app";
   - se a fpdf2 não suportar checkbox de formulário, use outra biblioteca (pypdf ou reportlab) só para essa parte e explique a escolha.
3. Testes automáticos: marcar e desmarcar, total parcial, salvar o progresso, "terminei" movendo para a despensa, preço informado pelo usuário e PDF com os campos de checkbox.

#### Ordem

Custo do cardápio → C10 (incluindo a lacuna 3) → C9, C11 e Modo mercado → C6 → C2 → C3 → C13 (Fase 1 e Fase 2) → C14 → C15 → C12.
Ao final: relatório completo (PARTE F) e o roteiro do teste no celular, que eu faço depois de trocar as chaves.

#### Ajustes nas mensagens seguintes (24/11)

- A cópia de segurança ficou no outro computador; não precisa procurar.
- As chaves só serão trocadas depois dos testes: **pode** fazer chamadas pagas ao Claude nos testes reais, avisando o custo estimado antes de cada rodada. **Push continua bloqueado** até o dono confirmar a troca.
- Esta cópia antiga foi alinhada com o GitHub (`reset --hard origin/main`) e o commit antigo com o `.env` foi apagado também do reflog local.
- Biblioteca anthropic 2.13 nos dois computadores; `.env` com `APAGAR_PDF_APOS_MIN` e `COTACAO_DOLAR`.
- Medição do custo: o "antes" é o teste real (US$ 0,36 com o Opus refazendo); o "depois" é estimado de graça e confirmado com UMA rodada real só no Sonnet, se custar até US$ 0,15.
- O bot do outro computador fica desligado; os testes reais são feitos neste.
- Sem parar entre os itens: só um resumo curto ao final de cada C.
