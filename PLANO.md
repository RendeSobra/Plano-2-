# Rende: plano de trabalho

Bot de Telegram em Python que monta o cardápio da semana e a lista de compras
dentro do orçamento, mostra promoções e diz onde comprar mais barato, para famílias
brasileiras de baixa e média renda (foco em Goiânia).
Bot: @cesta_cardapio_bot (nome de exibição passa de "Cesta" para "Rende").

Última atualização: 24/11/2026. A especificação em vigor é o **Pedido H**
([docs/PEDIDOS.md](docs/PEDIDOS.md)); onde ela discordar dos pedidos anteriores, vale ela.
O **Pedido I** (mesmo arquivo) manda executar os itens pendentes do H numa ordem própria,
com decisões do dono que valem por cima do H (ver "Decisões do Pedido I").
Histórico, testes reais e detalhes: [CONTEXTO.md](CONTEXTO.md).

Testes automáticos: `.venv\Scripts\python testes\testar.py` (**337 de 337 OK em 24/11/2026**).

## Pedidos e situação

| # | Pedido | Situação |
|---|---|---|
| 0 | Bot Cesta (cardápio por texto) | ✅ Feito e testado no celular |
| A | Áudio e foto | ✅ Código e testes automáticos. Áudio testado no celular; geladeira e nota ainda não |
| B | Assistente Rende com ferramentas, SQLite, PDF, mercados, promoções e avisos | 🔧 B1 ✅ · B2 quase (falta encarte) · B3 PDF ✅ · B4 ⏳ · B5 ⏳ (/custos ✅) |
| C | Coletor de promoções de Goiânia | ⏳ Virou o item C13 do Pedido H |
| D | Roteador Gemini/Claude + personalidade | ✅ Personalidade feita; roteador substituído pela escada (F) |
| E | Experiência com botões: cadastro, "montando seu plano", cardápio por dia, troca, receita passo a passo, nota | ✅ Feito e testado no celular (23/11) |
| F | Escada de modelos: Gemini → Haiku → Sonnet → Opus, limites por modelo, cache, /custos | ✅ Feito e testado no celular (23/11) |
| G | Mensagens de troca e PDF sem poluir o chat; contexto no GitHub | ✅ Feito |
| H | Retomada com a especificação completa (PARTES A a F) | 🔧 PARTE A ✅ (24/11). Itens pendentes: ver Pedido I |
| I | Executar os pendentes do H sem parar entre etapas + Modo mercado + PDF com caixinhas | 🔧 Custo do cardápio ✅ · C10 ✅ · C9, C11 e Modo mercado ✅ · C6 ✅ · C2 ✅ · C3 ✅ · C13 ✅ · C14 ✅ · C15 ✅ · C12 ✅ · relatório ✅ (24/11). Falta: teste no celular (roteiro em docs/RELATORIO.md) |
| PR #2 | Outro colaborador: toque de botão de ~930 ms para ~220 ms (conexão com o Telegram mantida aberta e aquecida, confirmação do toque em paralelo, SQLite em WAL), teclado de múltipla escolha novo (⬜/✅, contador, "Marcar todas"/"Limpar") e robustez | ✅ Revisado, corrigido (filtro de escopo que barrava frases normais, tela redesenhada depois do limite do Telegram, conta do cache no `/custos`, teto de tokens da mídia, toque confirmado no erro) e juntado na main (24/11). Falta ver a velocidade no celular |

## Pedido H: situação de cada item da PARTE C (conferido em 24/11/2026)

