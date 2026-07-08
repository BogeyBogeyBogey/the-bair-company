# WindowPilot scoring v2

Datum: 8 juli 2026  
Model: `windowpilot_property_opportunity_v2_2026_07`

## Doel

WindowPilot gebruikt dezelfde HomePilot-datalaag als FacadePilot, maar scoort op
een andere commerciële vraag: welke woningen zijn interessant voor ramen,
deuren, poorten, rolluiken, screens en buitenschrijnwerk.

De score blijft een **property opportunity score**. Ze zegt niet dat de bewoner
wil kopen. Ze rangschikt woningen op gebouw-, buurt-, timing- en partnerdata die
een meetbare WindowPilot-campagne nuttig maken.

## Scorecomponenten

| Component | Gewicht | Wat meet dit? | Bronstatus |
| --- | ---: | --- | --- |
| Raam-/deur-/poortvolume | 22% | Proxy voor aantal en waarde van ramen, deuren, poorten, screens of rolluiken. | GRB/Capakey + woningtypeproxy; later eigen beeldherkenning of veldcontrole |
| Woningtype | 15% | Vrijstaand, halfopen, rijwoning of dicht bebouwd. Woningen met meer buitenopeningen wegen zwaarder. | GRB-geometrie |
| Bouwouderdom | 17% | Oudere woningen hebben vaker verouderd glas, profielen, deuren of poorten. | Bouwjaar indien beschikbaar, anders Statbel bouwperiode |
| EPC-/comfortproxy | 17% | Slechtere energieprestatie ondersteunt boodschappen rond glas, isolatie, tocht, comfort en premies. | VEKA/EPC-zone of proxy |
| Buurt-draagkracht | 12% | Betaalcapaciteit voor ticketgevoelige investeringen zoals ramen, deuren, poorten en zonwering. | Statbel inkomensstatistiek |
| Koop/verhuis-trigger | 10% | Recent gekocht of verhuisd blijft een sterk renovatiemoment. | Te contracteren: Realo, bpost Movers of vergunde bron |
| Partnerfit | 7% | Kan de juiste WindowPilot-partner dit type lead snel en goed opvolgen? | Eigen campagnehistoriek en partnercapaciteit |

Daarna trekt het model punten af voor belemmeringen zoals te weinig
schrijnwerkvolume, appartement/VME-context, recent vernieuwd schrijnwerk,
erfgoedcontext of tijdelijke werfzones.

## Wat verandert in de app?

Als de gebruiker in de campagne-wizard `WindowPilot` kiest:

- de backend roept `score_leads(..., module_key="windowpilot")` aan;
- elke woning krijgt `score_method_version = windowpilot_property_opportunity_v2_2026_07`;
- het info-icoontje in de database toont WindowPilot-componenten;
- `score_breakdown_json` bevat per component score, gewicht, bewijs, bron en uitleg;
- `module_key = windowpilot` blijft bewaard voor latere tenant- en modulefiltering.

Als de gebruiker `FacadePilot` kiest, blijft het bestaande gevelmodel actief.

## Belangrijk voor klantcommunicatie

Gebruik deze formulering:

> WindowPilot selecteert geen mensen die willen kopen. Het selecteert woningen
> waar ramen, deuren, poorten of zonwering commercieel logisch zijn om te testen,
> op basis van gebouwkenmerken, buurtcontext, energieproxy, timing en partnerfit.

## Databronnen

Dezelfde bronnen als FacadePilot blijven relevant:

- Digitaal Vlaanderen GRB/Capakey en adresregister voor gebouw- en perceeldata;
- Statbel voor inkomens- en buurtcontext;
- bouwjaar of Statbel bouwperiode als ouderdomsproxy;
- VEKA/EPC-zoneproxy voor energie- en comfortsegmentatie;
- GIPOD voor werf- en hindercontext;
- Realo, bpost Movers of een andere vergunde partij voor koop/verhuis-triggers.

Extra WindowPilot-datavelden die later nuttig zijn:

- `window_surface_m2` of `visible_window_area_m2`;
- `window_count`, `raam_count`, `deur_count`, `garage_door_count`, `poort_count`;
- `screen_count` en `rolluik_count`;
- `recent_window_permit` of `recent_schrijnwerk`;
- `window_partner_fit_score` of `window_partner_response_rate`.

Zonder die extra velden gebruikt het model een verdedigbare proxy op basis van
bebouwde oppervlakte, perceelverhouding en woningtype.

## Nog te contacteren partijen

### Realo

Vraag naar recente verkoop/verhuisdata, bouwjaar, woningtype, EPC en waarde-indicatie.

- API-docs: https://api.realo.com/docs
- salesformulier: https://pro.realo.com/nl/contact-sales
- supportadres uit API-docs: support@realo.com

### bpost

Vraag naar Movers, Renovators, Structural Renovators, Home Owners, filtering op
postcodes, eigenaars/huurders, inkomensklasse en unieke QR/personalisatie.

- simulation-data: https://www.bpost.be/nl/simulation-data

### Belmap / GIM / Zadu

Vraag naar verrijkte gebouw-, eigendom-, buurt- en vastgoedprofielen voor
Belgische woningen.

- contact: https://www.belmap.be/contact

## Guardrails

- Geen scraping van Google Street View of immosites als databron.
- Geen claim dat een specifieke bewoner renovatie-intentie heeft.
- Geen cross-tenant data delen.
- Partnerportalen zien alleen hun toegewezen records.
- Responslearnings worden geaggregeerd per segment, partner, regio of campagne.
