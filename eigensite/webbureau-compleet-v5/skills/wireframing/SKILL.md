---
name: wireframing
description: >
  Ontwerp unieke paginastructuren en sitemaps die NOOIT hetzelfde zijn.
  Nu met video-secties, interactieve elementen en scroll-storytelling.
  Triggers: "wireframe", "sitemap", "paginastructuur", "navigatie", "menu structuur",
  "layout", "pagina-indeling", "informatie-architectuur", "UX structuur",
  "welke paginas", "site structuur", "draadmodel".
version: 4.0.0
---

# Wireframing — Unieke Structuren per Project

## KERNREGEL: Geen twee sites mogen dezelfde structuur hebben

De standaard "Hero → Cards → About → Services → CTA → Footer" flow is VERBODEN. Elke site heeft een eigen verhaal, een eigen ritme, een eigen visuele journey.

## ZERO TOLERANCE

| VERBODEN | ALTERNATIEF |
|----------|-------------|
| Hero → 3 Cards → About → CTA → Footer | Unieke compositie per project |
| Diensten als 3 identieke kaartjes met iconen | Zigzag, magazine grid, sticky scroll, tabs |
| Iconen/emoji's als visuele elementen | Foto's, video, echte beelden |
| Elke sectie dezelfde breedte/padding | Varieer: full-bleed, narrow, overlapping |
| Voorspelbare top-to-bottom flow | Diagonalen, parallax, horizontaal scroll |

---

## Stap 1: Sitemap afleiden

Lees `site-research.md` en leid de sitemap af:

### Verplichte pagina's:
- Homepage (index.html)
- Contact (contact.html)
- Privacy Policy (privacy-policy.html)

### Optionele pagina's (toevoegen waar relevant):
- Per dienst een eigen pagina (als er 2+ diensten zijn)
- Over ons (als er bedrijfsinformatie/team is)
- Portfolio/Projecten (als er cases/werk is)
- Blog/Nieuws (als er updates zijn)
- FAQ

### Navigatie:
- **Hoofdmenu**: max 5-6 items
- **Footer**: alle links + legal
- **Mobile**: hamburger menu met slide-in animatie

---

## Stap 2: Homepage-compositie ontwerpen

Dit is het BELANGRIJKSTE deel. De homepage bepaalt de identiteit van de hele site.

### Stap 2a: Hero-strategie kiezen

Beantwoord: **Wat is het eerste dat een bezoeker ziet?**

| Strategie | Wanneer gebruiken | Impact |
|-----------|-------------------|--------|
| Full-bleed foto + overlay | Elk type bedrijf, altijd goed | ★★★★ |
| Video-achtergrond | Ambacht, horeca, bouw (visueel werk) | ★★★★★ |
| Mega-typografie + foto clip | Creatief, bold merken | ★★★★★ |
| Split layout (tekst/foto) | Zakelijk, consultancy | ★★★ |
| Glassmorphism card op foto | Tech, modern, SaaS | ★★★★ |
| Text-reveal animatie | Premium, luxe merken | ★★★★★ |
| Diagonal split | Dynamisch, energiek | ★★★★ |
| Mosaic multi-foto | Portfolio, meerdere diensten | ★★★★ |

### Stap 2b: Diensten-presentatie kiezen

Beantwoord: **Hoe tonen we de diensten?** (NOOIT 3 identieke kaartjes met iconen!)

| Patroon | Beschrijving |
|---------|-------------|
| **Zigzag met grote foto's** | Afwisselend foto links/rechts per dienst |
| **Magazine grid** | Onregelmatig: 1 groot + 2 klein, of 2+1 |
| **Sticky scroll** | Foto vast, tekst scrollt (of omgekeerd) |
| **Full-width banden** | Per dienst een full-bleed sectie met achtergrond-foto |
| **Horizontal scroll galerij** | Horizontaal scrollende dienst-kaarten |
| **Animated tabs** | Klikbare tabs, per tab andere foto + tekst |
| **Before/after slider** | Voor diensten met visueel verschil (renovatie, beauty) |
| **Video per dienst** | Korte video-achtergrond per dienst-sectie |

### Stap 2c: Vertrouwen opbouwen

Beantwoord: **Hoe bouwen we vertrouwen?**

| Patroon | Effect |
|---------|--------|
| Animated counters | "25+ jaar ervaring", "1500+ projecten" — cijfers die optellen |
| Marquee/ticker band | Doorlopende banner met klantennamen of certificaten |
| Grote quote + foto-achtergrond | Testimonial als hero-element |
| Klant-logo band | Logo's van bekende klanten in donkere band |
| Glassmorphism stats | Frosted glass kaarten met KPI's op een foto |
| Video-testimonial | Korte video-getuigenis (indien beschikbaar) |

### Stap 2d: Afsluiting kiezen

Beantwoord: **Hoe sluiten we af?**

