---
name: launch-qa
description: >
  Automatische kwaliteitscontrole en deployment via Vercel.
  Triggers: "lanceren", "live zetten", "deploy", "QA", "quality assurance",
  "speedtest", "Lighthouse", "pre-launch checklist", "go live", "opleveren".
version: 2.0.0
---

# Launch & QA — Automatisch

Na goedkeuring van de volledige site wordt de QA-checklist automatisch doorlopen.

## QA Checklist (automatisch)

### 1. Visuele controle
- [ ] Alle pagina's laden correct
- [ ] Responsive op mobile (320px), tablet (768px), desktop (1200px+)
- [ ] Geen broken links
- [ ] Alle afbeeldingen laden
- [ ] Animaties werken correct
- [ ] Formulieren zijn functioneel

### 2. Technische controle
- [ ] HTML validatie (geen errors)
- [ ] Alle meta tags aanwezig
- [ ] Structured data correct
- [ ] Sitemap.xml aanwezig
- [ ] Robots.txt aanwezig
- [ ] Cookie banner werkt
- [ ] Privacy policy gelinkt

### 3. Performance
- [ ] Afbeeldingen geoptimaliseerd
- [ ] CSS/JS geminimaliseerd
- [ ] Geen ongebruikte libraries
- [ ] Lazy loading op afbeeldingen

### 4. SEO check
- [ ] Unieke title per pagina
- [ ] Meta descriptions aanwezig
- [ ] H1 hiërarchie correct
- [ ] Alt-teksten op afbeeldingen
- [ ] Interne links werken

### 5. Toegankelijkheid (WCAG 2.1 AA) — via `design:accessibility-review` skill

Voer een **automatische accessibility-audit** uit op basis van de `design:accessibility-review` skill. Dit is wettelijk verplicht in de EU (European Accessibility Act, juni 2025).

**Verplichte checks:**
- [ ] **Kleurcontrast**: ratio ≥ 4.5:1 voor normale tekst, ≥ 3:1 voor grote tekst (18px+)
- [ ] **Alt-teksten**: alle betekenisvolle afbeeldingen hebben beschrijvende alt-tekst
- [ ] **Toetsenbordnavigatie**: alle interactieve elementen bereikbaar via Tab, Enter, Escape
- [ ] **Focus-indicator**: zichtbare focus-ring op alle klikbare elementen
- [ ] **Formulierlabels**: elk invoerveld heeft een gekoppeld `<label>` element
- [ ] **Semantische HTML**: correcte heading-hiërarchie (h1→h2→h3), landmarks (`<nav>`, `<main>`, `<footer>`)
- [ ] **Touch targets**: knoppen en links minimaal 44x44px op mobile
- [ ] **prefers-reduced-motion**: animaties respecteren deze instelling (reeds verplicht in development skill)
- [ ] **ARIA-landmarks**: `role` attributen waar nodig voor screenreaders
- [ ] **Zoom tot 200%**: layout mag niet breken bij 200% zoom in de browser

**Hoe te testen:**
1. Bekijk de HTML-code en controleer bovenstaande punten
2. Test toetsenbordnavigatie via Chrome: Tab door de hele pagina
3. Controleer kleurcontrast met WebSearch naar `webaim contrast checker` en test de primaire kleuren
4. Rapporteer gevonden issues en fix ze VOOR deployment

> **Referentie**: Lees de `design:accessibility-review` SKILL.md voor de volledige WCAG 2.1 AA checklist.

## Deployment

### Via Vercel (aanbevolen)
Gebruik de Vercel MCP-connector:
1. Deploy de site naar Vercel
2. Controleer de build logs
3. Test de live URL
4. Deel de URL met de opdrachtgever

### Handmatig
Als Vercel niet beschikbaar:
- Lever alle bestanden op als ZIP in de outputfolder
- Inclusief instructies voor de klant om te uploaden naar hun hosting

## Oplevering

Na succesvolle deployment:
1. Deel de live URL
2. Geef een overzicht van alle pagina's
3. Vermeld wat de klant nog moet doen:
   - Formspree account koppelen (als formulieren aanwezig)
   - Eigen foto's uploaden (waar placeholders staan)
   - Google Analytics instellen (optioneel)
   - Google Business profiel updaten (optioneel)