| Item | Situação | O que falta |
|---|---|---|
| C1 Arquitetura | ✅ (24/11) | Pasta `coletor/` criada no C13 |
| C2 Escada de modelos | ✅ (24/11) | `/custos` mostra as subidas de nível do dia e do mês, o custo médio por cardápio e em quantos o Opus entrou. Haiku na troca com effort "medium" (conferido: o Haiku 5.5 aceita low a max e o padrão dele é medium; a troca custa ~US$ 0,001 e exige conta de orçamento). Limite de saída de 32 mil tokens com streaming (decisão de 24/11). Cardápio compacto e Sonnet em effort "low" (Pedido I): ver "Custo do cardápio" |
| C3 Escopo | ✅ (24/11) | `escopo.py`, três camadas: (1) filtro em código antes de qualquer IA para o que é claramente de fora e não tem nenhuma palavra do Rende (custo zero); (2) toda resposta final começa com a linha "no_escopo: sim/nao" (linha de texto, não JSON forçado, para funcionar igual no Gemini e no Claude com ferramentas); com "nao" o código descarta o texto e manda 1 de 4 mensagens fixas com [📅 Meu cardápio] [🔥 Promoções] [🛒 Lista]; (3) o especialista (Claude) exige no_escopo = true. Conta no limite diário, não entra no histórico e o log diz só "fora_do_escopo". Teste com 40 mensagens: o filtro pega 17 de 20 de fora (todas as de manipulação) e não barra nenhuma de dentro nem as mistas. Sem o campo, a resposta é tratada como dentro (fica um aviso no log). Tela [🔥 Promoções] simples já existe (C14 completa) |
| C4 Personalidade | ✅ | O resumo semanal depende do C14 |
| C5 Memória | ✅ | Funciona com nomes diferentes do pedido: despensa é uma coluna de `usuarios` e os custos ficam em `uso_ia`. `/perfil` não edita cidade nem localização |
| C6 Entender qualquer mensagem | ✅ (24/11) | Foto ou PDF de encarte: a ferramenta `salvar_promocoes_de_encarte` salva as ofertas em `promocoes` (origem "usuario"), conferindo preço, validade (sem data impressa: 6 dias; vencida: nada) e repetição. Arquivo de áudio (mp3, m4a...) aceito como a mensagem de voz (só Gemini; como documento, o Telegram não dá a duração e vale o limite de 10 MB). Localização: guarda e mostra os mercados próximos (C12) |
| C7 Cadastro | ✅ | — |
| C8 "Montando seu plano" | ✅ | — |
| C9 Resultado | ✅ (24/11) | Texto e botões como no pedido ([📅 Ver cardápio] [🛒 Lista] [📄 PDF] [🔄 Refazer] [🏪 Onde comprar]) + [🛒 Modo mercado] |
| C10 Conferências em código | ✅ (24/11) | Feito no Pedido I: pratos que costumam levar o ingrediente proibido são barrados pelo nome (purê, strogonoff, empadão, lasanha, escondidinho, pamonha, feijoada, galinhada, vatapá...), salvo a versão segura escrita no nome ("sem lactose", "vegetariano"); 2 ou mais pratos repetidos da semana passada (fora favoritos) fazem refazer, 1 é só aviso; plano acima do orçamento é entregue com o aviso e os botões [Tirar lanches] [Aumentar para R$ X] [Pratos mais simples], e o cadastro avisa quando o orçamento fica abaixo de 75% da sugestão; a receita guarda as porções e é refeita na nova proporção se a família mudar (a lista não muda sozinha). Alergia no registro é reconhecida pelo rótulo "(Lactose)", não pela palavra solta |
| C11 PDF | ✅ (24/11) | Cada item com "≈ estimado", "PROMOÇÃO (mercado, até dd/mm)" ou "preço pago" (Modo mercado); caixinhas clicáveis (AcroForm, via pypdf: a fpdf2 2.9 só cria campo de assinatura) por cima do quadradinho desenhado, que sai na impressão; dica do Modo mercado no fim; o PDF nunca vai para o disco. As fontes padrão não têm emoji: as marcas são texto e o "≈" usa a fonte Symbol. Compra dividida (C15): uma parte por mercado, com subtotal |
| C12 Mercados próximos | ✅ (24/11) | `mercados_proximos.py`: Overpass (OpenStreetMap), supermercados e atacarejos (`shop=supermarket` e `wholesale`) num raio de 3 km (`RAIO_MERCADOS_M`), até 8, do mais perto ao mais longe, com distância em linha reta, link do Google Maps e 🔥 nas redes com promoção. Boa conduta: User-Agent do app, uma consulta por vez, resultado guardado 24 h para o mesmo lugar, servidor lotado (429/5xx) = espera 3 s e tenta de novo, depois o espelho público. Privacidade: a localização vai arredondada (~100 m) e sem dado da pessoa. Botão "📍 Enviar minha localização" (ação `lc:pedir`, também no "Onde comprar" e nas promoções); a IA abre com `mostrar(mercados_proximos)`. O "Onde comprar" mostra a distância da loja mais perto de cada rede. **Teste real (24/11, à tarde): 8 mercados em 30 s** perto da Praça Cívica, redes reconhecidas (Pão de Açúcar, Tático, Barão); de manhã a Overpass estava lotada (502) e o caminho de erro funcionou. **Achado do teste real e corrigido:** nenhuma loja das redes com promoção estava entre as 8 mais perto, então elas sumiam da tela e da distância no "Onde comprar". Agora a busca guarda todas as lojas do raio, a tela põe a loja mais perto de cada rede com promoção no lugar das últimas (continua com 8) e o "Onde comprar" usa todas |
| C13 Coletor | ✅ (24/11) | Redes escolhidas pelos critérios do dono: **Prezunic, Atacadão e Dia a Dia** (tabela em "C13: redes de Goiânia"). `coletor/` com um arquivo por rede (`coletar(nav)`), `web.py` (robots.txt, 1 requisição a cada 5 s por site, timeout, User-Agent "RendeColetor", até 18 MB, nada no disco), `extrair.py` (Gemini com JSON; a tarefa "coletor" **nunca** sobe para o Claude) e `promocoes.py` (normaliza "ARROZ TIO JOÃO 5KG" → arroz / Tio João / 5 kg, confere preço e validade, não repete). Hash sha256 + endereço de cada encarte em `encartes`: o mesmo não vai de novo para a IA. Encarte de bazar/eletro nem é baixado. Uma rede quebrada não derruba as outras e o admin recebe aviso. Coleta diária às 6h (`COLETOR_HORA`) pelo JobQueue e `/coletar` (admin). Rodar à mão: `python -m coletor` (`--listar` só lista, sem IA). Coleta real de 24/11: ver "C13: coleta real" |
| C14 Promoções e avisos | ✅ (24/11) | `avisos.py` (sem Telegram): promoção nova avisa quem tem avisos ligados, cadastro pronto, mora na cidade e tem o produto na lista do plano, nos pratos favoritos ou nas preferências (sem contar "não gosto de..."), nunca de algo proibido pelas restrições; no máximo 1 aviso por dia, só das 8h às 21h e nunca no dia do resumo. Resumo semanal no dia/hora escolhidos (padrão sábado 9h) com a sobra do último plano 🎉, as promoções (as da lista primeiro) e [📅 Montar cardápio]. JobQueue a cada 15 min; limpeza das vencidas às 00h10 e depois de cada coleta. `/avisos` liga e desliga; `/promo mercado; produto; preço; dd/mm[; marca=...; condicao=...; cidade=...]` (admin) dispara os avisos na hora. Quem bloqueia o bot para de receber. O cardápio recebe até 40 promoções de **comida** que a pessoa pode comer, nos mercados dela, maior desconto primeiro, e as instruções pedem preferência a elas sem quebrar orçamento, restrições e variedade |
| C15 "Onde comprar" | ✅ (24/11) | `onde_comprar.py`: total da lista em cada mercado (promoção que combina com o item, convertida para a quantidade que a lista precisa; senão o estimado), 3 melhores com medalha, % da lista com preço real, condições ("com clube", "só no app"...), divisão entre 2 mercados só se economizar R$ 15+. [📋 mercado] mostra cada item como "🔥 promoção (até dd/mm)" ou "≈ estimado"; [✅ Vou comprar no X] e [✂️ Dividir] guardam a escolha no plano: lista, PDF (separado por mercado) e Modo mercado passam a usar esses preços; [↩️ Desfazer]. Com a localização, mostra a distância (C12) |

