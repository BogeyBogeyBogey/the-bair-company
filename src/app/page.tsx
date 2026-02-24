"use client";

import { useState, useEffect, useRef } from "react";
import Image from "next/image";
import { translations, Lang } from "../lib/translations";

/* ───────────── Intersection Observer Hook ───────────── */
function useInView(threshold = 0.15) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setVisible(true); obs.disconnect(); } },
      { threshold }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);
  return { ref, visible };
}

/* ═══════════════════════════════════════════════════════
   MAIN PAGE
   ═══════════════════════════════════════════════════════ */
export default function Home() {
  const [lang, setLang] = useState<Lang>("nl");
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const t = translations[lang];

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <>
      {/* ── NAV ── */}
      <nav
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
          scrolled
            ? "bg-background/80 backdrop-blur-xl border-b border-border"
            : "bg-transparent"
        }`}
      >
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <a href="#" className="flex items-center gap-3 group">
            <Image
              src="/logo-light.png"
              alt="The Bair Company"
              width={36}
              height={36}
              className="rounded-full transition-transform group-hover:scale-110"
            />
            <span className="font-semibold text-sm tracking-wide hidden sm:inline">
              The Bair Company
            </span>
          </a>

          <div className="hidden md:flex items-center gap-8 text-sm text-muted">
            <a href="#services" className="hover:text-foreground transition-colors">{t.nav.services}</a>
            <a href="#projects" className="hover:text-foreground transition-colors">{t.nav.projects}</a>
            <a href="#about" className="hover:text-foreground transition-colors">{t.nav.about}</a>
            <a href="#contact" className="hover:text-foreground transition-colors">{t.nav.contact}</a>

            <div className="flex items-center gap-1 bg-surface rounded-full p-1">
              <button
                onClick={() => setLang("nl")}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                  lang === "nl" ? "bg-accent text-white" : "text-muted hover:text-foreground"
                }`}
              >
                NL
              </button>
              <button
                onClick={() => setLang("en")}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                  lang === "en" ? "bg-accent text-white" : "text-muted hover:text-foreground"
                }`}
              >
                EN
              </button>
            </div>

            <a
              href="#contact"
              className="bg-accent hover:bg-accent-light text-white px-5 py-2 rounded-full text-sm font-medium transition-all hover:scale-105"
            >
              {t.nav.cta}
            </a>
          </div>

          <button
            className="md:hidden text-foreground"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label="Menu"
          >
            <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2">
              {menuOpen ? (
                <path d="M6 6l12 12M6 18L18 6" />
              ) : (
                <path d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>
        </div>

        {menuOpen && (
          <div className="md:hidden bg-background/95 backdrop-blur-xl border-b border-border px-6 pb-6 animate-fade-in">
            <div className="flex flex-col gap-4 text-lg">
              <a href="#services" onClick={() => setMenuOpen(false)} className="text-muted hover:text-foreground">{t.nav.services}</a>
              <a href="#projects" onClick={() => setMenuOpen(false)} className="text-muted hover:text-foreground">{t.nav.projects}</a>
              <a href="#about" onClick={() => setMenuOpen(false)} className="text-muted hover:text-foreground">{t.nav.about}</a>
              <a href="#contact" onClick={() => setMenuOpen(false)} className="text-muted hover:text-foreground">{t.nav.contact}</a>
              <div className="flex gap-2 pt-2">
                <button onClick={() => setLang("nl")} className={`px-4 py-2 rounded-full text-sm ${lang === "nl" ? "bg-accent text-white" : "bg-surface text-muted"}`}>NL</button>
                <button onClick={() => setLang("en")} className={`px-4 py-2 rounded-full text-sm ${lang === "en" ? "bg-accent text-white" : "bg-surface text-muted"}`}>EN</button>
              </div>
            </div>
          </div>
        )}
      </nav>

      {/* ── HERO ── */}
      <section className="min-h-screen flex items-center justify-center relative overflow-hidden">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-accent/5 rounded-full blur-[120px] pointer-events-none" />
        <div className="absolute bottom-0 right-0 w-[400px] h-[400px] bg-purple-500/5 rounded-full blur-[100px] pointer-events-none" />

        <div className="max-w-5xl mx-auto px-6 text-center relative z-10">
          <div className="inline-flex items-center gap-2 bg-surface border border-border rounded-full px-4 py-2 mb-8 animate-fade-in-up opacity-0">
            <span className="w-2 h-2 bg-accent rounded-full animate-pulse" />
            <span className="text-sm text-muted">{t.hero.badge}</span>
          </div>

          <h1 className="text-5xl sm:text-7xl lg:text-8xl font-bold leading-[0.95] tracking-tight mb-8">
            <span className="block animate-fade-in-up opacity-0">{t.hero.title1}</span>
            <span className="block gradient-text animate-fade-in-up opacity-0 delay-200 italic">
              {t.hero.title2}
            </span>
            <span className="block animate-fade-in-up opacity-0 delay-400">{t.hero.title3}</span>
          </h1>

          <p className="text-lg sm:text-xl text-muted max-w-2xl mx-auto mb-10 animate-fade-in-up opacity-0 delay-500">
            {t.hero.subtitle}
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center animate-fade-in-up opacity-0 delay-600">
            <a
              href="#projects"
              className="bg-accent hover:bg-accent-light text-white px-8 py-3.5 rounded-full font-medium transition-all hover:scale-105 hover:shadow-[0_0_30px_rgba(46,138,255,0.3)]"
            >
              {t.hero.cta1}
            </a>
            <a
              href="#contact"
              className="border border-border hover:border-muted text-foreground px-8 py-3.5 rounded-full font-medium transition-all hover:bg-surface"
            >
              {t.hero.cta2}
            </a>
          </div>
        </div>

        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 animate-float">
          <div className="w-6 h-10 border-2 border-border rounded-full flex justify-center pt-2">
            <div className="w-1 h-2 bg-muted rounded-full animate-pulse" />
          </div>
        </div>
      </section>

      {/* ── SERVICES ── */}
      <ServicesSection t={t} />

      {/* ── PROJECTS ── */}
      <ProjectsSection t={t} />

      {/* ── ABOUT ── */}
      <AboutSection t={t} />

      {/* ── CONTACT ── */}
      <ContactSection t={t} />

      {/* ── FOOTER ── */}
      <footer className="border-t border-border py-10 px-6">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row justify-between items-center gap-4">
          <div className="flex items-center gap-3">
            <Image src="/logo-light.png" alt="B" width={28} height={28} className="rounded-full" />
            <div>
              <span className="font-semibold text-sm">The Bair Company</span>
              <span className="text-muted text-xs block">{t.footer.tagline}</span>
            </div>
          </div>
          <p className="text-muted text-xs">
            &copy; {new Date().getFullYear()} The Bair Company. {t.footer.rights}
          </p>
        </div>
      </footer>
    </>
  );
}

/* ═══════════════════════════════════════════════════════
   SERVICES
   ═══════════════════════════════════════════════════════ */
function ServicesSection({ t }: { t: (typeof translations)["nl"] }) {
  const { ref, visible } = useInView();
  return (
    <section id="services" ref={ref} className="py-28 px-6">
      <div className="max-w-7xl mx-auto">
        <div className={`text-center mb-16 transition-all duration-700 ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
          <span className="inline-block bg-accent/10 text-accent text-xs font-medium px-4 py-1.5 rounded-full mb-4">
            {t.services.badge}
          </span>
          <h2 className="text-4xl sm:text-5xl font-bold mb-4">{t.services.title}</h2>
          <p className="text-muted max-w-xl mx-auto">{t.services.subtitle}</p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {t.services.items.map((item, i) => (
            <div
              key={i}
              className={`group bg-surface border border-border rounded-2xl p-7 transition-all duration-500 hover:border-accent/30 glow-hover ${
                visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
              }`}
              style={{ transitionDelay: visible ? `${i * 100}ms` : "0ms" }}
            >
              <span className="text-3xl block mb-4">{item.icon}</span>
              <h3 className="text-lg font-semibold mb-2 group-hover:text-accent transition-colors">
                {item.title}
              </h3>
              <p className="text-muted text-sm leading-relaxed">{item.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════
   PROJECTS
   ═══════════════════════════════════════════════════════ */
function ProjectsSection({ t }: { t: (typeof translations)["nl"] }) {
  const { ref, visible } = useInView();
  return (
    <section id="projects" ref={ref} className="py-28 px-6 bg-surface/50">
      <div className="max-w-7xl mx-auto">
        <div className={`text-center mb-16 transition-all duration-700 ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
          <span className="inline-block bg-accent/10 text-accent text-xs font-medium px-4 py-1.5 rounded-full mb-4">
            {t.projects.badge}
          </span>
          <h2 className="text-4xl sm:text-5xl font-bold mb-4">{t.projects.title}</h2>
          <p className="text-muted max-w-xl mx-auto">{t.projects.subtitle}</p>
        </div>

        <div className="grid md:grid-cols-2 gap-8">
          {t.projects.items.map((project, i) => (
            <a
              key={i}
              href={project.url}
              target="_blank"
              rel="noopener noreferrer"
              className={`group relative bg-surface border border-border rounded-2xl overflow-hidden transition-all duration-500 hover:border-accent/30 glow-hover ${
                visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
              }`}
              style={{ transitionDelay: visible ? `${i * 150}ms` : "0ms" }}
            >
              <div className={`h-48 bg-gradient-to-br ${project.color} flex items-center justify-center`}>
                <span className="text-5xl font-bold text-foreground/20 group-hover:text-foreground/40 transition-colors">
                  {project.title.charAt(0)}
                </span>
              </div>
              <div className="p-7">
                <div className="flex items-center gap-2 mb-3">
                  <h3 className="text-xl font-bold group-hover:text-accent transition-colors">
                    {project.title}
                  </h3>
                  <svg className="w-4 h-4 text-muted group-hover:text-accent group-hover:translate-x-1 transition-all" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path d="M7 17L17 7M17 7H7M17 7v10" />
                  </svg>
                </div>
                <p className="text-muted text-sm mb-4 leading-relaxed">{project.description}</p>
                <div className="flex flex-wrap gap-2">
                  {project.tags.map((tag) => (
                    <span key={tag} className="bg-background text-xs text-muted px-3 py-1 rounded-full">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════
   ABOUT
   ═══════════════════════════════════════════════════════ */
function AboutSection({ t }: { t: (typeof translations)["nl"] }) {
  const { ref, visible } = useInView();
  return (
    <section id="about" ref={ref} className="py-28 px-6">
      <div className="max-w-5xl mx-auto">
        <div className={`transition-all duration-700 ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
          <span className="inline-block bg-accent/10 text-accent text-xs font-medium px-4 py-1.5 rounded-full mb-4">
            {t.about.badge}
          </span>
          <h2 className="text-4xl sm:text-5xl font-bold mb-8">{t.about.title}</h2>

          <div className="grid md:grid-cols-2 gap-12">
            <div>
              <p className="text-muted leading-relaxed mb-4">{t.about.p1}</p>
              <p className="text-muted leading-relaxed">{t.about.p2}</p>
            </div>
            <div className="grid grid-cols-3 gap-4">
              {[
                { num: "2+", label: t.about.stat1label },
                { num: "2+", label: t.about.stat2label },
                { num: "\u221E", label: t.about.stat3label },
              ].map((stat, i) => (
                <div
                  key={i}
                  className={`bg-surface border border-border rounded-2xl p-5 text-center transition-all duration-500 ${
                    visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
                  }`}
                  style={{ transitionDelay: visible ? `${300 + i * 100}ms` : "0ms" }}
                >
                  <span className="text-3xl font-bold gradient-text block">{stat.num}</span>
                  <span className="text-muted text-xs mt-1 block">{stat.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════
   CONTACT
   ═══════════════════════════════════════════════════════ */
function ContactSection({ t }: { t: (typeof translations)["nl"] }) {
  const { ref, visible } = useInView();
  return (
    <section id="contact" ref={ref} className="py-28 px-6 bg-surface/50">
      <div className="max-w-3xl mx-auto">
        <div className={`text-center mb-12 transition-all duration-700 ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
          <span className="inline-block bg-accent/10 text-accent text-xs font-medium px-4 py-1.5 rounded-full mb-4">
            {t.contact.badge}
          </span>
          <h2 className="text-4xl sm:text-5xl font-bold mb-4">{t.contact.title}</h2>
          <p className="text-muted">{t.contact.subtitle}</p>
        </div>

        <form
          className={`bg-surface border border-border rounded-2xl p-8 transition-all duration-700 ${
            visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
          }`}
          style={{ transitionDelay: "200ms" }}
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.target as HTMLFormElement;
            const name = (form.elements.namedItem("name") as HTMLInputElement).value;
            const email = (form.elements.namedItem("email") as HTMLInputElement).value;
            const message = (form.elements.namedItem("message") as HTMLTextAreaElement).value;
            window.location.href = `mailto:kristofbogaerts@hotmail.com?subject=Contact via The Bair Company — ${name}&body=${encodeURIComponent(`Van: ${name}\nEmail: ${email}\n\n${message}`)}`;
          }}
        >
          <div className="grid sm:grid-cols-2 gap-5 mb-5">
            <div>
              <label className="text-sm text-muted block mb-2">{t.contact.name}</label>
              <input
                name="name"
                type="text"
                required
                className="w-full bg-background border border-border rounded-xl px-4 py-3 text-sm text-foreground placeholder:text-muted/50 focus:outline-none focus:border-accent transition-colors"
                placeholder="Jan Janssen"
              />
            </div>
            <div>
              <label className="text-sm text-muted block mb-2">{t.contact.email}</label>
              <input
                name="email"
                type="email"
                required
                className="w-full bg-background border border-border rounded-xl px-4 py-3 text-sm text-foreground placeholder:text-muted/50 focus:outline-none focus:border-accent transition-colors"
                placeholder="jan@voorbeeld.be"
              />
            </div>
          </div>
          <div className="mb-6">
            <label className="text-sm text-muted block mb-2">{t.contact.message}</label>
            <textarea
              name="message"
              required
              rows={5}
              className="w-full bg-background border border-border rounded-xl px-4 py-3 text-sm text-foreground placeholder:text-muted/50 focus:outline-none focus:border-accent transition-colors resize-none"
              placeholder="..."
            />
          </div>
          <button
            type="submit"
            className="w-full bg-accent hover:bg-accent-light text-white py-3.5 rounded-full font-medium transition-all hover:scale-[1.02] hover:shadow-[0_0_30px_rgba(46,138,255,0.3)]"
          >
            {t.contact.send}
          </button>
          <p className="text-center text-muted text-xs mt-4">
            {t.contact.or}{" "}
            <a href="mailto:kristofbogaerts@hotmail.com" className="text-accent hover:underline">
              kristofbogaerts@hotmail.com
            </a>
          </p>
        </form>
      </div>
    </section>
  );
}
