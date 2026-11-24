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

Testes automáticos: `.venv\Scripts\python testes\testar.py` (**145 de 145 OK em 24/11/2026**).

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
| I | Executar os pendentes do H sem parar entre etapas + Modo mercado + PDF com caixinhas | 🔧 Custo do cardápio ✅ · C10 ✅ (24/11). Próximo: C9, C11 e Modo mercado |

## Pedido H: situação de cada item da PARTE C (conferido em 24/11/2026)

| Item | Situação | O que falta |
|---|---|---|
| C1 Arquitetura | 🟡 | Só a pasta `coletor/` (vem no C13) |
| C2 Escada de modelos | 🟢 quase | `/custos` mostra os escalonamentos só do dia (pedido: dia e mês). O Haiku usa effort "medium" na troca: conferir na documentação atual se é o certo. Feito em 24/11 (depois do teste real): limite de 32 mil tokens com streaming; a troca recebe a folga exata e as sobras das embalagens; conferir no próximo teste se ela passa de primeira. **Cardápio compacto e Sonnet em effort "low" (Pedido I, 24/11): ver "Custo do cardápio"** |
| C3 Escopo | ❌ | Hoje é só uma frase no prompt. Falta o campo `no_escopo` conferido em código, as mensagens fixas com botões, o log "fora_do_escopo" e o teste com 40 mensagens |
| C4 Personalidade | ✅ | O resumo semanal depende do C14 |
| C5 Memória | ✅ | Funciona com nomes diferentes do pedido: despensa é uma coluna de `usuarios` e os custos ficam em `uso_ia`. `/perfil` não edita cidade nem localização |
| C6 Entender qualquer mensagem | 🟡 | Foto de encarte não salva as ofertas (origem "usuario"). Localização só é guardada. Arquivo de áudio (que não seja mensagem de voz) não é aceito |
| C7 Cadastro | ✅ | — |
| C8 "Montando seu plano" | ✅ | — |
| C9 Resultado | 🟡 | Falta o botão "🏪 Onde comprar" (depende do C15); textos dos botões diferentes do pedido |
| C10 Conferências em código | ✅ (24/11) | Feito no Pedido I: pratos que costumam levar o ingrediente proibido são barrados pelo nome (purê, strogonoff, empadão, lasanha, escondidinho, pamonha, feijoada, galinhada, vatapá...), salvo a versão segura escrita no nome ("sem lactose", "vegetariano"); 2 ou mais pratos repetidos da semana passada (fora favoritos) fazem refazer, 1 é só aviso; plano acima do orçamento é entregue com o aviso e os botões [Tirar lanches] [Aumentar para R$ X] [Pratos mais simples], e o cadastro avisa quando o orçamento fica abaixo de 75% da sugestão; a receita guarda as porções e é refeita na nova proporção se a família mudar (a lista não muda sozinha). Alergia no registro é reconhecida pelo rótulo "(Lactose)", não pela palavra solta |
| C11 PDF | 🟡 | Falta "≈ estimado" em cada item (hoje é nota no rodapé), a marca "🔥 promoção (mercado, até dd/mm)" e a separação por mercado. A fonte padrão (Helvetica) não desenha emoji |
| C12 Mercados próximos | ❌ | Não começado |
| C13 Coletor | ❌ | Não começado. Fase 1 (pesquisa) **para e espera aprovação** |
| C14 Promoções e avisos | ❌ quase tudo | Existem a tabela `promocoes` e o liga/desliga pela conversa. Faltam `/promo`, `/avisos`, avisos pelo JobQueue, resumo semanal e limpeza das vencidas |
| C15 "Onde comprar" | ❌ | Não começado |

## Ordem de trabalho (Pedido I, 24/11; substitui a PARTE D do Pedido H)

Sem parar entre os itens; resumo curto ao fim de cada C.

1. ✅ PARTE A do H: ler tudo, segurança, resumo (24/11).
2. ✅ **Custo do cardápio** (24/11): JSON compacto sem modo de preparo; medição antes/depois.
3. ✅ C10 (conferências), incluindo a lacuna 3 (plano acima do orçamento) (24/11).
4. ⏳ **Próximo:** C9, C11 e **Modo mercado** (marcar o que já foi comprado; PDF com caixinhas clicáveis).
5. C6 (entender qualquer mensagem).
6. C2 (escada de modelos).
7. C3 (escopo).
8. C13 Fases 1 e 2 (o Claude escolhe as redes pelos critérios do dono; não para).
9. C14 → C15 → C12.
10. Relatório final (PARTE F) e roteiro do teste no celular (o dono testa depois de trocar as chaves).

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

## Decisões do Pedido I (24/11/2026)

- Executar os pendentes do H **sem esperar aprovação entre as etapas**; resumo curto ao fim de cada C.
- **Push bloqueado** até o dono confirmar a troca das 3 chaves. Chamadas pagas ao Claude nos
  testes reais: permitidas, avisando o custo estimado antes de cada rodada.
- Lacuna 3 do C10: sem nenhum modelo dentro do orçamento, entregar o melhor plano avisando quanto
  passou, com os botões [Tirar lanches] [Aumentar para R$ X] [Pratos mais simples]; avisar já no
  cadastro se o orçamento estiver muito abaixo do sugerido.
- Cardápio em JSON compacto sem modo de preparo; meta de custo: Sonnet sozinho abaixo de US$ 0,08.
- C13: o Claude escolhe as redes (loja em Goiânia hoje, ofertas sem login, robots.txt e termos
  permitem) e já faz a Fase 2 para até 5; as outras ficam como "candidatas a parceria".
- Novo: 🛒 Modo mercado e PDF com caixinhas clicáveis (texto completo no Pedido I).

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
- **Pendente (só o dono pode fazer):** trocar as 3 chaves (BotFather `/revoke`, Google AI Studio,
  Anthropic Console) e colar as novas só no `.env` local. O GitHub ainda guarda o commit antigo
  por um tempo, acessível só por quem tem o código dele; a troca das chaves resolve de vez.
  Para apagar também essa cópia, é preciso pedir ao suporte do GitHub (opcional).
- Depois da troca: apagar a cópia de segurança local feita antes da limpeza (tem as chaves antigas;
  fica no outro computador).
- No computador `C:\Users\Matheus Duarte\cesta-bot` (24/11): a cópia antiga, que ainda tinha o
  commit com o `.env`, foi alinhada com o GitHub (`reset --hard origin/main`, guardando o `.env`)
  e o commit antigo foi apagado também do registro local (`reflog expire` + `gc --prune=now`).

## Chaves no .env (o dono preenche; nunca vão para a conversa nem para o Git)

TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, ANTHROPIC_API_KEY: preenchidas, **mas precisam ser
trocadas** (ver Segurança). COTACAO_DOLAR (opcional): vazia.