## Ordem de trabalho (Pedido I, 24/11; substitui a PARTE D do Pedido H)

Sem parar entre os itens; resumo curto ao fim de cada C.

1. ✅ PARTE A do H: ler tudo, segurança, resumo (24/11).
2. ✅ **Custo do cardápio** (24/11): JSON compacto sem modo de preparo; medição antes/depois.
3. ✅ C10 (conferências), incluindo a lacuna 3 (plano acima do orçamento) (24/11).
4. ✅ C9, C11 e **Modo mercado** (marcar o que já foi comprado; PDF com caixinhas clicáveis).
5. ✅ C6 (entender qualquer mensagem) (24/11).
6. ✅ C2 (escada de modelos) (24/11).
7. ✅ C3 (escopo) (24/11).
8. ✅ C13 Fases 1 e 2 (24/11): redes escolhidas pelos critérios do dono, coletor e coleta real.
9. ✅ C14 → ✅ C15 → ✅ C12 (24/11).
10. ✅ Relatório final (PARTE F) e roteiro do teste no celular: [docs/RELATORIO.md](docs/RELATORIO.md) (24/11).

## Custo do cardápio (Pedido I, 24/11/2026)

Medido com o mesmo perfil do teste de 23/11 (2 adultos + 1 criança, 21 refeições, sem lactose,
R$ 300). Script: `.venv\Scripts\python testes\medir_cardapio.py` (estimativa grátis) e
`... --real` (uma chamada paga ao Sonnet, limitada a US$ 0,15).

