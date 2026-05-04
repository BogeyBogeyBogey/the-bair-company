# Koffiemachine Merken — Afbeeldingsbronnen & Patronen

Referentiegids per merk. Gebruik deze informatie bij het zoeken naar productafbeeldingen.
De informatie is gebaseerd op bekende patronen — URL-structuren kunnen veranderen, dus
verifieer altijd of de URL werkt.

---

## Inhoudsopgave

### Volautomaten
1. [Jura](#jura)
2. [Siemens](#siemens)
3. [De'Longhi](#delonghi)
4. [Philips](#philips)
5. [Miele](#miele)
6. [Melitta](#melitta)
7. [Krups](#krups)

### Espressomachines (halfautomaat)
8. [Sage (Breville)](#sage-breville)
9. [Gaggia](#gaggia)
10. [Lelit](#lelit)
11. [Rancilio](#rancilio)
12. [La Marzocco](#la-marzocco)
13. [ECM](#ecm)
14. [Rocket Espresso](#rocket-espresso)
15. [Bezzera](#bezzera)

### Bonenmolens
16. [Eureka](#eureka)
17. [Baratza](#baratza)
18. [Niche](#niche)
19. [Mahlkoenig](#mahlkoenig)
20. [Mazzer](#mazzer)

### Accessoires & Algemeen
21. [Algemene tips voor webshops](#webshop-tips)

---

## Jura

- **Site:** `jura.com` (regionaal: `nl.jura.com`, `be.jura.com`)
- **Productpagina patroon:** `/nl/producten/[categorie]/[productnaam]`
  - Bijv.: `nl.jura.com/nl/producten/volautomaten/z10-aluminium-black-15488`
- **Afbeeldingsbron:** Eigen CDN en Adobe Scene7
- **CDN:** `www.jura.com/-/media/` of `jura.scene7.com`
- **Producten op Koffiemachinewijzer:** Z10, S8, E8
- **Tips:**
  - Jura heeft uitstekende studiofotografie met consistente witte achtergronden
  - `og:image` is betrouwbaar en geeft de hero-afbeelding
  - De productgalerij heeft vaak 8-12 foto's per model (hero, zij, achter, display, bonen, melk)
  - Jura biedt een perskit via `jura.com/press` met hoge-res media
  - Zoek specifiek naar "Jura [model] press photo" voor studio-kwaliteit
  - Kleuren/varianten hebben aparte pagina's (Piano Black, Dark Inox, etc.)
- **Bekende issues:** Regionale redirects. Gebruik `nl.jura.com` of `int.jura.com` voor stabiele URLs.
  JavaScript-heavy site — `og:image` is vaak de betrouwbaarste route.

## Siemens

- **Site:** `siemens-home.bsh-group.com` (NL: `siemens-home.bsh-group.com/nl`)
- **Productpagina patroon:** `/nl/productlijst/[categorie]/[productnaam]`
  - Bijv.: `siemens-home.bsh-group.com/nl/productlijst/volautomatische-espressomachines/EQ900`
- **Afbeeldingsbron:** BSH Group CDN
- **CDN:** `media3.bsh-group.com/Images/` of `media.flixcar.com`
- **Producten op Koffiemachinewijzer:** EQ.900, EQ.6 Plus
- **Tips:**
  - Siemens/BSH heeft een uitgebreide productdatabank met standaard persfoto's
  - Zoek op artikelnummer (bijv. "TQ903R09" voor EQ.900) voor precieze resultaten
  - `og:image` werkt betrouwbaar
  - Coolblue en MediaMarkt hebben vaak uitstekende Siemens productfoto's
  - Siemens biedt vaak meerdere hoeken: front, 3/4, display detail, boven
- **Bekende issues:** De BSH-groep site is complex. Zoek liever via WebSearch op artikelnummer
  dan direct navigeren. Flixcar CDN URLs zijn stabiel en betrouwbaar.

## De'Longhi

- **Site:** `delonghi.com` (NL: `delonghi.com/nl-nl`, BE: `delonghi.com/nl-be`)
- **Productpagina patroon:** `/nl-nl/producten/koffie/[categorie]/[productnaam]`
  - Bijv.: `delonghi.com/nl-nl/producten/koffie/volautomatische-koffiemachines/rivelia-ecam450-65-s`
- **Afbeeldingsbron:** De'Longhi CDN
- **CDN:** `delonghi.widen.net/` of `www.delonghi.com/medias/`
- **Producten op Koffiemachinewijzer:** Rivelia, Magnifica Evo, Dinamica Plus
- **Tips:**
  - De'Longhi gebruikt Widen DAM (Digital Asset Management) — URLs zijn lang maar stabiel
  - Productpagina's hebben uitgebreide galerijen (soms 10+ foto's)
  - LatteCrema-systeem en koffiebereiding-actiefoto's zijn vaak beschikbaar
  - De'Longhi biedt kleurvarianten als afzonderlijke producten (Rivelia in zilver, zwart, beige, etc.)
  - Zoek "De'Longhi [model] press release" voor persmateriaal
  - `og:image` is betrouwbaar
- **Bekende issues:** De apostrof in "De'Longhi" kan problemen geven in URLs — gebruik `delonghi`
  in zoekopdrachten. Site is JavaScript-heavy, gebruik `og:image` als eerste optie.

## Philips

- **Site:** `philips.nl` of `philips.be`
- **Productpagina patroon:** `/c-p/[artikelnummer]/[productnaam]`
  - Bijv.: `philips.nl/c-p/EP3321_40/3300-serie-volautomatische-espressomachine`
- **Afbeeldingsbron:** Philips DAM / Scene7
- **CDN:** `images.philips.com/is/image/philipsconsumer/`
- **Producten op Koffiemachinewijzer:** 3300 LatteGo, 5400 LatteGo
- **Tips:**
  - Philips heeft een zeer gestructureerde CDN met voorspelbare URL-patronen
  - Artikelnummers (bijv. EP3321/40) zijn de sleutel — zoek altijd op artikelnummer
  - Scene7 CDN ondersteunt formaat-parameters: `?wid=800&hei=800&$pnglarge$`
  - Philips biedt consistente productfotografie met witte achtergrond
  - LatteGo-systeem foto's zijn populair en goed beschikbaar
  - Zoek ook op Philips persroom: `philips.com/a-w/about/news/archive/`
- **Bekende issues:** Philips site redirects op basis van geo-locatie. Gebruik `philips.nl`
  direct of voeg `/nl_NL/` toe aan de URL. Scene7 URLs zijn zeer betrouwbaar.

## Miele

- **Site:** `miele.nl` of `miele.be`
- **Productpagina patroon:** `/nl/e/[categorie]/[model]-[artikelnummer].htm`
  - Bijv.: `miele.nl/nl/e/volautomatische-koffiemachine-cm-7750/CM7750OBSW.htm`
- **Afbeeldingsbron:** Miele Media CDN
- **CDN:** `media.miele.com/`
- **Producten op Koffiemachinewijzer:** CM 7750, CM 5310
- **Tips:**
  - Miele heeft premium productfotografie van hoge kwaliteit
  - Zoek op model + artikelnummer (bijv. "CM 7750 OBSW") voor exacte resultaten
  - Miele's site heeft vaak interactieve 360° views — individuele frames zijn soms downloadbaar
  - `og:image` werkt goed
  - Miele-persdienst biedt hoge-res beelden: `miele.com/media/`
- **Bekende issues:** Miele sites zijn zwaar en traag — WebSearch + `og:image` is sneller dan scraping.

## Melitta

- **Site:** `melitta.com` of `melitta.nl`
- **Productpagina patroon:** `/nl/koffiemachines/volautomaat/[productnaam]/`
- **Afbeeldingsbron:** Eigen CDN
- **Producten op Koffiemachinewijzer:** Barista Smart TS
- **Tips:**
  - Melitta heeft eenvoudige, goed gestructureerde productpagina's
  - Productfoto's zijn vaak direct in `<img>` tags te vinden
  - Zoek op "Melitta [model] press photo" voor persfoto's
  - `og:image` is betrouwbaar
- **Bekende issues:** Minder issues dan premium merken — relatief dev-friendly.

## Krups

- **Site:** `krups.nl` of `krups.be` (onderdeel van Groupe SEB)
- **Productpagina patroon:** `/[categorie]/[productnaam]`
- **Afbeeldingsbron:** Groupe SEB CDN
- **Producten op Koffiemachinewijzer:** Evidence Plus
- **Tips:**
  - Krups/SEB sites delen CDN-infrastructuur met Tefal en Moulinex
  - Productfoto's zijn standaard-kwaliteit, consistent witte achtergrond
  - WebSearch via webshops (Coolblue, Bol.com) levert vaak betere foto's
- **Bekende issues:** Site kan traag zijn. Webshops zijn vaak een betere bron.

## Sage (Breville)

- **Site:** `sageappliances.com` (EU) of `breville.com` (VS/AU)
- **Productpagina patroon:** `/nl/espressomachines/[productnaam].html`
  - Bijv.: `sageappliances.com/nl/espressomachines/the-oracle-jet.html`
- **Afbeeldingsbron:** Breville/Sage CDN
- **CDN:** `www.sageappliances.com/content/dam/` of Cloudinary
- **Producten op Koffiemachinewijzer:** Oracle Jet, Barista Touch Impress, Barista Express Impress
- **Tips:**
  - Sage/Breville heeft uitstekende productfotografie — vaak 15+ foto's per product
  - Zoek op zowel "Sage [model]" als "Breville [model]" voor maximale dekking
  - Productpagina's bevatten gedetailleerde close-ups van features
  - Breville US site (`breville.com`) heeft vaak hogere resolutie foto's
  - `og:image` is betrouwbaar op beide domeinen
  - Zoek ook "Breville [model] review" op YouTube thumbnails
- **Bekende issues:** Sage (EU) en Breville (VS) gebruiken verschillende productnamen.
  Bijv. Sage Oracle Jet = Breville Oracle Jet. Zoek op beide namen.

## Gaggia

- **Site:** `gaggia.com`
- **Productpagina patroon:** `/[taal]/[categorie]/[productnaam]`
- **Afbeeldingsbron:** Eigen CDN
- **Producten op Koffiemachinewijzer:** Classic Pro, Babila
- **Tips:**
  - Gaggia Classic Pro is een iconisch model — veel review-foto's beschikbaar
  - Gaggia Babila-foto's zijn minder verspreid — fabrikantsite is de beste bron
  - `og:image` werkt op de meeste pagina's
  - Zoek op "Gaggia Classic Pro setup" voor lifestyle-foto's
- **Bekende issues:** Gaggia.com kan regionaal variëren. Probeer `.com/en/` als `.nl` niet werkt.

## Lelit

- **Site:** `lelit.com`
- **Productpagina patroon:** `/[taal]/[categorie]/[productnaam]`
- **Afbeeldingsbron:** Eigen CDN
- **Producten op Koffiemachinewijzer:** Bianca V3
- **Tips:**
  - Lelit is een Italiaans premium merk met goede productfotografie
  - De Bianca is een populair model — veel review-foto's op specialty-coffee sites
  - Zoek op "Lelit Bianca review" voor uitgebreide foto-galerijen
  - home-barista.com forum heeft vaak user-foto's van hoge kwaliteit
- **Bekende issues:** Kleinere fabrikant, minder anti-bot bescherming dan grote merken.

## Rancilio

- **Site:** `ranciliogroup.com`
- **Productpagina patroon:** `/[taal]/[categorie]/[productnaam]`
- **Afbeeldingsbron:** Eigen CDN
- **Producten op Koffiemachinewijzer:** Silvia Pro X
- **Tips:**
  - Rancilio Silvia is een iconisch model — enorm veel foto's beschikbaar
  - Zoek op "Rancilio Silvia Pro X" voor de specifieke versie
  - Professionele espresso-review sites hebben vaak uitgebreide foto-sets
  - `og:image` werkt betrouwbaar
- **Bekende issues:** Rancilio maakt ook professionele machines — zorg dat je het juiste
  (thuisgebruik) model selecteert.

## La Marzocco

- **Site:** `lamarzocco.com` (home: `home.lamarzocco.com`)
- **Productpagina patroon:** `/[productnaam]/`
- **Afbeeldingsbron:** Eigen CDN / Shopify
- **Tips:**
  - La Marzocco staat bekend om prachtige productfotografie
  - De Linea Mini is hun populairste thuismodel — veel lifestyle-foto's beschikbaar
  - Premium merk = premium beeldmateriaal
  - Shopify-gebaseerde webshop — JSON endpoint kan werken
- **Bekende issues:** Sommige foto's zijn alleen beschikbaar in hoge resolutie (5000px+).
  Altijd resizen na download.

## ECM

- **Site:** `ecm.de` (voorheen ECM Manufacture)
- **Productpagina patroon:** `/[taal]/[categorie]/[productnaam]`
- **Tips:**
  - Duits premium merk met uitstekende studiofotografie
  - Mechanika en Synchronika zijn populaire modellen
  - Zoek op "ECM [model] review" voor aanvullende foto's
- **Bekende issues:** Duitse site — gebruik `/en/` voor Engelse versie.

## Rocket Espresso

- **Site:** `rocket-espresso.com`
- **Productpagina patroon:** `/[categorie]/[productnaam]`
- **Tips:**
  - Italiaans premium merk met iconisch design
  - Appartamento en Giotto zijn populaire thuismodellen
  - Zoek ook op "Rocket Espresso [model] barista setup" voor lifestyle-beelden
- **Bekende issues:** Site kan langzaam laden. WebSearch is vaak sneller.

## Bezzera

- **Site:** `bfrancesco.com` (Bezzera Francesco)
- **Tips:**
  - Italiaans merk met traditioneel design
  - Minder mainstream, dus minder foto's beschikbaar online
  - Gespecialiseerde espresso-webshops (espressoperfetto.nl, koffiewarenhuis.nl) zijn goede bronnen

## Eureka

- **Site:** `eureka.co.it`
- **Producten:** Bonenmolens (Mignon Specialita, Mignon Notte, Atom)
- **Tips:**
  - Eureka Mignon-serie is extreem populair — veel foto's beschikbaar
  - Zoek op kleurvariant (zwart, wit, chroom, rood)
  - Specialty-coffee webshops hebben vaak betere foto's dan de fabrikant

## Baratza

- **Site:** `baratza.com`
- **Producten:** Bonenmolens (Sette 270, Encore, Vario)
- **Tips:**
  - Baratza heeft goede productfoto's op hun site
  - Populair in de specialty-coffee community — veel review-foto's
  - Shopify-gebaseerde webshop

## Niche

- **Site:** `nichecoffee.co.uk`
- **Producten:** Niche Zero, Niche Duo
- **Tips:**
  - Cult-status molen — enorm veel community-foto's beschikbaar
  - Niche Zero in wit of zwart — beide kleuren goed gedocumenteerd
  - Instagram en Reddit r/espresso zijn goede bronnen voor lifestyle-foto's

---

## Webshop Tips

Veel koffiemachines zijn het best te vinden via Nederlandse/Belgische webshops:

### Coolblue
- **Site:** `coolblue.nl`
- **URL-patroon:** `coolblue.nl/product/[product-id]/[slug].html`
- **Tips:**
  - Coolblue maakt eigen productfoto's van hoge kwaliteit
  - Vaak 5-10 foto's per product inclusief details
  - CDN: `image.coolblue.nl/`
  - Zoek op productnaam of artikelnummer

### MediaMarkt
- **Site:** `mediamarkt.nl`
- **Tips:**
  - Gebruikt fabrikantfoto's maar vaak in hoge resolutie
  - CDN: `assets.mmsrg.com/`

### Bol.com
- **Site:** `bol.com`
- **URL-patroon:** `bol.com/nl/nl/p/[productnaam]/[ean]/`
- **Tips:**
  - Gebruikt mix van eigen en fabrikantfoto's
  - CDN: `media.s-bol.com/`
  - Zoek op EAN-code voor exacte productmatch

### Koffiediscounter.nl
- **Site:** `koffiediscounter.nl`
- **Tips:**
  - Gespecialiseerde koffiewebshop met goede productfoto's
  - Vaak lifestyle-foto's naast studiofoto's
  - Goede bron voor minder mainstream merken

### Amazon.nl
- **Site:** `amazon.nl`
- **Tips:**
  - Amazon CDN URLs zijn stabiel: `m.media-amazon.com/images/I/`
  - Vaak meerdere hoeken beschikbaar
  - Zoek op ASIN voor directe producttoegang

### Specialty Coffee Webshops
Voor espressomachines en molens zijn gespecialiseerde shops vaak de beste bron:
- `koffiewarenhuis.nl` — breed assortiment
- `espressoperfetto.nl` — premium machines
- `coffeefresh.nl` — Jura specialist
- `espressionista.nl` — home-barista focus
- `theespressoshop.co.uk` — UK-gebaseerd, goede foto's
