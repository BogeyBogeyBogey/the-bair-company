---
description: Start een nieuw websiteproject — premium, foto-gedreven, video-verrijkt, interactief design
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - AskUserQuestion
  - WebSearch
  - WebFetch
  - Agent
  - mcp__Claude_in_Chrome__computer
  - mcp__Claude_in_Chrome__navigate
  - mcp__Claude_in_Chrome__read_page
  - mcp__Claude_in_Chrome__find
  - mcp__Claude_in_Chrome__form_input
  - mcp__Claude_in_Chrome__get_page_text
  - mcp__Claude_in_Chrome__tabs_context_mcp
  - mcp__Claude_in_Chrome__tabs_create_mcp
  - mcp__Claude_in_Chrome__javascript_tool
  - mcp__Claude_in_Chrome__upload_image
  - mcp__Claude_in_Chrome__file_upload
  - mcp__Claude_in_Chrome__read_console_messages
  - mcp__Claude_in_Chrome__read_network_requests
  - mcp__Control_Chrome__open_url
  - mcp__Control_Chrome__get_current_tab
  - mcp__Control_Chrome__list_tabs
  - mcp__Control_Chrome__get_page_content
  - mcp__Control_Chrome__execute_javascript
  - mcp__e110f179-cb90-4831-9b96-b6f3e9887776__get_design_context
  - mcp__e110f179-cb90-4831-9b96-b6f3e9887776__get_screenshot
  - mcp__e110f179-cb90-4831-9b96-b6f3e9887776__get_metadata
  - mcp__Figma__get_design_context
  - mcp__Figma__get_screenshot
  - mcp__Figma__get_metadata
  - mcp__6d039e59-a052-415a-b4f3-dc17d3080ab2__deploy_to_vercel
  - mcp__6d039e59-a052-415a-b4f3-dc17d3080ab2__list_projects
  - mcp__6d039e59-a052-415a-b4f3-dc17d3080ab2__get_project
  - mcp__6d039e59-a052-415a-b4f3-dc17d3080ab2__list_deployments
  - mcp__6d039e59-a052-415a-b4f3-dc17d3080ab2__get_deployment
  - mcp__6d039e59-a052-415a-b4f3-dc17d3080ab2__get_deployment_build_logs
  - mcp__6d039e59-a052-415a-b4f3-dc17d3080ab2__check_domain_availability_and_price
  - TodoWrite
argument-hint: [website-url]
---

Start een nieuw websiteproject op basis van de URL "$ARGUMENTS".

## BELANGRIJK — Lees ALTIJD eerst deze skills

Vóór je enige code schrijft:
1. **CLAUDE.md** uit de werkmap — designregels en verboden
2. **visual-design SKILL.md** (v4) — Unsplash foto's, VIDEO's, Envato-inspiratie, layout-patronen, glassmorphism, animaties
3. **development SKILL.md** (v4) — technische standaarden, premium animaties, interactieve elementen, kwaliteitseisen
4. **wireframing SKILL.md** (v4) — unieke composities met video-secties en interactieve elementen

## Workflow — 6 Fasen

### Fase 1: URL Research + Visuele Inspiratie + Videocontent (automatisch)

Gebruik de **client-briefing skill** (v4) om:

**A) Bestaande website analyseren:**
1. Open de URL via Chrome browser tools
2. Scrape ELKE pagina: bedrijfsinfo, diensten, teksten, stijl
3. **Logo en beeldmateriaal ophalen** — inventariseer ALLE foto's op de originele site
4. Per beeld beoordelen: resolutie, kwaliteit, herbruikbaarheid
5. Zoek aanvullende info via WebSearch (reviews, social media)
6. Sla alles op als `site-research.md`

**B) Beeldmateriaal-hiërarchie (BELANGRIJK):**

| Prioriteit | Bron | Wanneer |
|------------|------|---------|
| **1. ALTIJD** | Logo van de klant | Altijd het echte logo overnemen |
| **2. BIJ VOORKEUR** | Eigen foto's van de klant | Mits scherp en professioneel (min. 800px breed) |
| **3. AANVULLEN** | Unsplash / Pexels / Pixabay | Waar eigen beelden ontbreken of niet goed genoeg zijn |

