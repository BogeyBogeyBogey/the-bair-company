---
name: brand-identity
description: >
  Automatische merkidentiteit afleiden van een bestaande website en upgraden naar
  professionele standaarden. Kleuren, fonts, tone of voice, animatie-tokens en
  designstijl worden automatisch bepaald op basis van URL-research.
  Triggers: "huisstijl maken", "branding", "merkidentiteit", "kleuren kiezen",
  "kleurenpalet", "fonts kiezen", "tone of voice", "brand guidelines",
  "huisstijlgids", "visuele identiteit".
version: 4.0.0
---

# Brand Identity — Automatisch afleiden en upgraden

Leid de merkidentiteit automatisch af van de bestaande website (uit site-research.md) en upgrade naar professionele standaarden conform CLAUDE.md.

## BELANGRIJK — Verboden fonts

De volgende fonts mogen NOOIT als primaire fonts worden gebruikt:
- Inter, Roboto, Arial, Helvetica, system-ui, Open Sans, Lato

Kies ALTIJD karaktervolle, intentionele fontcombinaties.

## Workflow (volledig automatisch)

### Stap 1: Sector bepalen en designstijl kiezen

Op basis van de site-research, classificeer het bedrijf en kies de passende designstijl. Elke sector heeft nu **2-3 font-alternatieven** zodat niet elk project in dezelfde sector er hetzelfde uitziet:

| Sector | Designstijl | Font-opties (kies er één) |
|--------|------------|---------------------------|
| Advocaten, notarissen, accountants | Corporate Refined | **A:** Playfair Display + Source Serif 4 · **B:** DM Serif Display + Outfit · **C:** Libre Caslon Display + Karla |
| Consultants, grote bedrijven | Executive Luxury | **A:** Cormorant Garamond + Jost · **B:** Spectral + Urbanist · **C:** Bodoni Moda + Plus Jakarta Sans |
| Ontwerpers, fotografen, architecten | Editorial Magazine | **A:** Bebas Neue + Libre Baskerville · **B:** Anton + Newsreader · **C:** Oswald + Lora |
| Creatieve studio's, reclame | Maximalist / Brutalist | **A:** Space Mono + Work Sans · **B:** Archivo Black + Inconsolata · **C:** Darker Grotesque + IBM Plex Mono |
| Zorgverleners, coaches, therapeuten | Organic Natural | **A:** Lora + Nunito · **B:** Bitter + Cabin · **C:** Merriweather + Open Sans (uitzondering: als body!) |
| Kinderopvang, welzijn | Soft Pastel Studio | **A:** Lora + Nunito · **B:** Quicksand + Mulish · **C:** Josefin Sans + Hind |
| Tech-startups, SaaS, AI | Dark Tech | **A:** JetBrains Mono + Manrope · **B:** Fira Code + General Sans · **C:** Space Grotesk + Geist |
| Fintech, engineering | Clean SaaS | **A:** Syne + DM Sans · **B:** Satoshi + Inter (alleen hier!) · **C:** Outfit + Figtree |
| Winkels, horeca, food | Artisan Craft | **A:** Fraunces + Crimson Pro · **B:** Vollkorn + Lexend · **C:** DM Serif Display + Atkinson Hyperlegible |
| Lifestyle, mode | Luxury Product | **A:** Cormorant Garamond + Jost · **B:** Bodoni Moda + Manrope · **C:** Marcellus + Questrial |
| Jonge doelgroep, entertainment | Bold & Playful | **A:** Space Grotesk + DM Sans · **B:** Rubik + Nunito Sans · **C:** Sora + Red Hat Display |
| Dokters, tandartsen, kinesisten | Personal Brand Premium | **A:** Lora + Nunito · **B:** Cardo + Poppins · **C:** Source Serif 4 + Lexend |
| Freelancers, vrije beroepen | Portfolio Showcase | **A:** Syne + DM Sans · **B:** Clash Display + General Sans · **C:** Cabinet Grotesk + Figtree |
| Bouw, renovatie, ambacht | Industrial Craft | **A:** Barlow Condensed + Source Sans 3 · **B:** Chakra Petch + Overpass · **C:** Teko + Titillium Web |

**Keuzeregel**: Als een vorig project in dezelfde sector font-optie A gebruikte, kies B of C. Varieer ALTIJD.

### Stap 2: Kleurenpalet upgraden

Neem de bestaande kleuren als uitgangspunt en verbeter:
1. **Behoud de primary kleur** als die sterk is (of kies een betere variant)
2. **Voeg een accent kleur toe** die contrast biedt
3. **Definieer neutral tinten** voor tekst en achtergronden
4. **Voeg functionele kleuren toe** (success, error, warning)

