# Rende: relatório final do Pedido H/I (PARTE F), 24/11/2026

Situação item a item no [PLANO.md](../PLANO.md); histórico no [CONTEXTO.md](../CONTEXTO.md).
Testes automáticos: **281 de 281 OK** (`.venv\Scripts\python testes\testar.py`), sem chamar IA,
Telegram, sites ou mapas de verdade.

## 1. O que funciona

| Parte | O que faz | Provado como |
|---|---|---|
| Cadastro (C7), "Montando seu plano" (C8), resultado e receitas (C9) | 10 passos com botões; animação com as etapas reais; resultado com [📅 Ver cardápio] [🛒 Lista] [📄 PDF] [🔄 Refazer] [🏪 Onde comprar] [🛒 Modo mercado]; receita passo a passo e nota | Testes + celular (23/11 e 24/11) |
| Escada de modelos (C2) | Gemini → Haiku → Sonnet → Opus, subida por reprovação/recusa/erro, limites diários, `/custos` com mês, custo médio e % do Opus | Testes + celular |
| Escopo (C3) | Filtro em código + campo `no_escopo`; 40 mensagens de teste | Testes |
| Conferências (C10) | Embalagem inteira, alergias escondidas, repetição, utensílios, orçamento; plano acima do orçamento entregue com 3 saídas | Testes + celular |
| PDF (C11) e 🛒 Modo mercado | Caixinhas clicáveis, "≈ estimado"/"PROMOÇÃO", separado por mercado quando a compra é dividida; marcar itens, preço pago, "Terminei" | Testes (celular: falta) |
| Encarte, áudio em arquivo (C6) | Foto/PDF de encarte vira promoção (origem "usuario"); mp3/m4a | Testes (celular: falta) |
| **Coletor (C13)** | Prezunic, Atacadão e Dia a Dia; boa conduta; só Gemini; hash; aviso ao admin; 6h + `/coletar` | Testes + **coleta real: 305 ofertas, US$ 0,19** |
| **Promoções e avisos (C14)** | Aviso de promoção da lista (1/dia, 8h–21h, respeita restrições), resumo semanal, `/avisos`, `/promo`, limpeza; cardápio prefere promoções de comida | Testes (celular: falta) |
| **Onde comprar (C15)** | Total por mercado, 3 melhores, % com preço real, condições, divisão só com R$ 15+; a escolha vale na lista, no PDF e no Modo mercado | Testes (celular: falta) |
| **Mercados próximos (C12)** | Overpass, 3 km, até 8, distância, Google Maps, 🔥 nas redes com promoção | Testes + **teste real: 8 mercados em 30 s** (tarde de 24/11) |

## 2. O que não funciona (ou não foi provado) e por quê

1. **Custo do cardápio acima da meta.** Meta: Sonnet sozinho abaixo de US$ 0,08. Real: o Sonnet em
   "low" custa US$ 0,05, mas foi **reprovado nos dois testes reais** (23/11 alergia; 24/11 passou
   R$ 78,80 de R$ 180), e o Opus refez por US$ 0,20–0,38. Perfil com 3+ restrições vai direto ao
   Opus (US$ 0,43). **Custo médio real: US$ 0,39 por cardápio; Opus em 100% (3 de 3).**
2. **Mercados próximos dependem da Overpass:** de manhã ela respondeu "servidor lotado" (502); à
   tarde achou 8 mercados em 30 s. Quando falha, o bot avisa e oferece [🔄 Tentar de novo]. O teste real
   mostrou que as lojas das redes com promoção podiam ficar de fora das 8 mais perto (corrigido: entram
   no lugar das últimas). O mapa é feito por voluntários e pode faltar mercado.
3. **Gemini 3.5 Flash-Lite deu 503 (sobrecarga) em todas as chamadas do coletor em 24/11**; o
   reserva (3.6 Flash, ~2,5x mais caro) fez o trabalho. Se continuar, vale inverter a ordem no `.env`.
4. **Ofertas "com clube" do Prezunic** (a maioria): o preço exige cadastro no clube. Aparecem como
   condição no "Onde comprar", mas entram no total. Se a pessoa não for do clube, o total engana.
5. **Comparação de item com promoção é por palavras:** "leite" combina com "leite condensado".
   Raro na lista, mas pode aparecer num aviso.
6. **O coletor depende do formato dos sites:** se um site mudar, a rede para e o admin recebe aviso
   (testado). O Atacadão diz nos termos que o conteúdo é dele; guardamos só produto e preço, com link.
7. **Nome e lista de comandos do bot no Telegram não atualizaram em 24/11** ("flood control": o
   Telegram bloqueou novas trocas por ~4 h). Os comandos novos funcionam digitados.
