---
name: visual-design
description: >
  Visuele designstrategie met Unsplash-fotografie, videocontent, Envato-template-inspiratie
  en unieke premium layouts. Triggers: "mockup maken", "design maken", "template kiezen",
  "visueel ontwerp", "homepage design", "landingspagina design", "UI design", "Unsplash",
  "Envato", "video achtergrond", "premium design".
version: 4.0.0
---

# Visueel Design — Premium, Interactief & Uniek

Elke website moet eruitzien als een **top-tier designbureau** het gebouwd heeft. Geen passe-partout layouts. Geen herhalende patronen. Elke site is uniek, foto-gedreven, video-verrijkt en onvergetelijk.

## ZERO TOLERANCE — Wat NOOIT mag

| VERBODEN | WAAROM | ALTERNATIEF |
|----------|--------|-------------|
| Emoji's als iconen (📞 📧 📍) | Amateuristisch, goedkoop | SVG inline iconen of tekst-only |
| Font Awesome / Unicode iconen als dienst-visual | Generiek, geen impact | Echte Unsplash-foto's per dienst |
| Grijze vakken / placehold.co | Onaf, onprofessioneel | Altijd echte foto's |
| Secties zonder enig beeld | Saai, muur van tekst | Foto, video, of visuele textuur |
| Identieke sectie-layouts herhaald | Voorspelbaar, verveling | Varieer ELKE sectie |
| Paarse gradiënten op wit | Generieke AI-look | Sector-passende kleuren |

---

## KERNPRINCIPE 1: Foto's maken het design

Een professionele website ZONDER foto's bestaat niet. Foto's zijn het verschil tussen een "AI-template" en een echte designbureau-site.

### Beeldmateriaal-hiërarchie (VERPLICHT)

Gebruik ALTIJD deze prioriteitsvolgorde bij het kiezen van beelden:

| Prioriteit | Bron | Wanneer |
|------------|------|---------|
| **1. ALTIJD** | **Logo van de klant** | Het echte logo wordt ALTIJD overgenomen van de originele site |
| **2. BIJ VOORKEUR** | **Eigen foto's van de klant** | Teamfoto's, werkplaats, producten, pand, projectfoto's — mits scherp en professioneel (min. 800px breed, goede belichting) |
| **3. AANVULLEN** | **Unsplash / Pexels / Pixabay** | Waar eigen beelden ontbreken of niet hoogwaardig genoeg zijn |

**Waarom?** Eigen beelden geven de site authenticiteit. Een echte foto van het team of de werkplaats is altijd waardevoller dan een generieke stockfoto — zolang de kwaliteit voldoende is.

**Wanneer NIET overnemen:**
- Foto's kleiner dan 800×600px (te laag voor professioneel gebruik)
- Wazige, slecht belichte of sterk gecomprimeerde beelden
- Screenshots of foto's van beeldschermen
- Clipart of stock-iconen van lage kwaliteit
- Foto's met watermerken

### Unsplash als aanvullende beeldbron

Gebruik Unsplash-foto's om het beeldmateriaal van de klant **aan te vullen**, niet te vervangen.

**Hoe Unsplash-foto's vinden:**

1. Gebruik **WebSearch**:
   ```
   WebSearch: "site:unsplash.com [sector] [keyword]"
   ```
   Voorbeelden:
   - `site:unsplash.com plumber bathroom renovation`
   - `site:unsplash.com modern office lawyer`
   - `site:unsplash.com bakery artisan bread`

2. Open de gevonden Unsplash-pagina's via **Chrome MCP** en kopieer de directe foto-URL's.

3. Gebruik het formaat:
   ```
   https://images.unsplash.com/photo-XXXXX?w=1600&h=900&fit=crop&auto=format&q=80
   ```

4. **Per project minimaal 10-15 unieke foto's** verzamelen:
   - 2-3 hero-foto's (breed, dramatisch, sfeerbepalend)
   - 2-3 sfeer/achtergrond-foto's (texturen, details, materialen)
   - 3-4 dienst/product-foto's (per dienst minstens 1 grote foto)
   - 1-2 team/werkplaats-achtige foto's
   - 1-2 detail/close-up foto's

