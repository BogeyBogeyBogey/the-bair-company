---
name: content-copy
description: >
  Automatische contentcreatie op basis van bestaande website-inhoud en site-research.
  Triggers: "teksten schrijven", "copy", "websiteteksten", "content maken",
  "vertalen", "meertalig", "SEO teksten", "homepage tekst".
version: 2.0.0
---

# Content & Copy — Automatisch

Alle webteksten worden AUTOMATISCH gegenereerd op basis van de site-research. De bestaande content van de klant vormt de basis — verbeterd, herstructureerd en geoptimaliseerd.

## Principes

- **Geen Lorem ipsum** — altijd echte, overtuigende content
- **Toon afleiden uit bestaande site** — formeel/informeel, je/u, technisch/toegankelijk
- **SEO-bewust schrijven** — natuurlijke zoekwoorden verwerken
- **Sector-passende taal** — advocaat ≠ bakker ≠ tech-startup

## Workflow

### Stap 1: Bestaande content hergebruiken
Uit `site-research.md`:
- Extraheer alle bestaande teksten per pagina
- Identificeer kernboodschappen en unique selling points
- Noteer de taal en toon van de originele site

### Stap 2: Content verbeteren
Per pagina:
- Herschrijf teksten in de juiste tone of voice
- Voeg overtuigende headlines en subheadlines toe
- Schrijf duidelijke calls-to-action
- Verwerk sector-specifieke zoekwoorden

### Stap 3: Aanvullende content genereren
Waar nodig:
- **Meta descriptions** (max 155 tekens)
- **Alt-teksten** voor afbeeldingen
- **CTA-teksten** per pagina
- **Microcopy**: formulierlabels, foutmeldingen, bevestigingen

### Stap 4: Meertalig (indien van toepassing)
Als de originele site meertalig is, gebruik dan de **bulk-translate skill** voor professionele vertalingen:

1. **Detecteer de talen** van de originele site (uit site-research.md)
2. **Roep de bulk-translate skill aan** — deze vertaalt alle HTML-bestanden met behoud van structuur en opmaak
3. Standaard taalsets voor Belgische klanten:
   - "Belgisch": NL, FR, DE
   - "Belgisch + EN": NL, FR, DE, EN (meest gangbaar)
4. De bulk-translate skill zorgt automatisch voor:
   - Natuurlijke vertalingen (geen Google Translate-achtige output)
   - Consistente terminologie door het hele document
   - Behoud van HTML-structuur, CSS-classes en technische attributen
   - SEO-bewuste vertalingen (zoekwoorden per taal, niet letterlijk vertaald)
5. **Bestandsnaamconventie**: `index.html`, `index-fr.html`, `index-en.html`
6. **Vertaal ALLES**: body text, microcopy, meta tags, alt-teksten, Open Graph, structured data
7. **Na vertaling**: laat een native speaker proeflezen voor productie-gebruik
8. **Taalnavigatie**: voeg een taalschakelaar toe in de header (vlaggen of taalcodes)

> **Referentie**: Lees de `bulk-translate` SKILL.md voor de volledige workflow en het Python-script voor JSON-gebaseerde vertalingen.

## Toon per sector (referentie)

| Sector | Aanspreking | Stijl | Voorbeeld |
|--------|-------------|-------|-----------|
| Advocaten/Notarissen | U | Formeel, gezaghebbend | "Wij begeleiden u bij elke juridische stap" |
| Zorgverleners | Je | Warm, empathisch | "Samen werken we aan jouw herstel" |
| Tech/Startups | Je | Direct, energiek | "Bouw sneller. Schaal slimmer." |
| Ambachtslieden | Je/U | Authentiek, trots | "Al drie generaties vakmanschap" |
| Retail/Horeca | Je | Uitnodigend, enthousiast | "Ontdek onze nieuwe collectie" |

## Geen apart document

Content wordt DIRECT in de HTML-bestanden geschreven via de development skill. Er is geen apart content-document nodig.
