# Design Specs — The Bair Company Social Media Kit
Vertaald door Template Adapter op 22 maart 2026
Bron: design-briefing-social.md (v2 monochroom)

---

## CSS Design Tokens (voor alle templates)

```css
/* === THE BAIR CO. — SOCIAL MEDIA DESIGN TOKENS === */

:root {
  /* Noir modus */
  --noir-base: #0a0a0a;
  --noir-surface: #141417;
  --noir-elevated: #1e1e24;
  --noir-line: #333333;
  --noir-line-subtle: rgba(160, 153, 143, 0.3);

  /* Bone modus */
  --bone-base: #f0ede8;
  --bone-surface: #e8e4de;
  --bone-line: #d0ccc5;

  /* Tekst op noir */
  --text-primary: #f0ede8;
  --text-secondary: #a0998f;
  --text-dim: #666666;

  /* Tekst op bone */
  --text-on-bone: #0a0a0a;
  --text-on-bone-muted: #888888;

  /* Typografie */
  --font-display: 'Syne', system-ui, sans-serif;
  --font-body: 'DM Sans', -apple-system, sans-serif;
  --font-serif: 'Instrument Serif', Georgia, serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;

  /* Animatie */
  --ease: cubic-bezier(0.16, 1, 0.3, 1);
  --duration-fast: 300ms;
  --duration-normal: 600ms;
  --duration-slow: 1200ms;

  /* Shadows (alleen op noir) */
  --shadow-mockup: 0 24px 80px rgba(0, 0, 0, 0.6);
  --shadow-card: 0 8px 32px rgba(0, 0, 0, 0.4);

  /* Noise texture (inline SVG) */
  --noise: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='1'/%3E%3C/svg%3E");
  --noise-opacity: 0.025; /* 2.5% — verhoogd voor tactiel gevoel */
}

/* Google Fonts import */
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,400&family=Instrument+Serif:ital@1&family=JetBrains+Mono:wght@400&display=swap');
```

---

## TEMPLATE 1: Instagram Carousel (1080 × 1350px, 4:5)

### Gedeelde elementen op ELKE slide

```
GRID:
- Canvas: 1080 × 1350px
- Safe zone: 60px padding rondom
- Content area: 960 × 1230px
- Kolommen: 2 × 460px met 40px gutter (voor split-slides)

NOISE OVERLAY (op elke slide):
- Pseudo-element ::after
- position: absolute; inset: 0
- background: var(--noise)
- opacity: var(--noise-opacity)
- mix-blend-mode: overlay
- pointer-events: none

VIGNETTE (op noir slides):
- Radial gradient: transparent 50%, rgba(0,0,0,0.4) 100%
- Geeft cinematisch, theatraal gevoel

SLIDE NUMMER (slide 2-9):
- Positie: linksboven, x=60px y=60px
- Font: JetBrains Mono 400
- Grootte: 13px
- Tracking: 0.05em
- Kleur: var(--text-dim) (#666)
- Format: "01", "02", etc. (altijd twee cijfers)

LOGO WATERMARK (slide 1-9):
- Positie: rechtsonder, x=60px y=60px vanaf hoek
- Asset: B-monogram PNG (Baircompanylogorender.png)
- Grootte: 24px breed
- Opacity: 0.25
- Kleur: bone-white (via CSS filter: brightness(0) invert(1) op dark variant)

STRUCTUURLIJNEN:
- Dikte: altijd 1px
- Kleur op noir: #333 (prominent) of rgba(160,153,143,0.3) (subtiel)
- Kleur op bone: #d0ccc5
- Nooit decoratief — altijd structureel (scheiding, indicator, grid)
```

### Slide 1: "De Hook"

```
DOEL: Stop de scroll. Vier woorden, maximale impact.

ACHTERGROND:
  background: var(--noir-base)  /* #0a0a0a */
  + noise overlay (2.5%)
  + vignette (radial-gradient)

LAYOUT: (centered, minimaal)
  ┌──────────────────────────────────┐
  │                                  │
  │           (50% leegte)           │
  │                                  │
  │     ┌────────────────────┐       │
  │     │   HEADLINE TEXT    │       │  ← Syne 800, 96-120px
  │     │   (max 4 woorden)  │       │     bone-white, centered
  │     └────────────────────┘       │     line-height: 0.95
  │              ───                 │  ← lijn: 80px breed, 1px
  │           (30% leegte)           │     rgba(160,153,143,0.3)
  │                                  │
  │                            [B]   │  ← logo 24px, 25% opacity
  └──────────────────────────────────┘

TYPOGRAFIE:
  - Headline: font-family: var(--font-display)
              font-weight: 800
              font-size: 96px (5+ letters per woord) tot 120px (kort)
              line-height: 0.95
              letter-spacing: -0.02em
              color: var(--text-primary)
              text-align: center
              text-transform: none (geen uppercase)

  - Lijn onder headline:
              width: 80px
              height: 1px
              background: var(--noir-line-subtle)
              margin: 24px auto 0
```