| | Antes (testes reais) | Depois: estimativa | Depois: rodada real |
|---|---|---|---|
| JSON do cardápio | ~7.400 tokens | ~4.700 (−37%) | ~4.500 |
| Raciocínio (saída) | ~5.000 (effort medium) | 1.500–2.500 (low, suposição) | ~0 (low) |
| Custo do Sonnet | US$ 0,131 (23/11) | US$ 0,068–0,078 | **US$ 0,053** |
| Com o Opus refazendo | US$ 0,33 (23/11) e US$ 0,36 (24/11) | — | — |
| Passou na conferência? | não (23/11: falso alarme de alergia; 24/11: cortado) | — | **não: R$ 351,50 de R$ 300** |

O que mudou: formato compacto (chaves curtas, café repetido numa entrada com vários dias,
ingrediente sem unidade, perecível deduzido da seção, sem "nome" e sem "reaproveitamento");
o modo de preparo continua sendo gerado só ao abrir o prato (Gemini → Haiku) e guardado;
Sonnet com effort "low" (`ESFORCO_CARDAPIO`); o Opus refaz com "medium".

O que a rodada real mostrou: a meta de custo foi batida, mas sem raciocínio o Sonnet escolheu
embalagens grandes demais para o uso (açúcar 5 kg para 270 g, café 500 g para 175 g, 2
bandejas de ovos) e estourou o orçamento; na escada, o Opus refaria (~US$ 0,19). Correções
feitas logo depois, ainda **sem nova medição real**: regra "menor embalagem que cubra o uso",
valor médio por refeição no pedido e, quando estoura, a correção diz quais itens pesam mais e
quais embalagens estão grandes demais. **Pendente:** uma nova rodada real (~US$ 0,05) para ver se
o Sonnet passa de primeira; se não passar, as opções são effort "medium" (~US$ 0,10) ou deixar o
próprio Sonnet corrigir o orçamento antes de chamar o Opus (decisão do dono).

**Teste real do dono (24/11, 10h16, já com as correções):** orçamento de R$ 180. O Sonnet
(US$ 0,046) montou R$ 258,80 e foi reprovado; o Opus refez dentro do orçamento (US$ 0,376, 17 mil
tokens de saída). Cardápio: **US$ 0,42**. Com orçamento apertado, o Sonnet em "low" ainda erra
a conta e o Opus sai caro: a decisão pendente acima ficou mais importante.

## C13: redes de Goiânia (pesquisa de 24/11/2026)

Critérios do dono: loja em Goiânia hoje; ofertas acessíveis sem login; robots.txt e termos de
uso não proíbem a coleta. Acessos com User-Agent "RendePesquisa/1.0" e pausa entre acessos.