| Patroon | Beschrijving |
|---------|-------------|
| Mega-typografie CTA | "Klaar voor uw project?" in 80px+ |
| Foto-achtergrond + telefoonknop | Direct contact-CTA op dramatische foto |
| Contact-info + formulier split | Twee kolommen: info links, formulier rechts |
| Dark-mode CTA-footer combo | Footer IS de CTA, donker en impactful |
| Video-achtergrond CTA | Loopende video met overlay + CTA |

### Stap 2e: Compositie documenteren

Schrijf de compositie als een reeks blokken. Elke compositie MOET bevatten:
- Minstens **7-10 secties** (niet minder!)
- Minstens **1 video-element** (hero, statement-band, of dienst)
- Minstens **1 interactief element** (tabs, slider, counter, marquee)
- Minstens **1 mega-typografie** statement
- Minstens **2 full-bleed foto-secties**
- **Variatie in licht/donker**: wissel af

**Voorbeeld compositie:**
```
HOMEPAGE COMPOSITIE:
1. [VIDEO HERO — Loopende achtergrondvideo van werkplaats, gradient overlay, mega-heading met text-reveal "Vakmanschap sinds 1998", subtitle, magnetic CTA knop]
2. [MARQUEE BAND — Doorlopende ticker: "Badkamerrenovatie • Verwarming • Sanitair • Onderhoud • Dakwerken" op donkere achtergrond]
3. [DIENSTEN — Animated tabs: 4 tabs, elke tab toont grote foto links + tekst rechts, smooth transitie]
4. [STATS — Glassmorphism kaarten op full-bleed foto: animated counters "25+ jaar", "1500+ projecten", "98% tevredenheid"]
5. [PORTFOLIO — Horizontal scroll galerij van projectfoto's met image-reveal animatie]
6. [FULL-WIDTH VIDEO — Statement-band met korte video, overlay, mega-tekst "Kwaliteit is geen toeval"]
7. [WAAROM WIJ — Magazine grid: 1 groot + 3 klein, met hover-effecten en staggered reveal]
8. [TESTIMONIAL — Grote quote op parallax foto-achtergrond, naam + locatie]
9. [CTA — Donkere band met mega-tekst + magnetic button + telefoon]
10. [FOOTER — 4 kolommen met staggered reveal, Google Maps embed, social links]
```

---

## Stap 3: Subpagina's structureren

### Dienstenpagina:
```
1. [HERO — Dienst-specifieke foto of video, titel met text-reveal, korte intro]
2. [DETAIL — Zigzag layout met grote foto's en uitgebreide tekst per aspect]
3. [SPECIFICATIES — Animated tabs of accordion met sub-diensten]
4. [BEFORE/AFTER — Slider met voor/na foto's (indien relevant)]
5. [GALLERY — Masonry grid of horizontal scroll met projectfoto's, image-reveal animatie]
6. [CTA — Foto-achtergrond met mega-tekst en contact-knop]
```

### Contactpagina:
```
1. [HERO — Mega-typografie "Neem Contact Op" met sfeer-foto achtergrond]
2. [SPLIT — Links: contactgegevens + openingsuren met iconen. Rechts: premium formulier met floating labels]
3. [MAP — Full-width Google Maps embed]
4. [EXTRA — Werkgebied of FAQ-accordion]
```

### Over ons pagina:
```
1. [HERO — Team/bedrijfsfoto full-bleed met overlay]
2. [VERHAAL — Tijdlijn of zigzag van de bedrijfsgeschiedenis met foto's]
3. [TEAM — Grid met foto's, hover-effect voor details]
4. [WAARDEN — Glassmorphism cards of magazine grid]
5. [CTA — "Word onderdeel van ons verhaal" met contact-link]
```

---

## Stap 4: Foto- en video-planning

Per pagina, lijst de benodigde media op:

```
MEDIA-LIJST HOMEPAGE:
- Hero video: [sector-relevant onderwerp] via Coverr/Pexels (15-30 sec loop)
- Hero fallback foto: breed panorama (1600x900) via Unsplash
- Dienst 1: [specifiek onderwerp] (800x600)
- Dienst 2: [specifiek onderwerp] (800x600)
- Dienst 3: [specifiek onderwerp] (800x600)
- Stats-achtergrond: [werkplaats/sfeer] (1600x900)
- Portfolio: 4-6 projectfoto's (800x600)
- Statement-band video: [sfeer/ambacht] via Pexels (10-20 sec loop)
- Testimonial-achtergrond: [textuur/sfeer] (1600x900)
- CTA: [actie/urgent] (1600x600)
```

---

## Output

De wireframe wordt als onderdeel van de automatische workflow verwerkt. De compositie wordt direct toegepast bij het bouwen van de pagina's. Geen apart wireframe-document — de compositie wordt intern vastgesteld en meteen gebouwd.
