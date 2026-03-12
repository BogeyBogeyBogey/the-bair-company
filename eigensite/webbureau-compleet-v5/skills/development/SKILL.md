---
name: development
description: >
  Bouw unieke, foto-gedreven websites op topniveau. Geen templates, geen herhalende patronen.
  Triggers: "website bouwen", "development", "coderen", "programmeren", "Next.js",
  "HTML site", "React", "Tailwind", "frontend", "backend",
  "responsive maken", "componenten bouwen", "pagina bouwen".
version: 4.0.0
---

# Website Development — Next-Level Designbureau-kwaliteit

## DE GOUDEN REGEL

Elke website moet eruitzien alsof een **Awwwards-winnend designbureau** er weken aan heeft gewerkt. **Foto-gedreven. Video-verrijkt. Cinematische composities. Interactieve ervaringen.**

## LEES ALTIJD EERST

1. **CLAUDE.md** — designregels, verboden fonts, verplichte technieken
2. **visual-design SKILL.md** — Unsplash-fotografie, stockvideo, Envato-inspiratie, layout-patronen

## ABSOLUUT VERBODEN — Zero Tolerance

| VERBODEN element | VERPLICHT alternatief |
|---|---|
| Iconen (emoji, Unicode, Font Awesome) als dienst-illustratie | Echte foto's per dienst, full-bleed of als card met hover |
| Gekleurde vlakken met tekst zonder foto | Foto-achtergronden met gradient overlay |
| Placehold.co, grijze vakken, "hier komt uw foto" | Echte Unsplash-foto's (min. 10-15 per site) |
| Hero→Cards→About→Services→CTA→Footer flow | Unieke compositie per project |
| Eenvoudige `opacity: 0 → 1` als enige animatie | Minstens 5 verschillende animatie-types |
| Statische tekst die gewoon "staat" | Text-reveal, staggered entry, of scroll-triggered animatie |
| Vlakke egale achtergrondkleur als enige achtergrond | Gradient mesh, noise texture, foto, of video-achtergrond |
| Generic card-grid met icoon + titel + tekst | Foto-gedreven kaarten met hover-reveal, 3D tilt, of parallax |
| Standaard knop (background-color + border-radius) | Animated buttons (magnetic, ripple, slide-fill, outline-to-fill) |
| Statische pagina zonder enige interactiviteit | Minstens 2 interactieve elementen (slider, tabs, accordion, etc.) |

## PREMIUM ANIMATIE-TOOLKIT

### 1. Text Reveal Animaties (VERPLICHT op hero + minstens 2 secties)

```css
@keyframes revealChar {
  from { opacity: 0; transform: translateY(100%) rotateX(-80deg); }
  to { opacity: 1; transform: translateY(0) rotateX(0); }
}
.text-reveal span {
  display: inline-block; opacity: 0;
  animation: revealChar 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
```

```javascript
function splitText(selector) {
  document.querySelectorAll(selector).forEach(el => {
    const text = el.textContent;
    el.innerHTML = '';
    text.split('').forEach((char, i) => {
      const span = document.createElement('span');
      span.textContent = char === ' ' ? '\u00A0' : char;
      span.style.animationDelay = `${i * 0.04}s`;
      el.appendChild(span);
    });
  });
}
```

### 2. Scroll-Driven Animaties (VERPLICHT)

```javascript
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const el = entry.target;
      setTimeout(() => el.classList.add('visible'), el.dataset.delay || 0);
      if (el.dataset.counter) animateCounter(el);
      revealObserver.unobserve(el);
    }
  });
}, { threshold: 0.15, rootMargin: '0px 0px -80px 0px' });
document.querySelectorAll('[data-reveal]').forEach(el => revealObserver.observe(el));

window.addEventListener('scroll', () => {
  const progress = window.scrollY / (document.body.scrollHeight - window.innerHeight);
  document.querySelector('.scroll-progress')?.style.setProperty('--progress', progress);
});
```

### 3. Parallax Layers (VERPLICHT op minstens 2 secties)