5. Zoek altijd SECTOR-SPECIFIEK:
   | Sector | Zoektermen |
   |--------|-----------|
   | Verwarming/sanitair | bathroom renovation, modern bathroom, plumbing, copper pipes |
   | Advocaat/notaris | law office, legal documents, courthouse, professional meeting |
   | Bakker/horeca | artisan bread, pastry kitchen, cafe interior, food styling |
   | Bouw/renovatie | construction site, home renovation, architecture, building |
   | Kapper/beauty | salon interior, hair styling, beauty treatment |
   | Tech/startup | workspace, coding, technology, modern office |
   | Architectuur | architectural design, blueprint, modern building |
   | Kinesist/zorg | physiotherapy, wellness, medical office, healthcare |

---

## KERNPRINCIPE 2: Video maakt het verschil

Video-achtergronden tillen een site van "mooi" naar "wauw". Gebruik ze strategisch.

### Gratis videobronnen

| Bron | URL | Zoekstrategie |
|------|-----|---------------|
| **Coverr.co** | coverr.co | Zoek op sfeer: "office", "nature", "technology" |
| **Pexels Video** | pexels.com/videos | Breed aanbod, hoge kwaliteit, zoek op sector |
| **Pixabay Video** | pixabay.com/videos | Gratis, geen attributie nodig |

### Video-integratie regels

1. **Maximaal 1-2 video-secties per site** (anders te druk)
2. **Hero of statement-sectie** zijn de beste plekken
3. **Altijd met fallback**: `poster` attribuut met Unsplash-foto voor mobile/slow connections
4. **Gedempt en loopend**: `autoplay muted loop playsinline`
5. **Overlay verplicht**: gradient of semi-transparante laag zodat tekst leesbaar blijft
6. **Mobile**: vervang video door statische poster-afbeelding op schermen < 768px

### Video HTML-patroon
```html
<section class="video-hero">
  <video autoplay muted loop playsinline
         poster="unsplash-fallback.jpg"
         class="video-bg">
    <source src="video-url.mp4" type="video/mp4">
  </video>
  <div class="video-overlay"></div>
  <div class="video-content">
    <h1>Mega Statement</h1>
  </div>
</section>
```

```css
.video-hero { position: relative; min-height: 100vh; overflow: hidden; }
.video-bg {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  object-fit: cover;
}
.video-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(135deg, rgba(0,0,0,0.7), rgba(0,0,0,0.3));
}
.video-content {
  position: relative; z-index: 2;
  display: flex; align-items: center; justify-content: center;
  min-height: 100vh; text-align: center; color: white;
}
@media (max-width: 768px) {
  .video-bg { display: none; }
  .video-hero {
    background: url('unsplash-fallback.jpg') center/cover;
  }
}
```

---

## KERNPRINCIPE 3: Envato/ThemeForest als inspiratiebron

Vóór je begint met een design, zoek ALTIJD naar premium templates als **inspiratie**:

1. Gebruik **WebSearch**:
   ```
   "themeforest [sector] website template best sellers"
   "awwwards [sector] website design"
   "dribbble [sector] landing page"
   ```

2. Open 2-3 templates/voorbeelden via **Chrome MCP** en neem screenshots

3. Analyseer wat ze GOED doen:
   - Hoe gebruiken ze foto's? (full-bleed, overlappend, als achtergrond)
   - Welke layout-patronen? (asymmetrisch, parallax, grid-brekend)
   - Welke typografische statements? (mega-koppen, overlappende tekst)
   - Welke interacties? (hover reveals, scroll transformaties)
   - Gebruiken ze video? Hoe?
   - Glassmorphism, blur-effecten, floating cards?

4. Noteer 3-5 specifieke designtechnieken die je gaat toepassen

---

## LAYOUT-PATRONEN — Catalogus

### Hero-varianten (kies er één)