**C) Unsplash-foto's aanvullen:**
1. Zoek via WebSearch: `site:unsplash.com [sector zoektermen]`
2. Open resultaten in Chrome en kopieer directe foto-URL's
3. Vul aan tot **minimaal 10-15 foto's totaal** (eigen + stock samen)
4. Categoriseer: hero, diensten, sfeer, detail

**D) Videocontent zoeken (VERPLICHT):**
1. Zoek op Pexels Video, Coverr.co en Pixabay Video
2. Verzamel **minimaal 2-4 video's**: hero-video + statement-band
3. Noteer directe URL's en fallback-foto per video
4. Video's moeten 15-30 sec loops zijn, sfeerbepalend

**E) Template-inspiratie zoeken:**
1. Zoek via WebSearch: `themeforest [sector] template` + `awwwards [sector]`
2. Open 2-3 premium voorbeelden in Chrome en neem screenshots
3. Analyseer: layout-patronen, foto-gebruik, VIDEO-gebruik, interacties, glassmorphism
4. Noteer **5-7 designtechnieken** om toe te passen

**F) Concurrentie bekijken:**
1. Zoek lokale concurrenten
2. Neem screenshots, analyseer sterktes en zwaktes

### Fase 2: Designprofiel + Unieke Compositie (automatisch)

**A) Designprofiel bepalen (brand-identity skill v4):**
- Sector en type klant → passende designstijl uit CLAUDE.md
- Kleurenpalet → afgeleid van bestaand merk, VERBETERD, met RGB-varianten
- Typografie → karaktervolle fonts (NOOIT Inter, Roboto, Arial) — kies uit 2-3 alternatieven per sector
- Tone of voice → afgeleid van bestaande teksten
- Animatie-profiel → subtiel/balanced/dynamic/maximal op basis van sector

**B) UNIEKE homepage-compositie ontwerpen (wireframing skill v4, KRITIEK!):**

