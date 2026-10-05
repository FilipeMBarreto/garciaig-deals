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
2. `select`: escolhe destaque, pré-venda e 4 escalões de preço (20/10/5/2 €), com pausa de 4 semanas.
3. `render` + `discord`: geram `site/` e `data/discord_payload.json`. Todos os links passam por `affiliate.py`.
4. GitHub Actions (`weekly.yml`) corre todos os dias às 08:00 UTC durante a PoC (em produção: à segunda-feira), publica no Pages e envia o Discord.

## Ativar na produção
- Repositório GitHub com Pages (Source: GitHub Actions).
- Variable `SITE_URL` (URL público) e Secret `DISCORD_WEBHOOK_URL`.
- Uma nova execução manual na mesma semana volta a publicar no Discord: só a faças se a anterior tiver falhado.
- Recomenda-se uma primeira execução manual (`workflow_dispatch`) para confirmar que o site é acessível a partir dos runners do GitHub.

## Limitações conhecidas
- Os blocos "até 5 €" e "até 2 €" ficam incompletos: as páginas permitidas têm poucos jogos baratos. A solução é um feed oficial do programa de parceiros.
- Depende da estrutura atual das páginas; se mudar, o pipeline falha (não publica dados errados).
- Confirmar com a Instant Gaming que este uso é aceitável antes de produção.
