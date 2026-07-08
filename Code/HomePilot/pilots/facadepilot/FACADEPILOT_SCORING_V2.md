# FacadePilot scoring v2

Datum: 7 juli 2026  
Model: `facadepilot_property_opportunity_v2_2026_07`

## Doel

FacadePilot scoort geen bewonersintentie. De score is een **property opportunity score**:
welke woningen zijn commercieel interessant om in een gevelcampagne te testen, met
brondata die juridisch en operationeel verdedigbaar is.

De score helpt DAW/Caparol beslissen:

- welke adressen eerst in een QR-postkaartgolf gaan;
- welke partner welk type kansen krijgt;
- welke boodschap of afwerking per segment getest wordt;
- waar extra datakoppeling nodig is voor een betere selectie;
- welke resultaten betrouwbaar genoeg zijn om op te schalen.

## Scorecomponenten

| Component | Gewicht | Wat meet dit? | Bronstatus |
| --- | ---: | --- | --- |
| Gevelvolume | 20% | Meer gevel-/bouwvolume = meer renovatiewaarde en zichtbare impact. | GRB/Capakey of eigen meting |
| Woningtype | 18% | Vrijstaand/halfopen/rijwoning op basis van perceel en bebouwingsratio. | GRB-geometrie |
| Bouwouderdom | 18% | Oudere woningvoorraad verhoogt renovatiekans. Exact bouwjaar is beter dan sectorproxy. | Bouwjaar indien beschikbaar, anders Statbel bouwperiode |
| EPC-/energieproxy | 15% | Slechtere EPC-zone of oudere woningvoorraad wijst op energie-renovatiekans. | VEKA/EPC-zone of proxy |
| Buurt-draagkracht | 14% | Betaalcapaciteit van de omgeving voor duurdere gevelrenovatie. | Statbel inkomensstatistiek |
| Koop/verhuis-trigger | 10% | Recent gekocht/verhuisd is vaak een sterk renovatiemoment. | Te contracteren: Realo, bpost Movers of andere vergunde bron |
| Partnerfit | 5% | Kan de juiste partner dit volume en dit type vraag opvolgen? | Eigen campagnehistoriek en partnercapaciteit |

Daarna trekt het model punten af voor belemmeringen zoals kleine gevels, erfgoed,
recente renovatie/vergunning of tijdelijke werfzones.

## Uitlegbaarheid in de app

Elke gescoorde woning krijgt:

- `lead_score` en `lead_klasse`;
- `score_confidence`;
- `score_method_version`;
- `score_breakdown_json` met per component:
  - score;
  - gewicht;
  - bijdrage aan totaalscore;
  - bewijs;
  - bron;
  - uitleg;
- `score_penalties_json` voor aftrekpunten.

In de database staat naast elke score een informatieknop. Die opent het dossier
met de volledige score-opbouw.

## Databronnen die we nu kunnen gebruiken

### 1. Digitaal Vlaanderen / GRB / adressenregister

Gebruik:

- adres en geocodering;
- perceel en gebouwcontour;
- bebouwde oppervlakte;
- woningtypeproxy via perceelgrootte en bebouwingsratio.

Rol in score:

- gevelvolume;
- woningtype;
- eerste uitsluiting van oninteressante panden.

### 2. Statbel

Gebruik:

- inkomensklasse op statistische sector;
- bouwperiode/woningvoorraad op sectorniveau waar beschikbaar;
- buurtcontext.

Rol in score:

- buurt-draagkracht;
- bouwouderdomproxy;
- segmentatie voor DAW-learnings.

### 3. VEKA / EPC-zoneproxy

Gebruik:

- EPC- of energieprestatiegegevens waar publiek/vergund beschikbaar;
- anders benadering via bouwjaar, woningtype en oudere woningvoorraad.

Rol in score:

- energie-renovatiekans;
- boodschaptesten rond comfort, isolatie en premies.

### 4. GIPOD

Gebruik:

- openbare werken en hindercontext.

Rol in score:

- tijdelijke negatieve factor;
- fotoroutes en postkaarttiming slimmer plannen.

Publieke documentatie: https://docs.athumi.eu/gipod/help/open-data-public-api

## Databronnen waarvoor we partijen moeten contacteren

### Realo

Waarom:

- recente verkoop-/transactie-indicator;
- vastgoedhistoriek, kenmerken, EPC en prijshistoriek;
- API-integratie mogelijk.

Bronnen:

- API-docs: https://api.realo.com/docs
- salesformulier: https://pro.realo.com/nl/contact-sales
- supportadres uit API-docs: support@realo.com

Mail aan Realo:

