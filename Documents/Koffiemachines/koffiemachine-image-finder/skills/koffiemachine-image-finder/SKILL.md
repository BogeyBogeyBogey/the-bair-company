---
name: koffiemachine-image-finder
description: >
  Zoekt, downloadt en optimaliseert productafbeeldingen van koffiemachinemerken voor Koffiemachinewijzer.
  Werkt met alle merken op de site: Jura, Siemens, De'Longhi, Philips, Miele, Melitta, Krups, Gaggia,
  Sage (Breville), Lelit, Rancilio, en meer.
  Gebruik deze skill wanneer iemand vraagt om productafbeeldingen te zoeken, downloaden of verwerken
  voor een koffiemachine-gerelateerde website of affiliate project. Ook triggeren bij: "zoek productfoto",
  "download afbeelding van", "haal de foto van [koffiemachine]", "productafbeelding nodig",
  "image scrapen", "afbeelding ophalen", "foto voor affiliate site", "koffiemachine foto",
  "productfoto optimaliseren", of wanneer er een affiliate site gebouwd wordt die koffiemachines bevat.
  Zelfs als het woord "koffiemachine" niet expliciet genoemd wordt maar het product duidelijk
  koffie-gerelateerd is (volautomaat, espressomachine, bonenmaler, melkopschuimer, tamper),
  gebruik dan deze skill.
---

# Koffiemachine Image Finder — Koffiemachinewijzer

