# FacadePilot — Handover Document

**Datum:** 27 april 2026 (laatste update — Wave 1 verbeteringen)
**Project:** FacadePilot — AI-gestuurde leadgeneratie voor gevelrenovatie in Vlaanderen
**Locatie:** `~/Documents/FacadePilot/`
**Status:** MVP werkend, Wave 1 (4 quick wins) doorgevoerd, klaar voor hertest

## Wave 1 — Doorgevoerde verbeteringen (deze sessie)

### 1. Pre-render kwaliteitscheck (nieuwe module)
- Nieuwe file: `facadepilot_quality_check.py` — checkt met `gpt-4o-mini` of een Street View foto een herkenbare voorgevel toont VOOR de dure render
- Kost ~$0.001 per check, bespaart ~$0.10 per slechte render
- Fail-open: bij API-fout of geen key wordt de check overgeslagen, niet de render
- Gekoppeld in `process_renders()` als `quality_check=True` (default)
- Resultaten per lead in CSV: `render_quality_pass`, `render_quality_type`, `render_quality_reason`

### 2. Cost tracker live in dashboard
- Module-level cost-counters in `facadepilot_streetview.py`, `facadepilot_render.py`, `facadepilot_quality_check.py`
- `pipeline.py` aggregeert via nieuwe `refresh_costs()` na elke step
- Dashboard heeft nu een live "API-kosten" widget met 3 kaartjes (Street View / Quality / Render) + totaal
- Toont automatisch hoeveel quality-check je bespaard heeft op slechte renders

### 3. Bouwjaar / huistype in scoring
- Scoring uitgebreid van 4 → 5 metrics (huistype 20%)
- Nieuwe functie `classify_huistype()` werkt ALTIJD (geen externe data nodig) op basis van perceel + ratio
- Categorieën: vrijstaand_ruim, halfopen_ruim, halfopen, rijwoning, stadswoning, appartement_dicht
- Optioneel: als `TF_BUILDING_AGE_SECTOR.xlsx` (Statbel) in folder staat, wordt pct_pre_1990 als bonus gebruikt
- Output kolommen: `huistype`, `huistype_score`, `pct_pre_1990`, `sector_id`

### 4. Multi-preset render voor A+ leads
- Nieuwe params in `process_renders()`: `multi_preset_for_klassen` + `multi_presets`
- Dashboard-toggle "Multi-preset voor A+" — wanneer aan: voor elke A+ lead worden 3 stijlen gerenderd (crepi + baksteen + totaal)
- Output: extra kolommen `render_path_moderne_crepi`, `render_path_baksteen_rejoint`, etc.
- Files genaamd `{idx}_{adres}_render_{preset}.jpg`

---

---

## Wat is FacadePilot?

Een end-to-end pipeline die automatisch gevelrenovatie-leads genereert voor aannemers in Vlaanderen:

1. **Adresselectie** — haalt kadastrale percelen + gebouwen op via GRB OGC API, filtert op woninggrootte
2. **Lead scoring** — rankt leads op basis van woninggrootte, buurtinkomen, perceelgrootte en bebouwd ratio
3. **Street View** — haalt Google Street View foto's op met automatische heading-berekening
4. **AI Render** — stuurt Street View foto naar GPT Image 2 die een fotorealistische gevelrenovatie genereert
5. **Flyer** — maakt gepersonaliseerde before/after PDF-flyers (A4 + A5) per adres

Alles draait via een web-dashboard (`facadepilot_pipeline.py` → `http://localhost:8769`).

---

## Bestanden

| Bestand | Doel |
|---|---|
| `facadepilot_pipeline.py` | Web dashboard + orchestratie van alle stappen |
| `facadepilot_adresselectie.py` | GRB API → kadastrale data → gefilterde leadlijst CSV |
| `facadepilot_lead_scoring.py` | Scoring engine (4 gewogen metrics, A+/A/B/C/D klassen) |
| `facadepilot_streetview.py` | Google Street View ophalen met auto-heading + afstandscheck |
| `facadepilot_render.py` | GPT Image 2 gevelrenovatie renders (4 presets) |
| `facadepilot_flyer.py` | PDF flyer generator (Jinja2 + playwright) |
| `.env` | API keys (OPENAI_API_KEY + GOOGLE_API_KEY) — NIET committen |
| `.env.example` | Template voor .env |

**Testdata aanwezig (Tienen, NIS 24107):**
- `facadepilot_leads_24107.csv` — ruwe leads
- `facadepilot_leads_24107_scored.csv` — gescoorde leads
- `facadepilot_leads_24107_scored_with_renders.csv` — met render-paden
- `renders/` — Street View + render JPGs
- `flyers/` — gegenereerde PDF flyers

---

## Starten