```javascript
function initParallax() {
  const layers = document.querySelectorAll('[data-speed]');
  window.addEventListener('scroll', () => {
    layers.forEach(layer => {
      const speed = parseFloat(layer.dataset.speed);
      const offset = (layer.getBoundingClientRect().top - window.innerHeight / 2) * speed;
      layer.style.transform = `translateY(${offset}px)`;
    });
  }, { passive: true });
}
```

### 4. Magnetic Buttons (VERPLICHT op primaire CTA's)

```javascript
document.querySelectorAll('.magnetic-btn').forEach(btn => {
  btn.addEventListener('mousemove', (e) => {
    const rect = btn.getBoundingClientRect();
    btn.style.transform = `translate(${(e.clientX-rect.left-rect.width/2)*0.3}px, ${(e.clientY-rect.top-rect.height/2)*0.3}px)`;
  });
  btn.addEventListener('mouseleave', () => {
    btn.style.transform = 'translate(0,0)';
    btn.style.transition = 'transform 0.5s cubic-bezier(0.16,1,0.3,1)';
  });
  btn.addEventListener('mouseenter', () => { btn.style.transition = 'none'; });
});
```

### 5. 3D Card Tilt (VERPLICHT op service/portfolio cards)

```javascript
document.querySelectorAll('.tilt-card').forEach(card => {
  card.addEventListener('mousemove', (e) => {
    const rect = card.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    card.style.transform = `perspective(800px) rotateX(${(0.5-y)*15}deg) rotateY(${(x-0.5)*15}deg) scale(1.02)`;
  });
  card.addEventListener('mouseleave', () => {
    card.style.transform = 'perspective(800px) rotateX(0) rotateY(0) scale(1)';
    card.style.transition = 'transform 0.6s cubic-bezier(0.16,1,0.3,1)';
  });
  card.addEventListener('mouseenter', () => { card.style.transition = 'none'; });
});
```

### 6. Marquee / Ticker

```css
.marquee { overflow: hidden; white-space: nowrap; }
.marquee-content { display: inline-flex; gap: 4rem; animation: marquee 25s linear infinite; }
@keyframes marquee { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
```

### 7. Image Reveal on Scroll

```css
.image-reveal { clip-path: inset(0 100% 0 0); transition: clip-path 1.2s cubic-bezier(0.16,1,0.3,1); }
.image-reveal.visible { clip-path: inset(0 0 0 0); }
.image-reveal-center { clip-path: inset(0 50%); transition: clip-path 1s cubic-bezier(0.16,1,0.3,1); }
.image-reveal-center.visible { clip-path: inset(0 0); }
```

### 8. Animated Gradient Mesh

```css
.gradient-mesh {
  background: radial-gradient(at 20% 80%, var(--color-primary) 0%, transparent 60%),
    radial-gradient(at 80% 20%, var(--color-accent) 0%, transparent 60%),
    radial-gradient(at 50% 50%, var(--color-secondary) 0%, transparent 70%);
  background-size: 200% 200%;
  animation: meshMove 15s ease-in-out infinite alternate;
}
@keyframes meshMove {
  0% { background-position: 0% 0%, 100% 100%, 50% 50%; }
  50% { background-position: 100% 0%, 0% 100%, 30% 70%; }
  100% { background-position: 0% 50%, 100% 50%, 50% 50%; }
}
```

### 9. Noise/Grain Overlay

```css
.noise-overlay::after {
  content: ''; position: absolute; inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
  pointer-events: none; z-index: 1;
}
```

### 10. Counter Animatie

```javascript
function animateCounter(el) {
  const target = parseInt(el.dataset.counter);
  const suffix = el.dataset.suffix || '';
  const prefix = el.dataset.prefix || '';
  let current = 0;
  const step = target / (2000 / 16);
  const timer = setInterval(() => {
    current += step;
    if (current >= target) { current = target; clearInterval(timer); }
    el.textContent = prefix + Math.floor(current).toLocaleString('nl-BE') + suffix;
  }, 16);
}
```

