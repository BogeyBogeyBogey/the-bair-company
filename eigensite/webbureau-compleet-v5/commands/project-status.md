---
description: Toon de voortgang van het huidige websiteproject
allowed-tools:
  - Read
  - Glob
  - Grep
  - TodoWrite
argument-hint: [projectnaam]
---

Toon de voortgang van het websiteproject "$ARGUMENTS".

## Stappen

1. **Zoek de projectmap** — als er een argument is opgegeven, zoek die map. Als er geen argument is, zoek naar mappen met een `site-research.md` bestand.

2. **Lees de bestanden** in de projectmap om te bepalen welke fases afgerond zijn.

3. **Toon een visueel overzicht** van alle fases:

```
📋 PROJECT STATUS: {projectnaam}
═══════════════════════════════════

✅ Fase 1:  URL Research            — Afgerond
✅ Fase 2:  Designprofiel           — Afgerond
🔄 Fase 3:  Landingspagina          — Bezig
⏳ Fase 4:  Goedkeuring             — Wacht op feedback
⏳ Fase 5:  Volledige site          — Nog niet gestart
⏳ Fase 6:  Oplevering              — Nog niet gestart

Voortgang: ████████░░░░░░░░ 50%
```

4. **Toon per afgeronde fase** een korte samenvatting van wat er opgeleverd is.

5. **Vraag de gebruiker** of hij wil doorgaan met de eerstvolgende onafgeronde fase.

## Fase-detectie

| Fase | Klaar als... |
|------|-------------|
| 1. URL Research | `site-research.md` bestaat |
| 2. Designprofiel | Kleurenpalet en fonts bepaald in research |
| 3. Landingspagina | `index.html` bestaat |
| 4. Goedkeuring | Gebruiker heeft goedgekeurd |
| 5. Volledige site | Meerdere HTML-bestanden bestaan |
| 6. Oplevering | Alle bestanden in output-directory |

## Taal

Communiceer in het Nederlands.