### Slide 2-3: "Probleem / Context"

```
DOEL: Bouw spanning op. Identificeer het probleem.

ACHTERGROND:
  background: var(--noir-surface)  /* #141417 — subtiel lichter */
  + noise overlay

LAYOUT: (links-uitgelijnd, verticaal gecentreerd)
  ┌──────────────────────────────────┐
  │ 02                               │  ← slide-nummer
  │                                  │
  │                                  │
  │  HEADING IN                      │  ← Syne 700, 36px
  │  TWEE REGELS                     │     bone-white
  │                                  │     max-width: 720px
  │  ─────────────────               │  ← lijn: 100%, 1px, #333
  │                                  │
  │  Body tekst die het probleem     │  ← DM Sans 300, 20px
  │  beschrijft. Kort en krachtig.   │     text-secondary
  │  Maximaal 4 regels.              │     line-height: 1.6
  │                                  │     max-width: 680px
  │                                  │
  │                            [B]   │
  └──────────────────────────────────┘

TYPOGRAFIE:
  - Slide-nummer: JetBrains Mono 400, 13px, #666, linksboven
  - Heading: Syne 700, 36px, line-height 1.15, bone-white
  - Scheidingslijn: width: 100% content area, 1px, #333, margin: 20px 0
  - Body: DM Sans 300, 20px, line-height 1.6, text-secondary

ACCENT-TECHNIEK:
  - Eén sleutelwoord in de heading of body mag Syne 800 + bone-white
    krijgen terwijl de rest DM Sans 300 + text-secondary is
  - Dit creëert typografisch "highlight" effect zonder kleur
```

### Slide 4: "Screenshot/Mockup"

```
DOEL: Laat het werk zien.

ACHTERGROND:
  background: var(--noir-base)
  + noise overlay

LAYOUT: (centraal mockup)
  ┌──────────────────────────────────┐
  │ 04                               │
  │                                  │
  │    CASE STUDY                    │  ← JetBrains Mono 11px, #666
  │                                  │     tracking 0.15em, uppercase
  │  ┌────────────────────────────┐  │
  │  │ ┌──────────────────────┐   │  │  ← Browser frame:
  │  │ │ ● ● ●                │   │  │     border: 2px solid #333
  │  │ ├──────────────────────┤   │  │     border-radius: 12px
  │  │ │                      │   │  │     overflow: hidden
  │  │ │    SCREENSHOT         │   │  │
  │  │ │                      │   │  │  ← box-shadow: var(--shadow-mockup)
  │  │ │                      │   │  │
  │  │ └──────────────────────┘   │  │
  │  └────────────────────────────┘  │
  │                                  │
  │                            [B]   │
  └──────────────────────────────────┘

BROWSER FRAME:
  - Buitenkant: border: 2px solid #333, border-radius: 12px
  - Titelbalk: 32px hoog, background: #1e1e24
  - Drie dots: 8px diameter, #333, gap 6px, links uitgelijnd, padding-left 12px
  - Content area: screenshot (object-fit: cover)
  - Shadow: 0 24px 80px rgba(0,0,0,0.6)

LABEL BOVEN MOCKUP:
  - "CASE STUDY" of "LIVE PROJECT" of "BEFORE → AFTER"
  - JetBrains Mono 400, 11px, tracking 0.15em, uppercase, #666
  - Geen pill/badge — puur tekst
```

### Slide 5: "Split Layout"

