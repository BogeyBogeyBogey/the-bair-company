---
name: forms-integrations
description: >
  Automatische integratie van contactformulieren en nieuwsbriefinschrijving.
  Triggers: "contactformulier", "formulier", "Formspree", "Brevo",
  "nieuwsbrief", "e-mail marketing", "inschrijfformulier".
version: 2.0.0
---

# Formulieren & Integraties — Automatisch

Formulieren worden AUTOMATISCH toegevoegd als de bestaande site een contactformulier of nieuwsbrief heeft.

## Detectie

Uit `site-research.md`, check of de bestaande site bevat:
- Contactformulier → voeg Formspree-formulier toe
- Nieuwsbrief inschrijving → voeg e-mail capture toe
- Offerteaanvraag → voeg uitgebreid formulier toe
- Boekingssysteem → voeg basis boekingsformulier toe

## Contactformulier (Formspree)

Standaard implementatie:
```html
<form action="https://formspree.io/f/{FORM_ID}" method="POST">
  <input type="text" name="naam" placeholder="Uw naam" required>
  <input type="email" name="email" placeholder="Uw e-mailadres" required>
  <input type="tel" name="telefoon" placeholder="Telefoonnummer">
  <textarea name="bericht" placeholder="Uw bericht" rows="5" required></textarea>
  <input type="hidden" name="_subject" value="Nieuw bericht via website">
  <input type="text" name="_gotcha" style="display:none">
  <button type="submit">Verstuur</button>
</form>
```

**Opmerking**: Gebruik `{FORM_ID}` als placeholder. De klant moet een Formspree-account aanmaken en het ID invullen.

## Styling

Formulieren volgen het designprofiel:
- Dezelfde fonts en kleuren als de rest van de site
- Focus-states met accent kleur
- Foutmeldingen in het rood
- Succes-feedback na verzending

## Geen aparte configuratie

Formulieren worden direct in de HTML-pagina's geïntegreerd via de development skill.
