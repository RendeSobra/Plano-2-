# Rende: plano de trabalho

Bot de Telegram em Python que monta o cardápio da semana e a lista de compras
dentro do orçamento, para famílias brasileiras (foco em Goiânia).
Bot: @cesta_cardapio_bot (nome de exibição passa de "Cesta" para "Rende").

## Pedidos e situação

| # | Pedido | Situação |
|---|---|---|
| 0 | Bot Cesta (cardápio por texto) | ✅ Feito e testado no celular |
| A | Áudio e foto | ✅ Código e testes automáticos. Áudio testado no celular; geladeira e nota ainda não |
| B | Assistente Rende com ferramentas, SQLite, PDF, mercados, promoções e avisos | 🔧 B1 ✅ · B2 quase (falta encarte) · B3 PDF ✅ · B4 ⏳ · B5 ⏳ (/custos ✅) |
| C | Coletor de promoções de Goiânia | ⏳ Fase 1 (pesquisa) depois da B5, e **espera aprovação** |
| D | Roteador Gemini/Claude + personalidade | ✅ Personalidade feita; roteador substituído pela escada (F) |
| E | Experiência com botões (estilo NeatEat): cadastro, "montando seu plano", cardápio por dia, troca de prato, receita passo a passo, nota | ✅ Feito e testado no celular (23/11) |
| F | Escada de modelos: Gemini → Haiku → Sonnet → Opus, limites por modelo, cache, /custos | ✅ Feito e testado no celular (23/11): plano Sonnet→Opus, 2 trocas Haiku→Sonnet, receita Gemini, /custos |
| G | Mensagens de troca e PDF sem poluir o chat; contexto no GitHub | ✅ Feito (troca no topo da tela do dia; PDF some em 5 min) |

Testes automáticos: `.venv\Scripts\python testes\testar.py` (101 de 101 OK em 23/11/2026).
Resultados do teste real, defeitos corrigidos e próximos passos: [CONTEXTO.md](CONTEXTO.md).

## Ordem de construção

1. **B1 + D + núcleo do E**: banco SQLite, roteador, cadastro com botões, plano com
   embalagens/despensa/alergias/variedade validados em código, cardápio por dia,
   troca de prato, receita passo a passo, nota.
2. **B2**: entender qualquer mensagem (PDF, imagem como documento, localização, figurinha, encarte).
3. **B3**: PDF da lista.
4. **B4**: mercados próximos (OpenStreetMap/Overpass).
5. **B5**: promoções (/promo), avisos (JobQueue), /avisos, /custos.
6. **Testes no celular** dos pedidos A, B, D e E.
7. **C, Fase 1**: pesquisa das redes. Parar e esperar aprovação.

## Decisões já tomadas

- Bot atual renomeado para "Rende" (o @ continua cesta_cardapio_bot).
- Testes com áudio e fotos: o usuário grava e fotografa; o resto é feito pelo celular via adb.
- Teste de localização: ponto público de Goiânia escolhido no mapa (não o GPS do celular).
- ADMIN_IDS = conta do usuário no Telegram.
- Claude: Opus 5.5 com effort "medium"; sem temperature/top_p/top_k/budget_tokens; tool_choice "auto";
  recusa (stop_reason "refusal") vai para o Gemini. Fallback no servidor da Anthropic **não** ativado,
  porque a regra do usuário manda recusas para o Gemini.
- O Claude não ouve áudio: turnos com áudio ficam no Gemini.
- Somas, embalagens, alergias e repetição de pratos são sempre conferidas em código, nunca só pela IA.
- Receitas (passo a passo) são geradas pelo Gemini só quando a pessoa abre o prato, e guardadas no plano.
- "Compra do mês": por enquanto o plano continua semanal, com orçamento mensal ÷ 4,3.

## Chaves no .env (o usuário preenche; nunca vão para a conversa)

TELEGRAM_BOT_TOKEN, GEMINI_API_KEY (preenchidas) · ANTHROPIC_API_KEY (pendente)