```
DOEL: Tekst + visual naast elkaar.

ACHTERGROND:
  background: var(--noir-elevated)  /* #1e1e24 */
  + noise overlay

LAYOUT: (50/50 split)
  ┌────────────────┬─────────────────┐
  │ 05             │                 │
  │                │                 │
  │                │                 │
  │  HEADING       │  [VISUAL]       │
  │  tekst hier    │  screenshot     │
  │                │  of visual      │
  │  Body tekst    │                 │
  │  eronder       │                 │
  │                │                 │
  │                │                 │
  │           [B]  │                 │
  └────────────────┴─────────────────┘
                   ↑
          Verticale lijn: 1px, #333

LINKS (tekst-zone):
  - Width: 460px (helft minus gutter)
  - Heading: Syne 700, 28px, bone-white
  - Body: DM Sans 300, 18px, text-secondary, line-height 1.6
  - Verticaal gecentreerd

RECHTS (visual-zone):
  - Width: 460px
  - Screenshot met border-radius: 8px, overflow: hidden
  - Of: abstracte visual, diagram, detail-screenshot

SCHEIDING:
  - Verticale lijn: 1px, #333, full height content area
  - Met 20px padding aan beide zijden
```

### Slide 6: "Full-bleed Visual"

```
DOEL: Visuele impact, de carousel ademt.

LAYOUT:
  ┌──────────────────────────────────┐
  │ 06                               │
  │                                  │
  │                                  │
  │     [FULL BLEED VISUAL]          │  ← Screenshot of foto
  │     object-fit: cover            │     volledige canvas
  │     grayscale of desaturated     │
  │                                  │
  │  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │  ← Gradient overlay:
  │  ▓  Projectnaam               ▓  │     linear-gradient(
  │  ▓  Korte beschrijving     [B] ▓  │       transparent 50%,
  │  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │       #0a0a0a 85%
  └──────────────────────────────────┘     )

FOTO BEHANDELING:
  - filter: grayscale(100%) contrast(1.1) brightness(0.9)
  - Of: filter: saturate(0.15) contrast(1.05) — bijna zwart-wit

GRADIENT OVERLAY (onderaan):
  - linear-gradient(to bottom, transparent 50%, rgba(10,10,10,0.95) 85%)
  - Tekst zit IN de donkere zone

TEKST OP GRADIENT:
  - Projectnaam: Syne 700, 28px, bone-white
  - Beschrijving: DM Sans 300, 16px, text-secondary
  - Positie: linksonder, 60px padding
```

### Slide 7: "Grote Metric"

```
DOEL: Eén getal dat alles zegt.

ACHTERGROND:
  background: var(--noir-base)
  + noise overlay + vignette

LAYOUT: (centraal, maximale leegte)
  ┌──────────────────────────────────┐
  │ 07                               │
  │                                  │
  │                                  │
  │                                  │
  │          +45%                    │  ← JetBrains Mono 400
  │                                  │     96px, bone-white
  │       meer bezoekers             │  ← DM Sans 300, 18px
  │       in 3 maanden               │     text-secondary
  │                                  │     text-align: center
  │                                  │
  │                                  │
  │                                  │
  │                            [B]   │
  └──────────────────────────────────┘

METRIC:
  - Font: JetBrains Mono 400
  - Size: 96px
  - Color: bone-white (#f0ede8)
  - letter-spacing: -0.02em
  - Centered horizontaal en verticaal (iets boven midden)

LABEL:
  - Font: DM Sans 300, 18px
  - Color: text-secondary (#a0998f)
  - margin-top: 16px
  - text-align: center
```

### Slide 8: "Testimonial"

```
DOEL: Menselijk bewijs.

ACHTERGROND:
  background: var(--noir-surface)
  + noise overlay

LAYOUT:
  ┌──────────────────────────────────┐
  │ 08                               │
  │                                  │
  │      "                           │  ← Decoratief aanhalingsteken
  │                                  │     Syne 800, 200px, #1e1e24
  │                                  │     achtergrond-element
  │   "Dit is een quote van          │  ← Instrument Serif italic
  │    de klant die hier iets        │     28px, bone-white
  │    moois zegt over Bair."        │     line-height: 1.5
  │                                  │     max-width: 720px
  │   — Naam Achternaam              │  ← DM Sans 500, 14px
  │     Functie, Bedrijf             │     text-secondary
  │                                  │
  │                            [B]   │
  └──────────────────────────────────┘

DECORATIEF AANHALINGSTEKEN:
  - Karakter: " (open double quote, U+201C)
  - Syne 800, 200px
  - Color: #1e1e24 (net zichtbaar op #141417 achtergrond)
  - Position: absolute, top: 80px, left: 40px
  - z-index achter de tekst

QUOTE TEKST:
  - Instrument Serif italic, 28px
  - line-height: 1.5
  - bone-white
  - Voorafgegaan door " en afgesloten met "
  - Max-width: 720px, centered

AUTEUR:
  - em-dash + naam: DM Sans 500, 14px, text-secondary
  - functie + bedrijf: DM Sans 300, 14px, text-dim
  - margin-top: 24px
```

