# Webbureau Compleet Plugin — Volledig Overzicht (v8.0)

## Wat is dit?

Een Claude Cowork-plugin die functioneert als een **volledig geautomatiseerd webdesignbureau**. Je geeft een bestaande website-URL en krijgt een complete, premium, productie-klare website terug — zonder één regel code zelf te schrijven.

De plugin draait in **Claude Desktop (Cowork mode)** en maakt gebruik van Claude's tools: browser-automatisering (Chrome), bestandsbeheer, Vercel deployment, Figma-integratie en web search.

---

## Kernfilosofie

- **Foto-gedreven**: minimaal 10-15 echte foto's per site (eigen + Unsplash), geen stock-iconen of emoji's als vervanging
- **Video-verrijkt**: elke site heeft minstens 1 video-element (hero of statement-band) met mobile fallback
- **Unieke composities**: geen herhalend template-patroon — elke site krijgt een eigen layout-compositie
- **Awwwards-niveau design**: glassmorphism, mega-typografie, parallax, 3D tilt cards, magnetic buttons, animated counters
- **Alles automatisch**: van research tot deployment, inclusief SEO, GDPR, accessibility, security en performance-optimalisatie

---

## De 3 Commands (workflows)

### 1. `/nieuw-project [url]` — Hoofdworkflow

Start een volledig websiteproject in **7 fasen**:

