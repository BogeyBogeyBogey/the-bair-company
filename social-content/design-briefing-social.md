# Design Briefing — The Bair Company Social Media Kit
Gegenereerd: 22 maart 2026 (v2 — monochroom update)
Gebaseerd op: 10+ designs geanalyseerd + Precision Noir filosofie + bestaande site-code + feedback Kristof

---

## 1. Visuele Identiteit

### Kleurenstrategie — PUUR MONOCHROOM

Geen kleuraccenten. Alleen zwart en bone-white. De kracht zit in compositie, typografie en contrast — niet in kleur. Dit is Precision Noir in zijn zuiverste vorm.

#### Modus A: "Noir" (Instagram primair, LinkedIn carousel, stories)
| Token | Hex | Gebruik |
|-------|-----|---------|
| noir-base | #0a0a0a | Primaire achtergrond |
| noir-surface | #141417 | Kaarten, content-blokken — subtiel contrast op donker |
| noir-elevated | #1e1e24 | Verhoogde elementen, LinkedIn-variant, variatie |
| text-primary | #f0ede8 | Headlines, primaire tekst (warm bone-white) |
| text-secondary | #a0998f | Ondertitels, bijschriften, metadata |
| text-dim | #666 | Slide-nummers, timestamps, tertiaire info |

#### Modus B: "Bone" (variatie-posts, LinkedIn thought leadership)
| Token | Hex | Gebruik |
|-------|-----|---------|
| bone-base | #f0ede8 | Achtergrond — consistent met de website |
| bone-surface | #e8e4de | Subtiel kaartcontrast |
| text-on-bone | #0a0a0a | Headlines en body |
| text-muted | #888 | Secundaire tekst |

#### Gradient-strategie
- **Noir depth**: Lineair gradient van #0a0a0a naar #141417 voor subtiele diepte — geen kleur, alleen donkerder-naar-minder-donker
- **Noise overlay**: SVG grain texture op 2-3% opacity over alle achtergronden (hoger dan de site om tactiel gevoel te versterken nu er geen kleur is)
- **Bone warmth**: Op bone-modus, extreem subtiele radiale gradient van #f0ede8 naar #e8e4de — geeft warmte zonder kleur
- **Vignette**: Op noir-slides een subtiele donkere vignette aan de randen — theatraal, cinematisch