### Slide 9: "Takeaway"

```
DOEL: De kernboodschap. Eén zin die blijft hangen.

ACHTERGROND:
  background: var(--noir-base)
  + noise + sterkere vignette

LAYOUT:
  ┌──────────────────────────────────┐
  │ 09                               │
  │                                  │
  │                                  │
  │  │  De kernboodschap             │  ← Verticale lijn: 1px,
  │  │  in één of twee               │     #a0998f, 60px hoog
  │  │  zinnen.                      │     links naast tekst
  │                                  │
  │     En een warme afsluiter       │  ← Instrument Serif italic
  │     in serif.                    │     24px, text-secondary
  │                                  │
  │                                  │
  │                            [B]   │
  └──────────────────────────────────┘

HOOFDTEKST:
  - Syne 800, 48-60px, bone-white
  - line-height: 1.15
  - max-width: 760px
  - Links-uitgelijnd met blockquote-lijn ernaast

BLOCKQUOTE LIJN:
  - width: 1px, height: 60px
  - background: #a0998f
  - Positie: links van de tekst, 16px afstand
  - Verticaal gecentreerd met de heading

SERIF AFSLUITER:
  - Instrument Serif italic, 24px, text-secondary
  - margin-top: 24px
  - Zonder blockquote-lijn
```

### Slide 10: "CTA"

```
DOEL: Actie. Wie ben je, wat wil je dat ze doen.

ACHTERGROND:
  background: var(--noir-base)
  + noise overlay

LAYOUT: (centered, verticaal gestapeld)
  ┌──────────────────────────────────┐
  │                                  │
  │                                  │
  │                                  │
  │             [B]                  │  ← B-monogram, 48px
  │                                  │     bone-white, centered
  │         THE BAIR CO.             │  ← Syne 700, 16px
  │                                  │     tracking: 0.3em
  │    Merken die blijven hangen.    │  ← Instrument Serif italic
  │                                  │     20px, text-secondary
  │                                  │
  │     ┌─────────────────────┐      │  ← Ghost button:
  │     │  Neem contact op    │      │     border: 1px solid #f0ede8
  │     └─────────────────────┘      │     background: transparent
  │                                  │     DM Sans 500, 16px
  │        baircompany.be            │     padding: 14px 36px
  │                                  │     border-radius: 100px
  │                                  │
  │                                  │  ← JetBrains Mono, 13px
  └──────────────────────────────────┘     text-dim

SPACING (top to bottom, centered):
  - Logo: 48px breed/hoog
  - 40px gap
  - Bedrijfsnaam: Syne 700, 16px, tracking 0.3em, bone-white, uppercase
  - 12px gap
  - Tagline: Instrument Serif italic, 20px, text-secondary
  - 48px gap
  - Ghost button
  - 24px gap
  - URL: JetBrains Mono 400, 13px, text-dim (#666)

GHOST BUTTON:
  - border: 1px solid var(--text-primary)
  - background: transparent
  - color: var(--text-primary)
  - font: DM Sans 500, 16px
  - padding: 14px 36px
  - border-radius: 100px (pill)
  - Hover (voor interactieve versies): background: var(--text-primary), color: var(--noir-base)
```

---

## TEMPLATE 2: LinkedIn Single Image (1200 × 628px)

### Variant A: Portfolio Showcase (noir)

