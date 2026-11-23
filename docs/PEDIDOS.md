# Pedidos (texto original, em ordem)

Todos feitos em 23/11/2026. Situação de cada um: [PLANO.md](../PLANO.md) e [CONTEXTO.md](../CONTEXTO.md).

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