| Rede | Loja em Goiânia | Onde ficam as ofertas | Varia por loja/região | robots.txt e termos | Observações | Decisão |
|---|---|---|---|---|---|---|
| **Prezunic** (Cencosud) | Sim (assumiu lojas do Bretas) | `/encartes`: PDFs com estado, início e fim num JSON da página | Sim: seletor RJ/GO (pegamos GO) | robots libera `/encartes` e os PDFs (`/arquivos`); termos não publicados em texto legível (a página carrega vazia) e nenhuma proibição achada | Muitas ofertas "com clube" (cadastro no clube) | ✅ coletada |
| **Atacadão** (Carrefour) | Sim (Av. Independência) | Página da loja (`/loja/goiania-avenida-independencia`): folhetos em PDF com validade | Sim, por loja | robots libera `/loja/`; o servidor dos PDFs não tem robots; termos não proíbem coleta ("conteúdo do Atacadão, vedado o uso não autorizado": guardamos só produto e preço, com link, nunca o folheto) | Preço varejo e atacado (vai na condição) | ✅ coletada |
| **Dia a Dia** (Atacadão Dia a Dia) | Sim (Setor Novo Horizonte e Balneário) | Site de ofertas por loja + API pública do WordPress com o PDF do tabloide | Sim, por loja | robots libera tudo para `*` (bloqueia só robôs de treino de IA); política de privacidade não proíbe | Campanhas diárias (ex.: "Dia da Limpeza") | ✅ coletada |
| Assaí | Sim | Página `/ofertas` com encarte por loja, carregado de um JSON | Sim, por loja | robots libera `/ofertas`, mas o JSON é bloqueado por proteção anti-robô (Incapsula) | Contornar a proteção não é boa conduta | ❌ candidata a parceria |
| Bretas | Lojas viraram Prezunic em 2026 | Só no app, ativando a oferta com CPF | — | — | Exige cadastro | ❌ candidata a parceria |
| Carrefour (hiper) | Não confirmada | Página de ofertas das lojas: 404/403 (Akamai) | — | — | — | ❌ candidata a parceria |
| Sam's Club | Sim | Loja online | Por CEP | Termos **proíbem** "mineração de dados de qualquer tipo" | Preço só para sócio | ❌ não coletar |
| Pão de Açúcar | Não confirmada (imóvel da loja de Goiânia vendido em 2026; GPA em recuperação) | Loja online por CEP, sem encarte | Por CEP | robots não proíbe | — | ❌ candidata a parceria |
| Tático | Sim (segundo agregadores) | Site oficial fora do ar/bloqueado (erro 409); encartes só em agregadores | — | — | — | ❌ candidata a parceria |
| Barão (Super Barão) | Sim | App "Clube Barão" (cadastro); site com erro 520 | — | — | Exige cadastro | ❌ candidata a parceria |
| Cerrado | Não confirmada | Loja online (app de página única), sem encarte público achado | — | robots libera tudo | — | ❌ candidata a parceria |

**C13: coleta real (24/11/2026, 10h17–10h21):** 305 ofertas novas, nenhum erro. Prezunic 172
(2 encartes), Atacadão 83 (4 folhetos), Dia a Dia 50 (3 tabloides; o de Bazar foi pulado).
Exemplos: arroz 5 kg R$ 19,90 (Prezunic, com clube) e R$ 20,99 (Atacadão); feijão carioca 1 kg
R$ 6,59; óleo de soja 900 ml R$ 5,98; café 500 g R$ 17,99 (Atacadão). Custo: US$ 0,19 em 17
chamadas (o Gemini 3.5 Flash-Lite deu 503 em todas e o reserva 3.6 Flash leu os encartes).
Nas próximas coletas só entram encartes novos (hash).

## Decisões do Pedido I (24/11/2026)

- Executar os pendentes do H **sem esperar aprovação entre as etapas**; resumo curto ao fim de cada C.
- Push estava bloqueado até a troca das 3 chaves; **liberado em 24/11** (o dono trocou as chaves
  e pediu para subir). Chamadas pagas ao Claude nos testes reais: avisar o custo estimado antes.
- Lacuna 3 do C10: sem nenhum modelo dentro do orçamento, entregar o melhor plano avisando quanto
  passou, com os botões [Tirar lanches] [Aumentar para R$ X] [Pratos mais simples]; avisar já no
  cadastro se o orçamento estiver muito abaixo do sugerido.
- Cardápio em JSON compacto sem modo de preparo; meta de custo: Sonnet sozinho abaixo de US$ 0,08.
- C13: o Claude escolhe as redes (loja em Goiânia hoje, ofertas sem login, robots.txt e termos
  permitem) e já faz a Fase 2 para até 5; as outras ficam como "candidatas a parceria".
- Novo: 🛒 Modo mercado e PDF com caixinhas clicáveis (texto completo no Pedido I). Feito em 24/11:
  `mercado.py` (progresso guardado no plano, campo "mercado"; /esquecer apaga junto), tabela `precos`
  (preço informado, origem "usuario", sem dizer quem informou), campo `usuarios.aguardando` (o próximo
  número escrito é o preço). [🏁 Terminei]: o comprado vai para a despensa (o que tem em casa agora),
  o resto vira "não encontrei" com substitutos simples (sem IA, respeitando as restrições) e botões para
  trocar os pratos afetados; a troca evita e reprova o item que faltou.