## VIDEO-INTEGRATIE (VERPLICHT waar passend)

### Video-achtergrond Hero

```html
<section class="video-hero">
  <video autoplay muted loop playsinline class="video-bg">
    <source src="VIDEO_URL" type="video/mp4">
  </video>
  <div class="video-overlay"></div>
  <div class="hero-content">
    <h1 class="text-reveal mega">Vakmanschap<br>in beweging</h1>
    <a href="#contact" class="magnetic-btn btn-slide"><span>Neem contact op →</span></a>
  </div>
</section>
```

```css
.video-hero { position: relative; min-height: 100vh; overflow: hidden; display: flex; align-items: center; }
.video-bg { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.video-overlay { position: absolute; inset: 0; background: linear-gradient(135deg, rgba(0,0,0,0.7), rgba(0,0,0,0.3)); }
.hero-content { position: relative; z-index: 2; }
@media (max-width: 768px) {
  .video-bg { display: none; }
  .video-hero { background: linear-gradient(135deg, rgba(0,0,0,0.7), rgba(0,0,0,0.3)), url('fallback.jpg') center/cover; }
}
```

### Gratis videobronnen

| Bron | URL | Gebruik |
|------|-----|---------|
| Coverr | coverr.co | MP4, gratis commercieel |
| Pexels Video | pexels.com/videos | MP4, gratis commercieel |
| Pixabay Video | pixabay.com/videos | MP4, gratis |

**Video-regels:** autoplay muted loop playsinline, fallback-foto mobile, max 10-15s loop, donkere overlay, max 1 video per pagina.

## INTERACTIEVE ELEMENTEN (VERPLICHT — minstens 2 per site)

### Before/After Slider
```javascript
document.querySelectorAll('.before-after').forEach(ba => {
  const slider = ba.querySelector('.slider-handle');
  slider.addEventListener('input', (e) => {
    ba.querySelector('.after-img').style.clipPath = `inset(0 ${100-e.target.value}% 0 0)`;
    ba.querySelector('.slider-line').style.left = `${e.target.value}%`;
  });
});
```

### Animated Tabs
```javascript
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.tab-panel').forEach(panel => {
      if (panel.id === btn.dataset.tab) {
        panel.style.display = 'block';
        requestAnimationFrame(() => panel.classList.add('active'));
      } else {
        panel.classList.remove('active');
        setTimeout(() => panel.style.display = 'none', 400);
      }
    });
  });
});
```

### Animated Accordion
```javascript
document.querySelectorAll('.accordion-trigger').forEach(trigger => {
  trigger.addEventListener('click', () => {
    const content = trigger.nextElementSibling;
    const isOpen = trigger.classList.contains('open');
    document.querySelectorAll('.accordion-trigger.open').forEach(t => {
      t.classList.remove('open'); t.nextElementSibling.style.maxHeight = '0px';
    });
    if (!isOpen) { trigger.classList.add('open'); content.style.maxHeight = content.scrollHeight + 'px'; }
  });
});
```

### Horizontal Scroll Gallery
```css
.horizontal-scroll-section { position: relative; }
.horizontal-track { position: sticky; top: 0; display: flex; gap: 2rem; height: 100vh; align-items: center; padding: 0 4rem; }
.horizontal-item { flex-shrink: 0; width: 70vw; max-width: 800px; border-radius: 16px; overflow: hidden; }
.horizontal-item img { width: 100%; height: 60vh; object-fit: cover; transition: transform 0.5s; }
.horizontal-item:hover img { transform: scale(1.03); }
```

## GLASSMORPHISM & MODERNE EFFECTEN

```css
.glass { background: rgba(255,255,255,0.08); backdrop-filter: blur(20px); border: 1px solid rgba(255,255,255,0.12); border-radius: 16px; }
.glass-dark { background: rgba(0,0,0,0.3); backdrop-filter: blur(24px); border: 1px solid rgba(255,255,255,0.08); }
.glow { box-shadow: 0 0 30px rgba(var(--color-primary-rgb),0.3), 0 0 60px rgba(var(--color-primary-rgb),0.1); }
```

