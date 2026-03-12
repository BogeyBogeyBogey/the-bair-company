---
name: geo-optimization
description: >
  Automatische lokale SEO-optimalisatie op basis van bedrijfslocatie.
  Triggers: "lokale SEO", "GEO", "Google Business", "Google Maps",
  "lokale vindbaarheid", "regionale SEO".
version: 2.0.0
---

# Lokale/Regionale SEO — Automatisch

Lokale SEO wordt AUTOMATISCH toegepast als het bedrijf een fysiek adres heeft.

## Automatische detectie

Uit `site-research.md`:
- Heeft het bedrijf een fysiek adres? → Voeg LocalBusiness structured data toe
- Is er een telefoonnummer? → Voeg tel: link toe
- Is er een Google Maps locatie? → Embed kaart op contactpagina

## Implementatie

### NAP-consistentie (Name, Address, Phone)
Zorg dat bedrijfsnaam, adres en telefoonnummer EXACT hetzelfde zijn op:
- Elke pagina (footer)
- Contact pagina
- Structured data
- Meta tags

### Google Maps embed
Op de contactpagina:
```html
<iframe src="https://www.google.com/maps/embed?pb=..." 
  width="100%" height="400" style="border:0;" 
  allowfullscreen="" loading="lazy">
</iframe>
```

### Lokale zoekwoorden
Verwerk automatisch in de content:
- "[Dienst] in [Stad]"
- "[Dienst] [Regio]"
- "Nabij [Bekende locatie]"

### Structured Data
```json
{
  "@context": "https://schema.org",
  "@type": "LocalBusiness",
  "name": "[Bedrijfsnaam]",
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "[Straat]",
    "addressLocality": "[Stad]",
    "postalCode": "[Postcode]",
    "addressCountry": "BE"
  },
  "geo": {
    "@type": "GeoCoordinates",
    "latitude": "...",
    "longitude": "..."
  },
  "telephone": "[Telefoon]"
}
```

## Geen apart document

Lokale SEO wordt direct in de HTML-code en structured data ingebouwd.
