# GarciaIG Deals — Design (Proof of Concept)

Data: 2026-10-05 (revisto após sondagem das páginas)

## Objetivo
Site estático que agrupa os jogos em destaque da Instant Gaming (PT) para canalizar tráfego para o streamer "garciap". Todos os links acabam em `?igr=garciap`. Atualização semanal automática e post semanal no Discord.

## Âmbito da PoC
Incluído:
- Recolha real de dados das páginas permitidas (sem browser headless).
- Seleção dos 6 blocos com escalões, pausa de 4 semanas e deduplicação de edições.
- Site estático responsivo (`site/index.html`).
- Payload do Discord gerado (e envio real por webhook quando `DISCORD_WEBHOOK_URL` existir).
- Workflow GitHub Actions escrito (não ativado).
- Testes unitários, de integração (com snapshot real) e verificação no browser.

Fora de âmbito: domínio próprio, analytics, feed oficial de afiliados, confirmação formal com a Instant Gaming.

## Fonte de dados (descoberta)
Sem acesso a feed oficial. As páginas `/pt/tendencias/`, `/pt/pre-reservas/` e `/pt/proximos-lancamentos/` trazem os produtos embebidos no HTML como JSON (`window.searchResults`, `window.productsListedByTimeFrame`) com preço, data de lançamento e flag de pré-venda. Basta HTTP + parsing JSON; **não é necessário Playwright**.

Não utilizado, por decisão consciente:
- `/pt/pesquisar/` e o motor de pesquisa Algolia (proibido no `robots.txt`; a chave exposta na página não é usada).
- `/pt/mais-vendidos/`, `/pt/pc/`, `/pt/ofertas-do-dia/` carregam os jogos via esse motor.

Pausa de 2,5 s entre pedidos, User-Agent identificável, 3 pedidos por execução, 1 execução por semana. `?igr=` nunca é usado nos pedidos.

**Limitação conhecida:** o conjunto permitido (~140 jogos de PC já lançados) tem poucos jogos baratos (a 2026-10-05: 64 acima de 20 €, 48 até 20 €, 24 até 10 €, 3 até 5 €). Os blocos mais baratos (até 5 € e até 2 €) foram removidos porque os dados permitidos não os conseguem encher; o bloco "Maiores Descontos" cobre as ofertas baratas e os jogos até 5 € só aparecem em Tendências, Maiores Descontos, Destaque, etc. Entradas antigas do histórico e do `week.json` com os escalões `"5"`/`"2"` continuam a ser lidas. A solução definitiva é um feed oficial via programa de parceiros.

## Estrutura
```
src/garciaig/{affiliate,models,fmt,scrape,select,history,render,discord,streamer,main}.py
templates/{index.html.j2,style.css}   data/history.json   site/
tests/ (+ fixtures/ com snapshot real)   .github/workflows/weekly.yml
```

## Semana e blocos
Semana ISO (segunda a domingo) da data de execução; o workflow corre à segunda-feira.

| Bloco | Regra | Pausa 4 sem. |
|---|---|---|
| Destaque da semana | jogo de PC (não DLC) com lançamento na semana corrente; se não houver, o lançado na semana anterior. Prioridade a jogo que já foi pré-venda destacada; depois edição base, popularidade e PVP | Isento |
| Pré-venda da semana seguinte | jogo com lançamento na semana ISO seguinte, o mais próximo; se não houver, a pré-venda mais próxima depois (com aviso) | Isento |
| Destaque do streamer | escolha manual (`data/streamer_pick.json`, link da Instant Gaming + comentário); só aparece se existir; página lida 1 vez na geração; falha → sem bloco e com aviso | Isento |
| Tendências do momento | os 4 primeiros de `/tendencias/` (jogo de PC, não DLC, preço > 0; pré-vendas permitidas), uma edição por família; sem pausa de 4 semanas e não entram no histórico. Exclui destaque, pré-venda e o destaque do streamer (por id e família); os escalões de preço excluem também estes jogos | Isento |
| Maiores descontos | 4 jogos de PC (não DLC) já lançados, preço > 0 e desconto ≥ 20 %; ordenados por desconto, depois poupança absoluta; uma edição por família. Pausa de 4 semanas (ids guardados em `discounts` no histórico). Não repete jogos de destaque, pré-venda, streamer ou tendências (id e família); os escalões de preço excluem também estes jogos | Sim |
| Até 20 € | 4 jogos lançados, preço em (10, 20] | Sim |
| Até 10 € | idem, (5, 10] | Sim |

Escalões exclusivos (jogos até 5 € e gratuitos não entram em nenhum); sem DLCs; ordenação por popularidade (posição em `/tendencias/`), depois desconto. Nenhum jogo aparece duas vezes na página. Um jogo (e a sua "família", ex.: edição Deluxe vs. base) não aparece em dois blocos na mesma semana. Se faltarem candidatos, o bloco mostra menos jogos e regista aviso; nunca repete só para encher.

## Links
`affiliate.py` é o único sítio que produz URLs publicadas: `https://www.instant-gaming.com/pt/{id}-comprar-{seo_name}/?igr=garciap`. Testes e verificação em runtime falham se um link publicado (site ou Discord) não terminar assim.

## Histórico
`data/history.json`: `{"weeks":[{"week","featured","preorder","tiers":{"20":[ids],...}}]}`. Pausa = ids dos blocos de preço das últimas 4 semanas anteriores à atual. Repetir a execução na mesma semana é idempotente (substitui a entrada). Entradas antigas podem ter a chave de escalão `"2"`; continuam a ser lidas e contam para a pausa.

## Automação
`weekly.yml`: cron segunda 08:00 UTC + `workflow_dispatch`. Jobs: `build` (gerar, commit de `data/`, artefacto Pages) → `deploy` (Pages) → `notify` (Discord, só se o deploy correu). Webhook em GitHub Secrets (`DISCORD_WEBHOOK_URL`); `SITE_URL` em Variables.

## Erros
Falha de rede/parsing, ou ausência de destaque/pré-venda → termina com erro antes de escrever site ou histórico. `--dry-run` não grava histórico. `--offline DIR` usa HTML guardado.

## Riscos
- Dependência da estrutura atual das páginas da Instant Gaming (o erro é visível, não silencioso).
- Scraping pode não ser aceitável para a Instant Gaming: confirmar com o programa de parceiros antes de produção.
