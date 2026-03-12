---
name: client-briefing
description: >
  Automatische URL-analyse, website-research, visuele inspiratie én videocontent verzamelen.
  Triggers: "nieuw project", "website analyseren", "URL onderzoeken", "site research",
  "website scrapen", "bestaande site analyseren", "url research".
version: 4.0.0
---

# URL Research, Visuele Inspiratie & Videocontent

Analyseer een bestaande website EN verzamel visuele inspiratie + videocontent voor het nieuwe design. Geen vragen aan de gebruiker — alles wordt automatisch afgeleid.

## Fase 1: Website scrapen

### Stap 1: Website openen en navigatiestructuur in kaart brengen

1. **Open de URL** via Chrome browser tools (tabs_context_mcp → navigate)
2. **Lees de volledige pagina-inhoud** via get_page_text of read_page
3. **Identificeer de navigatie** — klik door het hoofdmenu en noteer alle pagina's
4. **Bezoek ELKE pagina** en extraheer:
   - Paginatitel (H1)
   - Volledige tekst-inhoud
   - Afbeeldingen en hun alt-teksten
   - CTA's (calls-to-action)
   - Formulieren en hun velden

### Stap 2: Bedrijfsinformatie extraheren

Zoek op de website naar:
- **Bedrijfsnaam** (logo, title tag, footer)
- **Adres** (contactpagina, footer, Google Maps embed)
- **Telefoon** (contactpagina, header, footer)
- **Email** (contactpagina, footer)
- **BTW-nummer** (footer, juridische pagina's)
- **Social media** (footer links naar Facebook, Instagram, LinkedIn, etc.)
- **Openingsuren** (als vermeld)

### Stap 3: Diensten/producten inventariseren

- Maak een lijst van alle aangeboden diensten of producten
- Noteer per dienst: naam, korte beschrijving, eventuele prijzen
- Identificeer de USP's (unique selling points) van het bedrijf

### Stap 4: Logo's en beeldmateriaal van de originele site ophalen

**CRUCIAAL: Bestaande beelden hebben ALTIJD voorrang.**

1. **Logo ophalen:**
   - Gebruik Chrome javascript_tool om het logo te vinden:
     ```javascript
     // Logo zoeken
     const logos = [];
     document.querySelectorAll('img').forEach(img => {
       const src = img.src || '';
       const alt = (img.alt || '').toLowerCase();
       const cl = (img.className || '').toLowerCase();
       if (alt.includes('logo') || cl.includes('logo') || src.includes('logo')) {
         logos.push({ src: img.src, alt: img.alt, width: img.naturalWidth, height: img.naturalHeight });
       }
     });
     // Zoek ook in CSS achtergronden en SVG's
     document.querySelectorAll('[class*="logo"], [id*="logo"], header img, .navbar img').forEach(el => {
       if (el.src) logos.push({ src: el.src, alt: el.alt || 'logo', width: el.naturalWidth, height: el.naturalHeight });
     });
     JSON.stringify(logos);
     ```
   - Neem indien nodig een **screenshot** van het logo-element
   - Noteer de logo-URL in site-research.md

2. **Alle foto's van de originele site inventariseren:**
   ```javascript
   const images = [];
   document.querySelectorAll('img').forEach(img => {
     if (img.naturalWidth > 200 && img.naturalHeight > 200) { // Filter kleine iconen weg
       images.push({
         src: img.src,
         alt: img.alt,
         width: img.naturalWidth,
         height: img.naturalHeight,
         location: img.closest('section')?.className || img.closest('div')?.className || 'unknown'
       });
     }
   });
   JSON.stringify(images);
   ```

3. **Per foto beoordelen:**
   - Is de resolutie hoog genoeg? (minimaal 800px breed voor secties, 1200px voor hero)
   - Is de kwaliteit professioneel? (scherp, goede belichting, niet pixelig)
   - Past de foto bij het nieuwe premium design?

4. **Beelden categoriseren in 3 niveaus:**

   | Prioriteit | Bron | Wanneer gebruiken |
   |------------|------|-------------------|
   | **1. ALTIJD** | Logo van de originele site | Altijd het echte logo overnemen |
   | **2. BIJ VOORKEUR** | Eigen foto's van de klant (hoge kwaliteit) | Teamfoto's, werkplaats, producten, pand — als ze scherp en professioneel zijn |
   | **3. AANVULLEN** | Unsplash / Pexels / Pixabay | Waar originele beelden ontbreken of niet hoogwaardig genoeg zijn |

5. **Herhaal voor ELKE pagina** van de originele site — niet alleen de homepage

### Stap 5: Visuele stijl analyseren

Gebruik Chrome javascript_tool om CSS-waarden te extraheren:

```javascript
// Kleuren extraheren
const allElements = document.querySelectorAll('*');
const colors = new Set();
allElements.forEach(el => {
  const style = getComputedStyle(el);
  colors.add(style.color);
  colors.add(style.backgroundColor);
});
JSON.stringify([...colors].filter(c => c !== 'rgba(0, 0, 0, 0)'));
```

```javascript
// Fonts extraheren
const fonts = new Set();
document.querySelectorAll('*').forEach(el => {
  fonts.add(getComputedStyle(el).fontFamily);
});
JSON.stringify([...fonts]);
```

### Stap 6: Aanvullend online onderzoek

Gebruik WebSearch voor:
- Google "[bedrijfsnaam]" voor reviews, nieuws, social media
- Check Google Maps voor locatie en reviews
- Bekijk social media profielen voor extra content en tone of voice
- Zoek concurrenten in dezelfde sector en regio

### Stap 7: Taal en tone of voice bepalen

- In welke taal/talen is de site? (NL, FR, EN)
- Is de aanspreking formeel (u) of informeel (je)?
- Is de toon zakelijk, warm, speels, technisch?

---

## Fase 2: Visuele inspiratie verzamelen

### Stap 8: Unsplash-foto's zoeken (AANVULLEND op originele beelden)

Unsplash-foto's worden gebruikt om het beeldmateriaal van de klant **aan te vullen** — niet te vervangen. Gebruik Unsplash voor:
- Categorieën waar de klant geen eigen foto's heeft
- Sfeer/achtergrond-beelden die het design verrijken
- Wanneer de foto's van de klant niet hoogwaardig genoeg zijn

1. Gebruik WebSearch om sector-specifieke Unsplash-foto's te vinden:
   ```
   site:unsplash.com [sector engelse zoekterm]
   site:unsplash.com [specifieke dienst engelse zoekterm]
   ```

2. Open de gevonden Unsplash-pagina's via Chrome MCP

3. Kopieer de directe foto-URL's (formaat: `https://images.unsplash.com/photo-XXXXX`)

4. Verzamel minimaal **10-15 foto's** in categorieën:
   - **Hero** (2-3 brede, dramatische foto's)
   - **Diensten** (1-2 per dienst)
   - **Sfeer/achtergrond** (2-3 texturen, details, materialen)
   - **Team/werkplaats** (1-2)
   - **Detail/close-up** (1-2)

### Stap 9: Videocontent zoeken (VERPLICHT)

Video's tillen een website naar premium niveau. Zoek ALTIJD naar bruikbare video's.

1. **Zoek op Pexels Video:**
   ```
   WebSearch: "site:pexels.com/video [sector engelse zoekterm]"
   WebSearch: "pexels free video [specifieke dienst]"
   ```

2. **Zoek op Coverr.co:**
   ```
   WebSearch: "site:coverr.co [sector zoekterm]"
   ```

3. **Zoek op Pixabay Video:**
   ```
   WebSearch: "site:pixabay.com/videos [sector zoekterm]"
   ```

4. Open resultaten via Chrome MCP en kopieer directe video-URL's

5. Verzamel **minimaal 2-4 video's**:
   - **Hero-video** (1): breed, sfeerbepalend, 15-30 seconden loop
   - **Statement-band video** (1): korter, abstract of detail, 10-20 seconden
   - **Optioneel per dienst** (1-2): dienst-specifieke beelden

6. **Per video noteer**:
   - Directe URL (MP4 bij voorkeur)
   - Beschrijving van de inhoud
   - Geschiktheid: hero / statement-band / dienst-achtergrond
   - Unsplash fallback-foto URL (voor mobile)

### Stap 10: Template-inspiratie zoeken

Zoek premium website-ontwerpen als inspiratiebron:

1. WebSearch:
   ```
   themeforest [sector] website template best seller 2024 2025
   awwwards [sector] website design
   dribbble [sector] landing page design
   ```

2. Open 2-3 resultaten via Chrome MCP en neem **screenshots**

3. Analyseer en noteer per voorbeeld:
   - Layout-patronen (hoe zijn secties opgebouwd?)
   - Foto-gebruik (hoe worden foto's geïntegreerd?)
   - **Video-gebruik** (hebben ze video? Waar? Hoe?)
   - Typografische effecten (mega-koppen, overlapping?)
   - Kleurgebruik (contrast, donker/licht wisselingen?)
   - **Interactieve elementen** (tabs, sliders, accordions, hover-effecten?)
   - **Glassmorphism, blur, overlay-effecten?**
   - Animaties en interacties
   - Wat maakt het UNIEK en premium?

4. Kies 5-7 specifieke designtechnieken die je wilt toepassen

### Stap 11: Concurrenten bekijken

1. WebSearch: "[sector] [locatie] website"
2. Open 1-2 concurrenten via Chrome MCP
3. Neem screenshots en noteer: wat doen zij goed? Wat kan beter?
4. Zorg dat het nieuwe ontwerp BETER is dan de concurrentie

---

## Output

Sla ALLES op als `site-research.md` in de projectmap:

```markdown
# Site Research: [Bedrijfsnaam]

## Bedrijfsgegevens
- Naam: ...
- Adres: ...
- Telefoon: ...
- Email: ...
- Website: [originele URL]
- Social media: ...
- BTW: ...
- Openingsuren: ...

## Sector & Type
- Sector: ...
- Type bedrijf: ...
- Doelgroep: ...
- USP's: ...

## Diensten/Producten
1. [Dienst] — [beschrijving]
2. [Dienst] — [beschrijving]

## Paginastructuur (huidige site)
- Homepage
- [pagina's]

## Content per pagina
### Homepage
[Volledige tekst]
### [Andere pagina's]
[Volledige tekst]

## Visuele stijl (huidige site)
- Kleuren: ...
- Fonts: ...
- Sfeer: ...
- Platform: ...

## Taal & Tone of Voice
- Talen: ...
- Aanspreking: je/u
- Toon: ...

## Online aanwezigheid
- Google reviews: ...
- Social media: ...
- Concurrenten: ...

---

## BEELDMATERIAAL

### Originele beelden van de klant
| Categorie | URL | Resolutie | Kwaliteit | Hergebruiken? |
|-----------|-----|-----------|-----------|---------------|
| Logo | [URL] | [bxh] | ✅ Goed | ✅ Ja |
| Teamfoto | [URL] | [bxh] | ⚠️ Matig | ❌ Nee, vervangen door Unsplash |
| ... | ... | ... | ... | ... |

### Unsplash foto's (aanvullend)
| Categorie | URL | Beschrijving |
|-----------|-----|-------------|
| Hero | https://images.unsplash.com/photo-XXX | [beschrijving] |
| Dienst 1 | https://images.unsplash.com/photo-XXX | [beschrijving] |
| ... | ... | ... |

### Video's verzameld
| Categorie | Platform | URL | Duur | Fallback foto |
|-----------|----------|-----|------|---------------|
| Hero-video | Pexels | [URL] | 20s | [Unsplash URL] |
| Statement-band | Coverr | [URL] | 15s | [Unsplash URL] |
| ... | ... | ... | ... | ... |

### Template-inspiratie
1. [Template/site naam] — [URL]
   - Opvallend: [wat maakt het goed]
   - Video-gebruik: [ja/nee, hoe]
   - Interactieve elementen: [tabs, sliders, etc.]
   - Toe te passen: [welke techniek overnemen]
2. ...

### Concurrentie-analyse
1. [Concurrent] — [URL]
   - Sterktes: ...
   - Zwaktes: ...
   - Onze kans: ...

### Gekozen designtechnieken
1. [Techniek 1] — bijv. video hero met text-reveal
2. [Techniek 2] — bijv. animated tabs voor diensten
3. [Techniek 3] — bijv. marquee band met klantennamen
4. [Techniek 4] — bijv. glassmorphism stats op parallax foto
5. [Techniek 5] — bijv. horizontal scroll portfolio
6. [Techniek 6] — bijv. magnetic buttons
7. [Techniek 7] — bijv. image reveal on scroll
```