```
LAYOUT:
  ┌───────────────────────┬──────────────────┐
  │                       │                  │
  │                       │  HEADING         │  ← Syne 700, 24px
  │    [SCREENSHOT]       │  tekst hier      │     bone-white
  │    660 × 628          │                  │
  │    object-fit: cover  │  Beschrijving    │  ← DM Sans 300, 14px
  │    grayscale          │  tekst eronder   │     text-secondary
  │                       │                  │     line-height: 1.6
  │                       │            [B]   │  ← logo 20px, 30% opacity
  └───────────────────────┴──────────────────┘
  ← 55% = 660px →         ← 45% = 540px →
           ↑ verticale lijn 1px #333

LINKS:
  - Width: 660px (55%)
  - Screenshot: object-fit cover, full height
  - filter: grayscale(100%) contrast(1.05)

SCHEIDING:
  - Verticale lijn: 1px, #333, full height

RECHTS:
  - Width: 540px (45%)
  - Background: var(--noir-elevated) #1e1e24
  - Padding: 48px
  - Tekst verticaal gecentreerd
  - Heading: Syne 700, 24px, bone-white, line-height 1.2
  - Body: DM Sans 300, 14px, text-secondary, margin-top 12px
  - Logo: rechtsonder, 20px, 30% opacity
```

### Variant B: Thought Leadership (bone)

```
LAYOUT:
  ┌──────────────────────────────────────────┐
  │                                          │
  │   "Een krachtige uitspraak               │  ← Syne 700, 28px
  │    over design of tech                   │     #0a0a0a
  │    die blijft hangen."                   │     line-height: 1.3
  │                                          │     max-width: 800px
  │                                          │     padding-left: 64px
  │                        — Kristof Bogaerts│  ← DM Sans 400, 14px
  │                          The Bair Co. [B]│     #888
  └──────────────────────────────────────────┘

ACHTERGROND:
  - background: var(--bone-base) #f0ede8
  - + noise overlay (2.5%, mix-blend-mode: multiply op licht)

TEKST:
  - Quote: Syne 700, 28px, #0a0a0a, line-height 1.3
  - Auteur: DM Sans 400, 14px, #888, rechtsonder
  - Logo: B-monogram, 20px, #0a0a0a, naast auteursnaam
```

### Variant C: Metric/Insight (noir)

```
LAYOUT:
  ┌──────────────────────────────────────────┐
  │                                          │
  │                                          │
  │            +127%                         │  ← JetBrains Mono 400
  │        organisch verkeer                 │     64px, bone-white
  │                                          │
  │                                     [B]  │  ← DM Sans 300, 18px
  └──────────────────────────────────────────┘     text-secondary

ACHTERGROND:
  - background: var(--noir-base)
  - + noise overlay

CENTRAAL (horizontaal + verticaal):
  - Metric: JetBrains Mono 400, 64px, bone-white, centered
  - Label: DM Sans 300, 18px, text-secondary, centered, margin-top 8px
  - Logo: rechtsonder, 20px, 30% opacity
```

---

## TEMPLATE 3: Instagram Story (1080 × 1920px)

### Template A: Quick Tip

```
LAYOUT:
  ┌──────────────────────────────────┐
  │                                  │
  │   QUICK TIP                      │  ← JetBrains Mono 400
  │   ─────────────────────          │     11px, tracking 0.2em
  │                                  │     uppercase, #666
  │                                  │     lijn: full-width, 1px, #333
  │                                  │
  │                                  │
  │   De tip in grote                │  ← Syne 800, 48px
  │   bold letters                   │     bone-white
  │                                  │     line-height: 1.1
  │                                  │     max-width: 840px
  │                                  │
  │   En een korte uitleg            │  ← DM Sans 300, 18px
  │   van maximaal twee              │     text-secondary
  │   regels eronder.                │     line-height: 1.6
  │                                  │
  │                                  │
  │             ↑                    │  ← Subtiele swipe hint
  │        Meer zien                 │     DM Sans 300, 14px, #666
  │                                  │
  └──────────────────────────────────┘

ACHTERGROND:
  - var(--noir-base) + noise + vignette

PADDING:
  - 60px links/rechts
  - Label op y=180px
  - Lijn op y=220px
  - Heading start op y=520px (verticaal gecentreerd in de ruimte)
  - Body 24px onder heading
  - Swipe hint: y=1720px, centered
```

### Template B: Portfolio Tease

```
LAYOUT:
  ┌──────────────────────────────────┐
  │                                  │
  │ [B]                              │  ← logo 20px, 30% opacity
  │                                  │     linksboven
  │                                  │
  │   [FULL BLEED SCREENSHOT]        │
  │   object-fit: cover              │
  │   grayscale + contrast           │
  │                                  │
  │                                  │
  │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│  ← gradient overlay:
  │▓                                ▓│     transparent → #0a0a0a
  │▓  Projectnaam                   ▓│     Syne 700, 28px, bone-white
  │▓  Bekijk het project →          ▓│     DM Sans 300, 14px, text-secondary
  │▓                                ▓│     padding: 60px
  └──────────────────────────────────┘

GRADIENT:
  - linear-gradient(to bottom, transparent 55%, rgba(10,10,10,0.95) 80%)
  - Over de volledige story

FOTO:
  - filter: grayscale(100%) contrast(1.1) brightness(0.85)
  - object-fit: cover, volledige 1080×1920
```