```text
Onderwerp: Datakoppeling voor gevelrenovatie-prospectie in Belgie

Beste Realo-team,

Wij bouwen met FacadePilot een B2B market-intelligence en QR-postkaartplatform
voor gevelrenovatiecampagnes. Voor DAW/Caparol willen we woningen prioriteren
op basis van woningkenmerken, regio, bouwouderdom, EPC-/energiecontext en
mogelijke koop/verhuis-triggers.

Kunnen jullie aangeven of Realo via API of export de volgende signalen kan leveren
voor Belgische adressen of adresmatches:

- recente verkoop- of off-market indicator;
- maanden sinds laatste verkoop of publicatie;
- woningtype, bouwjaar, oppervlakte, perceel en staat/renovatie-indicatoren;
- EPC-label of EPC-score waar beschikbaar;
- prijs- of waarde-indicatie;
- gebruiksrechten voor B2B-campagneprioritering en aggregatie in klantdashboards.

Belangrijk: wij willen geen bewonersintentie claimen. We gebruiken de data als
property opportunity scoring en rapporteren learnings bij voorkeur geaggregeerd
per regio/partner/segment.

Kunnen jullie ook prijsindicatie geven voor 1.000, 5.000 en 12.000 adresmatches
per jaar, inclusief API-limieten, bewaartermijnen en GDPR/contractuele voorwaarden?

Met vriendelijke groeten,
Kristof
```

### bpost

Waarom:

- doelgroepsegmenten zoals Movers, Renovators, Structural Renovators en Home Owners
  staan in de simulation-data tool;
- mogelijk interessant voor geadresseerde direct mail of doelgroepselectie.

Bron:

- https://www.bpost.be/nl/simulation-data

Te vragen via bpost-accountmanager of contactflow:

```text
Onderwerp: Vraag over bpost data-segmenten voor gevelrenovatiecampagnes

Beste bpost-team,

Wij onderzoeken voor FacadePilot/DAW Belgium een geadresseerde QR-postkaartcampagne
voor gevelrenovatie. In jullie simulation-data tool zien we segmenten zoals Movers,
Renovators, Structural Renovators en Home Owners.

Kunnen jullie verduidelijken:

1. krijgen wij adressen als export, of verzorgt bpost de verzending zonder adresoverdracht?
2. kunnen we filteren op Structural Renovators + Home Owners + specifieke postcodes?
3. kunnen we combineren met inkomensklasse, woningtype of eigenaars/huurders?
4. kunnen appartementen, huurders of jonge gebouwen uitgesloten worden?
5. wat kost 1.000, 5.000 en 12.000 geadresseerde contacten?
6. mag elk adres een unieke QR-code krijgen?
7. kunnen jullie personalisatie/QR-codes verwerken in print en mailflow?
8. mogen wij respons terugkoppelen op segmentniveau zonder individuele profieldata te hergebruiken?

Wij willen de data gebruiken voor property opportunity scoring en meetbare
campagneanalyse, niet voor ongefundeerde bewonersintentieclaims.

Met vriendelijke groeten,
Kristof
```

### Belmap / GIM / Zadu

Waarom:

- verrijkte locatie- en gebouwintelligentie;
- mogelijk betere gebouwkenmerken, buurtprofielen, eigendom/gebruik en doelgroepmodellen.

Bron:

- https://www.belmap.be/contact

Mail/bericht via contactformulier:

```text
Onderwerp: Gebouw- en locatie-intelligentie voor gevelrenovatieprospectie

Beste Belmap/GIM-team,

Wij bouwen FacadePilot, een B2B platform dat gevelrenovatiecampagnes prioriteert
voor producenten en renovatiepartners. We zoeken vergunde data voor Belgische
woningen om adressen te segmenteren op gebouwtype, bouwperiode, waarde-/buurtprofiel,
renovatiekans en uitsluitingsregels.

Kunnen jullie aangeven welke Belmap/Zadu/GIM-datasets bruikbaar zijn voor:

- woningtype en gebouwkenmerken;
- bouwjaar of bouwperiode;
- eigenaars/bewonerscontext waar juridisch toegestaan;
- buurtinkomen of socio-demografische segmentatie;
- recente verhuis/verkoop- of renovatie-indicatoren;
- API/export, gebruiksrechten en prijs voor 1.000/5.000/12.000 adressen?

Met vriendelijke groeten,
Kristof
```

### Athumi / GIPOD

Waarom:

- publieke API voor werken/hinder;
- nuttig als timing- en routebelemmering.

Contact:

- documentatie: https://docs.athumi.eu/gipod/help/open-data-public-api
- gekende contactvraag uit eerdere research: gipod@athumi.eu

### Solvari of andere leadpartijen

Waarom:

- benchmarken welke renovatievragen echt binnenkomen;
- eventueel geen bron voor koude selectie, wel interessant voor conversievalidatie.

Contact uit eerdere research:

- pro@solvari.com

## Implementatiestatus

In deze versie:

- scoremodel v2 is lokaal geimplementeerd;
- ontbrekende commerciele databronnen krijgen neutrale score, geen verzonnen data;
- de app toont per woning een score-uitleg met componenten, bronnen en aftrekpunten;
- de score kan later automatisch verbeteren zodra Realo/bpost/Belmap-data gekoppeld is.

Volgende productiestap:

1. contracteer of test Realo/bpost/Belmap-datakoppeling;
2. voeg importkolommen toe zoals `recent_verkocht`, `months_since_sale`, `epc_label`,
   `epc_score`, `bouwjaar`, `partner_capacity_score`;
3. draai scoring opnieuw;
4. vergelijk QR-respons per component en pas gewichten aan op echte resultaten.