```bash
cd ~/Documents/FacadePilot
python3 facadepilot_pipeline.py
```

Opent een dashboard op `http://localhost:8769` (of de eerstvolgende vrije poort tot 8900).

**Vereisten:**
- Python 3.10+
- Packages: `pandas`, `geopandas`, `numpy`, `requests`, `Pillow`, `openai`, `python-dotenv`, `jinja2`, `playwright`, `qrcode`
- `.env` met `OPENAI_API_KEY` en `GOOGLE_API_KEY`

---

## Recent opgeloste problemen (deze sessie)

### 1. Niet-residentiële gebouwen in leadlijst
**Probleem:** Loodsen, magazijnen en industriegebouwen werden meegenomen.
**Oplossing:** Twee nieuwe filters toegevoegd:
- `max_woning` (default 350m²) — gebouwen groter dan dit worden uitgesloten
- `max_bebouwd_ratio` (default 0.75) — percelen waar >75% bebouwd is = industrieel

Doorgevoerd in: `facadepilot_adresselectie.py` (CLI) én `facadepilot_pipeline.py` (dashboard UI + backend).
Dashboard heeft nu velden "Max. woninggrootte" en "Max. bebouwingsgraad".

### 2. Street View pakt verkeerd gebouw
**Probleem:** Te breed beeld (FOV 90°), verkeerde elementen in beeld (veranda's, bijgebouwen).
**Oplossing:**
- FOV: 90° → **65°** (meer focus op doelhuis)
- Pitch: 10° → **5°** (minder dak, meer gevel)
- **Afstandscheck:** panorama's >80m van het adres worden geweigerd (= verkeerd gebouw)
- `haversine_distance()` functie toegevoegd

Doorgevoerd in: `facadepilot_streetview.py`

### 3. Renders te ingrijpend (ramen/deuren verplaatst)
**Probleem:** GPT Image verplaatste ramen en deuren, veranderde dakvormen.
**Oplossing:**
- `_PRESERVE_RULE` constante die aan ELKE preset wordt toegevoegd:
  > "STRIKT: behoud de EXACTE positie, grootte en aantal van alle ramen en deuren. Verplaats NIETS..."
- Alle 4 preset-prompts herschreven: "bestaande ramen/deuren" ipv "nieuwe", geen carports/overstek meer

Doorgevoerd in: `facadepilot_render.py`

### 4. Port 8769 bezet
**Oplossing:** `find_free_port()` functie die poorten 8769-8900 probeert. Dashboard meldt welke poort wordt gebruikt.

---

## Render Presets (4 stuks)

| Key | Label | Indicatieprijs |
|---|---|---|
| `moderne_crepi` | Moderne crépi-afwerking | vanaf €20K |
| `baksteen_rejoint` | Baksteen reiniging + hervoegen | vanaf €12K |
| `isolatie_gevelbekleding` | Buitenisolatie + gevelbekleding | vanaf €30K |
| `totaalrenovatie` | Totale gevelrenovatie | vanaf €50K |

---

## Scoring Model

4 gewogen metrics:
- **Woninggrootte** (35%) — meer geveloppervlak = meer renovatie-impact
- **Buurtinkomen** (35%) — gevelrenovatie is een serieuze investering (€12K-€50K+)
- **Perceelgrootte** (15%) — proxy voor property-waarde
- **Bebouwd ratio** (15%) — hoger = meer geveloppervlak per perceel

Klassen: A+ (top 5%), A (top 15%), B (top 35%), C (top 65%), D (rest)

---

## Kosten per run

| Stap | Kosten |
|---|---|
| Adresselectie (GRB API) | Gratis |
| Street View metadata check | Gratis |
| Street View foto ophalen | ~$7 per 1.000 foto's |
| GPT Image 2 render | ~$0.08-0.17 per render (afhankelijk van formaat) |
| Flyer generatie | Gratis (lokaal) |

**Typische run:** 100 leads → ~$7 Street View + ~$10-15 renders = **~$20-25 totaal**

---

## Wave 2 — Doorgevoerde verbeteringen (zelfde sessie)

### 5. Supabase CRM (`facadepilot_crm.py` + nieuw project)
- Nieuw Supabase project: **FacadePilot** (`xndfyjhpmuaqaxndznji.supabase.co`, eu-west-1)
- Tables: `leads` (27 kolommen, status-workflow + status_history JSONB) + `lead_events` (analytics)
- View: `lead_public` (read-only voor landingpagina, security_invoker, alleen veilige kolommen)
- RLS: aan op beide tabellen. Service role bypasst voor pipeline. Anon kan alleen `lead_events INSERT` (scans, clicks, form submits) en `lead_public SELECT`.
- Geen openstaande security-advisors (na fix-migratie)
- Module gebruikt PostgREST via `requests` — geen extra dependencies
- CLI: `python3 facadepilot_crm.py {check, import, status, list, funnel}`
- Status-workflow: `gegenereerd → geflyerd → gescand → contact → afspraak → klant | afgewezen`

### 6. Heatmap met clustering (`facadepilot_pipeline.py` dashboard)
- Nieuwe card "Kaart & clusters" — Leaflet + MarkerCluster (CDN)
- Punten gekleurd per lead-klasse (A+ groen → D grijs)
- Cluster-iconen tonen aantal en % top-leads (A+/A) — perfect voor wijk-targeting
- Popup per lead: adres, score, status, bebouwd_m² + render-thumbnail
- Bron: Supabase als geconfigureerd, anders fallback op meest recente CSV
- Donker basemap (CartoDB Dark) past bij dashboard

### 7. Landingpagina per adres (`facadepilot_landing.py`)
- Genereert per lead een **statische, self-contained HTML-pagina** in `landing/{niscode}/{slug}.html`
- Before/after slider (mouse + touch), persoonlijke aanhef, facts-strip, offerteformulier
- Afbeeldingen geëmbed als data: URI → werkt offline / op elke host
- Tracking via Supabase: scan-event bij page load, form_submit-event bij submit
- Public URL pattern: `facadepilot.be/r/{niscode}-{capakey}?src=qr|flyer|email` (te uploaden naar Vercel)
- URL wordt teruggesynced naar `leads.landing_url`

### 8. HTML e-mail-flyer (`facadepilot_email.py`)
- Mail-veilige HTML (table-based, inline styles) — werkt in Gmail/Outlook/Apple Mail
- Genereert zowel `.html` als `.eml` (kant-en-klaar voor mail-merge)
- Before/after zij-aan-zij + facts-strip + CTA-button naar landingpagina
- Plain-text fallback in `.eml` voor clients zonder HTML
- Output: `emails/{niscode}/{slug}.html` + `.eml`

### 9. Omgevingsvergunning pre-filter (`facadepilot_vergunning.py`)
- `VergunningChecker` filtert leads met recente gevelvergunning op CAPAKEY
- Werkt nu via lokale CSV (`vergunningen_cache.csv`) — productie-hook gedocumenteerd voor het Vlaamse Omgevingsloket-kwartaalbestand
- Pre-filter draait automatisch in `step_adresselectie` (toggle "Vergunning pre-filter" in dashboard)
- CLI: `python3 facadepilot_vergunning.py {seed, check, filter}`

### 10. Pipeline-orkestratie uitgebreid
- `step_scoring` → automatische CRM upsert na scoring
- `step_render` → render-paden gesynced naar CRM
- Nieuwe steps `step_landing` + `step_email` na de flyer-stap
- Dashboard toont 6 stappen ipv 4 + 2 toggles voor landing/email + toggles voor "Vergunning pre-filter" en "CRM-sync"
- Nieuw CRM-tab in dashboard: live conversion funnel + bewerkbare lead-tabel met status-dropdown

---

## Setup-checklist voor Wave 2

1. **Service-role key kopiëren** uit Supabase dashboard:
   `https://supabase.com/dashboard/project/xndfyjhpmuaqaxndznji/settings/api-keys`
   en plakken in `.env` bij `SUPABASE_SERVICE_KEY=...`
2. (Optioneel) Vergunning-cache vullen:
   `python3 facadepilot_vergunning.py seed` → bewerk `vergunningen_cache.csv`
3. Test verbinding: `python3 facadepilot_crm.py check`
4. Pipeline draaien — leads worden auto-gepopuleerd in Supabase
5. CRM-tab in dashboard toont funnel + status-dropdowns
6. Voor productie van landingpagina's: `landing/{niscode}/` uploaden naar Vercel
   met routing `r/{niscode}-{capakey} → {slug}.html`

---

## Spoor 1 — Verbeteringen overgenomen van PoolPilot (3 mei 2026)

### 11. Centrale logging (`facadepilot_logging.py`)
- `get_logger(__name__)` — schrijft naar console + `facadepilot.log` met RotatingFileHandler (10 MB × 3 backups = max 40 MB op disk)
- Auto-silence van urllib3/requests/openai/PIL noise
- Vervangt scattered `print()` over de tijd

### 12. Retry + backoff op render-call (`facadepilot_render.py`)
- 3 pogingen, exponential backoff (2s, 4s, 8s)
- 4xx (behalve 429) → geen retry, 5xx + 429 + connection-errors → wel retry
- Bij definitieve fail → `failed_renders.csv` met timestamp, idx, adres, capakey, lat/lon, reason
- Buffer wordt per poging opnieuw geopend (read-after-EOF probleem opgelost)

### 13. Postcodes naar JSON (`data/postcodes_vlaanderen.json`)
- 519 Vlaamse postcodes verplaatst uit pipeline.py (180 regels code weg)
- Lazy-load bij module-init
- Hergebruikbaar voor andere Pilot-projecten (1-op-1 kopie)

### 14. Auto-select facade preset per lead (`facadepilot_facade_selector.py`)
- Beslislogica per lead op basis van huistype + bouwjaar + buurtinkomen + lead_klasse
- 4 regels met fallback:
  - Welvarend + ruim + topklasse → `totaalrenovatie`
  - Oude buurt (>60% pre-1990) + bakstenen profiel → `baksteen_rejoint`
  - Halfopen ruim + groot oppervlak + hoog inkomen → `isolatie_gevelbekleding`
  - Default → `moderne_crepi`
- Output kolommen: `preset_auto`, `preset_reden`
- Dashboard-toggle "🤖 Auto-preset per lead"

### 15. Handmatig adres (`facadepilot_manueel.py`)
- Geocoder via Geopunt Location v4 (gratis, geen key)
- Optionele perceel-lookup via GRB ADP
- Auto-fallback "zonder komma" voor inconsistente Geopunt-resultaten
- 4 dashboard-endpoints: POST `/api/manual_address`, GET `/api/manual_addresses`, POST `/api/manual_clear`, POST `/api/manual_run`
- "📍 Handmatig adres" UI-paneel met lijstje + Express-run knop
- Express-flow start pipeline met `input_csv=manual_leads.csv`, alleen render+flyer+landing aan, auto_preset=True

### 16. Print.one integratie (`facadepilot_printone.py`)
- `PrintOneClient` met x-api-key auth, `Idempotency-Key` header (sha1 van postcode_huisnummer_file), retry + backoff, **default DRY RUN**
- `parse_vlaams_adres()` — Vlaamse adres-strings → straat/huisnummer/suffix/bus/postcode/gemeente, ondersteunt BIS/TER/1A/etc.
- `build_printone_csv()` — combineert scored CSV + flyers/ map → input-CSV
- `send_csv_to_printone()` — batch-flow + `printone_jobs.csv` met file_id/order_id/status/error per rij
- CLI: `python3 facadepilot_printone.py --csv ... [--live]`
- ⚠️ Eerste live-test = klein! Body-velden zijn op basis van publieke conventies, niet officiële spec
- `PRINTONE_API_KEY` toegevoegd aan `.env.example`

### 17. Skip-cache filename verrijking (`facadepilot_render.py`)
- Render-bestanden krijgen nu de preset-key in de naam: `000_Mulkstraat_2_3300_Tienen_moderne_crepi_render.jpg`
- Backward-compatibel: oude `..._render.jpg` blijven geldig als cache-hit
- Maakt het mogelijk verschillende presets naast elkaar te testen zonder cache-collision

### 18. iCloud cleanup script (`scripts/cleanup_icloud_duplicates.sh`)
- Verwijdert "* 2.html", "* 3.txt" sync-conflicten van iCloud Drive
- Default = dry-run, `--apply` flag voor echte verwijdering
- Skipt `_archive*/`, `.git/`, `node_modules/`, `__pycache__/`
- Patterns: txt/md/py/html/json/csv/jpg/png/pdf/eml met suffix " 2", " 3", " 4"

---

## Mogelijke volgende stappen

- **Statbel bouwjaar-bestand downloaden** — om `pct_pre_1990` te activeren in scoring
- **Productie-API voor vergunningen** — kwartaalbestand parser uit Vlaams Omgevingsloket
- **Vercel deployment van landingpagina's** met dynamic routing
- **Mail-merge integratie** met Brevo/Resend voor automatische verzending vanuit `.eml`-bestanden
- **Hertest met nieuwe filters** voor Tienen (24107)
- **Meer gemeenten testen** (Leuven 24062, Mechelen 12025, Gent 44021)
- **Flyer design iteratie**
- **Batch-modus** voor meerdere gemeenten

---

## Architectuur

```
facadepilot_pipeline.py (web dashboard, port 8769+)
    ├── facadepilot_adresselectie.py  (GRB OGC API → CSV)
    ├── facadepilot_lead_scoring.py   (CSV → scored CSV)
    ├── facadepilot_streetview.py     (Google Street View API)
    ├── facadepilot_render.py         (OpenAI GPT Image 2 API)
    └── facadepilot_flyer.py          (Jinja2 + Playwright → PDF)
```

Elke module werkt ook standalone via CLI (`python3 <module>.py --help`).

---

## API Keys nodig

- `OPENAI_API_KEY` — voor GPT Image 2 renders
- `GOOGLE_API_KEY` — voor Street View (moet Street View Static API enabled hebben)

Beide staan in `.env` (niet in git).
