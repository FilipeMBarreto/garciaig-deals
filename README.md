# GarciaIG Deals (prova de conceito)

Site semanal com jogos da Instant Gaming (PT) em destaque, todos com `?igr=garciap`, mais um post automático no Discord.

## Usar localmente
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                  # testes
python -m garciaig.main --dry-run       # recolhe dados reais e gera site/index.html (sem gravar histórico; `data/week.json` e `data/discord_payload.json` são sempre reescritos)
python -m garciaig.main --offline tests/fixtures --today 2026-10-05 --dry-run   # com o snapshot guardado
python -m http.server 8765 --directory site
```

## Como funciona
1. `scrape`: lê `/tendencias/`, `/pre-reservas/` e `/proximos-lancamentos/` (JSON embebido nas páginas; 3 pedidos, 2,5 s de pausa).
2. `select`: escolhe o destaque, "Próximos Lançamentos" (4 pré-vendas por lançar, por relevância: famílias em `/tendencias/` primeiro, depois PVP; janela de 30 dias, completada com as mais próximas; sem pausa de 4 semanas), "Tendências" (os 4 primeiros de `/tendencias/`, sem pausa e sem repetir nada da página), "Maiores Descontos" (os 4 jogos já lançados com maior desconto, mínimo 20 %, com pausa de 4 semanas e sem repetir nada da página; mostra quanto poupas) e 2 escalões de preço (20/10 €, até 4 jogos cada; jogos até 5 € não têm bloco próprio), com pausa de 4 semanas.
3. `streamer`: se existir `data/streamer_pick.json`, acrescenta o bloco manual "Destaque do Streamer" (ver abaixo).
4. `render` + `discord`: geram `site/` e `data/discord_payload.json`. Todos os links passam por `affiliate.py`.
5. GitHub Actions (`weekly.yml`) corre todos os dias às 08:00 UTC durante a PoC (em produção: à segunda-feira), publica no Pages e envia o Discord.

Cada cartão mostra a loja (Steam, Microsoft Store, EA App, ...) numa etiqueta sobre a capa; no Discord a loja aparece a seguir ao preço.

## Destaque do streamer (manual)
Um jogo escolhido à mão aparece num cartão grande no topo do site (sem título visível), com a etiqueta "Escolha do streamer" e o comentário em citação; o destaque da semana segue-se, com a etiqueta "Destaque da semana" e como primeiro embed no Discord. Sem escolha, a secção não existe.

**Pelo GitHub:** Actions → "Atualização semanal" → *Run workflow* → preencher o link do jogo na Instant Gaming (`https://www.instant-gaming.com/pt/NÚMERO-comprar-nome/`) e, se quiser, o comentário (até 280 caracteres). Para tirar o destaque, marcar "Remover o destaque do streamer".
- Só quem tem permissão de escrita no repositório pode executar o workflow; o controlo de acesso é essa permissão do GitHub. Um URL "secreto" não protegeria nada num repositório público.
- Esta execução **só republica o site**: não envia nada para o Discord e não volta a sortear os restantes blocos (usa a semana já guardada em `data/week.json`; se ainda não existir para esta semana, faz uma execução completa, também sem Discord).
- A escolha fica guardada em `data/streamer_pick.json` (é gravada no repositório) e mantém-se nas execuções seguintes até ser alterada ou removida.
- Uma execução do formulário só com comentário e sem link é ignorada (faz uma execução completa normal). A escolha não é deduplicada face aos jogos do destaque semanal nem dos blocos de preço: pode repetir-se.
- Duas execuções manuais lançadas em simultâneo podem ser fundidas pela configuração de concorrência do GitHub: lance-as uma de cada vez.
- Links soltos no comentário são removidos automaticamente.
- Se a página do jogo não puder ser lida, o site é gerado sem esta secção e a execução mostra um aviso; nunca falha por isso.

**Localmente:**
```bash
python -m garciaig.streamer set --url "https://www.instant-gaming.com/pt/21378-comprar-star-wars-galactic-racer-pc-steam/" --note "Joguem isto!"
python -m garciaig.streamer show
python -m garciaig.streamer clear
python -m garciaig.main --republish     # só atualiza o destaque do streamer na semana guardada
```
`set` só valida o link (não faz pedidos); a página do jogo é lida uma vez ao gerar o site.

## Ativar na produção
- Repositório GitHub com Pages (Source: GitHub Actions).
- Variable `SITE_URL` (URL público) e Secret `DISCORD_WEBHOOK_URL`.
- Uma nova execução manual na mesma semana volta a publicar no Discord: só a faças se a anterior tiver falhado.
- Recomenda-se uma primeira execução manual (`workflow_dispatch`) para confirmar que o site é acessível a partir dos runners do GitHub.

## Limitações conhecidas
- Os blocos de preço mais baixos (até 5 € e até 2 €) foram removidos: as páginas permitidas têm poucos jogos baratos para os encher. "Maiores Descontos" cobre as boas ofertas baratas. A solução definitiva seria um feed oficial do programa de parceiros.
- Depende da estrutura atual das páginas; se mudar, o pipeline falha (não publica dados errados).
- Confirmar com a Instant Gaming que este uso é aceitável antes de produção.
