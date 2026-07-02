/* ============================================================
   THE BAIR CO. — shared engine
   header/footer injection · i18n (EN/NL/FR) · consent · motion
   ============================================================ */
(function () {
  'use strict';

  /* ---------- shared translations ---------- */
  var COMMON = {
    en: {
      'nav.solutions': 'Solutions',
      'nav.work': 'Work',
      'nav.company': 'Company',
      'nav.contact': 'Contact',
      'nav.cta': 'Start a project',
      'foot.desc': 'AI solutions partner. We design, build and deploy AI products, intelligent automation and AI-ready platforms — for enterprises, mid-market companies and SMEs.',
      'foot.solutions': 'Solutions',
      'foot.s1': 'AI Products',
      'foot.s2': 'Intelligent Automation',
      'foot.s3': 'Enterprise AI',
      'foot.s4': 'AI-ready Platforms',
      'foot.company': 'Company',
      'foot.work': 'Work',
      'foot.about': 'About',
      'foot.contact': 'Contact',
      'foot.get': 'Get in touch',
      'foot.loc': 'Belgium — working across Europe',
      'foot.rights': 'All rights reserved.',
      'foot.privacy': 'Privacy',
      'foot.terms': 'Terms',
      'foot.cookies': 'Cookies',
      'ck.title': 'Cookie preferences',
      'ck.desc': 'We use cookies to improve your experience. Choose which categories you allow.',
      'ck.nec': 'Necessary — required for the site to function',
      'ck.ana': 'Analytics — helps us understand how visitors use the site',
      'ck.mkt': 'Marketing — used for personalised advertising',
      'ck.save': 'Save choices',
      'ck.all': 'Accept all',
      'ck.reopen': 'Cookies'
    },
    nl: {
      'nav.solutions': 'Oplossingen',
      'nav.work': 'Werk',
      'nav.company': 'Bedrijf',
      'nav.contact': 'Contact',
      'nav.cta': 'Start een project',
      'foot.desc': 'AI solutions partner. We ontwerpen, bouwen en implementeren AI-producten, intelligente automatisering en AI-ready platformen — voor enterprises, mid-market en kmo’s.',
      'foot.solutions': 'Oplossingen',
      'foot.s1': 'AI-producten',
      'foot.s2': 'Intelligente automatisering',
      'foot.s3': 'Enterprise AI',
      'foot.s4': 'AI-ready platformen',
      'foot.company': 'Bedrijf',
      'foot.work': 'Werk',
      'foot.about': 'Over ons',
      'foot.contact': 'Contact',
      'foot.get': 'Contacteer ons',
      'foot.loc': 'België — actief in heel Europa',
      'foot.rights': 'Alle rechten voorbehouden.',
      'foot.privacy': 'Privacy',
      'foot.terms': 'Voorwaarden',
      'foot.cookies': 'Cookies',
      'ck.title': 'Cookie-instellingen',
      'ck.desc': 'Wij gebruiken cookies om je ervaring te verbeteren. Kies welke categorieën je toestaat.',
      'ck.nec': 'Noodzakelijk — vereist voor de werking van de site',
      'ck.ana': 'Analytisch — helpt ons begrijpen hoe bezoekers de site gebruiken',
      'ck.mkt': 'Marketing — gebruikt voor gepersonaliseerde advertenties',
      'ck.save': 'Keuzes opslaan',
      'ck.all': 'Alles accepteren',
      'ck.reopen': 'Cookies'
    },
    fr: {
      'nav.solutions': 'Solutions',
      'nav.work': 'Réalisations',
      'nav.company': 'Entreprise',
      'nav.contact': 'Contact',
      'nav.cta': 'Démarrer un projet',
      'foot.desc': 'Partenaire en solutions IA. Nous concevons, développons et déployons des produits IA, de l’automatisation intelligente et des plateformes AI-ready — pour les grandes entreprises, le mid-market et les PME.',
      'foot.solutions': 'Solutions',
      'foot.s1': 'Produits IA',
      'foot.s2': 'Automatisation intelligente',
      'foot.s3': 'IA d’entreprise',
      'foot.s4': 'Plateformes AI-ready',
      'foot.company': 'Entreprise',
      'foot.work': 'Réalisations',
      'foot.about': 'À propos',
      'foot.contact': 'Contact',
      'foot.get': 'Contactez-nous',
      'foot.loc': 'Belgique — actifs dans toute l’Europe',
      'foot.rights': 'Tous droits réservés.',
      'foot.privacy': 'Confidentialité',
      'foot.terms': 'Conditions',
      'foot.cookies': 'Cookies',
      'ck.title': 'Préférences de cookies',
      'ck.desc': 'Nous utilisons des cookies pour améliorer votre expérience. Choisissez les catégories que vous autorisez.',
      'ck.nec': 'Nécessaires — indispensables au fonctionnement du site',
      'ck.ana': 'Analytiques — nous aident à comprendre l’utilisation du site',
      'ck.mkt': 'Marketing — utilisés pour la publicité personnalisée',
      'ck.save': 'Enregistrer',
      'ck.all': 'Tout accepter',
      'ck.reopen': 'Cookies'
    }
  };

  var LANGS = ['en', 'nl', 'fr'];
  var PAGE = window.BAIR_PAGE_I18N || { en: {}, nl: {}, fr: {} };

  function dict(lang) {
    var out = {};
    var c = COMMON[lang] || COMMON.en;
    var p = PAGE[lang] || {};
    var k;
    for (k in c) out[k] = c[k];
    for (k in p) out[k] = p[k];
    return out;
  }

  function getLang() {
    try {
      var s = localStorage.getItem('bair-lang');
      if (s && LANGS.indexOf(s) > -1) return s;
    } catch (e) {}
    var nav = (navigator.language || 'en').slice(0, 2).toLowerCase();
    return LANGS.indexOf(nav) > -1 ? nav : 'en';
  }

  var current = getLang();

  function applyLang(lang) {
    current = lang;
    try { localStorage.setItem('bair-lang', lang); } catch (e) {}
    document.documentElement.setAttribute('lang', lang);
    var d = dict(lang);
    var nodes = document.querySelectorAll('[data-i18n]');
    for (var i = 0; i < nodes.length; i++) {
      var key = nodes[i].getAttribute('data-i18n');
      if (d[key] !== undefined) nodes[i].innerHTML = d[key];
    }
    var phs = document.querySelectorAll('[data-i18n-ph]');
    for (var j = 0; j < phs.length; j++) {
      var k2 = phs[j].getAttribute('data-i18n-ph');
      if (d[k2] !== undefined) phs[j].setAttribute('placeholder', d[k2]);
    }
    if (d['meta.title']) document.title = d['meta.title'];
    if (d['meta.desc']) {
      var md = document.querySelector('meta[name="description"]');
      if (md) md.setAttribute('content', d['meta.desc']);
    }
    var btns = document.querySelectorAll('.lang-switch button');
    for (var b = 0; b < btns.length; b++) {
      btns[b].classList.toggle('active', btns[b].getAttribute('data-lang') === lang);
    }
  }

  /* ---------- header / footer ---------- */
  function langButtons() {
    return '<div class="lang-switch" role="group" aria-label="Language">' +
      LANGS.map(function (l) {
        return '<button type="button" data-lang="' + l + '">' + l + '</button>';
      }).join('') + '</div>';
  }

  var LINKEDIN_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>';

  function buildHeader() {
    var h = document.createElement('header');
    h.className = 'site';
    h.innerHTML =
      '<div class="nav-inner">' +
        '<a href="/" class="brand"><img src="/logo-white.png" alt="The Bair Co. logo" width="26" height="26">The Bair Co.</a>' +
        '<button class="menu-toggle" aria-label="Menu" aria-expanded="false"><span></span><span></span><span></span></button>' +
        '<nav class="nav-links" aria-label="Main">' +
          '<a href="/#solutions" data-i18n="nav.solutions" data-nav="solutions">Solutions</a>' +
          '<a href="/cases" data-i18n="nav.work" data-nav="work">Work</a>' +
          '<a href="/over" data-i18n="nav.company" data-nav="company">Company</a>' +
          '<a href="/contact" data-i18n="nav.contact" data-nav="contact">Contact</a>' +
          langButtons() +
          '<a href="/contact" class="nav-cta" data-i18n="nav.cta">Start a project</a>' +
        '</nav>' +
      '</div>';
    document.body.insertBefore(h, document.body.firstChild);

    var toggle = h.querySelector('.menu-toggle');
    var links = h.querySelector('.nav-links');
    toggle.addEventListener('click', function () {
      var open = links.classList.toggle('open');
      toggle.classList.toggle('open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    links.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') { links.classList.remove('open'); toggle.classList.remove('open'); }
    });

    var onScroll = function () { h.classList.toggle('scrolled', window.scrollY > 24); };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    // active nav
    var active = document.body.getAttribute('data-nav');
    if (active) {
      var a = h.querySelector('[data-nav="' + active + '"]');
      if (a) a.classList.add('active');
    }
  }

  function buildFooter() {
    var f = document.createElement('footer');
    f.className = 'site';
    f.innerHTML =
      '<div class="container">' +
        '<div class="foot-grid">' +
          '<div>' +
            '<div class="foot-brand"><img src="/logo-white.png" alt="" width="24" height="24">The Bair Co.</div>' +
            '<p class="foot-desc" data-i18n="foot.desc"></p>' +
            '<div style="margin-top:1.2rem"><a class="social-icon" href="https://www.linkedin.com/company/the-bair-company" target="_blank" rel="noopener" aria-label="LinkedIn">' + LINKEDIN_SVG + '</a></div>' +
          '</div>' +
          '<div class="foot-col">' +
            '<h4 data-i18n="foot.solutions">Solutions</h4>' +
            '<a href="/solutions/ai-products" data-i18n="foot.s1">AI Products</a>' +
            '<a href="/solutions/intelligent-automation" data-i18n="foot.s2">Intelligent Automation</a>' +
            '<a href="/solutions/enterprise-ai" data-i18n="foot.s3">Enterprise AI</a>' +
            '<a href="/solutions/ai-platforms" data-i18n="foot.s4">AI-ready Platforms</a>' +
          '</div>' +
          '<div class="foot-col">' +
            '<h4 data-i18n="foot.company">Company</h4>' +
            '<a href="/cases" data-i18n="foot.work">Work</a>' +
            '<a href="/over" data-i18n="foot.about">About</a>' +
            '<a href="/contact" data-i18n="foot.contact">Contact</a>' +
          '</div>' +
          '<div class="foot-col">' +
            '<h4 data-i18n="foot.get">Get in touch</h4>' +
            '<a href="mailto:kristof@baircompany.be">kristof@baircompany.be</a>' +
            '<a href="/contact" data-i18n="foot.loc">Belgium — working across Europe</a>' +
          '</div>' +
        '</div>' +
        '<div class="foot-bottom">' +
          '<div>&copy; <span id="bair-year"></span> The Bair Co. <span data-i18n="foot.rights">All rights reserved.</span></div>' +
          '<div class="foot-legal">' +
            '<a href="/privacy" data-i18n="foot.privacy">Privacy</a>' +
            '<a href="/voorwaarden" data-i18n="foot.terms">Terms</a>' +
            '<a href="/cookies" data-i18n="foot.cookies">Cookies</a>' +
            '<span>VAT BE 1034.232.509</span>' +
          '</div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(f);
    var y = document.getElementById('bair-year');
    if (y) y.textContent = String(new Date().getFullYear());
  }

  /* ---------- consent + analytics ---------- */
  var GA_ID = 'G-TEPNG02Z0J';
  window.dataLayer = window.dataLayer || [];
  function gtag() { window.dataLayer.push(arguments); }
  window.gtag = window.gtag || gtag;
  gtag('consent', 'default', {
    analytics_storage: 'denied',
    ad_storage: 'denied',
    ad_user_data: 'denied',
    ad_personalization: 'denied'
  });

  var gaLoaded = false;
  function loadGA() {
    if (gaLoaded) return;
    gaLoaded = true;
    var s = document.createElement('script');
    s.async = true;
    s.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
    document.head.appendChild(s);
    gtag('js', new Date());
    gtag('config', GA_ID, { anonymize_ip: true });
  }

  function getConsent() {
    try { return JSON.parse(localStorage.getItem('bair-consent-v2') || 'null'); } catch (e) { return null; }
  }
  function setConsent(c) {
    try { localStorage.setItem('bair-consent-v2', JSON.stringify(c)); } catch (e) {}
    gtag('consent', 'update', {
      analytics_storage: c.analytics ? 'granted' : 'denied',
      ad_storage: c.marketing ? 'granted' : 'denied',
      ad_user_data: c.marketing ? 'granted' : 'denied',
      ad_personalization: c.marketing ? 'granted' : 'denied'
    });
    if (c.analytics) loadGA();
    window.dispatchEvent(new CustomEvent('cookieConsentUpdated', { detail: c }));
  }

  var banner, reopenBtn;
  function buildConsent() {
    banner = document.createElement('div');
    banner.className = 'cookie-banner';
    banner.setAttribute('role', 'dialog');
    banner.setAttribute('aria-label', 'Cookies');
    banner.innerHTML =
      '<h4 data-i18n="ck.title"></h4>' +
      '<p data-i18n="ck.desc"></p>' +
      '<div class="cookie-opts">' +
        '<label><input type="checkbox" checked disabled><span data-i18n="ck.nec"></span></label>' +
        '<label><input type="checkbox" id="ck-ana"><span data-i18n="ck.ana"></span></label>' +
        '<label><input type="checkbox" id="ck-mkt"><span data-i18n="ck.mkt"></span></label>' +
      '</div>' +
      '<div class="cookie-actions">' +
        '<button type="button" class="btn btn-primary" id="ck-all" data-i18n="ck.all"></button>' +
        '<button type="button" class="btn btn-ghost" id="ck-save" data-i18n="ck.save"></button>' +
      '</div>';
    document.body.appendChild(banner);

    reopenBtn = document.createElement('button');
    reopenBtn.type = 'button';
    reopenBtn.className = 'cookie-reopen';
    reopenBtn.setAttribute('data-i18n', 'ck.reopen');
    reopenBtn.style.display = 'none';
    reopenBtn.addEventListener('click', function () { showBanner(); });
    document.body.appendChild(reopenBtn);

    banner.querySelector('#ck-all').addEventListener('click', function () {
      setConsent({ analytics: true, marketing: true, ts: Date.now() });
      hideBanner();
    });
    banner.querySelector('#ck-save').addEventListener('click', function () {
      setConsent({
        analytics: banner.querySelector('#ck-ana').checked,
        marketing: banner.querySelector('#ck-mkt').checked,
        ts: Date.now()
      });
      hideBanner();
    });

    var c = getConsent();
    if (c) {
      if (c.analytics) setConsent(c); // re-apply + load GA
      reopenBtn.style.display = '';
    } else {
      setTimeout(showBanner, 900);
    }
  }
  function showBanner() {
    var c = getConsent();
    if (c) {
      banner.querySelector('#ck-ana').checked = !!c.analytics;
      banner.querySelector('#ck-mkt').checked = !!c.marketing;
    }
    banner.classList.add('show');
    reopenBtn.style.display = 'none';
  }
  function hideBanner() {
    banner.classList.remove('show');
    reopenBtn.style.display = '';
  }

  /* ---------- reveal on scroll ---------- */
  function initReveal() {
    var els = document.querySelectorAll('.reveal');
    if (!('IntersectionObserver' in window)) {
      for (var i = 0; i < els.length; i++) els[i].classList.add('in');
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
    for (var j = 0; j < els.length; j++) io.observe(els[j]);
  }

  /* ---------- boot ---------- */
  function boot() {
    buildHeader();
    buildFooter();
    buildConsent();
    applyLang(current);
    initReveal();
    document.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('.lang-switch button') : null;
      if (b) applyLang(b.getAttribute('data-lang'));
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