## BUTTON-STIJLEN

```css
.btn-slide { position: relative; overflow: hidden; border: 2px solid var(--color-primary); color: var(--color-primary); background: transparent; padding: 1rem 2.5rem; font-weight: 600; }
.btn-slide::before { content: ''; position: absolute; inset: 0; background: var(--color-primary); transform: translateX(-101%); transition: transform 0.4s cubic-bezier(0.16,1,0.3,1); z-index: -1; }
.btn-slide:hover { color: white; }
.btn-slide:hover::before { transform: translateX(0); }
```

## PREMIUM FORMULIER (floating labels)

```css
.form-group { position: relative; margin-bottom: 2rem; }
.form-group input, .form-group textarea { width: 100%; padding: 1rem 0; border: none; border-bottom: 2px solid rgba(var(--color-primary-rgb),0.2); background: transparent; font-size: 1rem; }
.form-group label { position: absolute; left: 0; top: 1rem; transition: all 0.3s; color: #999; pointer-events: none; }
.form-group input:focus ~ label, .form-group input:valid ~ label,
.form-group textarea:focus ~ label, .form-group textarea:valid ~ label { top: -0.75rem; font-size: 0.75rem; color: var(--color-primary); }
```

## CSS CUSTOM PROPERTIES

```css
:root {
  --color-primary: #XXXXXX;
  --color-primary-rgb: XX, XX, XX;
  --color-secondary: #XXXXXX;
  --color-accent: #XXXXXX;
  --color-dark: #1a1a2e;
  --color-light: #f8f8f8;
  --font-heading: 'FontNaam', serif;
  --font-body: 'FontNaam', sans-serif;
  --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
  --section-padding: clamp(4rem, 8vw, 8rem);
  --container-width: min(1200px, 90vw);
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
.scroll-progress { position: fixed; top: 0; left: 0; width: 100%; height: 3px; background: var(--color-primary); transform: scaleX(var(--progress, 0)); transform-origin: left; z-index: 9999; }
```

## VOORBEELD-COMPOSITIES

**"The Cinematic"**: Video-hero text-reveal → Animated counters → Horizontal scroll portfolio → Parallax foto-band → Before/after slider → Marquee ticker → Glass testimonial → Dark CTA magnetic → Mega footer

**"The Interactive"**: Split hero 3D tilt → Staggered image-reveals → Tabbed crossfade → Parallax floating stats → Accordion FAQ → Gallery hover-reveal → Gradient mesh CTA → Photo footer

**"The Storyteller"**: Minimal hero character-split → Scroll timeline → Zigzag image-reveals → Video sectie → Magazine 3D tilt cards → Large testimonial → Marquee logos → Slide-fill CTA → Mega footer

**"The Premium"**: Mega-typografie foto achter letters → Noise gradient mesh → Sticky scroll diensten → Diagonal foto → Glass cards → Horizontal gallery → Dark counters → Magnetic contact

## KWALITEITSCHECK

- [ ] 10+ echte Unsplash-foto's homepage?
- [ ] GEEN iconen als foto-vervanging?
- [ ] Video-element waar passend?
- [ ] 5+ animatie-types?
- [ ] 2+ interactieve elementen?
- [ ] Magnetic buttons op CTA's?
- [ ] 3D tilt/hover-reveal op cards?
- [ ] Text-reveal op hero?
- [ ] Scroll-progress indicator?
- [ ] Unieke compositie?
- [ ] Diagonale/overlappende elementen?
- [ ] Full-bleed foto + overlay?
- [ ] Glass/gradient mesh effect?
- [ ] Noise/grain overlay?
- [ ] Premium floating-label formulier?
- [ ] Mobile responsive + video fallback?
- [ ] prefers-reduced-motion?
- [ ] Geen verboden fonts?
- [ ] Echte content, geen Lorem ipsum?
- [ ] Cookie banner + structured data?
