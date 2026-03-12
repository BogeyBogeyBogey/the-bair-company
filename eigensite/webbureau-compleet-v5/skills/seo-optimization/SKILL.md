---
name: seo-optimization
description: >
  Automatische SEO-optimalisatie ingebouwd in elke pagina.
  Triggers: "SEO", "zoekmachine", "Google ranking", "meta tags",
  "structured data", "Schema.org", "sitemap", "zoekwoorden".
version: 2.0.0
---

# SEO Optimalisatie — Automatisch

SEO wordt AUTOMATISCH in elke pagina ingebouwd. Er is geen aparte SEO-stap nodig.

## Standaard in elke pagina

### Meta tags
```html
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>[Bedrijfsnaam] — [Kernactiviteit]</title>
<meta name="description" content="[Max 155 tekens beschrijving]">
<meta name="robots" content="index, follow">
<link rel="canonical" href="https://[domein]/[pagina]">
```

### Open Graph (social sharing)
```html
<meta property="og:title" content="[Titel]">
<meta property="og:description" content="[Beschrijving]">
<meta property="og:type" content="website">
<meta property="og:url" content="https://[domein]/[pagina]">
<meta property="og:image" content="https://[domein]/og-image.jpg">
```

### Structured Data (JSON-LD)
Voeg automatisch toe op basis van het type bedrijf:

**Lokaal bedrijf:**
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "LocalBusiness",
  "name": "[Bedrijfsnaam]",
  "address": { "@type": "PostalAddress", ... },
  "telephone": "[Telefoon]",
  "openingHours": "..."
}
</script>
```

### Technische SEO
- Semantische HTML: `<header>`, `<nav>`, `<main>`, `<article>`, `<footer>`
- Heading-hiërarchie: één `<h1>` per pagina, logische `<h2>`-`<h6>`
- Alt-teksten op alle afbeeldingen
- Interne links tussen pagina's
- Snelle laadtijd (geen zware libraries)

### Sitemap
Genereer een `sitemap.xml` met alle pagina's:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://[domein]/</loc><priority>1.0</priority></url>
  <url><loc>https://[domein]/over-ons</loc><priority>0.8</priority></url>
  ...
</urlset>
```

### Robots.txt
```
User-agent: *
Allow: /
Sitemap: https://[domein]/sitemap.xml
```

## Geen apart document

Alle SEO wordt direct in de HTML-code ingebouwd.
