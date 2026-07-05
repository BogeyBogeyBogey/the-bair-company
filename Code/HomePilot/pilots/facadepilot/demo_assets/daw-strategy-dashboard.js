(function () {
  const LANG_KEY = "facadepilot.internalDemodashboard.language";
  const params = new URLSearchParams(window.location.search);
  const lang = params.get("lang") || localStorage.getItem(LANG_KEY) || "nl";
  const isEn = lang === "en";
  const RAW = window.HOMEPILOT_DASHBOARD || window.HOMEPILOT_LIVE_SNAPSHOT || window.HOMEPILOT_SAMPLE || {};

  const t = (nl, en) => isEn ? en : nl;
  const nf = new Intl.NumberFormat("nl-BE", { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat("nl-BE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

  const esc = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

  const formatInt = (value) => nf.format(Math.round(Number(value) || 0));
  const formatPct = (value) => `${nf1.format(Number(value) || 0)}%`;
  const formatEuro = (value) => {
    const number = Number(value) || 0;
    if (number >= 1000000) return `EUR ${nf1.format(number / 1000000)}M`;
    if (number >= 1000) return `EUR ${formatInt(number / 1000)}k`;
    return `EUR ${formatInt(number)}`;
  };
  const formatArea = (value) => `${formatInt(value)} m²`;

  function properties() {
    return Array.isArray(RAW.properties) ? RAW.properties : [];
  }

  function partners() {
    return Array.isArray(RAW.network?.partners) ? RAW.network.partners : [];
  }

  function bestAssessment(property) {
    const assessments = property?.assessments || {};
    const entries = Object.entries(assessments)
      .map(([key, value]) => ({ key, ...(value || {}) }))
      .filter((item) => Number.isFinite(Number(item.score)));
    return entries.sort((a, b) => Number(b.score) - Number(a.score))[0] || null;
  }

  function grade(property) {
    return bestAssessment(property)?.grade || "";
  }

  function isTop(property) {
    const g = grade(property);
    return g === "A" || g === "A+";
  }

  function countBy(rows, fn) {
    return rows.reduce((acc, row) => {
      const key = fn(row) || "unknown";
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});
  }

  function sum(rows, fn) {
    return rows.reduce((total, row) => total + (Number(fn(row)) || 0), 0);
  }

  function partnerRows() {
    const all = properties();
    return partners().map((partner) => {
      const rows = all.filter((property) => String(property.partner?.id || "") === String(partner.id || ""));
      const topRows = rows.filter(isTop);
      const contacted = Number(partner.contacted || rows.filter((property) => ["sent", "clicked", "responded", "appointment", "no_response"].includes(property.status)).length);
      const responded = Number(partner.responded || rows.filter((property) => ["clicked", "responded", "appointment"].includes(property.status)).length);
      const appointments = Number(partner.appointments || rows.filter((property) => property.status === "appointment").length);
      const responseRate = contacted ? (responded / contacted) * 100 : Number(partner.response_rate_pct || 0);
      const appointmentRate = contacted ? (appointments / contacted) * 100 : Number(partner.appointment_rate_pct || 0);
      const capacity = Number(partner.capacity || 0);
      const capacityLoad = capacity ? (topRows.length / capacity) * 100 : 0;
      const noResponse = Number(partner.no_response || rows.filter((property) => property.status === "no_response").length);
      let classKey = "test_batch";
      if (responseRate >= 60 && appointmentRate >= 22) classKey = "volume_ready";
      else if (responseRate < 55 || noResponse >= 28) classKey = "coach_first";
      return {
        id: partner.id,
        name: partner.name || partner.id,
        region: partner.region || partner.territory || "",
        city: Array.isArray(partner.cities) ? partner.cities[0] : "",
        properties: rows.length || Number(partner.properties || 0),
        top: topRows.length || Number(partner.top_opportunities || 0),
        contacted,
        responded,
        appointments,
        noResponse,
        responseRate,
        appointmentRate,
        capacity,
        capacityLoad,
        pipeline: Number(partner.pipeline_value || sum(rows, (property) => property.estimatedValue)),
        facadeM2: Number(partner.facade_m2 || sum(rows, (property) => property.estimatedFacadeM2)),
        classKey
      };
    }).sort((a, b) => b.top - a.top || b.responseRate - a.responseRate);
  }

  function messageTests() {
    return Array.isArray(RAW.messageStrategy?.best_message_tests)
      ? RAW.messageStrategy.best_message_tests
      : [];
  }

  function segments() {
    return Array.isArray(RAW.campaignSegmentation?.best_segments)
      ? RAW.campaignSegmentation.best_segments
      : [];
  }

  function productRows() {
    const topRows = properties().filter(isTop);
    const styleCounts = countBy(topRows, (property) => property.facadeStyle || property.houseType || "unknown");
    const labels = {
      old_crepi: t("Crepi renovatie", "Crepi renovation"),
      painted_brick: t("Minerale gevelpleister", "Mineral facade render"),
      mixed_facade: t("Mix steenstrips en crepi", "Brick slips and crepi mix"),
      sixties_brick: t("Buitenisolatie + crepi", "External insulation + crepi"),
      brick: t("Baksteen reinigen/heropvoegen", "Brick cleaning/repointing")
    };
    return Object.entries(styleCounts)
      .map(([key, count]) => ({
        key,
        label: labels[key] || key.replaceAll("_", " "),
        count,
        share: topRows.length ? (count / topRows.length) * 100 : 0
      }))
      .sort((a, b) => b.count - a.count);
  }

  const HOUSE_LABELS = {
    rijwoning: t("Rijwoning", "Terraced house"),
    halfopen: t("Halfopen woning", "Semi-detached house"),
    vrijstaand: t("Vrijstaande woning", "Detached house"),
    bungalow: t("Bungalow", "Bungalow"),
    hoekwoning: t("Hoekwoning", "Corner house")
  };

  const FACADE_LABELS = {
    brick: t("Baksteen", "Brick"),
    painted_brick: t("Geschilderde baksteen", "Painted brick"),
    old_crepi: t("Oude crepi", "Old crepi"),
    mixed_facade: t("Gemengde gevel", "Mixed facade"),
    sixties_brick: t("Jaren 60/70 baksteen", "Sixties/seventies brick")
  };

  const INCOME_LABELS = {
    budgetbewust: t("Budgetbewuste buurt", "Budget-conscious area"),
    middenklasse: t("Middenklasse buurt", "Middle-income area"),
    comfortklasse: t("Comfortklasse", "Comfort-class area"),
    premiumbuurt: t("Premiumbuurt", "Premium area")
  };

  const MESSAGE_LABELS = {
    facade_refresh: t("Gevel opfrissen", "Facade refresh"),
    energy_savings: t("Energie & comfort", "Energy and comfort"),
    maintenance_free: t("Minder onderhoud", "Lower maintenance"),
    local_partner_review: t("Lokale partnercheck", "Local partner review"),
    premium_finish: t("Premium uitstraling", "Premium finish")
  };

  function labelFromMap(map, value) {
    const key = String(value || "").trim();
    return map[key] || key.replaceAll("_", " ") || t("Onbekend", "Unknown");
  }

  function houseLabel(value) {
    return labelFromMap(HOUSE_LABELS, value);
  }

  function facadeLabel(value) {
    return labelFromMap(FACADE_LABELS, value);
  }

  function incomeClass(property) {
    const direct = property?.neighbourhoodIncomeClass;
    if (direct) return direct;
    const feature = (property?.publicContext?.features || []).find((item) => item.key === "stat_sector_income_class");
    return feature?.value || "middenklasse";
  }

  function incomeLabel(value) {
    return labelFromMap(INCOME_LABELS, value);
  }

  function suggestedMessageAngle(property) {
    const style = property?.facadeStyle || "";
    const income = incomeClass(property);
    const house = property?.houseType || "";
    if (income === "premiumbuurt" || house === "vrijstaand") return "premium_finish";
    if (style === "old_crepi" || style === "painted_brick") return "facade_refresh";
    if (style === "sixties_brick" || house === "bungalow") return "energy_savings";
    if (style === "brick") return "maintenance_free";
    return "local_partner_review";
  }

  function messageLabel(value) {
    return MESSAGE_LABELS[value] || String(value || "").replaceAll("_", " ");
  }

  function postcardPromise(angle) {
    const map = {
      facade_refresh: t("Laat uw gevel gratis beoordelen door een lokale DAW-partner.", "Have your facade reviewed by a local DAW partner."),
      energy_savings: t("Ontdek of gevelisolatie comfort en energiewinst kan opleveren.", "Discover whether facade insulation can improve comfort and energy performance."),
      maintenance_free: t("Minder onderhoud, frissere gevel: bekijk een veilige renovatiecheck.", "Lower maintenance, fresher facade: review a safe renovation check."),
      local_partner_review: t("Een erkende lokale partner bekijkt of uw gevel klaar is voor renovatie.", "A trusted local partner checks whether your facade is renovation-ready."),
      premium_finish: t("Bekijk welke premium afwerking past bij uw woning en buurt.", "See which premium finish fits your home and neighbourhood.")
    };
    return map[angle] || map.local_partner_review;
  }

  function landingPromise(angle) {
    const map = {
      facade_refresh: t("Voor/na-inspiratie, afwerkingskeuzes en afspraak met de juiste partner.", "Before/after inspiration, finish choices and an appointment with the right partner."),
      energy_savings: t("Uitleg over isolatiepad, comfortvoordelen, subsidievragen en partnercheck.", "Explanation of insulation path, comfort benefits, subsidy questions and partner check."),
      maintenance_free: t("Onderhoudsarme oplossingen, kleurkeuzes en snelle geschiktheidscheck.", "Low-maintenance solutions, color choices and quick suitability check."),
      local_partner_review: t("Lokale referenties, partnervertrouwen en laagdrempelige gevelscan.", "Local references, partner trust and low-friction facade scan."),
      premium_finish: t("Premium referenties, kleurpaletten, materiaalgevoel en offerte-aanvraag.", "Premium references, color palettes, material feel and quote request.")
    };
    return map[angle] || map.local_partner_review;
  }

  function groupRows(rows, keyFn, labelFn = (key) => key) {
    const groups = new Map();
    rows.forEach((property) => {
      const key = keyFn(property) || "unknown";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(property);
    });
    return Array.from(groups.entries()).map(([key, items]) => {
      const contacted = items.filter((property) => ["sent", "clicked", "responded", "appointment", "no_response"].includes(property.status)).length;
      const responded = items.filter((property) => ["clicked", "responded", "appointment"].includes(property.status)).length;
      const appointments = items.filter((property) => property.status === "appointment").length;
      const top = items.filter(isTop).length;
      return {
        key,
        label: labelFn(key),
        rows: items,
        count: items.length,
        top,
        topShare: items.length ? (top / items.length) * 100 : 0,
        responseRate: contacted ? (responded / contacted) * 100 : 0,
        appointmentRate: contacted ? (appointments / contacted) * 100 : 0,
        value: sum(items, (property) => property.estimatedValue),
        facadeM2: sum(items, (property) => property.estimatedFacadeM2)
      };
    }).sort((a, b) => b.responseRate - a.responseRate || b.topShare - a.topShare || b.count - a.count);
  }

  function computeStrategy() {
    const rows = properties();
    const topRows = rows.filter(isTop);
    const partnerData = partnerRows();
    const volumeReady = partnerData.filter((partner) => partner.classKey === "volume_ready");
    const coachFirst = partnerData.filter((partner) => partner.classKey === "coach_first");
    const testBatch = partnerData.filter((partner) => partner.classKey === "test_batch");
    const noResponse = rows.filter((property) => property.status === "no_response");
    const contacted = rows.filter((property) => ["sent", "clicked", "responded", "appointment", "no_response"].includes(property.status)).length;
    const responded = rows.filter((property) => ["clicked", "responded", "appointment"].includes(property.status)).length;
    const appointments = rows.filter((property) => property.status === "appointment").length;
    const responseRate = contacted ? (responded / contacted) * 100 : 0;
    const pipeline = sum(topRows, (property) => property.estimatedValue);
    const facadeM2 = sum(topRows, (property) => property.estimatedFacadeM2);
    const strongestRegion = partnerData[0] || {};
    const capacityRisk = partnerData.slice().sort((a, b) => b.capacityLoad - a.capacityLoad).slice(0, 2);
    const weakerFollowup = partnerData.slice().sort((a, b) => b.noResponse - a.noResponse || a.responseRate - b.responseRate).slice(0, 2);
    const topMessage = messageTests()[0] || {};
    const topSegment = segments()[0] || {};
    const products = productRows();
    const topProduct = products[0] || {};
    const objections = countBy(rows.flatMap((property) => property.objections || []), (item) => item);
    const topObjection = Object.entries(objections).sort((a, b) => b[1] - a[1])[0];

    const firstWaveCount = Math.max(1, Math.ceil(topRows.length / 400));
    const reviewBatch = Array.isArray(RAW.partnerAssignment?.best_assignment)
      ? RAW.partnerAssignment.best_assignment.reduce((total, item) => total + (Number(item.selected_count) || 0), 0)
      : 50;

    const insights = [
      {
        id: "market-capacity",
        theme: t("Markt en capaciteit", "Market and capacity"),
        title: t("Er is genoeg A/A+ potentieel voor meerdere golven, maar DAW moet partnercapaciteit sturen.", "There is enough A/A+ potential for multiple waves, but DAW must steer partner capacity."),
        see: t(`${formatInt(topRows.length)} A/A+ woningen, goed voor ${formatArea(facadeM2)} gevel en ${formatEuro(pipeline)} pipeline. Hoogste concentratie zit bij ${strongestRegion.name || "de grootste partnerzone"}.`, `${formatInt(topRows.length)} A/A+ properties, worth ${formatArea(facadeM2)} facade and ${formatEuro(pipeline)} pipeline. The highest concentration sits with ${strongestRegion.name || "the largest partner zone"}.`),
        why: t("Dit bepaalt waar DAW verificatiebudget, partneraandacht en eerste postkaartgolven op inzet.", "This decides where DAW spends verification budget, partner attention and first postcard waves."),
        decide: t(`Start ${firstWaveCount} gecontroleerde campagnegolven en reserveer extra opvolgcapaciteit voor ${capacityRisk.map((p) => p.name).join(" en ") || "de drukste partnerzones"}.`, `Launch ${firstWaveCount} controlled campaign waves and reserve extra follow-up capacity for ${capacityRisk.map((p) => p.name).join(" and ") || "the busiest partner zones"}.`),
        measure: t("Meet QR-scanrate, afspraakratio en opvolgtijd per partnerzone vooraleer volume wordt opgeschaald.", "Measure QR scan rate, appointment rate and follow-up speed per partner zone before scaling volume."),
        metric: `${formatInt(topRows.length)} A/A+`
      },
      {
        id: "partner-growth",
        theme: t("Partnergroei", "Partner growth"),
        title: t("Niet elke partner moet evenveel leads krijgen; het netwerk moet als portefeuille gestuurd worden.", "Not every partner should receive the same volume; the network should be managed as a portfolio."),
        see: t(`${formatInt(volumeReady.length)} partners zijn volumeklaar, ${formatInt(coachFirst.length)} moeten eerst opvolging of capaciteit bewijzen, ${formatInt(testBatch.length)} passen in een testbatch.`, `${formatInt(volumeReady.length)} partners are volume-ready, ${formatInt(coachFirst.length)} must prove follow-up or capacity first, ${formatInt(testBatch.length)} fit a test batch.`),
        why: t("DAW vermijdt dat sterke regio's verbranden door trage opvolging of te veel druk op een partner.", "DAW avoids burning strong regions through slow follow-up or too much pressure on one partner."),
        decide: t(`Geef volume aan ${volumeReady.slice(0, 2).map((p) => p.name).join(" en ") || "de sterkste partners"}; coach ${coachFirst.slice(0, 2).map((p) => p.name).join(" en ") || "de zwakkere follow-up zones"} voor opschaling.`, `Give volume to ${volumeReady.slice(0, 2).map((p) => p.name).join(" and ") || "the strongest partners"}; coach ${coachFirst.slice(0, 2).map((p) => p.name).join(" and ") || "weaker follow-up zones"} before scaling.`),
        measure: t("Opvolgafspraken: tijd tot eerste contact, afspraakratio, offertefeedback en gewonnen/verloren per batch.", "Partner follow-up agreement: time to first contact, appointment rate, quote feedback and won/lost per batch."),
        metric: `${formatInt(volumeReady.length)}/${formatInt(partnerData.length)}`
      },
      {
        id: "message-learning",
        theme: t("Boodschaptest", "Message test"),
        title: t("DAW moet niet een campagne lanceren, maar leren welke belofte per segment werkt.", "DAW should not launch one campaign, but learn which promise works per segment."),
        see: t(`De sterkste demohoek is ${String(topMessage.angle || "facade_refresh").replaceAll("_", " ")} met ${formatInt(topMessage.property_count || topSegment.property_count || 0)} records in de testcel.`, `The strongest demo angle is ${String(topMessage.angle || "facade_refresh").replaceAll("_", " ")} with ${formatInt(topMessage.property_count || topSegment.property_count || 0)} records in the test cell.`),
        why: t("QR-respons kan aantonen of energie, esthetiek, onderhoudsgemak, subsidiecheck of lokale partnertrust de markt activeert.", "QR response can show whether energy, aesthetics, low maintenance, subsidy check or local partner trust activates the market."),
        decide: t("Test per golf maximaal twee boodschaphoeken, met dezelfde denominator en duidelijke stop/scale-regel.", "Test at most two message angles per wave, with the same denominator and a clear stop/scale rule."),
        measure: t("Scanrate, formulierstart, gekozen reden van interesse, afspraakaanvraag en bezwaar per boodschap.", "Scan rate, form start, chosen interest reason, appointment request and objection per message."),
        metric: `${formatInt(messageTests().length)} tests`
      },
      {
        id: "product-finish",
        theme: t("Product en afwerking", "Product and finish"),
        title: t("Renderkeuzes kunnen DAW tonen welke afwerkingen tractie krijgen per woningtype en regio.", "Render choices can show DAW which finishes gain traction by property type and region."),
        see: t(`${topProduct.label || "Crepi"} komt het vaakst terug in de A/A+ demoqueue: ${formatInt(topProduct.count || 0)} records, ${formatPct(topProduct.share || 0)} van de topkansen.`, `${topProduct.label || "Crepi"} appears most often in the A/A+ demo queue: ${formatInt(topProduct.count || 0)} records, ${formatPct(topProduct.share || 0)} of top opportunities.`),
        why: t("DAW kan productfocus, staalkaarten en partnertraining afstemmen op echte voorkeuren in plaats van buikgevoel.", "DAW can tune product focus, sample cards and partner training to observed preference instead of gut feel."),
        decide: t("Laat elke QR-flow minstens een afwerking en kleurvoorkeur capteren voordat sales opvolgt.", "Capture at least one finish and color preference in every QR flow before sales follows up."),
        measure: t("Renderstijlkeuze, kleurkeuze, doorklik naar afspraak en offerteproduct per adres.", "Render style choice, color choice, appointment click-through and quote product per address."),
        metric: topProduct.label || "Crepi"
      },
      {
        id: "no-response",
        theme: t("No-response potentieel", "No-response potential"),
        title: t("Geen reactie is geen verloren markt; het is een aparte retargetingvraag.", "No response is not a lost market; it is a separate retargeting question."),
        see: t(`${formatInt(noResponse.length)} records staan in no-response, met ${weakerFollowup.map((p) => p.name).join(" en ") || "enkele partnerzones"} als opvallende opvolgzones.`, `${formatInt(noResponse.length)} records are no-response, with ${weakerFollowup.map((p) => p.name).join(" and ") || "some partner zones"} standing out as follow-up zones.`),
        why: t("DAW kan leren of het probleem boodschap, timing, partnertrust of opvolgsnelheid is.", "DAW can learn whether the issue is message, timing, partner trust or follow-up speed."),
        decide: t("Herstart no-response niet met dezelfde kaart, maar met een zachtere QR-flow en een andere reden van interesse.", "Do not restart no-response with the same card; use a softer QR flow and a different interest reason."),
        measure: t("Retarget-scanrate, tweede formulierstart, bezwaar en partnercontact binnen 48 uur.", "Retarget scan rate, second form start, objection and partner contact within 48 hours."),
        metric: formatInt(noResponse.length)
      },
      {
        id: "next-wave",
        theme: t("Volgende golf", "Next wave"),
        title: t("De eerstvolgende actie is geen brede lancering, maar een meetbare buyer-review golf.", "The next move is not a broad launch, but a measurable buyer-review wave."),
        see: t(`${formatInt(reviewBatch)} records zitten in de autoresearched partnerreviewqueue; huidige demo-responsgraad is ${formatPct(responseRate)} en ${formatInt(appointments)} afspraken.`, `${formatInt(reviewBatch)} records sit in the autoresearched partner review queue; current demo response rate is ${formatPct(responseRate)} with ${formatInt(appointments)} appointments.`),
        why: t("Een kleine, meetbare golf levert DAW sneller bewijs voor partnerfit, boodschap en producttractie.", "A small measurable wave gives DAW faster proof on partner fit, message and product traction."),
        decide: t("Kies 3 partners, 2 regio's en 2 boodschaphoeken voor de eerste echte test.", "Choose 3 partners, 2 regions and 2 message angles for the first real test."),
        measure: t("Een vast scorecardritme: scan, formulier, afspraak, offerte, gewonnen/verloren, partnerfeedback.", "A fixed scorecard rhythm: scan, form, appointment, quote, won/lost and partner feedback."),
        metric: formatPct(responseRate)
      }
    ];

    return {
      rows,
      topRows,
      partnerData,
      volumeReady,
      coachFirst,
      testBatch,
      products,
      topMessage,
      topSegment,
      noResponse,
      responseRate,
      appointments,
      insights
    };
  }

  const strategy = RAW.dawStrategy || computeStrategy();
  let selectedStrategyPartnerId = "";

  function injectStyles() {
    if (document.getElementById("daw-strategy-dashboard-style")) return;
    const style = document.createElement("style");
    style.id = "daw-strategy-dashboard-style";
    style.textContent = `
      :root {
        --daw-amber: #e99b50;
        --daw-blue: #5aa2e0;
        --daw-green: #5fbe8f;
        --daw-card: rgba(17, 26, 36, .92);
        --daw-ink: #edf3f8;
        --daw-muted: #9caabc;
      }
      .nav-tab[data-view="property"],
      .nav-tab[data-view="trust"],
      #trust {
        display: none !important;
      }
      #accessLensBox,
      #accessLensPanel,
      #executive .executive-layout,
      #executive .executive-split,
      #executive .executive-learning-panel,
      #trust .trust-layout-grid,
      #trust .trust-split,
      #campaign > .split-layout,
      #campaign > .recommendations-panel,
      #intelligenceDecisionBrief,
      #intelligenceLabCockpit,
      #intelligence .intelligence-impact,
      #intelligence .intelligence-grid,
      #intelligence .intelligence-split {
        display: none !important;
      }
      .nav-tab[data-view="executive"] { order: 1; }
      .nav-tab[data-view="map"] { order: 2; }
      .nav-tab[data-view="overview"] { order: 3; }
      .nav-tab[data-view="campaign"] { order: 4; }
      .nav-tab[data-view="intelligence"] { order: 5; }
      .nav-tab[data-view="database"] { order: 6; }
      .nav-tab[data-view="brain"] { order: 7; }
      .strategy-shell {
        border: 1px solid rgba(255,255,255,.10);
        border-radius: 10px;
        background:
          radial-gradient(700px 340px at 15% -5%, rgba(233,155,80,.16), transparent 60%),
          radial-gradient(620px 360px at 92% 10%, rgba(90,162,224,.14), transparent 62%),
          linear-gradient(180deg, rgba(255,255,255,.055), rgba(255,255,255,.018)),
          #0b1118;
        box-shadow: inset 0 1px 0 rgba(255,255,255,.045), 0 24px 70px rgba(0,0,0,.24);
      }
      .strategy-head {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: 18px;
        align-items: end;
        padding: 22px;
        border-bottom: 1px solid rgba(255,255,255,.08);
      }
      .strategy-head .eyebrow,
      .strategy-eyebrow {
        color: var(--daw-amber);
        font-size: 11px;
        font-weight: 950;
        letter-spacing: .12em;
        text-transform: uppercase;
      }
      .strategy-head h2 {
        margin: 8px 0 0;
        color: var(--daw-ink);
        font-size: clamp(28px, 3vw, 46px);
        line-height: .98;
        letter-spacing: 0;
      }
      .strategy-head p {
        margin: 10px 0 0;
        max-width: 900px;
        color: var(--daw-muted);
        font-size: 16px;
        line-height: 1.48;
      }
      .strategy-pulse {
        min-width: 190px;
        border: 1px solid rgba(95,190,143,.24);
        border-radius: 8px;
        background: rgba(95,190,143,.10);
        padding: 14px;
      }
      .strategy-pulse span,
      .strategy-pulse small {
        display: block;
        color: #b7c5d2;
        font-weight: 800;
      }
      .strategy-pulse strong {
        display: block;
        color: var(--daw-green);
        font-size: 28px;
        line-height: 1;
        margin: 4px 0;
      }
      .strategy-decision-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 16px;
        padding: 16px;
      }
      .strategy-card {
        border: 1px solid rgba(255,255,255,.10);
        border-radius: 8px;
        background: linear-gradient(180deg, rgba(255,255,255,.048), rgba(255,255,255,.014)), rgba(9, 15, 22, .74);
        padding: 20px;
        min-height: 0;
        display: grid;
        gap: 14px;
      }
      .strategy-card h3 {
        margin: 6px 0 0;
        color: var(--daw-ink);
        font-size: clamp(20px, 1.45vw, 25px);
        line-height: 1.2;
      }
      .strategy-card .metric {
        justify-self: start;
        border: 1px solid rgba(233,155,80,.24);
        border-radius: 999px;
        background: rgba(233,155,80,.11);
        color: #f1b66f;
        padding: 6px 10px;
        font-size: 12px;
        font-weight: 950;
      }
      .strategy-four {
        display: grid;
        gap: 10px;
      }
      .strategy-four div {
        border-left: 3px solid rgba(90,162,224,.62);
        border-radius: 6px;
        background: rgba(255,255,255,.025);
        padding: 10px 11px 10px 12px;
      }
      .strategy-four span {
        display: block;
        color: var(--daw-amber);
        font-size: 10px;
        font-weight: 950;
        letter-spacing: .08em;
        text-transform: uppercase;
      }
      .strategy-four p {
        margin: 3px 0 0;
        color: #d0d9e3;
        font-size: 14px;
        line-height: 1.42;
      }
      .strategy-strip {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 10px;
        padding: 0 14px 14px;
      }
      .strategy-stat,
      .strategy-mini,
      .strategy-partner-row,
      .strategy-qr-step,
      .strategy-product-row {
        border: 1px solid rgba(255,255,255,.10);
        border-radius: 8px;
        background: rgba(7, 12, 18, .62);
        padding: 12px;
      }
      .strategy-stat span,
      .strategy-mini span {
        display: block;
        color: var(--daw-muted);
        font-size: 11px;
        font-weight: 850;
        text-transform: uppercase;
      }
      .strategy-stat strong,
      .strategy-mini strong {
        display: block;
        color: var(--daw-ink);
        font-size: 23px;
        margin-top: 5px;
      }
      .strategy-stat small,
      .strategy-mini small {
        display: block;
        color: #8e9caf;
        line-height: 1.3;
        margin-top: 4px;
      }
      .strategy-section {
        margin-bottom: 16px;
      }
      .strategy-section .panel-head h2 {
        color: var(--daw-ink);
      }
      .strategy-partner-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 12px;
      }
      .strategy-partner-row {
        display: grid;
        gap: 8px;
        width: 100%;
        text-align: left;
        cursor: pointer;
        color: inherit;
      }
      button.strategy-partner-row {
        appearance: none;
        font: inherit;
      }
      .strategy-partner-row.is-active {
        border-color: rgba(233,155,80,.72);
        box-shadow: inset 0 0 0 1px rgba(233,155,80,.22), 0 16px 40px rgba(0,0,0,.18);
      }
      .strategy-partner-row strong {
        color: var(--daw-ink);
        font-size: 17px;
      }
      .strategy-partner-row b {
        color: var(--daw-green);
      }
      .strategy-partner-row small {
        color: var(--daw-muted);
        line-height: 1.35;
      }
      .strategy-qr-flow {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 10px;
      }
      .strategy-qr-step strong {
        color: var(--daw-ink);
        display: block;
        margin: 6px 0;
      }
      .strategy-qr-step span {
        color: var(--daw-amber);
        font-weight: 950;
        font-size: 11px;
      }
      .strategy-qr-step small {
        color: var(--daw-muted);
        line-height: 1.35;
      }
      .strategy-product-list {
        display: grid;
        gap: 10px;
      }
      .strategy-product-row {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 90px;
        gap: 12px;
        align-items: center;
      }
      .strategy-product-row strong {
        color: var(--daw-ink);
      }
      .strategy-product-row span {
        color: var(--daw-muted);
        display: block;
        margin-top: 4px;
      }
      .strategy-product-bar {
        height: 10px;
        border-radius: 999px;
        background: rgba(255,255,255,.08);
        overflow: hidden;
      }
      .strategy-product-bar i {
        display: block;
        height: 100%;
        border-radius: inherit;
        background: linear-gradient(90deg, var(--daw-green), var(--daw-amber));
      }
      .strategy-deep-dive,
      .strategy-message-lab,
      .strategy-segment-lab {
        margin-top: 14px;
        border: 1px solid rgba(255,255,255,.10);
        border-radius: 8px;
        background: rgba(7, 12, 18, .64);
        padding: 16px;
      }
      .strategy-deep-dive h3,
      .strategy-message-lab h3,
      .strategy-segment-lab h3 {
        margin: 0 0 12px;
        color: var(--daw-ink);
        font-size: 20px;
      }
      .strategy-deep-grid,
      .strategy-message-grid,
      .strategy-segment-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
      }
      .strategy-deep-card,
      .strategy-message-card,
      .strategy-segment-card {
        border: 1px solid rgba(255,255,255,.09);
        border-radius: 8px;
        background: rgba(17, 26, 36, .82);
        padding: 14px;
      }
      .strategy-deep-card span,
      .strategy-message-card span,
      .strategy-segment-card span {
        display: block;
        color: var(--daw-amber);
        font-size: 10px;
        font-weight: 950;
        letter-spacing: .09em;
        text-transform: uppercase;
      }
      .strategy-deep-card strong,
      .strategy-message-card strong,
      .strategy-segment-card strong {
        display: block;
        color: var(--daw-ink);
        font-size: 18px;
        line-height: 1.22;
        margin: 7px 0 5px;
      }
      .strategy-deep-card small,
      .strategy-message-card small,
      .strategy-segment-card small {
        color: var(--daw-muted);
        line-height: 1.4;
      }
      .strategy-message-card .promise {
        margin-top: 10px;
        padding-top: 10px;
        border-top: 1px solid rgba(255,255,255,.08);
      }
      .strategy-message-card .promise b {
        color: #d0d9e3;
      }
      .simple-data-check {
        display: grid;
        gap: 16px;
      }
      .simple-data-check .strategy-head {
        border-bottom: 0;
        padding: 22px;
      }
      .simple-data-check-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        padding: 0 22px 22px;
      }
      .simple-data-check-card {
        border: 1px solid rgba(255,255,255,.10);
        border-radius: 8px;
        background: rgba(7, 12, 18, .72);
        padding: 16px;
      }
      .simple-data-check-card span {
        display: block;
        color: var(--daw-amber);
        font-size: 11px;
        font-weight: 950;
        letter-spacing: .09em;
        text-transform: uppercase;
      }
      .simple-data-check-card strong {
        display: block;
        color: var(--daw-ink);
        font-size: 20px;
        margin: 8px 0 6px;
      }
      .simple-data-check-card small {
        color: var(--daw-muted);
        line-height: 1.45;
      }
      .intelligence-decision-list.strategy-owned {
        display: grid;
        gap: 12px;
      }
      .intelligence-decision-list.strategy-owned .strategy-card {
        min-height: 0;
      }
      @media (max-width: 1100px) {
        .strategy-decision-grid,
        .strategy-partner-grid,
        .strategy-deep-grid,
        .strategy-message-grid,
        .strategy-segment-grid,
        .simple-data-check-grid { grid-template-columns: 1fr 1fr; }
        .strategy-strip,
        .strategy-qr-flow { grid-template-columns: 1fr 1fr; }
      }
      @media (max-width: 760px) {
        .strategy-head,
        .strategy-decision-grid,
        .strategy-strip,
        .strategy-partner-grid,
        .strategy-qr-flow,
        .strategy-deep-grid,
        .strategy-message-grid,
        .strategy-segment-grid,
        .simple-data-check-grid,
        .strategy-product-row { grid-template-columns: 1fr; }
      }
    `;
    document.head.appendChild(style);
  }

  function setText(selector, value) {
    const element = document.querySelector(selector);
    if (element) element.textContent = value;
  }

  function labelNavigation() {
    const labels = {
      executive: t("DAW Cockpit", "DAW Cockpit"),
      map: t("Marktkaart", "Market map"),
      overview: t("Partnerprestaties", "Partner performance"),
      campaign: t("Campagnelearnings", "Campaign learnings"),
      intelligence: t("Product & Afwerking", "Product & Finish"),
      database: t("Adresdatabase", "Address database"),
      brain: t("Second Brain", "Second Brain")
    };
    document.querySelectorAll(".nav-tab").forEach((button) => {
      if (labels[button.dataset.view]) button.textContent = labels[button.dataset.view];
    });
    setText("#workspaceEyebrow", t("DAW Belgium demo - market intelligence + partner growth", "DAW Belgium demo - market intelligence + partner growth"));
    setText("#workspaceTitle", t("DAW Intelligence platform", "DAW Intelligence platform"));
    const search = document.getElementById("searchInput");
    if (search) search.placeholder = t("Zoek adres, partner, regio of signaal", "Search address, partner, region or signal");
  }

  function metricStrip() {
    const s = computeStrategy();
    return `
      <div class="strategy-strip">
        <div class="strategy-stat"><span>${t("Topmarkt", "Top market")}</span><strong>${formatInt(s.topRows.length)}</strong><small>${t("A/A+ woningen voor gefaseerde activatie", "A/A+ properties for phased activation")}</small></div>
        <div class="strategy-stat"><span>${t("Partnerportefeuille", "Partner portfolio")}</span><strong>${formatInt(s.volumeReady.length)}/${formatInt(s.partnerData.length)}</strong><small>${t("partners klaar voor meer volume", "partners ready for more volume")}</small></div>
        <div class="strategy-stat"><span>${t("Responsbewijs", "Response proof")}</span><strong>${formatPct(s.responseRate)}</strong><small>${t("synthetische demo-respons op gecontacteerde records", "synthetic demo response on contacted records")}</small></div>
        <div class="strategy-stat"><span>${t("Productsignaal", "Product signal")}</span><strong>${esc(s.products[0]?.label || "Crepi")}</strong><small>${t("meest voorkomende topkans in demoqueue", "most common top opportunity in demo queue")}</small></div>
      </div>
    `;
  }

  function insightCard(insight) {
    return `
      <article class="strategy-card">
        <div>
          <span class="strategy-eyebrow">${esc(insight.theme)}</span>
          <h3>${esc(insight.title)}</h3>
        </div>
        <span class="metric">${esc(insight.metric)}</span>
        <div class="strategy-four">
          <div><span>${t("Wat zien we?", "What do we see?")}</span><p>${esc(insight.see)}</p></div>
          <div><span>${t("Waarom telt dat?", "Why does it matter?")}</span><p>${esc(insight.why)}</p></div>
          <div><span>${t("Wat beslist DAW?", "What does DAW decide?")}</span><p>${esc(insight.decide)}</p></div>
          <div><span>${t("Hoe meten we dit?", "How do we measure it?")}</span><p>${esc(insight.measure)}</p></div>
        </div>
      </article>
    `;
  }

  function renderExecutiveStrategy() {
    const executive = document.getElementById("executive");
    if (!executive) return;
    let shell = document.getElementById("dawStrategyCockpit");
    if (!shell) {
      shell = document.createElement("section");
      shell.id = "dawStrategyCockpit";
      shell.className = "strategy-shell strategy-section";
      executive.prepend(shell);
    }
    const s = computeStrategy();
    shell.innerHTML = `
      <div class="strategy-head">
        <div>
          <div class="eyebrow">${t("DAW Cockpit", "DAW Cockpit")}</div>
          <h2>${t("Van adressen naar beslissingen over markt, partners en producttractie.", "From addresses to decisions about market, partners and product traction.")}</h2>
          <p>${t("Dit dashboard stuurt DAW op de vragen die ertoe doen: waar zit gevelpotentieel, welke partner kan het verzilveren, welke boodschap activeert de markt en welke productlijn verdient meer aandacht.", "This dashboard steers DAW on the questions that matter: where facade potential sits, which partner can convert it, which message activates the market and which product line deserves more attention.")}</p>
        </div>
        <div class="strategy-pulse">
          <span>${t("Volgende boardroombeslissing", "Next boardroom decision")}</span>
          <strong>${t("Golf 1", "Wave 1")}</strong>
          <small>${t("3 partners - 2 regio's - 2 boodschappen", "3 partners - 2 regions - 2 messages")}</small>
        </div>
      </div>
      ${metricStrip()}
      <div class="strategy-decision-grid">
        ${s.insights.map(insightCard).join("")}
      </div>
    `;
  }

  function renderStrategicBrief() {
    const brief = document.getElementById("intelligenceDecisionBrief");
    if (!brief) return;
    brief.querySelector(".eyebrow").textContent = t("Strategische learnings", "Strategic learnings");
    brief.querySelector("h2").textContent = t("Wat DAW nu kan bijsturen", "What DAW can steer now");
    setText("#intelligenceBriefStatus", t("boardroom ready", "boardroom ready"));
    const matrix = document.getElementById("intelligenceDecisionMatrix");
    const summary = document.getElementById("intelligenceBriefSummary");
    const s = computeStrategy();
    if (summary) {
      summary.innerHTML = `
        <div class="intelligence-brief-metric"><span>${t("Genoeg voor", "Enough for")}</span><strong>${formatInt(Math.max(1, Math.ceil(s.topRows.length / 400)))}</strong><small>${t("eerste campagnegolven", "first campaign waves")}</small></div>
        <div class="intelligence-brief-metric"><span>${t("Volumeklaar", "Volume-ready")}</span><strong>${formatInt(s.volumeReady.length)}</strong><small>${t("partners met sterk responsbewijs", "partners with strong response proof")}</small></div>
        <div class="intelligence-brief-metric"><span>${t("Testcellen", "Test cells")}</span><strong>${formatInt(messageTests().length)}</strong><small>${t("boodschap/product hypotheses", "message/product hypotheses")}</small></div>
        <div class="intelligence-brief-metric"><span>${t("Retargeting", "Retargeting")}</span><strong>${formatInt(s.noResponse.length)}</strong><small>${t("records voor zachtere tweede golf", "records for softer second wave")}</small></div>
      `;
    }
    if (matrix) {
      matrix.classList.add("strategy-owned");
      matrix.innerHTML = s.insights.map(insightCard).join("");
    }
  }

  function renderPartnerPerformance() {
    const overview = document.getElementById("overview");
    if (!overview) return;
    let panel = document.getElementById("partnerPerformanceStrategy");
    if (!panel) {
      panel = document.createElement("section");
      panel.id = "partnerPerformanceStrategy";
      panel.className = "panel strategy-section";
      overview.prepend(panel);
    }
    const s = computeStrategy();
    const rows = s.partnerData.slice(0, 9);
    if (!selectedStrategyPartnerId || !rows.some((partner) => partner.id === selectedStrategyPartnerId)) {
      selectedStrategyPartnerId = rows[0]?.id || "";
    }
    const selectedPartner = rows.find((partner) => partner.id === selectedStrategyPartnerId) || rows[0];
    const label = {
      volume_ready: t("volume klaar", "volume ready"),
      coach_first: t("eerst coachen", "coach first"),
      test_batch: t("testbatch", "test batch")
    };
    panel.innerHTML = `
      <div class="panel-head">
        <div><p class="eyebrow">${t("Partnerprestaties", "Partner performance")}</p><h2>${t("Wie kan DAW-vraag echt verzilveren?", "Who can truly convert DAW demand?")}</h2></div>
        <div class="scope-chip">${t("portfolio view", "portfolio view")}</div>
      </div>
      <div class="strategy-partner-grid">
        ${rows.map((partner) => `
          <button class="strategy-partner-row ${partner.id === selectedStrategyPartnerId ? "is-active" : ""}" type="button" data-strategy-partner="${esc(partner.id)}">
            <span class="strategy-eyebrow">${esc(partner.region)} - ${esc(label[partner.classKey])}</span>
            <strong>${esc(partner.name)}</strong>
            <small>${formatInt(partner.top)} A/A+ - ${formatPct(partner.responseRate)} ${t("respons", "response")} - ${formatPct(partner.appointmentRate)} ${t("afspraakratio", "appointment rate")}</small>
            <b>${formatEuro(partner.pipeline)}</b>
            <small>${t("Beslissing:", "Decision:")} ${partner.classKey === "volume_ready"
              ? t("meer volume geven en opvolging meten.", "give more volume and measure follow-up.")
              : partner.classKey === "coach_first"
                ? t("eerst opvolging, capaciteit of partnerproof verbeteren.", "improve follow-up, capacity or partner proof first.")
                : t("kleine testbatch geven met duidelijke stop/scale-regel.", "give a small test batch with a clear stop/scale rule.")}</small>
            <small>${t("Klik voor woningtypes, buurtklasse, boodschap en landingspagina.", "Click for property types, area class, message and landing page.")}</small>
          </button>
        `).join("")}
      </div>
      ${renderPartnerDeepDive(selectedPartner)}
    `;
  }

  function renderPartnerDeepDive(partner) {
    if (!partner) return "";
    const rows = properties().filter((property) => String(property.partner?.id || "") === String(partner.id || ""));
    const topRows = rows.filter(isTop);
    const house = groupRows(rows, (property) => property.houseType, houseLabel)[0] || {};
    const facade = groupRows(rows, (property) => property.facadeStyle, facadeLabel)[0] || {};
    const income = groupRows(rows, incomeClass, incomeLabel)[0] || {};
    const message = groupRows(rows, suggestedMessageAngle, messageLabel)[0] || {};
    const noResponse = rows.filter((property) => property.status === "no_response").length;
    return `
      <div class="strategy-deep-dive" id="partnerDeepDiveStrategy">
        <h3>${t("Waarom deze partner anders sturen?", "Why steer this partner differently?")} ${esc(partner.name)}</h3>
        <div class="strategy-deep-grid">
          <div class="strategy-deep-card">
            <span>${t("Sterkste woningtype", "Strongest property type")}</span>
            <strong>${esc(house.label || t("Nog te meten", "To be measured"))}</strong>
            <small>${formatInt(house.count || 0)} ${t("records", "records")} - ${formatPct(house.responseRate || 0)} ${t("respons", "response")} - ${formatPct(house.appointmentRate || 0)} ${t("afspraken", "appointments")}</small>
          </div>
          <div class="strategy-deep-card">
            <span>${t("Gevelsignaal", "Facade signal")}</span>
            <strong>${esc(facade.label || t("Nog te meten", "To be measured"))}</strong>
            <small>${formatInt(facade.top || 0)} A/A+ - ${formatArea(facade.facadeM2 || 0)} ${t("gevelpotentieel", "facade potential")}</small>
          </div>
          <div class="strategy-deep-card">
            <span>${t("Buurtklasse", "Area class")}</span>
            <strong>${esc(income.label || t("Middenklasse buurt", "Middle-income area"))}</strong>
            <small>${t("Gebruik dit voor prijsanker, toon en landingspagina-inhoud.", "Use this for price framing, tone and landing-page content.")}</small>
          </div>
          <div class="strategy-deep-card">
            <span>${t("Beste boodschap om te testen", "Best message to test")}</span>
            <strong>${esc(message.label || t("Lokale partnercheck", "Local partner review"))}</strong>
            <small>${t("Postkaart:", "Postcard:")} ${esc(postcardPromise(message.key || "local_partner_review"))}</small>
          </div>
        </div>
        <div class="strategy-deep-grid" style="margin-top:12px">
          <div class="strategy-deep-card">
            <span>${t("Landingspagina", "Landing page")}</span>
            <strong>${t("Niet dezelfde tekst als de kaart", "Not the same copy as the postcard")}</strong>
            <small>${esc(landingPromise(message.key || "local_partner_review"))}</small>
          </div>
          <div class="strategy-deep-card">
            <span>${t("Opvolgvraag", "Follow-up question")}</span>
            <strong>${formatInt(noResponse)} ${t("zonder respons", "without response")}</strong>
            <small>${t("Test of dit boodschap, timing of partneropvolging is voordat DAW meer adressen geeft.", "Test whether this is message, timing or partner follow-up before DAW gives more addresses.")}</small>
          </div>
          <div class="strategy-deep-card">
            <span>${t("Capaciteitsvraag", "Capacity question")}</span>
            <strong>${formatInt(topRows.length)} A/A+ ${t("kansen", "opportunities")}</strong>
            <small>${t("Kan deze partner binnen 48 uur reageren op scans en afspraken?", "Can this partner respond to scans and appointments within 48 hours?")}</small>
          </div>
          <div class="strategy-deep-card">
            <span>${t("DAW-beslissing", "DAW decision")}</span>
            <strong>${partner.classKey === "volume_ready" ? t("Opschalen", "Scale") : partner.classKey === "coach_first" ? t("Eerst coachen", "Coach first") : t("Kleine testbatch", "Small test batch")}</strong>
            <small>${t("Beslis niet op volume alleen, maar op respons, afspraakratio, woningmix en partnerfeedback.", "Decide not on volume alone, but on response, appointment rate, property mix and partner feedback.")}</small>
          </div>
        </div>
      </div>
    `;
  }

  function renderCampaignLearning() {
    const campaign = document.getElementById("campaign");
    if (!campaign) return;
    let panel = document.getElementById("qrLearningStrategy");
    if (!panel) {
      panel = document.createElement("section");
      panel.id = "qrLearningStrategy";
      panel.className = "panel strategy-section";
      campaign.prepend(panel);
    }
    const messageRows = groupRows(properties().filter(isTop), suggestedMessageAngle, messageLabel).slice(0, 4);
    const bestHouseByMessage = (group) => groupRows(group.rows || [], (property) => property.houseType, houseLabel)[0];
    const bestIncomeByMessage = (group) => groupRows(group.rows || [], incomeClass, incomeLabel)[0];
    const steps = [
      [t("QR-scan", "QR scan"), t("Welke regio, partner en boodschap wekt eerste aandacht?", "Which region, partner and message creates first attention?")],
      [t("Formulierstart", "Form start"), t("Welke belofte is sterk genoeg om gegevens achter te laten?", "Which promise is strong enough to leave details?")],
      [t("Interesse", "Interest"), t("Energie, esthetiek, onderhoud, subsidiecheck of comfort.", "Energy, aesthetics, maintenance, subsidy check or comfort.")],
      [t("Renderkeuze", "Render choice"), t("Welke afwerking, kleur en productlijn trekt door naar sales?", "Which finish, color and product line moves to sales?")],
      [t("Partneruitkomst", "Partner outcome"), t("Opvolgtijd, afspraak, offerte, gewonnen/verloren en bezwaar.", "Follow-up time, appointment, quote, won/lost and objection.")]
    ];
    panel.innerHTML = `
      <div class="panel-head">
        <div><p class="eyebrow">${t("Campagnelearnings", "Campaign learnings")}</p><h2>${t("Welke boodschap werkt voor welk woning- en buurtsegment?", "Which message works for which property and area segment?")}</h2></div>
        <div class="scope-chip">${t("postkaart + landingpagina", "postcard + landing page")}</div>
      </div>
      <div class="strategy-message-lab">
        <h3>${t("Boodschaptests voor golf 1", "Message tests for wave 1")}</h3>
        <div class="strategy-message-grid">
          ${messageRows.map((group) => {
            const house = bestHouseByMessage(group) || {};
            const income = bestIncomeByMessage(group) || {};
            return `
              <div class="strategy-message-card">
                <span>${t("Testcel", "Test cell")}</span>
                <strong>${esc(group.label)}</strong>
                <small>${formatInt(group.count)} A/A+ - ${formatPct(group.responseRate)} ${t("demo-respons", "demo response")} - ${esc(house.label || t("gemengde woningtypes", "mixed property types"))} - ${esc(income.label || t("middenklasse buurt", "middle-income area"))}</small>
                <div class="promise"><b>${t("Op de postkaart:", "On the postcard:")}</b><br><small>${esc(postcardPromise(group.key))}</small></div>
                <div class="promise"><b>${t("Op de landingspagina:", "On the landing page:")}</b><br><small>${esc(landingPromise(group.key))}</small></div>
                <div class="promise"><b>${t("Meet:", "Measure:")}</b><br><small>${t("scanrate, formulierstart, gekozen afwerking, afspraakvraag en bezwaar.", "scan rate, form start, chosen finish, appointment request and objection.")}</small></div>
              </div>
            `;
          }).join("")}
        </div>
      </div>
      <div class="strategy-qr-flow">
        ${steps.map(([title, detail], index) => `
          <div class="strategy-qr-step">
            <span>${t("Stap", "Step")} ${index + 1}</span>
            <strong>${esc(title)}</strong>
            <small>${esc(detail)}</small>
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderProductStrategy() {
    const intelligence = document.getElementById("intelligence");
    if (!intelligence) return;
    setText("#intelligenceModelName", t("Product- en afwerkingsintelligentie", "Product and finish intelligence"));
    setText("#intelligenceModelMeta", t("Welke DAW-productlijnen, kleuren en claims krijgen tractie per segment.", "Which DAW product lines, colors and claims gain traction per segment."));
    let panel = document.getElementById("productFinishStrategy");
    if (!panel) {
      panel = document.createElement("section");
      panel.id = "productFinishStrategy";
      panel.className = "panel strategy-section";
      const hero = intelligence.querySelector(".intelligence-hero");
      hero?.after(panel);
    }
    const products = computeStrategy().products.slice(0, 6);
    const topRows = properties().filter(isTop);
    const houseSegments = groupRows(topRows, (property) => property.houseType, houseLabel).slice(0, 4);
    const incomeSegments = groupRows(topRows, incomeClass, incomeLabel).slice(0, 4);
    panel.innerHTML = `
      <div class="panel-head">
        <div><p class="eyebrow">${t("Product & afwerking", "Product & finish")}</p><h2>${t("Wat DAW uit render- en QR-keuzes kan leren", "What DAW can learn from render and QR choices")}</h2></div>
        <div class="scope-chip">${t("hypotheses voor golf 1", "wave 1 hypotheses")}</div>
      </div>
      <div class="strategy-product-list">
        ${products.map((item) => `
          <div class="strategy-product-row">
            <div>
              <strong>${esc(item.label)}</strong>
              <span>${formatInt(item.count)} ${t("A/A+ records in demoqueue", "A/A+ records in demo queue")} - ${formatPct(item.share)}</span>
            </div>
            <div class="strategy-product-bar" aria-hidden="true"><i style="width:${Math.max(5, Math.min(100, item.share))}%"></i></div>
          </div>
        `).join("")}
      </div>
      <div class="strategy-segment-lab">
        <h3>${t("Segmentvragen die DAW hiermee kan beantwoorden", "Segment questions DAW can answer with this")}</h3>
        <div class="strategy-segment-grid">
          ${houseSegments.map((item) => `
            <div class="strategy-segment-card">
              <span>${t("Woningtype", "Property type")}</span>
              <strong>${esc(item.label)}</strong>
              <small>${formatInt(item.top)} A/A+ - ${formatPct(item.responseRate)} ${t("respons", "response")} - ${t("test afwerking en prijsanker apart.", "test finish and price framing separately.")}</small>
            </div>
          `).join("")}
          ${incomeSegments.map((item) => `
            <div class="strategy-segment-card">
              <span>${t("Buurtklasse", "Area class")}</span>
              <strong>${esc(item.label)}</strong>
              <small>${formatInt(item.count)} ${t("records", "records")} - ${formatEuro(item.value)} - ${t("stem toon en bewijsvoering af op koopkrachtcontext.", "tune tone and proof to purchasing-power context.")}</small>
            </div>
          `).join("")}
        </div>
      </div>
    `;
  }

  function renderMapStrategy() {
    const map = document.getElementById("map");
    if (!map) return;
    let panel = document.getElementById("marketMapStrategy");
    if (!panel) {
      panel = document.createElement("section");
      panel.id = "marketMapStrategy";
      panel.className = "panel strategy-section";
      map.prepend(panel);
    }
    const s = computeStrategy();
    const topRegions = s.partnerData.slice(0, 4);
    panel.innerHTML = `
      <div class="panel-head">
        <div><p class="eyebrow">${t("Marktkaart", "Market map")}</p><h2>${t("Niet alleen punten: partnerdekking, witte vlekken en volgende golf", "Not just dots: partner coverage, white spots and next wave")}</h2></div>
        <div class="scope-chip">${t("kaart = beslislaag", "map = decision layer")}</div>
      </div>
      <div class="strategy-strip">
        ${topRegions.map((partner) => `
          <div class="strategy-mini">
            <span>${esc(partner.region)}</span>
            <strong>${formatInt(partner.top)} A/A+</strong>
            <small>${esc(partner.name)} - ${formatPct(partner.capacityLoad)} ${t("van demo-capaciteit", "of demo capacity")}</small>
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderBrainStrategy() {
    const brain = document.getElementById("brain");
    if (!brain) return;
    const head = brain.querySelector(".panel-head h2");
    const eyebrow = brain.querySelector(".panel-head .eyebrow");
    if (eyebrow) eyebrow.textContent = t("Second Brain leerkaart", "Second Brain learning map");
    if (head) head.textContent = t("Partners, regio's, segmenten, bezwaren en beslissingen", "Partners, regions, segments, objections and decisions");
    const inspector = document.getElementById("brainInspector");
    if (inspector && /Click a node|Klik/.test(inspector.textContent)) {
      inspector.textContent = t("Klik op een node om te zien welke beslissing, hypothese of learning erachter zit.", "Click a node to see which decision, hypothesis or learning sits behind it.");
    }
  }

  function renderTrustStrategy() {
    const activeTrust = document.querySelector('.nav-tab.active[data-view="trust"], #trust.active');
    if (activeTrust) {
      document.querySelector('.nav-tab[data-view="executive"]')?.click();
    }
  }

  function renderAll() {
    injectStyles();
    labelNavigation();
    renderExecutiveStrategy();
    renderStrategicBrief();
    renderPartnerPerformance();
    renderCampaignLearning();
    renderProductStrategy();
    renderMapStrategy();
    renderBrainStrategy();
    renderTrustStrategy();
  }

  let scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(() => {
      scheduled = false;
      renderAll();
    });
  }

  function boot() {
    renderAll();
    document.addEventListener("click", (event) => {
      const strategyPartner = event.target.closest("[data-strategy-partner]");
      if (strategyPartner) {
        selectedStrategyPartnerId = strategyPartner.dataset.strategyPartner || "";
        renderPartnerPerformance();
        return;
      }
      if (event.target.closest(".nav-tab, .partner-card, .shortlist-row, #exportBtn")) {
        window.setTimeout(schedule, 0);
      }
    });
    document.addEventListener("change", schedule);
    document.addEventListener("input", (event) => {
      if (event.target.matches("input, select")) window.setTimeout(schedule, 30);
    });
    const observer = new MutationObserver((mutations) => {
      const externalChange = mutations.some((mutation) => Array.from(mutation.addedNodes).some((node) => {
        if (node.nodeType !== 1) return false;
        return !node.closest?.(".strategy-section, .strategy-shell, .strategy-owned, #languageToggle");
      }));
      if (externalChange) {
        schedule();
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