1. **Full-bleed foto hero** — foto over de hele viewport, tekst eroverheen met overlay
2. **Split hero** — 50/50 of 60/40 tekst links, foto rechts (of omgekeerd)
3. **Video-achtergrond hero** — loopende video met overlay en mega-tekst
4. **Mega-typografie hero** — enorm grote tekst (120px+) met foto achter de letters (CSS clip-path of mix-blend-mode)
5. **Diagonal split** — schuine lijn scheidt foto en kleurvlak
6. **Overlapping hero** — foto die uit het kader valt, overlapt met de volgende sectie
7. **Mosaic hero** — meerdere foto's in een asymmetrisch grid
8. **Minimal statement hero** — bijna lege pagina, één zin, één foto eronder die langzaam inscrollt
9. **Glassmorphism hero** — frosted glass card over een full-bleed foto of video
10. **Text-reveal hero** — tekst die letter voor letter of woord voor woord verschijnt bij laden

### Sectie-layouts (mix en match, gebruik minstens 5-6 per homepage)

1. **Full-bleed fotobanden** — foto over hele breedte met tekst overlay
2. **Alternating zigzag** — afwisselend foto links/tekst rechts, en omgekeerd
3. **Overlapping cards** — kaarten die over secties heen vallen
4. **Magazine grid** — onregelmatig grid met grote en kleine items
5. **Sticky scroll** — tekst scrollt terwijl foto vast blijft staan
6. **Parallax lagen** — elementen op verschillende snelheden
7. **Horizontal scroll** — horizontaal scrollende galerij binnen een verticale pagina
8. **Masonry layout** — Pinterest-achtig grid met variabele hoogtes
9. **Before/after reveal** — slider die twee toestanden toont
10. **Stats ticker** — grote animated cijfers die optellen bij inscroll
11. **Testimonial spotlight** — grote quote met foto-achtergrond, premium
12. **Full-screen secties** — elke sectie = één viewport hoog, scroll-snap
13. **Floating elements** — elementen die buiten hun containers vallen
14. **Diagonal/angled secties** — schuine snedes via clip-path
15. **Dark/light contrast** — dramatische wisselingen donker/licht
16. **Video statement band** — full-width video met korte impactful tekst
17. **Marquee/ticker band** — doorlopende tekst-animatie
18. **Glassmorphism cards** — frosted glass kaarten op een foto-achtergrond
19. **Image reveal on scroll** — foto's die met clip-path "opensliden" bij scrollen
20. **Animated tabs** — interactieve tabbladen met foto's die switchen

### Footer-varianten

1. **Mega footer** — breed, meerdere kolommen, embedded Google Maps
2. **Minimal footer** — één regel, essentieel
3. **CTA footer** — footer IS de call-to-action, mega-tekst
4. **Dark contrast footer** — dramatisch donkere footer als afsluiter
5. **Photo footer** — footer met achtergrondfoto

---

## PREMIUM CSS-TECHNIEKEN

### Foto-integratie
```css
/* Full-bleed met gradient overlay */
.hero {
  background: linear-gradient(135deg, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0.3) 100%),
              url('unsplash-url') center/cover no-repeat;
  min-height: 100vh;
}

/* Foto achter tekst (text-clip) */
.mega-heading {
  background: url('unsplash-url') center/cover;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  font-size: clamp(4rem, 12vw, 10rem);
}

/* Diagonal snede */
.diagonal-section {
  clip-path: polygon(0 5%, 100% 0, 100% 95%, 0 100%);
}

/* Parallax */
.parallax-bg {
  background: url('unsplash-url') center/cover no-repeat fixed;
}

/* Overlapping foto */
.overlap-image {
  position: relative; z-index: 2;
  margin-top: -8rem;
  border-radius: 12px;
  box-shadow: 0 25px 60px rgba(0,0,0,0.3);
}

/* Hover reveal */
.photo-card:hover img {
  transform: scale(1.08);
  filter: brightness(1.1);
}
```

### Glassmorphism
```css
.glass-card {
  background: rgba(255,255,255,0.12);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255,255,255,0.18);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.15);
}
```

### Noise/Grain overlay
```css
.section-with-texture::after {
  content: '';
  position: absolute; inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
  pointer-events: none;
  z-index: 1;
}
```

### Animated gradient mesh
```css
.gradient-bg {
  background: linear-gradient(-45deg, var(--color-primary), var(--color-secondary), var(--color-accent), var(--color-primary));
  background-size: 400% 400%;
  animation: gradientShift 12s ease infinite;
}
@keyframes gradientShift {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}
```

