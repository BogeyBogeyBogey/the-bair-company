---
name: lanceer
description: Start de finale QA-checklist en lanceer de website
argument-hint: ""
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - WebFetch
  - WebSearch
  - mcp__6d039e59-a052-415a-b4f3-dc17d3080ab2__deploy_to_vercel
  - mcp__6d039e59-a052-415a-b4f3-dc17d3080ab2__list_projects
  - mcp__6d039e59-a052-415a-b4f3-dc17d3080ab2__get_project
  - mcp__6d039e59-a052-415a-b4f3-dc17d3080ab2__list_deployments
  - mcp__6d039e59-a052-415a-b4f3-dc17d3080ab2__get_deployment_build_logs
  - mcp__Claude_in_Chrome__computer
  - mcp__Claude_in_Chrome__navigate
  - mcp__Claude_in_Chrome__read_page
  - mcp__Claude_in_Chrome__find
---

# /lanceer — Website live zetten

## Wat dit command doet

Voert de finale kwaliteitscontrole uit en deployt de site naar Vercel.

## Stappen

1. **QA-checklist doorlopen** — Raadpleeg de `launch-qa` skill (inclusief de nieuwe accessibility-audit)
2. **Accessibility-audit** — Voer de WCAG 2.1 AA check uit via de `design:accessibility-review` skill. Fix alle kritieke issues (contrast, alt-teksten, toetsenbord, focus) VOOR deployment
3. **Eventuele fixes** — Los problemen op die uit de QA en accessibility-audit komen
4. **Deploy naar Vercel** — Via de Vercel MCP-connector
5. **Test de live site** — Open via Chrome en controleer
6. **Lever op** — Deel de URL en geef instructies aan de opdrachtgever