**Fase 0: Discovery & Strategie** *(nieuw in v8)*
- Stelt 5 strategische vragen aan de klant via gestructureerde multiple-choice (AskUserQuestion):
  1. Hoofddoel van de website (leadgeneratie, branding, informatief, e-commerce, portfolio)
  2. Primaire doelgroep (leeftijd, regio, technisch niveau)
  3. Unieke verkooppunten (USP's)
  4. Succesindicatoren / KPI's
  5. Scope en must-have pagina's
- Legt antwoorden vast in `site-research.md` als strategisch kader vóór de research start

**Fase 1: URL Research + Visuele Inspiratie + Videocontent**
- Scrapet de bestaande website via Chrome (elke pagina, alle teksten, logo, beelden)
- Beoordeelt eigen beeldmateriaal op kwaliteit en herbruikbaarheid
- Zoekt aanvullende Unsplash-foto's (tot 10-15 totaal)
- Zoekt video's op Pexels Video, Coverr.co, Pixabay Video (2-4 stuks)
- Haalt template-inspiratie van ThemeForest en Awwwards
- Analyseert lokale concurrenten
- Slaat alles op als `site-research.md`

**Fase 1b: Research-goedkeuring** *(nieuw in v8)*
- Presenteert de klant een samenvatting van de research: gevonden beelden, kleurenpalet, fontkeuze, sectorclassificatie, voorgestelde paginastructuur
- Vraagt expliciete goedkeuring via AskUserQuestion vóór het bouwen begint
- Voorkomt dat er gebouwd wordt op basis van verkeerde aannames

**Fase 2: Designprofiel + Unieke Compositie**
- Bepaalt kleurenpalet (afgeleid van bestaand merk, verbeterd, met RGB-varianten voor glassmorphism)
- Kiest typografie (karaktervolle Google Fonts — Inter, Roboto, Arial zijn verboden)
- Optioneel: variable font self-hosting voor betere performance en privacy *(nieuw in v8)*
- Bepaalt tone of voice en animatie-profiel (subtiel/balanced/dynamic/maximal)
- Ontwerpt een unieke homepage-compositie met 7-10 secties

**Fase 3: Landingspagina bouwen**
- Bouwt de homepage met alle premium designelementen
- Voert automatische design-review uit (via `design:design-critique`) vóór de klant het ziet
- Fixt problemen automatisch

**Fase 4: Gestructureerde Feedback Loop**
- Deployt een Vercel preview zodat de klant op eigen telefoon/tablet kan testen
- Biedt een live kleurenkiezer (30+ professionele paletten)
- Doorloopt 6-stappen gestructureerde feedback via multiple-choice vragen:
  1. Kleuren & Branding
  2. Typografie & Tekst
  3. Layout & Structuur
  4. Foto's & Video
  5. Algemeen & Afronden
- Maximaal 2 feedbackrondes

**Fase 5: Volledige site bouwen**
- Alle subpagina's in dezelfde premium stijl
- 404-pagina (on-brand met navigatie)
- Privacy policy + cookie policy
- Toegankelijkheidsverklaring (wettelijk verplicht sinds EAA juni 2025) *(nieuw in v8)*
- Sitemap.xml + robots.txt
- Cookie consent manager met categorieën
- Google Analytics 4 met consent mode
- Structured data (Organization, WebSite, BreadcrumbList, Service, FAQPage)
- Favicon-set + OG-images per pagina
- Beeldoptimalisatie (AVIF + WebP, srcset, lazy loading) *(AVIF nieuw in v8)*
- Security headers via Vercel `_headers` bestand (CSP, HSTS, X-Frame-Options) *(nieuw in v8)*
- Meertalig (als van toepassing)

**Fase 6: Oplevering**
- Deploy naar Vercel
- Security headers testen via securityheaders.com (doel: score A+) *(nieuw in v8)*
- Client-handoff document (PDF/DOCX met logins, handleidingen, onderhoudsinstructies)
- Lighthouse-scores als kwaliteitsbewijs

### 2. `/lanceer` — Finale QA + Deployment

16-stappen QA-checklist *(was 13 in v7)*:
1. Visuele controle (alle pagina's, responsive, broken links)
2. Accessibility-audit (WCAG 2.1 AA — kleurcontrast, toetsenbord, screenreaders, focus, ARIA)
3. Beeldoptimalisatie controle (AVIF/WebP, srcset, lazy loading, width/height, paginagrootte < 2MB)
4. Structured data validatie (JSON-LD syntax, absolute URL's)
5. Cookie consent testen (localStorage, categorieën, GA4 consent mode)
6. Favicon & OG-images controle
7. Security headers controleren (`_headers` bestand, CSP correct per project) *(nieuw in v8)*
8. Toegankelijkheidsverklaring controleren (aanwezig, gelinkt in footer) *(nieuw in v8)*
9. 404-pagina controleren
10. Fixes doorvoeren
11. Lighthouse audit (Performance ≥ 90, Accessibility ≥ 95, SEO ≥ 95, LCP < 2.5s, TTFB < 800ms)
12. Deploy naar Vercel
13. Security headers testen op live URL via securityheaders.com *(nieuw in v8)*
14. Lighthouse op live URL als kwaliteitsbewijs
15. Client-handoff document genereren
16. Oplevering met URL, document, Lighthouse-scores en security-score

### 3. `/project-status` — Voortgangsindicator

Toont visueel welke van de 7 fasen afgerond zijn met percentage-balk.

---

## Alle 20 Skills (gedetailleerd)

### Kernworkflow skills (12 stuks)

| # | Skill | Versie | Wat het doet |
|---|-------|--------|-------------|
| 1 | **client-briefing** | v4 | Scrapet de bestaande site via Chrome, inventariseert beeldmateriaal, zoekt Unsplash-foto's, video's (Pexels/Coverr/Pixabay), ThemeForest-inspiratie en concurrenten |
| 2 | **brand-identity** | v4 | Leidt kleurenpalet, typografie, tone of voice en animatie-profiel af. Ondersteunt nu ook variable font self-hosting voor betere performance/privacy *(v8)* |
| 3 | **wireframing** | v4 | Ontwerpt unieke paginastructuren met video-secties, interactieve elementen en scroll-storytelling. Garandeert dat geen twee sites dezelfde layout krijgen |
| 4 | **visual-design** | v4 | Visuele designstrategie: Unsplash-fotografie, videocontent, Envato-template-inspiratie, layout-patronen, glassmorphism, premium animaties |
| 5 | **content-copy** | v4 | Schrijft alle websiteteksten op basis van bestaande content. Ondersteunt meertaligheid (NL/FR/DE/EN) via bulk-translate |
| 6 | **development** | v5 | Bouwt de daadwerkelijke website — bevat complete code-toolkit: 10 animatie-types, video-integratie, interactieve elementen, glassmorphism, formulieren, 404-pagina template. 21-punts kwaliteitscheck |
| 7 | **client-feedback** | v1 | Gestructureerde 6-stappen feedback via multiple-choice vragen. Vercel preview integratie. Max 2 rondes |
| 8 | **forms-integrations** | — | Contactformulieren (Formspree) met floating labels + nieuwsbriefinschrijving (Brevo) |
| 9 | **legal-gdpr** | v3 | Privacy policy, cookie policy, toegankelijkheidsverklaring (EAA-verplicht) en juridische pagina's conform GDPR/AVG *(v8: toegankelijkheidsverklaring toegevoegd)* |
| 10 | **seo-optimization** | — | Meta tags, Open Graph, canonical URLs, sitemap, robots.txt per pagina |
| 11 | **geo-optimization** | — | Lokale SEO: Google Business Profile, LocalBusiness schema, regionale zoekwoorden |
| 12 | **launch-qa** | v4 | Complete QA-checklist inclusief Lighthouse audit, Core Web Vitals, security headers controle, toegankelijkheidsverklaring check, cookie consent test *(v8: security + a11y checks)* |

### Technische optimalisatie skills (7 stuks)

| # | Skill | Wat het doet |
|---|-------|-------------|
| 13 | **image-optimization** *(v2)* | AVIF + WebP-conversie (50-70% kleiner via `<picture>` progressive enhancement), responsive srcset (480w/768w/1200w/1920w), lazy loading, fetchpriority="high" op hero, width/height attributen *(v8: AVIF toegevoegd)* |
| 14 | **favicon-social** | Complete favicon-set (ico/16/32/180/192/512), site.webmanifest, OG-images per pagina (1200x630px) |
| 15 | **cookie-consent** | Professionele GDPR cookie consent met categorieën (noodzakelijk/analytics/marketing), localStorage, "Cookie-instellingen" heropen-knop, GA4 consent mode integratie |
| 16 | **analytics-setup** | Google Analytics 4 met consent mode v2, scroll-diepte tracking, formulier-submits, telefoonklik tracking |
| 17 | **structured-data** | Schema.org JSON-LD voor Organization, WebSite, BreadcrumbList, Service, FAQPage, LocalBusiness |
| 18 | **client-handoff** | Genereert professioneel PDF/DOCX handoff-document: alle logins, CMS-handleidingen, onderhoudsinstructies, contactgegevens |
| 19 | **security-headers** *(nieuw in v8)* | Genereert Vercel `_headers` bestand met CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy. CSP wordt automatisch aangepast per project (Google Fonts, GA4, Unsplash, Formspree, etc.). Verificatie via securityheaders.com (doel: score A+) |

### Optionele skill (1 stuk)

| # | Skill | Wat het doet |
|---|-------|-------------|
| 20 | **cms-setup** | TinaCMS-integratie voor klanten die zelf content willen aanpassen — visueel bewerken, schema-definitie, deployment |

---

## Geïntegreerde externe skills (via andere plugins)

De plugin maakt ook gebruik van skills uit andere geïnstalleerde plugins:

| Skill | Bron | Gebruik in workflow |
|-------|------|-------------------|
| `design:design-critique` | Design plugin | Automatische design-review vóór klant het ziet (Fase 3b) |
| `design:accessibility-review` | Design plugin | WCAG 2.1 AA audit in launch-QA |
| `color-scheme-dev-toggle` | Anthropic skills | Live kleurenkiezer tijdens goedkeuringsfase |
| `bulk-translate` | Anthropic skills | Meertalige sites (NL/FR/DE/EN) |

---

## Technische architectuur

### Output-formaat
- Statische HTML/CSS/JS per pagina (geen framework nodig)
- CSS custom properties met RGB-varianten voor glassmorphism
- Animation tokens als CSS variables
- Google Fonts of variable font self-hosting (privacy/performance voorkeur) *(v8)*
- Formspree voor formulieren
- Vercel voor hosting/deployment met security headers via `_headers` bestand *(v8)*

### Premium design-elementen (ingebouwd in development skill)
- Text-reveal animaties (karakter-voor-karakter)
- Scroll-driven animaties (IntersectionObserver)
- Parallax layers
- Magnetic buttons
- 3D card tilt
- Marquee/ticker
- Image reveal on scroll (clip-path)
- Animated gradient mesh
- Noise/grain texture overlay
- Animated counters
- Before/after slider
- Animated tabs
- Animated accordion
- Horizontal scroll gallery
- Glassmorphism + blur-effecten
- Video-achtergrond hero met mobile fallback
- Scroll progress indicator
- Premium floating-label formulier
- `prefers-reduced-motion` respect

### 4 voorgedefinieerde compositie-stijlen
1. **"The Cinematic"** — Video-hero → Counters → Horizontal scroll → Parallax → Before/after → Marquee → Glass testimonial → Dark CTA
2. **"The Interactive"** — Split hero 3D tilt → Staggered reveals → Tabbed crossfade → Floating stats → Accordion → Gallery → Gradient mesh CTA
3. **"The Storyteller"** — Minimal hero → Scroll timeline → Zigzag reveals → Video sectie → Magazine cards → Large testimonial → Marquee logos
4. **"The Premium"** — Mega-typografie foto achter letters → Noise gradient → Sticky scroll → Diagonal foto → Glass cards → Horizontal gallery → Dark counters

### Verboden elementen (Zero Tolerance)
- Emoji's, Unicode-symbolen of Font Awesome als dienst-iconen
- Gekleurde vlakken zonder foto-achtergrond
- Placeholder-afbeeldingen
- Standaard Hero→Cards→About→Services→CTA→Footer flow
- Alleen `opacity: 0 → 1` als animatie
- Inter, Roboto, Arial als fonts
- Standaard knoppen zonder animatie
- Statische pagina's zonder interactiviteit
- Lorem ipsum tekst

### Kwaliteitsdrempels *(aangescherpt in v8)*
| Metric | Minimum |
|--------|---------|
| Lighthouse Performance | ≥ 90 |
| Lighthouse Accessibility | ≥ 95 |
| Lighthouse SEO | ≥ 95 |
| LCP (Largest Contentful Paint) | < 2.5s |
| TTFB (Time to First Byte) | < 800ms *(nieuw in v8)* |
| CLS (Cumulative Layout Shift) | < 0.1 |
| INP (Interaction to Next Paint) | ≤ 200ms *(was FID/INP)* |
| Paginagrootte | < 2MB *(was < 3MB in v7)* |
| Security headers score | A+ (securityheaders.com) *(nieuw in v8)* |
| Foto's per homepage | 10-15+ |
| Animatie-types per site | 5+ |
| Interactieve elementen per site | 2+ |
| Secties per homepage | 7-10 |

---

## Projectmap structuur (output)

```
{bedrijfsnaam}/
├── site-research.md          # Volledige research + Discovery antwoorden
├── index.html                # Homepage
├── [dienst-1].html           # Dienstenpagina's
├── [dienst-2].html
├── contact.html              # Met Formspree formulier
├── privacy-policy.html       # GDPR
├── cookie-policy.html        # GDPR
├── toegankelijkheidsverklaring.html  # EAA-verplicht (nieuw in v8)
├── 404.html                  # On-brand error page
├── _headers                  # Vercel security headers (nieuw in v8)
├── sitemap.xml
├── robots.txt
├── site.webmanifest          # PWA manifest
├── favicon.ico               # Multi-size favicon
├── favicon-16x16.png
├── favicon-32x32.png
├── apple-touch-icon.png      # 180px
├── android-chrome-192x192.png
├── android-chrome-512x512.png
├── og-image.png              # Default social preview
├── og-[pagina].png           # Per-pagina social previews
└── {bedrijfsnaam}-website-handleiding.pdf  # Client handoff
```

---

## Tools & Integraties

| Tool | Waarvoor |
|------|----------|
| Chrome browser (via Claude in Chrome) | Site scraping, screenshots, Lighthouse audit |
| Vercel MCP | Preview deployments, productie deployment |
| Figma MCP | Optioneel: design context ophalen |
| WebSearch | Unsplash foto's, video's, concurrenten, inspiratie |
| WebFetch | Pagina-content ophalen |
| Formspree | Contactformulieren |
| Google Analytics 4 | Analytics met consent mode |
| Brevo | Nieuwsbrief-integratie (optioneel) |
| TinaCMS | CMS voor klant-zelfbeheer (optioneel) |
| securityheaders.com | Security headers verificatie *(nieuw in v8)* |

---

## Doelgebruiker

- Niet-technische gebruiker (geen codering nodig)
- Communicatie in het Nederlands
- Beginner-vriendelijk (geen jargon)

---

## Versioneringsgeschiedenis

| Versie | Belangrijkste toevoegingen |
|--------|---------------------------|
| v1-v3 | Basisworkflow: URL research → design → build → deploy |
| v4 | Videocontent, premium animaties, interactieve elementen, font-diversiteit, 20+ kwaliteitschecks |
| v5 | Automatische design-review, live kleurenkiezer, meertaligheid, WCAG accessibility-audit |
| v6 | Image optimization (WebP/srcset), favicon-sets, OG-images, GA4 analytics, cookie consent manager, structured data, client-handoff document |
| v7 | Lighthouse audit (auto), gestructureerde client-feedback loop, Vercel preview deployment, 404-pagina in workflow |
| v8 | **Fase 0 Discovery** (strategische vragen vóór research), **Research-goedkeuring** (klant keurt research goed vóór bouwen), **Security headers** (CSP/HSTS via Vercel `_headers`), **AVIF beeldformaat** (50-70% kleiner dan JPG), **Variable font self-hosting** (performance + privacy), **Toegankelijkheidsverklaring** (EAA-verplicht), **Aangescherpte drempels** (< 2MB, TTFB < 800ms, security A+) |

---

## Vraag aan reviewende AI

Bekijk dit overzicht kritisch:

1. **Ontbrekende features**: Wat zou een professioneel webbureau standaard leveren dat hier nog niet in zit?
2. **Workflow-gaps**: Zijn er stappen in het proces die ontbreken of beter kunnen?
3. **Technische verbeteringen**: Zijn er moderne webtechnologieën of best practices die niet worden afgedekt?
4. **Kwaliteitsborging**: Zijn de kwaliteitsdrempels realistisch en volledig?
5. **Schaalbaarheid**: Wat zou nodig zijn om dit als een echt productie-systeem te draaien voor meerdere klanten tegelijk?
