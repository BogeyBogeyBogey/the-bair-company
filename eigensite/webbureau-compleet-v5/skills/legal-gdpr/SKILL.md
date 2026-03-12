---
name: legal-gdpr
description: >
  Automatische GDPR-compliance: privacy policy, cookie banner, en juridische pagina's.
  Triggers: "privacy policy", "GDPR", "AVG", "cookies", "cookiebeleid",
  "cookie banner", "algemene voorwaarden", "disclaimer".
version: 2.0.0
---

# Juridisch & GDPR — Automatisch

Juridische pagina's en cookie-compliance worden AUTOMATISCH gegenereerd op basis van de site-research.

## Standaard oplevering

Elke site krijgt automatisch:

### 1. Cookie Banner
Ingebouwd in elke pagina:
```html
<div id="cookie-banner" style="...">
  <p>Deze website gebruikt cookies om uw ervaring te verbeteren.</p>
  <button onclick="acceptCookies()">Accepteren</button>
  <a href="/privacy-policy.html">Meer info</a>
</div>
```

### 2. Privacy Policy pagina
Automatisch gegenereerd met:
- Bedrijfsnaam en contactgegevens uit site-research
- Welke gegevens worden verzameld (formulieren, cookies, analytics)
- Rechten van de bezoeker (AVG/GDPR)
- Bewaartermijnen
- Contactgegevens voor privacy-vragen

### 3. Cookie Policy
Als onderdeel van of apart van de privacy policy:
- Functionele cookies (altijd)
- Analytische cookies (indien Google Analytics)
- Marketing cookies (indien van toepassing)

### 4. Algemene Voorwaarden (indien e-commerce)
Alleen als de site een webshop is.

## Taal

Juridische pagina's in dezelfde taal als de hoofdsite. Bij meertalige sites: in alle talen.

## Disclaimer

Voeg onderaan juridische pagina's toe:
> "Dit privacybeleid is opgesteld als richtlijn. Raadpleeg een juridisch adviseur voor volledig op maat gemaakt advies."

## Implementatie

Juridische pagina's worden als aparte HTML-bestanden aangemaakt (bijv. `privacy-policy.html`) en gelinkt vanuit de footer van elke pagina.