#### Hoe compenseren we het gebrek aan kleur?
Zonder kleuraccent moet het contrast harder werken:
1. **Typografisch contrast**: Syne 800 (zwaar) naast DM Sans 300 (licht) — het gewichtsverschil IS het accent
2. **Schaduwen en diepte**: Meer gebruik van box-shadows en layering dan bij een kleur-design
3. **Wit als accent**: Op donkere slides wordt bone-white (#f0ede8) het "accent" — één wit element trekt alle aandacht
4. **Negatieve ruimte**: Meer leegte = meer impact per element. Elk woord moet zijn plek verdienen
5. **Textuur**: Noise, grain, subtiele lijnpatronen als vervanging voor kleur-decoratie

### Typografie-strategie

Typografie wordt de HELD van dit systeem nu kleur wegvalt.

| Rol | Font | Gewicht | Tracking | Formaat op social |
|-----|------|---------|----------|-------------------|
| **Display/Headlines** | Syne | 800 (ExtraBold) | -0.02em | 72-120px — GROTER dan met kleur, want typografie moet nu alles doen |
| **Body/Ondertitels** | DM Sans | 300-500 | 0 | 18-24px |
| **Statement/Serif** | Instrument Serif | 400 italic | 0 | 36-60px — de warme tegenhanger van Syne |
| **Code/Data** | JetBrains Mono | 400 | 0.05em | 14-96px (klein voor labels, groot voor metrics) |

#### Typografische technieken per slide-type
- **Hook-slide**: Syne 800 op 96-120px, maximaal 4 woorden, centered, bone-white op noir
- **Content-slide**: Syne 700 heading (36px) + DM Sans 300 body (20px) — het gewichtsverschil is het accent
- **Quote-slide**: Instrument Serif italic op 48px, centered, met em-dash — het enige "zachte" moment
- **Data-slide**: JetBrains Mono voor cijfers (72-96px, bone-white), DM Sans voor labels (16px, text-secondary)
- **CTA-slide**: Syne 700 (32px) + DM Sans (18px) + ghost button (1px border bone-white, geen fill)

---

## 2. Layout Blueprint — Instagram Carousel (1080×1350px)

### Grid-systeem
- **Canvas**: 1080 × 1350px (4:5 — maximaal Instagram-formaat)
- **Safe zone**: 60px padding aan alle kanten
- **Content grid**: 960px breed × 1230px hoog bruikbare ruimte
- **Kolommen**: 2-koloms grid (460px + 40px gutter + 460px) voor split-layouts
- **Baseline**: 8px grid voor alle spacing

### Slide-voor-slide layout

#### Slide 1: "De Hook"
- **Layout**: Centered, maximale leegte — minstens 50% van het canvas is leeg
- **Achtergrond**: Noir-base (#0a0a0a) met noise overlay
- **Headline**: Syne 800, 96-120px, bone-white (#f0ede8), maximaal 4 woorden
- **Ondersteuning**: Eén dunne horizontale lijn (1px, #a0998f op 30% opacity, 80px breed) onder de headline
- **Logo**: B-monogram, 24px, rechtsonder, 25% opacity
- **Sfeer**: Alsof je naar een filmtitel kijkt in een donkere bioscoop

#### Slide 2-3: "Het Probleem / De Context"
- **Layout**: Tekst-links-uitgelijnd, verticaal gecentreerd
- **Achtergrond**: Noir-surface (#141417)
- **Structuur**:
  - Slide-nummer in JetBrains Mono (13px, text-dim #666, linksboven): "02"
  - Heading in Syne 700 (36px, bone-white)
  - Body in DM Sans 300 (20px, text-secondary #a0998f)
  - Optioneel: dunne horizontale scheidingslijn (1px, #333)
- **Accent-techniek**: Eén sleutelwoord per slide in Syne 800 (bone-white) terwijl rest in DM Sans 300 (text-secondary) — typografisch gewicht als "highlight"

#### Slide 4-6: "De Oplossing / Content"
- **Layout**: Wisselt per slide:
  - Slide 4: Screenshot/mockup centraal, donkere browser-frame (2px border #333, border-radius 12px)
  - Slide 5: Split-layout (links tekst, rechts visual), gescheiden door verticale lijn (1px, #333)
  - Slide 6: Full-bleed visual met donkere gradient overlay onderaan
- **Achtergrond**: Mix van noir-base en noir-elevated
- **Screenshots**: In donkere mockup frame, box-shadow (0 24px 80px rgba(0,0,0,0.6))
- **Labels**: JetBrains Mono uppercase, 11px, tracking 0.15em, text-dim #666 — geen pills, geen kleur, puur tekst

#### Slide 7-8: "Het Bewijs"
- **Layout**: Data-centrisch, centered
  - Slide 7: Eén grote metric centraal (JetBrains Mono, 96px, bone-white) + label (DM Sans 300, 16px, text-secondary)
  - Slide 8: 2-3 metrics in een horizontale rij, of testimonial-quote
- **Achtergrond**: Noir-base
- **Testimonials**: Instrument Serif italic (28px, bone-white), naam in DM Sans 500 (14px, text-secondary), aanhalingstekens als decoratief element in #333 (200px, achtergrond)
- **Metrics**: Alleen zwart-wit. Geen groen voor positief. Het getal spreekt voor zich.

#### Slide 9: "De Takeaway"
- **Layout**: Centered statement
- **Achtergrond**: Noir-base met vignette
- **Tekst**: Syne 800, 48-60px, bone-white, maximaal 2 zinnen
- **Decoratie**: Dunne verticale lijn links (1px, #a0998f, 60px hoog) als blockquote-indicator
- **Extra**: Instrument Serif italic tagline eronder (24px, text-secondary) voor warmte

#### Slide 10: "De CTA"
- **Layout**: Centered, clean, ademt
- **Achtergrond**: Noir-base
- **Structuur**:
  - B-monogram (48px, bone-white, centered)
  - 40px ruimte
  - "THE BAIR CO." in Syne 700, tracking 0.3em, 16px, bone-white
  - "Merken die blijven hangen." in Instrument Serif italic, 20px, text-secondary
  - 48px ruimte
  - Ghost button: 1px border bone-white, DM Sans 500, 16px, padding 14px 36px, border-radius 100px — "Neem contact op"
  - 24px ruimte
  - baircompany.be in JetBrains Mono, 13px, text-dim

---

## 3. Layout Blueprint — LinkedIn Single Image (1200×628px)

### Variant A: Portfolio Showcase
- **Links (55%)**: Screenshot/mockup met subtiele donkere frame
- **Rechts (45%)**: Noir-elevated (#1e1e24) vlak met heading (Syne 700, 24px) + beschrijving (DM Sans 300, 14px) + B-monogram
- **Scheiding**: Verticale lijn (1px, #333)

### Variant B: Thought Leadership (bone-modus)
- **Full-width**: Bone-base (#f0ede8) met noise texture
- **Links-uitgelijnd**: Grote quote in Syne 700 (28px, #0a0a0a)
- **Rechtsonder**: Naam + functie in DM Sans (14px, #888) + B-monogram (20px, #0a0a0a)

### Variant C: Metric/Insight (noir-modus)
- **Full-width**: Noir-base
- **Centraal**: JetBrains Mono metric (64px, bone-white) + DM Sans label (18px, text-secondary)
- **Logo**: Rechtsonder, 30% opacity

---

## 4. Layout Blueprint — Instagram Story (1080×1920px)

### Template A: Quick Tip
- **Achtergrond**: Noir-base met noise + vignette
- **Bovenkant**: JetBrains Mono label ("QUICK TIP", 11px, tracking 0.2em, text-dim)
- **Midden**: Syne 800 (48px, bone-white)
- **Onderkant**: DM Sans 300 (18px, text-secondary) + subtiele pijl-hint
- **Structuur**: Dunne horizontale lijn (1px, #333) scheidt label van content

### Template B: Portfolio Tease
- **Full-bleed**: Screenshot/visual met donkere gradient overlay (transparant → #0a0a0a)
- **Onderaan**: Syne 700 (28px, bone-white) + DM Sans (14px, text-secondary, "Bekijk het project →")
- **Logo**: Linksboven, 20px, 30% opacity

### Template C: Behind the Scenes
- **Achtergrond**: Echte screenshot (dark code editor, Figma, terminal)
- **Overlay-band onderaan**: rgba(10,10,10,0.88), 200px hoog
- **Op de band**: DM Sans 400 (16px, bone-white) — kort commentaar
- **Vibe**: Ruw maar ingekaderd

---

## 5. Layout Blueprint — LinkedIn Banner (1584×396px)

- **Achtergrond**: Lineair gradient noir-base → noir-surface (links naar rechts)
- **Links**: B-monogram (160px, 6% opacity als watermark)
- **Centrum-rechts**: "THE BAIR CO." in Syne 800 (24px, tracking 0.25em, bone-white)
- **Onder naam**: "Merken die blijven hangen." in Instrument Serif italic (16px, text-secondary)
- **Structuur**: Dunne horizontale lijn full-width (1px, #333) op 1/3 hoogte
- **Noise**: Over het hele vlak, 2% opacity

---

## 6. Animatie & Interactie (voor video/motion posts)

### Basisbewegingen
- **Primaire reveal**: Fade-up + scale (0.97 → 1.0), 600ms, easing: cubic-bezier(0.16, 1, 0.3, 1)
- **Tekst reveal**: Per woord, 80ms stagger — woorden verschijnen als witte flitsen op donker
- **Grain shimmer**: Noise texture die heel subtiel schuift — geeft "levend" gevoel

### Speciale motion-effecten
- **Code-typing**: JetBrains Mono tekst getypt met knipperende bone-white cursor — 15s loop
- **Logo morph**: B-monogram opgebouwd uit geometrische lijnen, bone-white op noir, 3s
- **Metric counter**: Getal telt op in JetBrains Mono, bone-white, 2s
- **Lijn-tekenen**: Dunne lijnen die zichzelf "tekenen" als visuele scheiding — 800ms

---

## 7. Fotografie & Media

### Beeldstijl
- **Type**: Architecturaal, technisch, ruimtelijk. Geen mensen (tenzij authentiek behind-the-scenes)
- **Kleurbehandeling**: Zwart-wit of zwaar desaturated — consistent met monochroom palet
- **Compositie**: Negatieve ruimte dominant. Onderwerp decentraal.
- **Fallback**: Geen foto → abstracte geometrie: dunne witte lijnen op noir, rasterpatronen, of noise-texturen

### AI-prompts (aangepast naar monochroom)

**Abstract achtergrond:**
```
"dark geometric abstract background, thin white lines intersecting at
precise angles on pure black void, subtle grain texture, mathematical
precision, architectural blueprint feel, monochrome --ar 1:1 --v 6 --s 200"
```

**Tech workspace:**
```
"minimalist dark workspace from above, black and white photography,
single screen glow illuminating keyboard, high contrast, grain texture,
shot on Leica M11 Monochrom --ar 4:5 --v 6 --s 250 --style raw"
```

**Laptop mockup:**
```
"floating laptop in complete darkness, screen emitting soft white light,
monochrome, reflection on surface below, product photography, ultra
minimal, black and white --ar 4:5 --v 6"
```

---

## 8. Merkelementen — Op elke post

| Element | Specificatie |
|---------|-------------|
| **Logo** | B-monogram, bone-white op noir / noir op bone, 20-32px, 25-40% opacity (nooit dominant, altijd aanwezig) |
| **Bedrijfsnaam** | "THE BAIR CO." — Syne 700, uppercase, tracking 0.25em — alleen op CTA-slides en banners |
| **Tagline** | "Merken die blijven hangen." — Instrument Serif italic — alleen op CTA en banner |
| **Slide-indicator** | JetBrains Mono slide-nummer linksboven (13px, text-dim): "01", "02", etc. |
| **Structuurlijnen** | Dunne lijnen (1px, #333 of #a0998f) als scheiding, blockquote-indicator, of decoratie |
| **Noise texture** | SVG grain overlay, 2-3% opacity, op ALLE achtergronden — het tactiele fundament |

---

## 9. De 5 "wow-factors" (aangepast voor monochroom)

### 1. Radicaal monochroom als statement
In een wereld waar elke agency knalt met gradient-kleuren en neon-accenten, gaat Bair puur zwart-wit. Het is een statement van zelfvertrouwen: "ons werk spreekt voor zich, we hebben geen visuele trucs nodig." Het IS de differentiator.
**Effect**: Onmiddellijke herkenning in elke feed. Geen enkele concurrent doet dit.

### 2. Typografisch contrast als kleur-vervanging
Het gewichtsverschil tussen Syne 800 (120px, bold) en DM Sans 300 (18px, light) creëert dezelfde visuele spanning die normaal door kleur wordt bereikt. Het is alsof je schreeuwt en fluistert tegelijk.
**Effect**: De ogen worden geleid door gewicht in plaats van kleur — subtieler, intelligenter.

### 3. Instrument Serif als warm moment
Eén cursief woord in een zee van geometrische strengheid. Het is de menselijke hartslag in een machine. Quotes, taglines, een enkel accent-woord.
**Effect**: Emotionele landing in een verder strak systeem.

### 4. JetBrains Mono als tech-DNA
Monospace als identiteitsmarker. Niet voor code, maar voor alles dat "precies" en "gemeten" aanvoelt: nummers, datums, labels. Het is het typografische equivalent van een laboratoriumjas.
**Effect**: Communiceert tech-expertise zonder het te zeggen.

### 5. Noir + Bone ademhaling
De wisselwerking tussen donkere en lichte posts geeft de feed ritme. Drie noir, één bone. Als muzikale pauzes. De bone-variant (#f0ede8) voelt warm en menselijk — de noir voelt krachtig en cinematisch.
**Effect**: De feed voelt samengesteld, niet toevallig.

---

## 10. Wat NIET doen

| Anti-patroon | Waarom niet |
|---|---|
| **Kleuraccenten toevoegen** | Het hele punt is monochroom. Eén kleur erbij vernietigt het statement. |
| **Zuiver wit (#ffffff)** | Te koud, te digitaal. Altijd bone-white (#f0ede8) — warm, papierachtig. |
| **Zuiver zwart tekst op bone** | Gebruik #0a0a0a, nooit #000000 — iets zachter, menselijker. |
| **Canva-template-gevoel** | Geen rounded corners overal, geen gradient-confetti, geen Poppins. |
| **Stock-foto's** | Geen lachende teams. Architecturaal, technisch, of helemaal geen foto. |
| **Overgeanimeerd** | Beweging moet zo subtiel zijn dat je twijfelt of het beweegt. |
| **Emoji's** | Nooit. Punten. Korte zinnen. |
| **Inconsistentie** | Het systeem IS het merk. Één fout in plaatsing breekt de illusie. |

---

## 11. Content-categorieën

| Categorie | Frequentie | Template | Modus |
|-----------|-----------|----------|-------|
| Portfolio showcase | 2x/week | Carousel 7 slides | Noir |
| Behind-the-scenes | 1x/week | Story + single post | Noir (raw) |
| Thought leadership / tip | 1x/week | Carousel 5 slides | Noir |
| Client testimonial | 1x/2 weken | Single image | Bone |
| Data/resultaat | 1x/2 weken | Single image (metric) | Noir |
| Personal / team | 1x/maand | Single image of story | Bone |
| Motion reel | 2x/maand | Video 15-30s | Noir |
