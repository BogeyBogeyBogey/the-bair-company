(function () {
  const STORAGE_KEY = "facadepilot.internalDemodashboard.language";
  const SUPPORTED = new Set(["nl", "en"]);
  const params = new URLSearchParams(window.location.search);
  let language = params.get("lang") || localStorage.getItem(STORAGE_KEY) || "nl";
  if (!SUPPORTED.has(language)) language = "nl";

  document.documentElement.lang = language;
  document.documentElement.classList.add(`language-${language}`);
  document.title = language === "nl" ? "FacadePilot Intern Demo Dashboard" : "FacadePilot Internal Demo Dashboard";

  const exactText = new Map(Object.entries({
    "Property Intelligence": "Vastgoedintelligentie",
    "Tenant": "Klant",
    "Scope": "Bereik",
    "All partners": "Alle partners",
    "Network view": "Netwerkweergave",
    "Access lens": "Toegangsvenster",
    "Producer network": "Producentennetwerk",
    "Buyer-review lens": "Klantreview",
    "Executive": "Directie",
    "Trust": "Vertrouwen",
    "Intelligence": "Inzichten",
    "Overview": "Overzicht",
    "Database": "Database",
    "Property": "Woning",
    "Map": "Kaart",
    "Campaign": "Campagne",
    "Second brain": "Second brain",
    "Modules": "Modules",
    "DAW Belgium demo · synthetic buyer review": "DAW Belgium demo · synthetische marktintelligentie",
    "Facade opportunity command center": "Gevelkansen intelligence platform",
    "Demo · synthetic data": "Demo · synthetische data",
    "Boardroom report": "Boardroomrapport",
    "Export CSV": "Exporteer CSV",
    "Customer visibility": "Klantweergave",
    "Access lens cockpit": "Toegangsvenster",
    "Buyer review": "Klantreview",
    "Partner cockpit": "Partnerintelligentie",
    "Boardroom view": "Beslissingen",
    "Decision ledger": "Beslissingenlogboek",
    "Filtered workspace": "Gefilterde werkruimte",
    "Data trust": "Datacheck",
    "Ready for review": "Klaar voor review",
    "Best defended opportunities": "Eerste postkaartgolf",
    "Shortlist for sales": "Adressen om eerst te testen",
    "Risk and readiness": "Verzendcheck",
    "Handoff checks": "Klaar om te versturen?",
    "Campaign memory": "Campagnelearnings",
    "What the system learned": "Wat DAW na verzending leert",
    "Source ledger": "Bronnenregister",
    "Evidence and provenance": "Bewijs en herkomst",
    "Tenant scoped": "Klantgebonden",
    "Handoff confidence": "Datacheck",
    "Reviewing": "In review",
    "Module coverage": "Moduledekking",
    "What is defensible per pilot": "Wat verdedigbaar is per pilot",
    "Source runs": "Bronruns",
    "Lineage": "Herkomst",
    "Evidence types": "Bewijstypes",
    "Receipts behind the scores": "Bewijs achter de scores",
    "Review gaps": "Reviewgaten",
    "Before enterprise handoff": "Voor enterprise-overdracht",
    "Response funnel": "Responsfunnel",
    "Objections": "Bezwaren",
    "Learning signals": "Leersignalen",
    "Recommendations": "Aanbevelingen",
    "What the campaign learned": "Wat de campagne leerde",
    "Signals, properties, reactions, actions": "Signalen, woningen, reacties, acties",
    "Search graph": "Zoek in graaf",
    "Click a node to inspect its context.": "Klik op een knooppunt voor context.",
    "Focus best cluster": "Focus beste cluster",
    "Fit": "Passend",
    "Reset": "Reset",
    "Move": "Verplaatsen",
    "Zoom in/out": "Zoom in/uit",
    "Street View quick check": "Street View snelle controle",
    "Select a property on the map": "Selecteer een woning op de kaart",
    "not stored": "niet opgeslagen",
    "Street View opens in Google": "Street View opent in Google",
    "Use the button below if the embedded panorama is unavailable for this coordinate.": "Gebruik de knop hieronder als de ingesloten panorama niet beschikbaar is voor deze coordinaten.",
    "Workflow": "Workflow",
    "Quick visual triage only. Production visuals require own capture, partner upload, licensed provider or an official embed.": "Alleen snelle visuele triage. Productiebeelden vereisen eigen opname, partnerupload, vergunde provider of officiële embed.",
    "Open in Google Street View": "Open in Google Street View",
    "Open property dossier": "Open woningdossier",
    "Open fullscreen": "Open schermvullend",
    "Properties": "Woningen",
    "Responses": "Reacties",
    "Appointments": "Afspraken",
    "No response": "Geen respons",
    "Pipeline": "Pipeline",
    "Pipeline Value": "Geschatte projectwaarde",
    "Priority": "Prioriteit",
    "Score": "Score",
    "Status": "Status",
    "Partner": "Partner",
    "City": "Stad",
    "Address": "Adres",
    "Action": "Actie",
    "Source": "Bron",
    "Source-backed signals": "Brononderbouwde signalen",
    "Public context": "Publieke context",
    "Module scores": "Modulescores",
    "Contact history": "Contacthistoriek",
    "Next action": "Volgende actie",
    "Image policy": "Beeldbeleid",
    "Selected": "Geselecteerd",
    "Opportunity": "Kans",
    "Official embed": "Officiele embed",
    "No screenshots, no cached Street View, no Google-derived campaign asset.": "Geen screenshots, geen opgeslagen Street View en geen Google-afgeleid campagnebeeld.",
    "Select a geocoded property": "Selecteer een geocodeerde woning",
    "No coordinates": "Geen coordinaten",
    "Select a mapped property to start the quick check.": "Selecteer een woning op de kaart om de snelle controle te starten.",
    "Why this score": "Waarom deze score",
    "Confidence": "Vertrouwen",
    "Evidence trail": "Bewijsspoor",
    "references": "referenties",
    "No references yet": "Nog geen referenties",
    "Property fit": "Woningfit",
    "Photo verification": "Fotoverificatie",
    "Partner territory fit": "Partnergebied-fit",
    "Renovation context": "Renovatiecontext",
    "Campaign readiness": "Campagneklaarheid",
    "Value fit": "Waardefit",
    "Pending own/partner/licensed photo check": "Eigen, partner- of vergunde fotocheck nog nodig",
    "Source-backed scoring component": "Brononderbouwde scorecomponent",
    "Building type, facade age proxy and renovation suitability": "Woningtype, gevelleeftijdproxy en renovatiegeschiktheid",
    "Fits the assigned renovation partner route": "Past binnen de toegewezen route van de renovatiepartner",
    "Neighbourhood and property-context signals": "Buurt- en woningcontextsignalen",
    "Useful for a concrete direct-mail or sales action": "Bruikbaar voor concrete direct-mail of salesactie",
    "Estimated facade surface and weighted pipeline value": "Geschatte geveloppervlakte en projectwaarde",
    "review": "review",
    "Mapped area": "Gekarteerd gebied",
    "Partner, status, address, signal": "Partner, status, adres, signaal",
    "Tenant data": "Klantdata",
    "Live data": "Live data",
    "Synthetic data": "Synthetische data",
    "synthetic": "synthetisch",
    "queued": "wachtrij",
    "sent": "verzonden",
    "clicked": "geklikt",
    "responded": "gereageerd",
    "appointment": "afspraak",
    "no response": "geen respons",
    "no_response": "geen respons",
    "facadepilot": "facadepilot",
    "windowpilot": "windowpilot",
    "roofpilot": "roofpilot",
    "drivewaypilot": "drivewaypilot"
  }));

  const phraseRules = [
    [/\bFacade opportunity\b/g, "Gevelkans"],
    [/\bfacade opportunity\b/g, "gevelkans"],
    [/\bsynthetic buyer review\b/g, "synthetische marktintelligentie"],
    [/\bsynthetic demo\b/g, "synthetische demo"],
    [/\bPartner-SLA\b/g, "Opvolgafspraak met partner"],
    [/\bSLA\b/g, "opvolgafspraak"],
    [/\bsynthetic address\b/g, "synthetisch adres"],
    [/\blegal-first score\b/g, "legal-first score"],
    [/\bno Google imagery\b/g, "geen Google-beelden"],
    [/\bOpportunity score, not homeowner intent\b/g, "Kansscore voor de woning, geen bewonersintentie"],
    [/\bProperty opportunity score, not homeowner intent\b/g, "Woningkansscore, geen bewonersintentie"],
    [/\bSynthetic address and synthetic visual for demo\b/g, "Synthetisch adres en synthetisch beeld voor demo"],
    [/\bProduction image evidence requires own_capture, partner_upload, licensed_provider, or official_embed\b/g, "Productiebeeldbewijs vereist own_capture, partner_upload, licensed_provider of official_embed"],
    [/\bElectronic outreach still needs GDPR\/ePrivacy review and opt-out handling\b/g, "Elektronische outreach vereist nog GDPR/ePrivacy-review en opt-out-afhandeling"],
    [/\bGenerated demo records; not homeowner intent or real campaign results\b/g, "Gegenereerde demorecords; geen bewonersintentie of echte campagneresultaten"],
    [/\bGenerated demo records\b/g, "Gegenereerde demorecords"],
    [/\bnot homeowner intent\b/g, "geen bewonersintentie"],
    [/\breal campaign results\b/g, "echte campagneresultaten"],
    [/\bTop opportunities\b/g, "Topkansen"],
    [/\bhigh-priority records\b/g, "high-priority records"],
    [/\bVisible records\b/g, "Zichtbare woningen"],
    [/\bvisible records\b/g, "zichtbare woningen"],
    [/\btenant scoped\b/g, "klantgebonden"],
    [/\bnetwork scope\b/g, "volledig partnernetwerk"],
    [/\bpartner cutdown\b/g, "alleen deze partner"],
    [/\bA\/A\+ targets\b/g, "A/A+ kansen"],
    [/\bResponse proof\b/g, "Respons"],
    [/\bresponse proof\b/g, "respons"],
    [/\bWeighted pipeline\b/g, "Geschatte projectwaarde"],
    [/\bweighted pipeline\b/g, "geschatte projectwaarde"],
    [/\bPipeline Value\b/g, "Geschatte projectwaarde"],
    [/\bPipeline value\b/g, "Geschatte projectwaarde"],
    [/\bWeighted estimate\b/g, "Gewogen schatting"],
    [/\bTop share\b/g, "A/A+ aandeel"],
    [/\bFollow-up risk\b/g, "Opvolgdruk"],
    [/\breplies or meetings\b/g, "reacties of afspraken"],
    [/\bappointments\b/g, "afspraken"],
    [/\bopportunities\b/g, "kansen"],
    [/\bNo-response records\b/g, "woningen zonder respons"],
    [/\bA and A\+ in filtered set\b/g, "A en A+ in de selectie"],
    [/\bestimated\b/g, "geschat"],
    [/\bcoverage\b/g, "dekking"],
    [/\bbest module\b/g, "beste module"],
    [/\bresponse rate\b/g, "responsgraad"],
    [/\bresponse\b/g, "respons"],
    [/\bappointment\b/g, "afspraak"],
    [/\bsource-backed\b/g, "brononderbouwd"],
    [/\bsource backed\b/g, "brononderbouwd"],
    [/\bpartner route fit\b/g, "partnerroute-fit"],
    [/\bfield audit\b/g, "veldcontrole"],
    [/\bpending\b/g, "in afwachting"],
    [/\bown capture\b/g, "eigen opname"],
    [/\bpartner upload\b/g, "partnerupload"],
    [/\blicensed provider\b/g, "vergunde provider"],
    [/\bofficial embed\b/g, "officiële embed"],
    [/\bAntwerp\b/g, "Antwerpen"],
    [/\bBrussels\b/g, "Brussel"],
    [/\bHainaut\b/g, "Henegouwen"],
    [/\bproperty\b/g, "woning"],
    [/\bproperties\b/g, "woningen"],
    [/\bProperty\b/g, "Woning"],
    [/\bProperties\b/g, "Woningen"],
    [/\bfacade\b/g, "gevel"],
    [/\bFacade\b/g, "Gevel"],
    [/\bsource\b/g, "bron"],
    [/\bSource\b/g, "Bron"],
    [/\bactions\b/g, "acties"],
    [/\bActions\b/g, "Acties"],
    [/\baction\b/g, "actie"],
    [/\bAction\b/g, "Actie"]
  ];

  const attrTranslations = {
    "Search address, city, signal": "Zoek adres, stad of signaal",
    "Partner, status, address, signal": "Partner, status, adres, signaal",
    "Generated demo records; not homeowner intent or real campaign results.": "Gegenereerde demorecords; geen bewonersintentie of echte campagneresultaten.",
    "Executive decision view": "Directiebeslissingsweergave",
    "Trust and provenance": "Vertrouwen en herkomst",
    "Enabled modules": "Ingeschakelde modules",
    "Views": "Weergaven",
    "Workspace": "Werkruimte",
    "Data trust score": "Datacheckscore",
    "Source ledger trust score": "Bronregister-vertrouwensscore",
    "Decision ledger": "Beslissingenlogboek",
    "Google Street View quick check": "Google Street View snelle controle"
  };

  const skipTags = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEXTAREA"]);
  let observer = null;
  let translating = false;

  function normalize(text) {
    return String(text || "").replace(/\s+/g, " ").trim();
  }

  function applyPhraseRules(text) {
    let translated = text;
    for (const [pattern, replacement] of phraseRules) {
      translated = translated.replace(pattern, replacement);
    }
    return translated;
  }

  function translateString(text) {
    const normalized = normalize(text);
    if (!normalized) return text;
    if (exactText.has(normalized)) {
      const leading = text.match(/^\s*/)?.[0] || "";
      const trailing = text.match(/\s*$/)?.[0] || "";
      return `${leading}${exactText.get(normalized)}${trailing}`;
    }
    const phraseTranslated = applyPhraseRules(text);
    return phraseTranslated;
  }

  function translateTextNode(node) {
    if (!node || !node.nodeValue || !node.parentElement) return;
    if (skipTags.has(node.parentElement.tagName)) return;
    const next = translateString(node.nodeValue);
    if (next !== node.nodeValue) node.nodeValue = next;
  }

  function translateAttributes(element) {
    for (const attr of ["placeholder", "title", "aria-label", "alt"]) {
      const value = element.getAttribute(attr);
      if (!value) continue;
      const translated = attrTranslations[value] || translateString(value);
      if (translated !== value) element.setAttribute(attr, translated);
    }
  }

  function translateDom(root = document.body) {
    if (language !== "nl" || !root || translating) return;
    translating = true;
    if (observer) observer.disconnect();
    try {
      if (root.nodeType === Node.TEXT_NODE) {
        translateTextNode(root);
      } else {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        let node = walker.nextNode();
        while (node) {
          translateTextNode(node);
          node = walker.nextNode();
        }
        const elements = root.nodeType === Node.ELEMENT_NODE
          ? [root, ...root.querySelectorAll("[placeholder],[title],[aria-label],[alt]")]
          : [];
        elements.forEach(translateAttributes);
      }
    } finally {
      translating = false;
      if (observer) observer.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true });
    }
  }

  function injectStyles() {
    if (document.getElementById("internal-dashboard-language-style")) return;
    const style = document.createElement("style");
    style.id = "internal-dashboard-language-style";
    style.textContent = `
      .language-toggle {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 4px;
        border: 1px solid rgba(156, 181, 205, 0.22);
        border-radius: 999px;
        background: rgba(8, 13, 20, 0.72);
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
      }
      .language-toggle button {
        border: 0;
        border-radius: 999px;
        padding: 8px 11px;
        background: transparent;
        color: #a8b5c4;
        font: 800 12px/1 Inter, system-ui, sans-serif;
        letter-spacing: .08em;
        cursor: pointer;
      }
      .language-toggle button.is-active {
        background: #e99b50;
        color: #10141a;
      }
      .language-toggle button:focus-visible {
        outline: 2px solid #7ec3ff;
        outline-offset: 2px;
      }
      @media (max-width: 900px) {
        .language-toggle { order: -1; }
      }
    `;
    document.head.appendChild(style);
  }

  function setLanguage(nextLanguage) {
    if (!SUPPORTED.has(nextLanguage)) return;
    localStorage.setItem(STORAGE_KEY, nextLanguage);
    const url = new URL(window.location.href);
    url.searchParams.set("lang", nextLanguage);
    window.location.href = url.toString();
  }

  function installLanguageToggle() {
    if (document.getElementById("languageToggle")) return;
    const target = document.querySelector(".topbar-actions") || document.querySelector(".topbar") || document.body;
    const wrap = document.createElement("div");
    wrap.id = "languageToggle";
    wrap.className = "language-toggle";
    wrap.setAttribute("role", "group");
    wrap.setAttribute("aria-label", language === "nl" ? "Taalkeuze" : "Language");
    wrap.innerHTML = `
      <button type="button" data-lang="nl" class="${language === "nl" ? "is-active" : ""}" aria-pressed="${language === "nl"}">NL</button>
      <button type="button" data-lang="en" class="${language === "en" ? "is-active" : ""}" aria-pressed="${language === "en"}">EN</button>
    `;
    wrap.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-lang]");
      if (!button) return;
      setLanguage(button.dataset.lang);
    });
    target.prepend(wrap);
  }

  function boot() {
    injectStyles();
    installLanguageToggle();
    translateDom();
    observer = new MutationObserver((mutations) => {
      if (language !== "nl" || translating) return;
      window.requestAnimationFrame(() => {
        for (const mutation of mutations) {
          if (mutation.type === "characterData") {
            translateDom(mutation.target);
            continue;
          }
          if (mutation.type === "attributes") {
            translateAttributes(mutation.target);
            continue;
          }
          mutation.addedNodes.forEach((node) => translateDom(node));
        }
      });
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