## Regras de trabalho (PARTE B)

- Uma etapa por vez. Ao fim de cada uma: testes passando, resumo para o dono e este arquivo atualizado.
- Commits pequenos em português. **Push só com autorização.**
- Antes de teste real que gaste dinheiro (Claude): dizer o custo estimado.
- Antes de ação no celular fora do roteiro (mandar mensagem a alguém, instalar app, pagar): perguntar.
- Conferir a documentação atual das bibliotecas e APIs antes de escrever código.

## Decisões já tomadas

- Bot atual renomeado para "Rende" (o @ continua cesta_cardapio_bot).
- Testes com áudio e fotos: o dono grava e fotografa; o resto é feito pelo celular via adb.
- Teste de localização: ponto público de Goiânia escolhido no mapa (não o GPS do celular).
- ADMIN_IDS = conta do dono no Telegram.
- Claude em escada: Haiku na troca de prato, Sonnet no cardápio, Opus só por escalonamento ou
  caso complexo. Effort explícito ("low" na conversa, "medium" em troca e cardápio); sem
  temperature/top_p/top_k/budget_tokens/thinking; tool_choice "auto".
- Reprovação na conferência, recusa (stop_reason "refusal") ou erro → **sobe um nível**.
  Todos os níveis do Claude falharam → Gemini, com registro no log.
  O fallback no servidor da Anthropic **não** foi ativado (a escada é feita no nosso código).
- **Limite de saída do Claude: 32 mil tokens, com streaming** (o pedido era 16 mil no cardápio).
  Aprovado pelo dono em 24/11: no teste real o Sonnet gastou os 16 mil (o raciocínio conta no
  limite), o cardápio saiu cortado e o Opus refez tudo. Só se paga o que o modelo usa.
- **Troca de prato:** o modelo recebe a folga exata (lista recalculada sem o prato antigo) e as
  sobras das embalagens já compradas. Se nem um prato de graça caberia, o robô avisa sem chamar
  a IA. Se todos os níveis estourarem o orçamento, explica o motivo em vez de "tentar de novo".
- **Log sem dados pessoais:** nenhuma linha do registro grava o ID da conta do Telegram (regra A3).
- O Claude não ouve áudio: turnos com áudio ficam no Gemini.
- Somas, embalagens, alergias e repetição de pratos são sempre conferidas em código, nunca só pela IA.
- Receitas (passo a passo) são geradas pelo Gemini só quando a pessoa abre o prato, e guardadas no plano.
- "Compra do mês": por enquanto o plano continua semanal, com orçamento mensal ÷ 4,3.

## Segurança (24/11/2026)

- **O que aconteceu:** o `.env` com as 3 chaves (Telegram, Gemini, Anthropic) entrou no primeiro
  commit e foi enviado ao GitHub (repositório privado, sem forks).
- **O que foi feito, com autorização do dono:** o commit com o `.env` foi retirado da história
  (rebase) e o GitHub foi atualizado com force push protegido. O `.env` local foi mantido e o
  `.gitignore` agora o ignora (junto com `*.db`, `__pycache__/` e `.venv/`).
- **Feito pelo dono em 24/11:** as 3 chaves foram trocadas e as novas estão só no `.env` local.
  O GitHub ainda pode guardar o commit antigo por um tempo, mas as chaves dele não valem mais.
  Para apagar também essa cópia, é preciso pedir ao suporte do GitHub (opcional).
- Depois da troca: apagar a cópia de segurança local feita antes da limpeza (tem as chaves antigas;
  fica no outro computador).
- No computador `C:\Users\Matheus Duarte\cesta-bot` (24/11): a cópia antiga, que ainda tinha o
  commit com o `.env`, foi alinhada com o GitHub (`reset --hard origin/main`, guardando o `.env`)
  e o commit antigo foi apagado também do registro local (`reflog expire` + `gc --prune=now`).

## Chaves no .env (o dono preenche; nunca vão para a conversa nem para o Git)

TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, ANTHROPIC_API_KEY: preenchidas com as chaves novas (24/11).
COTACAO_DOLAR (opcional): vazia. Coletor (opcionais): COLETOR_HORA, COLETOR_MAX_ENCARTES,
COLETOR_ATACADAO_LOJAS, COLETOR_DIAADIA_LOJAS (ver `.env.example`).
