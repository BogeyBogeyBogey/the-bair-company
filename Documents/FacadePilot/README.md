# FacadePilot

> AI-gestuurde leadgeneratie voor gevelrenovatie in Vlaanderen.

End-to-end pipeline die kadasterdata van Vlaanderen (GRB) omzet in gescoorde
renovatieleads, automatisch een Street View foto haalt, daar een fotorealistische
AI-render van maakt en alles afsluit met persoonlijke flyers, landingpagina's
en e-mails — gekoppeld aan een Supabase CRM voor opvolging.

## Wat het doet

1. **Adresselectie** — haalt kadastrale percelen + gebouwen op via GRB OGC API,
   filtert op woninggrootte, sluit recente vergunningen uit
2. **Lead scoring** — rangschikt leads op 5 metrics (woninggrootte, buurtinkomen,
   perceelgrootte, bebouwd ratio, huistype) met A+/A/B/C/D klassificatie
3. **Pre-render kwaliteitscheck** — `gpt-4o-mini` checkt of een Street View foto
   bruikbaar is vóór de dure render (~$0.001 vs. ~$0.10 bespaard per slechte foto)
4. **AI Render** — stuurt Street View foto naar GPT Image 2 voor fotorealistische
   gevelrenovatie. Auto-selectie van renovatie-type per lead (crepi / baksteen /
   isolatie / totaalrenovatie).
5. **Premium flyer-templates** — 3 stijlen (Premium / Design / Klassiek) × 2
   formaten (A4 + A5 recto-verso) = 6 templates. Auto-selector kiest stijl op
   basis van huistype.
6. **Landingpagina per adres** — statische self-contained HTML met before/after
   slider en offerteformulier
7. **Email-flyer** — mail-veilige HTML + .eml voor mail-merge
8. **Print.one integratie** — automatische direct-mail bezorging
9. **Supabase CRM** — persistent lead-store met status-workflow en analytics
10. **Live dashboard** — voortgang, cost tracker, heatmap met clustering, CRM-tab

## Architectuur

```
facadepilot_pipeline.py     # web dashboard (port 8769) + orkestratie
├── facadepilot_adresselectie.py   # GRB → CSV
├── facadepilot_lead_scoring.py    # 5-metric scoring + huistype classifier
├── facadepilot_quality_check.py   # gpt-4o-mini pre-render filter
├── facadepilot_streetview.py      # Google Street View
├── facadepilot_render.py          # GPT Image 2 (retry + cache + multi-preset)
├── facadepilot_facade_selector.py # auto-kies preset per lead
├── facadepilot_flyer.py           # Playwright PDFs (3 stijlen)
├── facadepilot_landing.py         # statische HTML per adres
├── facadepilot_email.py           # mail-veilige HTML + .eml
├── facadepilot_crm.py             # Supabase CRM (PostgREST via requests)
├── facadepilot_manueel.py         # Geopunt geocoder + handmatig adres
├── facadepilot_vergunning.py      # pre-filter via CSV cache
├── facadepilot_printone.py        # Print.one wrapper (default dry-run)
└── facadepilot_logging.py         # centrale logger met file rotation
```

Plus templates in `templates/` (6 flyer-varianten), `data/postcodes_vlaanderen.json`
(519 Vlaamse postcodes), en utility scripts in `scripts/`.

## Setup

```bash
# 1. Clone
git clone git@github.com:USER/Facadepilot.git
cd Facadepilot

# 2. Python dependencies
pip3 install pandas geopandas numpy requests Pillow openai \
             python-dotenv jinja2 playwright qrcode openpyxl

# 3. Playwright browser
python3 -m playwright install chromium

# 4. Environment
cp .env.example .env
# Open .env en vul je keys in:
#   OPENAI_API_KEY        — voor GPT Image + gpt-4o-mini
#   GOOGLE_API_KEY        — voor Street View Static API
#   SUPABASE_URL          — uit Supabase dashboard
#   SUPABASE_ANON_KEY     — publishable key (mag publiek)
#   SUPABASE_SERVICE_KEY  — service_role key (NOOIT committen)
#   PRINTONE_API_KEY      — optioneel, alleen voor live mail-bezorging

# 5. Optioneel — Statbel bouwjaar-data voor 5e scoring metric
# Download van https://statbel.fgov.be/nl/open-data en plaats als
# TF_BUILDING_AGE_SECTOR.xlsx in de project root.

# 6. Start dashboard
python3 facadepilot_pipeline.py
# → opent http://localhost:8769 in browser
```

## Supabase setup

Het CRM-schema staat in een Supabase project. Apply via Supabase MCP of dashboard:

```sql
-- Zie facadepilot_crm.py voor het volledige schema
create table public.leads (
  capakey text primary key,
  niscode text, gemeente text, adres text,
  lat double precision, lon double precision,
  -- ... (27 kolommen totaal)
  status text not null default 'gegenereerd' check (status in (
    'gegenereerd','geflyerd','gescand','contact','afspraak','klant','afgewezen'
  )),
  status_history jsonb not null default '[]'::jsonb,
  -- ...
);

create table public.lead_events (
  id bigserial primary key,
  capakey text not null references public.leads(capakey) on delete cascade,
  ts timestamptz not null default now(),
  event text not null check (event in (
    'scan','click','form_submit','note','status_change','flyer_sent','email_sent'
  )),
  detail text,
  user_agent text, ip_hash text
);
```

## Kosten per run

| Stap | Kosten |
|---|---|
| Adresselectie (GRB API) | gratis |
| Street View metadata | gratis |
| Street View foto | $0.007/foto |
| Pre-render quality check (gpt-4o-mini) | ~$0.001/check |
| GPT Image 2 render | ~$0.10/render |
| Flyer + landing + email | gratis (lokaal) |
| Supabase | $10/maand vast |
| Print.one (optioneel) | varieert per kaart |

Typische run van 100 leads: **~$15-20** API-kosten + Supabase.

## Quality-check filosofie

De pre-render check (`facadepilot_quality_check.py`) blokkeert alleen wanneer de
foto een **expliciete fail-case** is (garage, schuur, kantoor, leeg, industrie,
magazijn, loods, bouwwerf, winkel). Twijfelgevallen ("onduidelijk", "ander")
worden als **soft pass** behandeld — de render gaat door.

Voor manuele adressen (Express-run) staat de check standaard UIT — als jij het
adres bewust koos, weet je al dat het een huis is.

## Flyer-stijlen

| Stijl | Look & feel | Voor welke woningen | Default accent |
|---|---|---|---|
| **Premium** | Sora + Instrument Serif italic, warm taupe, half-bleed hero | Default — werkt voor alles | `#a8784f` |
| **Design** | Brutalist editorial, donker, asymmetrisch, monospaced labels | Moderne / architecturale woningen, A+ leads | `#ff5722` |
| **Klassiek** | Atelier bourgeois, ivoor + bordeaux, ◆ ornamenten | Oude rijhuizen, herenhuizen pre-1990 | `#7a2f3e` |

Auto-mode kiest per lead op basis van huistype + lead-klasse + buurtbouwjaar.

## License

Privé project — niet voor publieke distributie.

## Spin-offs

Deze codebase deelt architectuur met `PoolPilot`, `PadelPilot` en `PorchPilot`.
Zie `OVERDRACHT_NAAR_PORCHPILOT_2026-05-03.md` (in parent folder) voor het patroon
om de architectuur te hergebruiken.