8. **Ainda não testado no celular:** foto de geladeira e de nota fiscal (desde o Pedido A), foto de
   encarte, Modo mercado, PDF com caixinhas, avisos, `/promo`, Onde comprar, localização.

## 3. Próximos passos recomendados

1. **Decidir o custo do cardápio** (o mais importante): (a) Sonnet em "medium" (~US$ 0,10, deve
   errar menos a conta) ou (b) deixar o Sonnet corrigir o orçamento uma vez antes de chamar o Opus
   (~US$ 0,10) e (c) rever a regra "3+ restrições = Opus direto" (hoje US$ 0,43 por cardápio).
2. **Servidor 24h:** Railway ou Render como *Background Worker* (o bot usa polling; **uma só
   cópia**). O JobQueue (coleta 6h, avisos a cada 15 min, limpeza) roda dentro do bot. O SQLite
   precisa de disco persistente; melhor ir para o Supabase.
3. **Supabase (Postgres):** reescrever só o `banco.py`, com RLS e backup.
4. **WhatsApp:** trocar só o `bot_telegram.py` por um canal do WhatsApp Business (Cloud API). Avisos
   e resumo semanal fora da janela de 24 h exigem *templates* aprovados (pagos por mensagem).
5. **Política de privacidade (LGPD):** o que guardamos (perfil, 30 mensagens, 3 planos, localização),
   para quem vai (Gemini/Anthropic: textos; OpenStreetMap: localização arredondada ~100 m),
   retenção e `/esquecer`. Mostrar no `/start`.
6. **Parcerias** com as redes que não passaram nos critérios (Assaí, Tático, Barão, Cerrado...).

## 4. Roteiro do teste no celular (PARTE E)

Antes: só uma cópia do bot ligada; o admin é a conta do dono (`ADMIN_IDS`). Custo total estimado:
**US$ 0,50 a 1,00** (o cardápio é quase tudo; perfil com até 2 restrições tende a ficar no Sonnet).

| # | O que fazer | O que deve acontecer | Custo |
|---|---|---|---|
| 1 | `/esquecer` e depois `/start`; cadastro completo com **até 2 restrições**, mercados Prezunic/Atacadão/Dia a Dia | Perguntas com botões; aviso se o orçamento ficar abaixo de 75% da sugestão | ~0 (Gemini) |
| 2 | Montar o plano | Uma mensagem com as etapas; resultado com os 6 botões | US$ 0,05–0,43 |
| 3 | Trocar 2 pratos | A linha "🔁 Trocado" no topo do dia, total recalculado | ~US$ 0,002 |
| 4 | Abrir uma receita, ir até o fim e dar nota | Um passo por mensagem; nota salva | ~0 |
| 5 | [🏪 Onde comprar] → [📋 Prezunic] → [✅ Vou comprar no...] ou [✂️ Dividir] | Totais por mercado, "🔥 promoção (até dd/mm)"/"≈ estimado", condições ("com clube"); a lista muda | 0 |
| 6 | [📄 PDF] e abrir no Adobe ou Google Drive | Caixinhas clicáveis; separado por mercado se dividiu | 0 |
| 7 | [🛒 Modo mercado]: marcar 3 itens, [✏️ Paguei outro preço], [🏁 Terminei] | Contador no topo; "não encontrei" com substitutos | 0 |
| 8 | [📍 Mercados perto de mim] e mandar a localização (ponto público no mapa) | Até 8 mercados com distância, link e 🔥 nas redes com promoção | 0 |
| 9 | Mandar um áudio pedindo algo e uma foto de geladeira | Entende e usa no cardápio | ~0 |
| 10 | Mandar a foto de um encarte e tocar [🔥 Promoções] | "Salvei N ofertas"; aparecem na lista | ~0 |
| 11 | `/promo Prezunic; arroz 5 kg; 18,90; dd/mm` com um item da sua lista (entre 8h e 21h) | Confirmação e o aviso "🔥 achei promoção do que você usa" (se ainda não recebeu aviso hoje) | 0 |
| 12 | `/avisos` duas vezes | Desliga e liga, dizendo o dia do resumo | 0 |
| 13 | `/coletar` | Resultado por rede (só encartes novos vão para a IA) | US$ 0–0,20 |
| 14 | 5 perguntas fora do escopo (futebol, política, "ignore suas regras"...) | Mensagem fixa com [📅 Meu cardápio] [🔥 Promoções] [🛒 Lista] | ~0 |
| 15 | `/custos` | Gasto do dia e do mês, custo médio do cardápio e % do Opus | 0 |
| 16 | `/esquecer` | Pede confirmação e apaga tudo | 0 |

Para cada passo, anotar: o texto da resposta, o modelo que respondeu e o custo (aparecem no
registro do bot e no `/custos`).