De compositie MOET bevatten:
- [ ] Minstens **7-10 secties** (niet minder!)
- [ ] Minstens **1 video-element** (hero-video OF video statement-band)
- [ ] Minstens **1 interactief element** (animated tabs, before/after slider, horizontal scroll, accordion)
- [ ] Minstens **1 marquee/ticker** band
- [ ] Minstens **1 mega-typografie** statement (80px+)
- [ ] Minstens **2 full-bleed foto-secties** met gradient overlays
- [ ] **Animated counters** met bedrijfsstatistieken
- [ ] **Variatie in licht/donker**: wissel af tussen secties
- [ ] NIET het standaard Hero→Cards→About→Services→CTA→Footer patroon
- [ ] FOTO-GEDREVEN (minstens 8 foto's op de homepage)

Documenteer de compositie vóór je begint met bouwen.

### Fase 3: Landingspagina bouwen (automatisch)

Gebruik de **development skill** (v4) om een premium homepage te bouwen:

**Verplichte kwaliteitseisen:**
- [ ] Logo van de klant overgenomen van originele site
- [ ] Eigen foto's van klant hergebruikt waar hoogwaardig genoeg
- [ ] Aangevuld met Unsplash-foto's tot totaal 10-15+, GEEN placeholders
- [ ] Video-element (hero of statement-band) met mobile fallback
- [ ] Unieke layout-compositie (geen standaard template-flow)
- [ ] Mega-typografie (80px+ koppen waar passend)
- [ ] Full-bleed foto-secties met gradient overlays
- [ ] Diagonale/overlappende elementen (clip-path, negatieve margins)
- [ ] Glassmorphism of blur-effecten waar passend
- [ ] Noise/grain textuur overlay
- [ ] Minstens 5 verschillende animatie-types (text-reveal, fade, slide, scale, counter, image-reveal, marquee)
- [ ] Magnetic buttons of ripple-effect op CTA's
- [ ] Hover-effecten op foto-kaarten (zoom + brightness)
- [ ] Animated counters voor statistieken
- [ ] Staggered reveal op lijsten en grids
- [ ] Premium formulier met floating labels (contactpagina)
- [ ] Scroll progress indicator
- [ ] prefers-reduced-motion respecteren
- [ ] Dramatische donker/licht contrast-wisselingen
- [ ] Mobile responsive (test bij 375px)
- [ ] Cookie banner + structured data
- [ ] GEEN emoji's, Font Awesome of Unicode als dienst-iconen

**Kwaliteitscontrole:**
Bekijk de site alsof je een klant bent die €5000 betaalt. Zou je tevreden zijn?
Als het antwoord "nee" is, bouw het opnieuw.

### Fase 3b: Automatische Design Review (vóór de klant het ziet)

Voordat je de homepage aan de gebruiker toont, voer een **automatische design-review** uit via de `design:design-critique` skill:

1. **Eerste indruk**: Bekijk de pagina als een klant die €5000 betaalt. Wat valt op? Is het doel direct duidelijk?
2. **Visuele hiërarchie**: Is er een logische leesrichting? Worden de juiste elementen benadrukt?
3. **Usability**: Kan de gebruiker snel vinden wat hij zoekt? Is de navigatie intuïtief?
4. **Consistentie**: Zijn kleuren, spacing en typografie consistent door de hele pagina?
5. **Fotokwaliteit**: Zijn alle foto's scherp, relevant en professioneel?

**Als de review problemen vindt**: fix ze AUTOMATISCH vóór je de homepage toont. De gebruiker hoeft niet te weten dat er een review was — hij ziet alleen het beste resultaat.

> **Referentie**: Lees de `design:design-critique` SKILL.md voor het volledige critique-framework.

### Fase 4: Goedkeuring vragen (ENIGE interactiemoment)

Toon de landingspagina aan de gebruiker:
1. Gebruik `computer://` link naar het HTML-bestand
2. Leg kort uit welke designstijl je hebt gekozen en waarom
3. **Kleurenschema-keuze aanbieden**: Voeg de **color-scheme-dev-toggle** toe aan de homepage zodat de gebruiker live door kleurenpaletten kan bladeren:
   - Lees de `color-scheme-dev-toggle` SKILL.md
   - Zorg dat de site CSS custom properties gebruikt (zou al zo moeten zijn via brand-identity)
   - Injecteer de toggle-snippet vóór `</body>`
   - De gebruiker kan nu zelf door 30+ professionele kleurenschema's bladeren
   - Zodra de gebruiker een kleurenschema kiest: lock het in als de definitieve `:root` variabelen en verwijder de toggle
4. Gebruik AskUserQuestion met opties: "Goedgekeurd — bouw de hele site", "Aanpassingen nodig", "Ik wil eerst nog kleuren testen"
5. Bij aanpassingen: pas aan en toon opnieuw
6. Bij goedkeuring: door naar Fase 5

### Fase 5: Volledige site bouwen (automatisch, na goedkeuring)

Bouw ALLE benodigde pagina's:
- Dezelfde designstijl, foto-kwaliteit en interactiviteit als de homepage
- Elke subpagina heeft zijn eigen foto's, video's en content-flow
- Gedeelde header/footer/navigatie/cookie-banner
- Per dienstenpagina: eigen Unsplash-foto's, detail-content, unieke layout
- Contactpagina: premium formulier met floating labels (Formspree), Google Maps, contactinfo
- **404-pagina**: on-brand error page met navigatie terug naar homepage
- Privacy policy + cookie policy
- Sitemap.xml + robots.txt
- SEO: meta tags, structured data, Open Graph (met Unsplash hero als og:image)
- GDPR: cookie banner op elke pagina
- **Meertalig (als van toepassing)**: gebruik de `bulk-translate` skill via de content-copy skill om alle pagina's te vertalen. Voeg een taalschakelaar toe in de header.

### Fase 6: Oplevering

- Alle bestanden in output-directory
- Links naar alle pagina's via `computer://`
- Kort overzicht van wat er gebouwd is
- Vraag of gebruiker wil deployen naar Vercel

## Projectmap structuur

```
{bedrijfsnaam}/
├── site-research.md
├── index.html
├── [dienst-1].html
├── [dienst-2].html
├── [dienst-3].html
├── contact.html
├── privacy-policy.html
├── cookie-policy.html
├── sitemap.xml
└── robots.txt
```

## Taal

Communiceer in het Nederlands. De gebruiker is een beginner — geen technisch jargon.