### Template C: Behind the Scenes

```
LAYOUT:
  ┌──────────────────────────────────┐
  │                                  │
  │   [ECHTE SCREENSHOT]             │
  │   Code editor / Figma / Terminal │
  │   Onbewerkt, authentiek          │
  │                                  │
  │                                  │
  │                                  │
  │                                  │
  │                                  │
  │                                  │
  │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│  ← Overlay band:
  │▓                                ▓│     background: rgba(10,10,10,0.88)
  │▓  Kort commentaar over wat      ▓│     height: 200px
  │▓  je hier ziet of doet.         ▓│     positie: onderaan
  │▓                           [B]  ▓│     DM Sans 400, 16px, bone-white
  └──────────────────────────────────┘

OVERLAY BAND:
  - Position: absolute, bottom: 0
  - Width: 100%, height: 200px
  - Background: rgba(10, 10, 10, 0.88)
  - Padding: 40px 60px
  - Tekst: DM Sans 400, 16px, bone-white
  - Logo: rechtsonder in de band, 20px, 40% opacity
```

---

## TEMPLATE 4: LinkedIn Banner (1584 × 396px)

```
LAYOUT:
  ┌─────────────────────────────────────────────────────┐
  │  [B watermark]          ──────────────────────────  │  ← lijn: 1px, #333
  │  160px, 6% opacity      op 1/3 hoogte (132px)      │     full width
  │  linksmidden                                        │
  │                              THE BAIR CO.           │  ← Syne 800, 24px
  │                        Merken die blijven hangen.   │     tracking 0.25em
  │                                                     │     bone-white
  └─────────────────────────────────────────────────────┘
                                                           ← Instrument Serif
ACHTERGROND:                                                  italic, 16px
  - linear-gradient(to right, #0a0a0a, #141417)              text-secondary
  - + noise overlay 2%

WATERMARK LOGO:
  - B-monogram, 160px breed
  - opacity: 0.06
  - Positie: left 80px, verticaal gecentreerd

TEKST (rechts van midden):
  - Bedrijfsnaam: Syne 800, 24px, tracking 0.25em, bone-white, uppercase
  - Tagline: Instrument Serif italic, 16px, text-secondary
  - Gap tussen naam en tagline: 8px
  - Positie: right 120px, verticaal gecentreerd

HORIZONTALE LIJN:
  - Full width (1584px)
  - 1px, #333
  - Op y=132px (1/3 van de hoogte)
```

---

## IMPLEMENTATIE-VOLGORDE

De templates kunnen gebouwd worden als:

1. **Statische HTML/CSS** — Eén HTML-bestand per template met inline CSS. Exporteerbaar als PNG via screenshot of html2canvas.
2. **React JSX** — Eén component per template-type, met props voor content. Kan gerenderd worden als artifact.
3. **Figma** — Als de Figma MCP beschikbaar is, kunnen frames geprogrammeerd worden.

**Aanbevolen aanpak**: Bouw als HTML/CSS bestanden. Eén bestand per template-variant. De gebruiker kan ze openen in de browser en screenshotten, of we renderen ze naar PNG.

**Bestandsstructuur:**
```
social-content/
├── design-inspiratie-social.md
├── design-briefing-social.md
├── design-specs.md (dit bestand)
├── templates/
│   ├── carousel-hook.html
│   ├── carousel-context.html
│   ├── carousel-mockup.html
│   ├── carousel-split.html
│   ├── carousel-fullbleed.html
│   ├── carousel-metric.html
│   ├── carousel-testimonial.html
│   ├── carousel-takeaway.html
│   ├── carousel-cta.html
│   ├── linkedin-portfolio.html
│   ├── linkedin-thought.html
│   ├── linkedin-metric.html
│   ├── story-tip.html
│   ├── story-portfolio.html
│   ├── story-bts.html
│   └── linkedin-banner.html
```
