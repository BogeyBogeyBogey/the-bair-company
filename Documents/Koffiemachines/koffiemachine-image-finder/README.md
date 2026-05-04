# Koffiemachine Image Finder

Zoekt, downloadt en optimaliseert productafbeeldingen van koffiemachinemerken voor Koffiemachinewijzer.

## Wat doet deze plugin?

Deze plugin helpt je om snel hoogwaardige productafbeeldingen van koffiemachinemerken te vinden en te downloaden. Hij kent de URL-patronen en CDN-structuren van alle grote koffiemachinemerken en kan automatisch afbeeldingen downloaden, valideren en optimaliseren voor gebruik op Koffiemachinewijzer.

## Ondersteunde merken

**Volautomaten:** Jura, Siemens, De'Longhi, Philips, Miele, Melitta, Krups

**Espressomachines:** Sage (Breville), Gaggia, Lelit, Rancilio, La Marzocco, ECM, Rocket Espresso, Bezzera

**Bonenmolens:** Eureka, Baratza, Niche, Mahlkönig, Mazzer

**Webshops:** Coolblue, MediaMarkt, Bol.com, Amazon.nl, Koffiediscounter

## Componenten

### Skill: koffiemachine-image-finder
Wordt automatisch geactiveerd wanneer je vraagt om productafbeeldingen van koffiemachines. Bevat:
- Stapsgewijze "waterval" methode om de beste afbeeldingsbron te vinden (WebSearch → WebFetch → Fabrikantsite → Screenshot)
- Merkenreferentie met URL-patronen per merk
- Download & optimalisatie script
- Affiliate link templates voor Amazon, Coolblue, Bol.com, MediaMarkt
- Tips voor veelvoorkomende problemen (403 errors, placeholders, WebP/AVIF conversie)

## Foto-types

De plugin zoekt naar meerdere soorten foto's per product:
- **Hero/productfoto** — studiokwaliteit op witte achtergrond
- **Schuin aanzicht** — 3/4 perspectief
- **Bediening/display** — close-up van bedieningspaneel
- **Melksysteem** — detail van melkopschuimer/LatteGo/cappuccinatore
- **Koffie-uitloop** — espresso die uit de machine loopt
- **Bonenreservoir** — bovenaanzicht
- **Actiefoto's** — machine in gebruik
- **Lifestylefoto's** — sfeerbeelden in keukenomgeving

## Vereisten

De plugin gebruikt standaard command-line tools voor beeldverwerking:
- `curl` — voor het downloaden van afbeeldingen
- `ImageMagick` (`convert`/`magick`) — voor resize en conversie
- `file` — voor bestandstype-detectie

## Gebruik

Vraag gewoon om een productafbeelding van een koffiemachine en de skill wordt automatisch geactiveerd. Voorbeelden:

- "Zoek foto's van de Jura Z10"
- "Download productafbeeldingen van de Sage Oracle Jet"
- "Haal de afbeelding van de Philips 3300 LatteGo op"
- "Ik heb productfoto's nodig van de Siemens EQ.900"
