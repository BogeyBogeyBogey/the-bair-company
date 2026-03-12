# Webbureau Compleet v5.0

Geef een URL, krijg een volledige premium website. Automatisch.

## Wat is nieuw in v5?

- **Automatische design-review**: Claude beoordeelt het design zelf vóór de klant het ziet — visuele hiërarchie, usability, consistentie en fotokwaliteit worden automatisch gecontroleerd en gefixt (via `design:design-critique`)
- **Live kleurenkiezer**: klanten kunnen via een floating toggle door 30+ professionele kleurenpaletten bladeren en live zien hoe de site eruitziet (via `color-scheme-dev-toggle`)
- **Professionele meertaligheid**: automatische vertalingen NL/FR/DE/EN met behoud van HTML-structuur, SEO per taal, en taalnavigatie in de header (via `bulk-translate`)
- **WCAG 2.1 AA accessibility-audit**: wettelijk verplichte toegankelijkheidscheck in de launch-QA — kleurcontrast, toetsenbord, screenreaders, focus-indicators (via `design:accessibility-review`)
- **404-pagina**: automatisch meegebouwd, on-brand

### Eerder in v4:
- Videocontent, premium animaties, interactieve elementen
- Geen generieke opmaak (emoji's, Font Awesome, templates verboden)
- Font-diversiteit per sector, animatieprofielen, 20+ kwaliteitschecks

## Hoe werkt het?

1. **Geef een URL** → `/nieuw-project https://voorbeeld.be`
2. **Claude onderzoekt de bestaande site** — scrapet alle pagina's, analyseert kleuren, fonts, content en structuur
3. **Claude zoekt foto's EN video's** — Unsplash, Pexels Video, Coverr.co, Pixabay Video
4. **Claude haalt inspiratie** — ThemeForest, Awwwards, concurrenten
5. **Claude bouwt een premium landingspagina** — met video, animaties, interactieve elementen
6. **Claude reviewt zichzelf** — automatische design-critique op usability, hiërarchie en consistentie
7. **Jij keurt goed** (of geeft feedback) — met live kleurenkiezer om paletten te vergelijken
8. **Claude bouwt de volledige site** — alle subpagina's, contactformulier, privacy policy, 404-pagina, SEO, alles
9. **Meertalig** (als van toepassing) — automatische vertalingen via bulk-translate
10. **Accessibility-audit + deployment** — WCAG 2.1 AA check, dan direct naar Vercel

## Commands

| Command | Wat het doet |
|---------|-------------|
| `/nieuw-project [url]` | Start een nieuw project vanuit een bestaande website-URL |
| `/project-status` | Bekijk de voortgang van het huidige project |
| `/lanceer` | Finale QA-check en website live zetten via Vercel |

## Wat wordt automatisch gedaan?

- Site-research en analyse van de bestaande website
- **Videocontent zoeken** (Pexels, Coverr, Pixabay) — minimaal 2-4 video's per project
- **Unsplash-foto's** — minimaal 10-15 per project
- Kleurenpalet en typografie afleiden en upgraden (met RGB-varianten voor glassmorphism)
- Professionele designkeuze op basis van de sector (CLAUDE.md repertoire)
- **Unieke homepage-compositie** met 7-10 secties (video, interactief, marquee, mega-typografie)
- Alle webteksten herschrijven en verbeteren
- SEO-optimalisatie (meta tags, structured data, sitemap)
- Contactformulier met floating labels (Formspree)
- Cookie banner en privacy policy (GDPR)
- Lokale SEO (als er een fysiek adres is)
- Responsive design (mobile-first) met prefers-reduced-motion
- **Premium animaties**: scroll-reveals, text-reveal, image-reveal, counters, marquee, magnetic buttons
- **Automatische design-review** vóór oplevering aan de klant
- **WCAG 2.1 AA accessibility-audit** in de launch-checklist
- **Live kleurenkiezer** in de goedkeuringsfase
- **404-pagina** on-brand meegebouwd

## Premium designkenmerken

- Video hero of video statement-band met mobile fallback
- Glassmorphism/blur-effecten
- Noise/grain textuur overlays
- Mega-typografie (80px+ koppen)
- Full-bleed foto-secties met gradient overlays
- Diagonale/overlappende elementen (clip-path)
- Animated counters voor bedrijfsstatistieken
- Scroll progress indicator
- Magnetic buttons en ripple-effecten
- Dramatische donker/licht contrast-wisselingen

## Technisch

- Statische HTML/CSS/JS per pagina (geen framework nodig)
- CSS custom properties met RGB-varianten voor glassmorphism
- Animation tokens (easing, durations) als CSS variables
- Google Fonts voor karaktervolle typografie
- Formspree voor formulieren
- Vercel voor deployment

## Automatisch (als van toepassing)

- **Meertalig** — als de originele site meertalig is, wordt dit automatisch vertaald via de `bulk-translate` skill (NL/FR/DE/EN) met taalnavigatie in de header

## Optioneel (na oplevering)

- **TinaCMS** — als de klant zelf content wil aanpassen

## Vereisten

- Claude in Chrome extensie (voor het scrapen van de bestaande site)
- Vercel account (voor deployment, optioneel)
