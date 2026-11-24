# Rende: plano de trabalho

Bot de Telegram em Python que monta o cardápio da semana e a lista de compras
dentro do orçamento, mostra promoções e diz onde comprar mais barato, para famílias
brasileiras de baixa e média renda (foco em Goiânia).
Bot: @cesta_cardapio_bot (nome de exibição passa de "Cesta" para "Rende").

Última atualização: 24/11/2026. A especificação em vigor é o **Pedido H**
([docs/PEDIDOS.md](docs/PEDIDOS.md)); onde ela discordar dos pedidos anteriores, vale ela.
Histórico, testes reais e detalhes: [CONTEXTO.md](CONTEXTO.md).

Testes automáticos: `.venv\Scripts\python testes\testar.py` (**101 de 101 OK em 24/11/2026**).

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
| H | Retomada com a especificação completa (PARTES A a F) | 🔧 PARTE A ✅ (24/11). Próximo: C1, C4–C11 |

## Pedido H: situação de cada item da PARTE C (conferido em 24/11/2026)

| Item | Situação | O que falta |
|---|---|---|
| C1 Arquitetura | 🟡 | Só a pasta `coletor/` (vem no C13) |
| C2 Escada de modelos | 🟢 quase | `/custos` mostra os escalonamentos só do dia (pedido: dia e mês). O Haiku usa effort "medium" na troca: conferir na documentação atual se é o certo |
| C3 Escopo | ❌ | Hoje é só uma frase no prompt. Falta o campo `no_escopo` conferido em código, as mensagens fixas com botões, o log "fora_do_escopo" e o teste com 40 mensagens |
| C4 Personalidade | ✅ | O resumo semanal depende do C14 |
| C5 Memória | ✅ | Funciona com nomes diferentes do pedido: despensa é uma coluna de `usuarios` e os custos ficam em `uso_ia`. `/perfil` não edita cidade nem localização |
| C6 Entender qualquer mensagem | 🟡 | Foto de encarte não salva as ofertas (origem "usuario"). Localização só é guardada. Arquivo de áudio (que não seja mensagem de voz) não é aceito |
| C7 Cadastro | ✅ | — |
| C8 "Montando seu plano" | ✅ | — |
| C9 Resultado | 🟡 | Falta o botão "🏪 Onde comprar" (depende do C15); textos dos botões diferentes do pedido |
| C10 Conferências em código | 🟡 | Alergia escondida só no nome do prato passa ("empadão", "strogonoff", "purê", "lasanha" para lactose). Repetir a semana anterior só gera aviso no log. Plano acima do orçamento pode ser entregue como "melhor resultado". Receita guardada não se atualiza se a família mudar de tamanho |
| C11 PDF | 🟡 | Falta "≈ estimado" em cada item (hoje é nota no rodapé), a marca "🔥 promoção (mercado, até dd/mm)" e a separação por mercado. A fonte padrão (Helvetica) não desenha emoji |
| C12 Mercados próximos | ❌ | Não começado |
| C13 Coletor | ❌ | Não começado. Fase 1 (pesquisa) **para e espera aprovação** |
| C14 Promoções e avisos | ❌ quase tudo | Existem a tabela `promocoes` e o liga/desliga pela conversa. Faltam `/promo`, `/avisos`, avisos pelo JobQueue, resumo semanal e limpeza das vencidas |
| C15 "Onde comprar" | ❌ | Não começado |

## Ordem de trabalho (PARTE D do Pedido H)

1. ✅ PARTE A: ler tudo, segurança, resumo (24/11).
2. ⏳ **Próximo:** conferir e completar C1, C4, C5, C6, C7, C8, C9, C10 e C11
   (começando pelas lacunas de alergia do C10 e pelo "≈ estimado" do PDF).
3. C2 (escada de modelos).
4. C3 (escopo).
5. C13 Fase 1 (pesquisa das redes) → **parar e esperar aprovação**.
6. C13 Fase 2 + C14.
7. C15.
8. C12.
9. Testes no celular (PARTE E) → **avisar o custo estimado antes**.
10. Relatório final (PARTE F) e PLANO.md atualizado.

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
- Depois da troca: apagar a cópia de segurança local feita antes da limpeza (tem as chaves antigas).

## Chaves no .env (o dono preenche; nunca vão para a conversa nem para o Git)

TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, ANTHROPIC_API_KEY: preenchidas, **mas precisam ser
trocadas** (ver Segurança). COTACAO_DOLAR (opcional): vazia.