**Palet formaat (uitgebreid):**
```
Primary:    #XXXXXX — [naam en gebruik]
Secondary:  #XXXXXX — [naam en gebruik]
Accent:     #XXXXXX — [naam en gebruik]
Dark:       #XXXXXX — donkere tekst/achtergrond
Light:      #XXXXXX — lichte achtergrond
White:      #FFFFFF — wit
Success:    #XXXXXX — bevestigingen
Error:      #XXXXXX — foutmeldingen
```

### Stap 3: Typografie selecteren

Kies ALTIJD uit de goedgekeurde font-koppelingen hierboven. NOOIT Inter, Roboto of Arial als heading font.

**Regels:**
- Maximum 2 fonts per project
- Heading font mag expressief zijn
- Body font moet goed leesbaar zijn (min. 16px)
- Laad via Google Fonts CDN
- Font sizes met clamp() voor responsive scaling

### Stap 4: Tone of Voice bepalen

Afleiden van de bestaande teksten:
- **Formeel ↔ Informeel**: hoe worden bezoekers aangesproken?
- **Serieus ↔ Speels**: hoeveel luchtigheid?
- **Respectvol ↔ Direct**: hoe assertief?
- **Enthousiast ↔ Nuchter**: hoeveel energie?
- **Aanspreking**: "je" of "u"?

### Stap 5: Animatie-profiel kiezen

Koppel het animatieniveau aan de sector en doelgroep:

| Profiel | Sectoren | Kenmerken |
|---------|----------|-----------|
| **Subtiel** | Advocaten, accountants, zorg | Zachte fades, trage reveals, geen video hero |
| **Balanced** | Consultants, freelancers, retail | Mix van fades, slides en 1 wow-element |
| **Dynamic** | Tech, creatief, entertainment | Video hero, marquee, magnetic buttons, glassmorphism |
| **Maximal** | Reclame, mode, portfolio | Alles: video, text-reveal, horizontal scroll, 3D tilt |

### Stap 6: CSS Custom Properties genereren

Genereer direct bruikbare CSS met **uitgebreide tokens**:

```css
:root {
  /* Kleuren */
  --color-primary: #XXXXXX;
  --color-primary-rgb: XX, XX, XX;  /* Voor rgba() gebruik */
  --color-secondary: #XXXXXX;
  --color-secondary-rgb: XX, XX, XX;
  --color-accent: #XXXXXX;
  --color-accent-rgb: XX, XX, XX;
  --color-dark: #XXXXXX;
  --color-dark-rgb: XX, XX, XX;
  --color-light: #XXXXXX;
  --color-white: #FFFFFF;

  /* Fonts */
  --font-heading: 'FontNaam', serif;
  --font-body: 'FontNaam', sans-serif;

  /* Responsive sizes */
  --text-hero: clamp(3rem, 8vw, 7rem);
  --text-h1: clamp(2.5rem, 5vw, 4rem);
  --text-h2: clamp(1.8rem, 3.5vw, 2.5rem);
  --text-h3: clamp(1.3rem, 2.5vw, 1.75rem);
  --text-body: clamp(1rem, 1.2vw, 1.125rem);
  --text-small: 0.875rem;

  /* Animatie tokens */
  --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-out-back: cubic-bezier(0.34, 1.56, 0.64, 1);
  --duration-fast: 0.3s;
  --duration-normal: 0.6s;
  --duration-slow: 1s;

  /* Spacing */
  --section-padding: clamp(4rem, 8vw, 8rem);
  --container-max: 1200px;

  /* Shadows */
  --shadow-sm: 0 2px 8px rgba(0,0,0,0.08);
  --shadow-md: 0 8px 24px rgba(0,0,0,0.12);
  --shadow-lg: 0 16px 48px rgba(0,0,0,0.16);
  --shadow-xl: 0 24px 64px rgba(0,0,0,0.2);

  /* Border radius */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 20px;
  --radius-full: 9999px;
}
```

## Output

Geen apart document nodig — de brand identity wordt direct verwerkt in de code van de landingspagina. De designkeuzes worden kort vermeld in `site-research.md` onder een "Gekozen designprofiel" sectie.

## Tips

- Test kleurcontrast voor accessibility (WCAG AA minimaal 4.5:1 voor tekst)
- Als de klant twijfelt na het zien van de landingspagina: maak 2-3 kleurvarianten
- Gebruik NOOIT paarse gradiënten op witte achtergronden (generieke AI-esthetiek)
- RGB-varianten van kleuren zijn VERPLICHT voor glassmorphism en overlay-effecten