### Image reveal on scroll
```css
.image-reveal {
  clip-path: inset(100% 0 0 0);
  transition: clip-path 1.2s cubic-bezier(0.77, 0, 0.175, 1);
}
.image-reveal.visible {
  clip-path: inset(0 0 0 0);
}
```

---

## TYPOGRAFISCHE STATEMENTS

```css
/* Mega heading */
.statement {
  font-size: clamp(3rem, 8vw, 8rem);
  font-weight: 900;
  line-height: 0.95;
  letter-spacing: -0.03em;
}

/* Outlined tekst */
.outline-text {
  -webkit-text-stroke: 2px var(--color-primary);
  color: transparent;
  font-size: clamp(3rem, 10vw, 9rem);
}

/* Markering/highlight */
.highlight {
  background: linear-gradient(transparent 60%, var(--color-accent) 60%);
  display: inline;
}

/* Text reveal animatie */
.text-reveal span {
  display: inline-block;
  opacity: 0;
  transform: translateY(40px) rotate(3deg);
  transition: all 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}
.text-reveal.visible span {
  opacity: 1;
  transform: translateY(0) rotate(0);
}
```

---

## ANIMATIES — Premium Toolkit

### Scroll-triggered reveals (basis)
```css
.reveal { opacity: 0; transform: translateY(40px); transition: all 0.8s cubic-bezier(0.16,1,0.3,1); }
.reveal.visible { opacity: 1; transform: translateY(0); }
.reveal-slide { opacity: 0; transform: translateX(-80px) rotate(-3deg); transition: all 0.8s cubic-bezier(0.16,1,0.3,1); }
.reveal-slide.visible { opacity: 1; transform: translateX(0) rotate(0); }
.reveal-scale { opacity: 0; transform: scale(0.8); transition: all 0.6s cubic-bezier(0.34,1.56,0.64,1); }
.reveal-scale.visible { opacity: 1; transform: scale(1); }
```

### Staggered children
```css
.stagger .item:nth-child(1) { transition-delay: 0s; }
.stagger .item:nth-child(2) { transition-delay: 0.1s; }
.stagger .item:nth-child(3) { transition-delay: 0.2s; }
.stagger .item:nth-child(4) { transition-delay: 0.3s; }
.stagger .item:nth-child(5) { transition-delay: 0.4s; }
.stagger .item:nth-child(6) { transition-delay: 0.5s; }
```

### Counter animation (JS)
```javascript
function animateCounter(el) {
  const target = parseInt(el.dataset.target);
  let current = 0;
  const increment = target / 60;
  const timer = setInterval(() => {
    current += increment;
    if (current >= target) { current = target; clearInterval(timer); }
    el.textContent = Math.floor(current).toLocaleString('nl-BE');
  }, 16);
}
```

### Marquee/ticker
```css
.marquee { overflow: hidden; white-space: nowrap; }
.marquee-track {
  display: inline-flex; gap: 4rem;
  animation: marquee 20s linear infinite;
}
@keyframes marquee { to { transform: translateX(-50%); } }
```

### Magnetic button (JS)
```javascript
document.querySelectorAll('.magnetic-btn').forEach(btn => {
  btn.addEventListener('mousemove', e => {
    const rect = btn.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width/2;
    const y = e.clientY - rect.top - rect.height/2;
    btn.style.transform = `translate(${x*0.3}px, ${y*0.3}px)`;
  });
  btn.addEventListener('mouseleave', () => {
    btn.style.transform = 'translate(0,0)';
    btn.style.transition = 'transform 0.4s cubic-bezier(0.16,1,0.3,1)';
  });
});
```

---

## Accessibility

Respecteer altijd `prefers-reduced-motion`:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
  .video-bg { display: none; }
}
```

## Geen aparte output

Alle visuele beslissingen worden toegepast in de code via de development skill. Het verschil met voorheen: nu worden er ECHTE foto's gezocht, VIDEO's geïntegreerd, ECHTE template-inspiratie bekeken, en UNIEKE layouts gekozen — vóór de eerste regel code geschreven wordt.