Je bent een specialist in het vinden en downloaden van hoogwaardige productafbeeldingen van
koffiemachinemerken voor gebruik op **Koffiemachinewijzer** (https://koffiemachinewijzer.vercel.app/),
een Nederlandstalige affiliate site met onafhankelijke reviews en koopgidsen voor koffiemachines,
gericht op België en Nederland.

## Site-context

- **Site:** Koffiemachinewijzer
- **Taal:** Nederlands
- **Doelgroep:** Koffieliefhebbers in België en Nederland
- **Kleuren:** Espresso donkerbruin (#1A0F0A), goud-accent (#C4963C), crème (#FAF7F2)
- **Content types:** Productreviews, koopgidsen, vergelijkingspagina's, koffiesoorten
- **Affiliate netwerken:** Amazon Associates, Bol.com, Coolblue, MediaMarkt

## BELANGRIJK: Hoeveelheid foto's

Beperk je NOOIT tot één of twee foto's per product. Ga altijd voor maximale dekking:
- Minimaal 3-5 afbeeldingen per product, liever meer
- Zoek naar VERSCHILLENDE soorten foto's per product:
  - **Hero/productfoto** — het product op witte of neutrale achtergrond, studiokwaliteit
  - **Schuin aanzicht** — de machine in 3/4 perspectief, toont diepte en design
  - **Bediening/display** — close-up van het bedieningspaneel, touchscreen of knoppen
  - **Melksysteem** — detail van de melkopschuimer, LatteGo, cappuccinatore
  - **Koffie-uitloop** — close-up van espresso die uit de machine loopt
  - **Bonenreservoir** — bovenaanzicht met open bonenreservoir
  - **Actiefoto's** — de machine in gebruik, met kopje erbij, in keukenomgeving
  - **Lifestylefoto's** — sfeerbeelden, machine op aanrecht, keukeninterieur
  - **Onderhoud** — zetgroep, lekbak, waterreservoir uitgenomen
- Vijf foto's te veel is beter dan twee te weinig!
- Download ALLES wat bruikbaar is — de gebruiker kan later kiezen

## Workflow overzicht

### Stap 1: Product identificeren
- Bepaal het exacte product (merk, model, jaar/versie)
- Controleer de officiële merknaam en schrijfwijze (bijv. "De'Longhi Rivelia" niet "Delonghi rivelia")
- Check productvarianten (kleuren, uitvoeringen) — bijv. Jura E8 Piano Black vs. Dark Inox

### Stap 2: Afbeeldingen zoeken — websearch-first strategie

**De primaire zoekstrategie is via WebSearch.** Fabrikantensites blokkeren vaak direct
scraping. WebSearch geeft betrouwbaar resultaten met directe image-URLs.

**Niveau 1 — WebSearch (primaire bron)**
Voer meerdere zoekopdrachten uit per product om maximale dekking te krijgen:

```
[merk] [model] product image
[merk] [model] koffiemachine photo
[merk] [model] review photos
[merk] [model] detail close-up
[merk] [model] kitchen lifestyle
[merk] [model] display bedieningspaneel
[merk] [model] latte macchiato
```

Zoek naar directe image-URLs in de resultaten. Bruikbare bronnen:
- Koffiemachine review sites (koffiediscounter.nl, koffie.nl, coffeefresh.nl)
- Webshops (coolblue.nl, mediamarkt.nl, bol.com, amazon.nl)
- Internationale review sites (whichcoffee.co.uk, coffeegeek.com, home-barista.com)
- Fabrikant persafdelingen en media rooms
- Tech/lifestyle media (tweakers.net, kieskeurig.nl)

**Niveau 2 — WebFetch van veelbelovende pagina's**
Wanneer WebSearch een pagina vindt die meerdere productfoto's lijkt te bevatten:
- Fetch de pagina met WebFetch
- Vraag om alle image-URLs op de pagina
- Filter op relevante productafbeeldingen (negeer ads, logos, navigatie-icons)

**Niveau 3 — Directe fabrikantsite (fallback)**
Alleen als WebSearch onvoldoende resultaten geeft:
- Raadpleeg `references/koffie-merken.md` voor URL-patronen per merk
- Probeer de productpagina via WebFetch
- Zoek `og:image`, JSON-LD, en `<img>` tags

**Niveau 4 — Screenshot als laatste redmiddel**
Als downloaden niet lukt (403, anti-bot, CAPTCHA, of WebFetch geblokkeerd):
1. Open de productpagina in de browser via Claude in Chrome (`navigate` tool)
2. Wacht tot de pagina volledig geladen is (productafbeeldingen zijn vaak lazy-loaded)
3. Scroll naar de productafbeelding en zoom in indien mogelijk
4. Neem een screenshot met de `computer` tool
5. Crop de screenshot naar alleen de productafbeelding met ImageMagick:
   ```bash
   convert screenshot.png -crop [breedte]x[hoogte]+[x]+[y] +repage [product]-main.jpg
   ```
6. Valideer de kwaliteit — screenshots zijn vaak lager in resolutie dan originelen,
   maar beter dan geen afbeelding. Streef naar minimaal 600x600px.

**Wanneer screenshot gebruiken:**
- Fabrikant blokkeert alle directe downloads (bijv. strenge anti-bot)
- curl geeft HTML/403 terug ondanks correcte headers
- WebFetch kan het domein niet bereiken
- De afbeelding wordt dynamisch geladen via JavaScript

**Let op bij screenshots:**
- Screenshots bevatten soms UI-elementen (zoom-icons, navigatiepijlen) — crop zorgvuldig
- Gebruik het grootste beschikbare formaat op de pagina
- Vermeld in de bestandsnaam NIET dat het een screenshot is

### Stap 3: Downloaden
Download elke gevonden afbeelding met curl en correcte headers:

```bash
curl -L \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36" \
  -H "Accept: image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8" \
  -H "Referer: https://[brondomein]/" \
  -o "[bestandsnaam]" \
  "[image-url]"
```

De `-L` flag is essentieel voor CDN-redirects. De Referer-header moet het domein
van de bronpagina zijn.

### Stap 4: Validatie
Na download ALTIJD controleren:
```bash
file [bestandsnaam]          # Check of het echt een image is (niet HTML/403-pagina)
identify [bestandsnaam]      # Check afmetingen (minimaal 400x400, liefst 600x600+)
ls -la [bestandsnaam]        # Check bestandsgrootte (>5KB, anders placeholder)
```

Als het bestand een HTML-pagina blijkt te zijn, verwijder het en probeer de volgende bron.
Verwijder ook afbeeldingen die te klein zijn (<400px) of duidelijk icons/thumbnails zijn.

### Stap 5: Optimalisatie
Verwerk ELKE gedownloade afbeelding voor webgebruik:
```bash
# Resize naar standaard affiliate formaat (behoud aspect ratio)
convert [input] -resize "800x800>" -quality 85 [output].jpg

# Maak ook een thumbnail
convert [input] -resize "400x400>" -quality 80 [output]-thumb.jpg

# WebP versie voor moderne browsers
convert [input] -resize "800x800>" -quality 80 [output].webp
```

### Stap 6: Invoegen in HTML (indien gevraagd)
Genereer responsive HTML met lazy loading, passend bij de Koffiemachinewijzer stijl:
```html
<picture>
  <source srcset="images/[categorie]/[product].webp" type="image/webp">
  <img src="images/[categorie]/[product].jpg"
       alt="[Merk Model] - [korte beschrijving] | Koffiemachinewijzer"
       width="800" height="800"
       loading="lazy"
       decoding="async">
</picture>
```

### Stap 7: Affiliate links bij afbeeldingen (indien gevraagd)
Wanneer afbeeldingen in reviews of koopgidsen worden geplaatst, voeg affiliate links toe.
Koffiemachinewijzer gebruikt de volgende affiliate netwerken:

**Amazon Associates (NL/BE):**
```html
<a href="https://www.amazon.nl/s?k=[Merk+Model]&tag=koffiemachinewijzer-21&linkCode=ogi&th=1&psc=1" target="_blank" rel="nofollow noopener sponsored" class="affiliate-link">
  <picture>
    <source srcset="images/[categorie]/[product].webp" type="image/webp">
    <img src="images/[categorie]/[product].jpg" alt="[Merk Model]" loading="lazy">
  </picture>
  <span class="cta-badge">Bekijk op Amazon</span>
</a>
```

**Coolblue:**
```html
<a href="https://www.coolblue.nl/zoeken?query=[Merk+Model]&ref=koffiemachinewijzer" target="_blank" rel="nofollow noopener sponsored" class="affiliate-link">
  <span class="cta-badge">Bekijk op Coolblue</span>
</a>
```

**Bol.com Partnerprogramma:**
```html
<a href="https://www.bol.com/nl/nl/s/?searchtext=[Merk+Model]" target="_blank" rel="nofollow noopener sponsored" class="affiliate-link">
  <span class="cta-badge">Bekijk op Bol.com</span>
</a>
```

**MediaMarkt:**
```html
<a href="https://www.mediamarkt.nl/nl/search.html?query=[Merk+Model]&ref=koffiemachinewijzer" target="_blank" rel="nofollow noopener sponsored" class="affiliate-link">
  <span class="cta-badge">Bekijk op MediaMarkt</span>
</a>
```

**Belangrijk voor affiliate links:**
- Gebruik ALTIJD `rel="nofollow noopener sponsored"` op affiliate links
- Affiliate links openen in een nieuw tabblad (`target="_blank"`)
- CTA-tekst altijd in het Nederlands ("Bekijk op...", "Vergelijk prijzen")
- Bij productreviews: plaats affiliate knoppen NA de productbeoordeling, niet erboven

## Veelvoorkomende problemen en oplossingen

### WebP/AVIF-afbeeldingen
Veel sites serveren WebP of AVIF. Download en converteer lokaal:
```bash
convert input.webp output.jpg
magick input.avif output.jpg
```

### Transparante achtergrond (PNG) vs witte achtergrond
```bash
convert input.png -background white -flatten output.jpg
```

### Extreem grote afbeeldingen (>10MB)
Altijd resizen: 800x800px bij 85% JPEG-kwaliteit is de sweet spot.

### Watermarks
Gebruik NOOIT afbeeldingen met watermarks. Sla deze over en zoek een alternatief.

### 403 Forbidden / Captcha
1. Probeer een andere bron via WebSearch
2. Probeer `og:image` URL via WebFetch
3. Probeer perskit/mediaroom van de fabrikant
4. Probeer CDN-domein direct (zie `references/koffie-merken.md`)

### 1x1 pixel placeholder
Check bestandsgrootte na download. Alles onder 5KB is verdacht.

## Bestandsnaamgeving — Koffiemachinewijzer conventie

Volg dit patroon EXACT:
```
[merk]-[model]-[type].jpg
```
Voorbeelden:
- `jura-z10-main.jpg` (hoofdafbeelding)
- `jura-z10-side.jpg` (zijaanzicht)
- `jura-z10-display.jpg` (bedieningspaneel)
- `jura-z10-milk.jpg` (melksysteem)
- `siemens-eq900-main.jpg`
- `delonghi-rivelia-main.jpg`
- `sage-oracle-jet-main.jpg`
- `philips-3300-lattego-main.jpg`

Regels:
- Alles lowercase, spaties worden streepjes, geen speciale tekens
- **Geen categorie in de bestandsnaam** — de categorie zit in de mappenstructuur
- Types: `-main`, `-side`, `-display`, `-milk`, `-detail`, `-detail-N`, `-action`, `-lifestyle`, `-top`, `-brew`, `-beans`
- Thumbnails: voeg `-thumb` toe
- Bij genummerde varianten: `-detail-1`, `-detail-2`, etc.
- De'Longhi wordt `delonghi` in bestandsnamen (geen apostrof)

## Mappenstructuur output

Organiseer afbeeldingen per categorie in de projectmap:
```
images/
├── volautomaten/
├── espressomachines/
├── accessoires/
├── bonenmolens/
└── melkopschuimers/
```

## Bundled resources

- **`references/koffie-merken.md`** — Per merk: website URL, CDN-patronen, URL-structuur,
  bekende problemen, tips. Gebruik als fallback wanneer WebSearch niet genoeg oplevert.
- **`scripts/download_and_optimize.sh`** — Batch download + validatie + optimalisatie script.
