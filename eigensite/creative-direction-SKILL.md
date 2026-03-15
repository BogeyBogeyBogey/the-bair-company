---
name: creative-direction
description: >
  Creatieve regie over UX, UI en visuele consistentie van websites — de ontbrekende schakel
  tussen wireframing, development en lancering. Werkt in drie modi: UX-review (na wireframing),
  UI-consistency check (tijdens/na development), en creatieve eindreview (voor lancering).
  Genereert een visueel HTML-rapport met scores per categorie.
  Triggers: "UX review", "UI check", "creatieve review", "design review", "consistentie check",
  "ziet het er goed uit", "klopt het design", "past alles bij elkaar", "visuele QA",
  "conversie check", "user flow check", "CTA strategie", "design beoordelen",
  "art direction", "creative direction", "UI consistentie", "look and feel checken".
  Gebruik deze skill ook automatisch: na wireframing (UX-modus), na development (UI-modus),
  en als onderdeel van launch-qa (eindreview). Zelfs als de gebruiker het niet expliciet vraagt
  maar er een wireframe of gebouwde site klaarstaat om beoordeeld te worden, stel dan proactief
  voor om een creative-direction review te doen.
version: 1.0.0
---

# Creative Direction — UX · UI · Visuele Regie

Deze skill is de creatieve regisseur van je webbureau-workflow. Waar andere skills elk hun eigen
ding doen (wireframing bouwt structuren, visual-design kiest foto's, brand-identity zet kleuren),
kijkt deze skill over alles heen en stelt de vraag: **werkt het als geheel?**

Denk aan een filmregisseur: de cameraman, de belichter en de acteurs zijn allemaal goed — maar
iemand moet het totaalplaatje bewaken. Dat is wat deze skill doet.

---

## Screenshots maken — visueel bewijs bij elke bevinding

Een creatieve review zonder visuele referenties is als een filmrecensie zonder beelden. Daarom
maakt deze skill screenshots van de site en verwerkt die in het rapport. Zo kan de klant exact
zien waar je het over hebt.

### Wanneer screenshots maken

- **UI Consistency** en **Creatieve Eindreview**: altijd (er is een gebouwde site)
- **UX Review**: alleen als er al een gebouwd prototype is; bij wireframes alleen tekst-review

### Screenshot-workflow

Gebruik de Chrome MCP tools om de site visueel vast te leggen. Dit is het stappenplan:

**Stap 1 — Schermformaten instellen en screenshots maken**

Maak voor elke pagina screenshots in drie formaten:

| Formaat | Breedte | Gebruik |
|---------|---------|---------|
| Desktop | 1440px | Hoofdweergave, compositie beoordelen |
| Tablet | 768px | Responsive gedrag middenformaat |
| Mobiel | 375px | Touch-targets, leesbaar, scroll-lengte |

Gebruik `mcp__Claude_in_Chrome__navigate` om naar elke pagina te navigeren,
`mcp__Claude_in_Chrome__resize_window` om het venster aan te passen, en
`mcp__Claude_in_Chrome__read_page` of `mcp__Claude_in_Chrome__upload_image` om
screenshots te maken.

**Stap 2 — Full-page screenshots per pagina**

Voor elke pagina in de sitemap:
1. Navigeer naar de pagina
2. Wacht tot alle afbeeldingen en animaties geladen zijn
3. Maak een screenshot op desktop-breedte
4. Resize naar tablet, screenshot
5. Resize naar mobiel, screenshot

Sla screenshots op in het project met duidelijke naamgeving:
```
creative-review-screenshots/
├── homepage-desktop.png
├── homepage-tablet.png
├── homepage-mobile.png
├── diensten-desktop.png
├── diensten-tablet.png
└── ...
```

**Stap 3 — Detail-screenshots bij problemen**

Als je een specifiek probleem vindt (bv. inconsistente buttons, slechte spacing):
- Maak een gericht screenshot van dat specifieke element
- Markeer in het rapport bij welke bevinding dit screenshot hoort

### Screenshots in het rapport embedden

Embed screenshots als base64 in het HTML-rapport, zodat het rapport als één zelfstandig
bestand werkt (geen losse afbeeldingen nodig):

```javascript
// Converteer screenshot naar base64 voor embedding
// Python: import base64; base64.b64encode(open('screenshot.png','rb').read()).decode()
```

Of verwijs naar de lokale bestanden als het rapport en screenshots in dezelfde map staan.

Toon screenshots in het rapport als:
- **Vergelijkingsweergave**: desktop / tablet / mobiel naast elkaar per pagina
- **Before/after suggestie**: bij bevindingen waar je een verbetering voorstelt
- **Annotaties**: beschrijf in de caption wat er goed of fout is aan wat je ziet

---

## Drie modi — kies op basis van de fase

| Modus | Wanneer | Wat het checkt |
|-------|---------|----------------|
| **UX Review** | Na wireframing, vóór development | Conversiedoelen, user flows, CTA-strategie, informatie-hiërarchie |
| **UI Consistency** | Tijdens of na development | Visueel systeem, spacing, componenten, interactie-patronen |
| **Creatieve Eindreview** | Voor lancering | Totaalbeeld, merkbeleving, emotionele impact, professionaliteit |

### Modus detectie

Bepaal automatisch welke modus relevant is:

- **Er is een wireframe/sitemap maar nog geen code** → UX Review
- **Er is een gebouwde site (HTML/CSS bestanden)** → UI Consistency
- **De gebruiker zegt "review", "check", "klopt het"** → kijk naar wat er beschikbaar is
- **De gebruiker vraagt expliciet** → gebruik die modus
- **Launch-qa wordt uitgevoerd** → Creatieve Eindreview (aanvullend op technische QA)

---

## Modus 1: UX Review

Doel: voorkom dat je een prachtige site bouwt die niet *werkt* voor de bezoeker.

### Lees eerst
- De wireframe/sitemap (uit wireframing skill)
- `site-research.md` (als beschikbaar)
- `brand-identity.md` of vergelijkbaar identiteitsdocument

### Check deze punten

**Conversie-architectuur:**
- Heeft elke pagina een duidelijk doel? (informeren, overtuigen, converteren)
- Is er een logisch pad van landing → interesse → actie?
- Zijn er voldoende maar niet te veel CTA's? (vuistregel: 1 primaire CTA per schermvullend gedeelte)
- Is de belangrijkste CTA boven de fold zichtbaar?

**User Flow analyse:**
- Kan een bezoeker in maximaal 3 kliks bij de belangrijkste actie komen?
- Is de navigatie voorspelbaar? (gebruiker moet nooit hoeven nadenken waar iets staat)
- Zijn er doodlopende pagina's zonder vervolgactie?
- Is er een terugweg vanuit elke subpagina?

**Informatie-hiërarchie:**
- Staat de belangrijkste informatie bovenaan?
- Is er een duidelijke visuele hiërarchie? (koppen > subkoppen > body > details)
- Wordt de bezoeker niet overladen met keuzes? (Hick's Law: minder opties = snellere beslissing)
- Is de tekst scanbaar? (koppen, bullets, witruimte)

**Doelgroep-fit:**
- Past de structuur bij het type bezoeker? (zakelijk publiek ≠ consument)
- Is de tone of voice consistent met de doelgroep?
- Zijn er vertrouwenssignalen op de juiste plekken? (reviews, certificaten, klantenlogo's)

**Mobiel-eerst denken:**
- Werkt de structuur op een smal scherm?
- Zijn touch-targets groot genoeg? (minimaal 44×44px)
- Zijn er secties die op mobiel onnodig lang worden?

### UX Scores (gebruik in rapport)

| Categorie | Gewicht |
|-----------|---------|
| Conversie-architectuur | 30% |
| User Flow | 25% |
| Informatie-hiërarchie | 20% |
| Doelgroep-fit | 15% |
| Mobiel-eerst | 10% |

---

## Modus 2: UI Consistency

Doel: zorg dat de gebouwde site voelt als één samenhangend ontwerp, niet als een verzameling losse pagina's.

### Lees eerst
- Alle HTML/CSS bestanden van het project
- `brand-identity.md` voor de gedefinieerde tokens
- `CLAUDE.md` als die design-afspraken bevat

### Check deze punten

**Kleurconsistentie:**
- Worden alleen de gedefinieerde merkkleuren gebruikt? (geen willekeurige hex-waarden)
- Is het kleurgebruik consistent? (primair voor CTA's, secundair voor accenten, neutrals voor tekst)
- Zijn hover/active states consistent over alle interactieve elementen?
- Is er voldoende contrast? (WCAG AA minimaal: 4.5:1 voor tekst, 3:1 voor grote tekst)

**Typografische consistentie:**
- Worden maximaal 2 fontfamilies gebruikt?
- Is de typografische schaal consistent? (niet 15 verschillende font-sizes)
- Zijn heading-niveaus logisch? (h1 → h2 → h3, geen sprongen)
- Is de line-height comfortabel? (body: 1.5-1.7, headings: 1.1-1.3)
- Wordt dezelfde font-weight consequent gebruikt voor dezelfde doeleinden?

**Spacing-systeem:**
- Is er een consistent spacing-systeem? (bv. 8px grid of 4px grid)
- Zijn margins en paddings niet willekeurig maar volgen ze een ritme?
- Is de verticale ruimte tussen secties consistent?
- Hebben vergelijkbare elementen dezelfde interne padding?

**Component-consistentie:**
- Zien buttons er overal hetzelfde uit? (grootte, border-radius, padding, animatie)
- Zijn cards consistent? (schaduw, border-radius, padding, hover-effect)
- Zijn formuliervelden uniform? (border, focus-state, placeholder-stijl)
- Zijn links consistent gestyled? (kleur, underline, hover)

**Interactie-patronen:**
- Hebben alle hover-effecten dezelfde timing? (bv. allemaal 0.3s ease)
- Zijn scroll-animaties consistent? (niet de ene sectie fade-in en de andere slide-up)
- Reageren interactieve elementen visueel op interactie? (feedback bij klik, hover, focus)
- Zijn loading-states en lege states ontworpen?

**Responsive gedrag:**
- Breken componenten netjes op kleinere schermen?
- Is de volgorde op mobiel logisch? (niet desktop-volgorde geforceerd)
- Zijn er geen horizontale scrollbars?
- Schalen afbeeldingen correct mee?

### UI Scores (gebruik in rapport)

| Categorie | Gewicht |
|-----------|---------|
| Kleurconsistentie | 20% |
| Typografie | 20% |
| Spacing-systeem | 15% |
| Component-consistentie | 20% |
| Interactie-patronen | 15% |
| Responsive gedrag | 10% |

---

## Modus 3: Creatieve Eindreview

Doel: de "art director blik" — voelt deze site als het werk van één samenhangend creatief team?

### Lees eerst
- Alle projectbestanden
- `site-research.md`
- `brand-identity.md`
- De wireframe/sitemap

### Check deze punten

**Merkbeleving:**
- Vertelt de site in 3 seconden wat het bedrijf doet en waarom het ertoe doet?
- Voelt de site "af"? (geen placeholder-teksten, geen lorem ipsum, geen ontbrekende beelden)
- Past de visuele stijl bij de sector en doelgroep?
- Is er een emotionele rode draad? (professioneel, warm, speels, betrouwbaar — consistent)

**Visuele compositie:**
- Is er visueel ritme? (afwisseling tussen zware en lichte secties)
- Zijn er rustpunten? (witruimte is geen verspilling maar een designkeuze)
- Heeft de pagina een visuele "groove"? (niet monotoon, niet chaotisch)
- Zijn foto's kwalitatief en stilistisch consistent? (niet: 1 stockfoto warm en de andere klinisch)

**Fotografie-consistentie:**
- Hebben alle foto's een vergelijkbare kleurtemperatuur?
- Is de beeldstijl consistent? (niet mixen: illustraties + foto's + iconen)
- Zijn er geen kwaliteitsverschillen tussen foto's? (niet: 1 in 4K en de andere pixelig)
- Passen de foto's bij het verhaal van het bedrijf?

**Eerste indruk (5-seconden test):**
- Wat is het eerste dat je ziet? Is dat het juiste?
- Is het duidelijk wat de bezoeker moet doen? (primaire actie)
- Voelt het vertrouwenwekkend?
- Is het visueel aantrekkelijk genoeg om te blijven scrollen?

**Concurrentie-benchmark:**
- Ziet deze site er beter uit dan wat vergelijkbare bedrijven hebben?
- Heeft de site een eigen karakter? (niet: generieke template-look)
- Zijn er elementen die opvallen in positieve zin? (een "wow" moment)

### Creatieve Scores (gebruik in rapport)

| Categorie | Gewicht |
|-----------|---------|
| Merkbeleving | 25% |
| Visuele compositie | 25% |
| Fotografie-consistentie | 20% |
| Eerste indruk | 20% |
| Concurrentie-benchmark | 10% |

---

## Scoringssysteem

Gebruik een consistent scoringsmodel over alle modi:

| Score | Label | Betekenis |
|-------|-------|-----------|
| 9-10 | **Excellent** | Designbureau-niveau. Klaar voor lancering. |
| 7-8 | **Goed** | Professioneel, kleine verbeterpunten. |
| 5-6 | **Voldoende** | Functioneel maar mist finesse. Verbeteringen nodig. |
| 3-4 | **Onvoldoende** | Duidelijke problemen. Moet aangepakt worden. |
| 1-2 | **Kritiek** | Fundamentele issues. Niet presenteerbaar. |

**Totaalscore**: gewogen gemiddelde van alle categorieën in de gekozen modus.

---

## HTML Rapport genereren

Na de review, genereer altijd een visueel HTML-rapport. Dit rapport moet professioneel genoeg
zijn om aan een klant te tonen als onderbouwing van designkeuzes.

### Rapport structuur

```html
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>Creative Direction Review — [Projectnaam]</title>
    <style>
        /* Modern, clean styling met het kleurenpalet van het project */
    </style>
</head>
<body>
    <!-- Header met projectnaam, datum, modus -->
    <!-- Totaalscore als groot visueel element -->

    <!-- SCREENSHOT GALERIJ -->
    <!-- Per pagina: desktop / tablet / mobiel naast elkaar -->
    <!-- Responsive grid: 3 kolommen op desktop, 1 op mobiel -->
    <!-- Caption onder elke set met pagina-naam -->

    <!-- Score per categorie met visuele balk -->

    <!-- Per categorie: bevindingen, met status-indicatoren -->
    <!--   ✓ Goed  |  ⚠ Aandachtspunt  |  ✗ Probleem -->
    <!--   Bij elke bevinding: relevante screenshot als visueel bewijs -->
    <!--   Zet het screenshot IN de bevinding, niet apart onderaan -->

    <!-- Aanbevelingen sectie: concrete actiepunten -->
    <!-- Footer met disclaimer -->
</body>
</html>
```

### Rapport design-richtlijnen

- Gebruik een **kleurcodering** voor scores: groen (7+), oranje (5-6), rood (< 5)
- Houd het **visueel**: progress bars, score-cirkels, iconen — niet alleen tekst
- Zet **concrete aanbevelingen** bij elke bevinding, niet alleen "dit is fout"
- Maak het rapport **responsive** (klant kan het op telefoon bekijken)
- Voeg een **samenvatting** toe bovenaan (3-5 zinnen, de hoofdconclusie)
- Stijl het rapport passend bij het project (gebruik de merkkleuren als accent)

### Screenshot-weergave in rapport

Het rapport bevat screenshots op twee niveaus:

**1. Pagina-overzicht (bovenaan het rapport)**
Een galerij met alle pagina's in desktop/tablet/mobiel. Dit geeft direct een totaaloverzicht
van de site. Gebruik een CSS grid met `grid-template-columns: 3fr 2fr 1fr` zodat de
verhouding desktop/tablet/mobiel visueel klopt.

```html
<div class="page-overview">
  <h2>Pagina-overzicht</h2>
  <div class="device-comparison">
    <div class="device desktop">
      <span class="device-label">Desktop 1440px</span>
      <img src="data:image/png;base64,..." alt="Homepage desktop">
    </div>
    <div class="device tablet">
      <span class="device-label">Tablet 768px</span>
      <img src="data:image/png;base64,..." alt="Homepage tablet">
    </div>
    <div class="device mobile">
      <span class="device-label">Mobiel 375px</span>
      <img src="data:image/png;base64,..." alt="Homepage mobiel">
    </div>
  </div>
</div>
```

**2. Inline bij bevindingen (in het rapport-body)**
Bij elke specifieke bevinding: toon het relevante screenshot direct naast de beschrijving.
Dit maakt het rapport veel concreter — de klant ziet meteen wat je bedoelt.

```html
<div class="finding">
  <div class="finding-text">
    <span class="status warning">⚠</span>
    <strong>Inconsistente teamfoto's</strong>
    <p>De foto's op de teampagina hebben verschillende kleurtemperaturen...</p>
    <p class="recommendation">Aanbeveling: pas een uniform kleurfilter toe...</p>
  </div>
  <div class="finding-screenshot">
    <img src="data:image/png;base64,..." alt="Teamfoto inconsistentie">
    <span class="caption">Teampagina — verschil in kleurtemperatuur zichtbaar</span>
  </div>
</div>
```

---

## Integratie met andere skills

### Na wireframing (automatisch)
Wanneer de wireframing-skill klaar is, stel voor:
> "De wireframe is klaar. Wil je dat ik een UX-review doe voordat we gaan bouwen?"

### Tijdens/na development (automatisch)
Wanneer significante development klaar is, stel voor:
> "De site is gebouwd. Zal ik een UI-consistency check doen?"

### Bij launch-qa (automatisch)
Wanneer launch-qa wordt gestart, voeg de creatieve eindreview toe als extra stap:
> "Naast de technische QA doe ik ook een creatieve eindreview."

---

## Belangrijk: bevindingen omzetten in actie

Een review is pas nuttig als de bevindingen leiden tot verbeteringen. Daarom:

1. **Wees specifiek**: niet "de typografie is inconsistent" maar "op de contactpagina is de
   heading 36px terwijl alle andere pagina's 42px gebruiken"
2. **Geef de oplossing**: niet alleen het probleem benoemen, maar ook zeggen hoe het op te lossen
3. **Prioriteer**: markeer wat kritiek is (moet voor lancering) versus nice-to-have
4. **Bied aan om te fixen**: na de review, bied aan om de gevonden problemen direct op te lossen

### Prioriteitsindeling in rapport

| Prioriteit | Label | Betekenis |
|------------|-------|-----------|
| P1 | **Must fix** | Blokkeert lancering. Direct aanpakken. |
| P2 | **Should fix** | Merkbaar voor gebruikers. Vóór lancering oplossen. |
| P3 | **Nice to have** | Verfijning. Kan na lancering. |
