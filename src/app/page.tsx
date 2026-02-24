"use client";

import { useState, useEffect, useRef } from "react";
import Image from "next/image";
import { translations, Lang } from "../lib/translations";

/* ─────────────────────────────────────────────
   HOOKS
   ───────────────────────────────────────────── */
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

function useMousePosition() {
  const [pos, setPos] = useState({ x: 0, y: 0 });
  useEffect(() => {
    const handler = (e: MouseEvent) => setPos({ x: e.clientX, y: e.clientY });
    window.addEventListener("mousemove", handler);
    return () => window.removeEventListener("mousemove", handler);
  }, []);
  return pos;
}

/* ─────────────────────────────────────────────
   CUSTOM CURSOR
   ───────────────────────────────────────────── */
function CustomCursor() {
  const dotRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);
  const [hovering, setHovering] = useState(false);

  useEffect(() => {
    let dotX = 0, dotY = 0, ringX = 0, ringY = 0;
    let mouseX = 0, mouseY = 0;
    let rafId: number;

    const onMove = (e: MouseEvent) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
    };

    const animate = () => {
      dotX += (mouseX - dotX) * 0.2;
      dotY += (mouseY - dotY) * 0.2;
      ringX += (mouseX - ringX) * 0.08;
      ringY += (mouseY - ringY) * 0.08;

      if (dotRef.current) {
        dotRef.current.style.transform = `translate(${dotX - 4}px, ${dotY - 4}px)`;
      }
      if (ringRef.current) {
        const size = hovering ? 60 : 40;
        ringRef.current.style.transform = `translate(${ringX - size / 2}px, ${ringY - size / 2}px)`;
      }
      rafId = requestAnimationFrame(animate);
    };

    window.addEventListener("mousemove", onMove);
    rafId = requestAnimationFrame(animate);

    const onEnter = () => setHovering(true);
    const onLeave = () => setHovering(false);

    // Use MutationObserver to handle dynamically added elements
    const attachListeners = () => {
      const interactives = document.querySelectorAll("a, button, [data-hover]");
      interactives.forEach((el) => {
        el.addEventListener("mouseenter", onEnter);
        el.addEventListener("mouseleave", onLeave);
      });
    };
    attachListeners();
    const observer = new MutationObserver(attachListeners);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      window.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(rafId);
      observer.disconnect();
    };
  }, [hovering]);

  return (
    <>
      <div ref={dotRef} className="cursor-dot hidden md:block" />
      <div ref={ringRef} className={`cursor-ring hidden md:block ${hovering ? "hovering" : ""}`} />
    </>
  );
}

/* ─────────────────────────────────────────────
   MARQUEE STRIP
   ───────────────────────────────────────────── */
function MarqueeStrip({ items }: { items: string[] }) {
  const content = [...items, ...items, ...items];
  return (
    <div className="overflow-hidden py-6 border-y border-border/50">
      <div className="marquee-track">
        {content.map((item, i) => (
          <span key={i} className="flex items-center gap-6 px-6 whitespace-nowrap">
            <span
              className="text-sm font-medium tracking-widest uppercase"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {item}
            </span>
            <span className="w-1.5 h-1.5 rounded-full bg-accent opacity-60" />
          </span>
        ))}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   MAIN PAGE
   ═══════════════════════════════════════════════ */
export default function Home() {
  const [lang, setLang] = useState<Lang>("nl");
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [mounted, setMounted] = useState(false);
  const t = translations[lang];
  const mouse = useMousePosition();

  useEffect(() => {
    setMounted(true);
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <>
      {/* Noise overlay */}
      <div className="noise-overlay" />

      {/* Custom cursor */}
      <CustomCursor />

      {/* ── NAV ── */}
      <nav
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 ${
          scrolled
            ? "bg-background/70 backdrop-blur-2xl border-b border-border/50"
            : "bg-transparent"
        }`}
      >
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          <a href="#" className="flex items-center gap-3 group" data-hover>
            <Image
              src="/logo-light.png"
              alt="The Bair Company"
              width={32}
              height={32}
              className="rounded-full transition-all duration-300 group-hover:scale-110 group-hover:shadow-[0_0_20px_rgba(46,138,255,0.3)]"
            />
            <span
              className="font-bold text-xs tracking-[0.2em] uppercase hidden sm:inline"
              style={{ fontFamily: "var(--font-display)" }}
            >
              The Bair Company
            </span>
          </a>

          <div className="hidden md:flex items-center gap-8">
            {[
              { href: "#services", label: t.nav.services },
              { href: "#projects", label: t.nav.projects },
              { href: "#about", label: t.nav.about },
              { href: "#contact", label: t.nav.contact },
            ].map((link) => (
              <a
                key={link.href}
                href={link.href}
                data-hover
                className="text-xs tracking-widest uppercase text-muted hover:text-foreground transition-colors duration-300 relative group"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {link.label}
                <span className="absolute -bottom-1 left-0 w-0 h-px bg-accent transition-all duration-300 group-hover:w-full" />
              </a>
            ))}

            <div className="flex items-center gap-0.5 ml-2">
              {(["nl", "en"] as const).map((l) => (
                <button
                  key={l}
                  onClick={() => setLang(l)}
                  data-hover
                  className={`px-2.5 py-1 text-xs tracking-wider uppercase transition-all duration-300 ${
                    lang === l
                      ? "text-foreground"
                      : "text-muted/40 hover:text-muted"
                  }`}
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {l}
                </button>
              ))}
            </div>

            <a
              href="#contact"
              data-hover
              className="magnetic-btn bg-foreground text-background px-6 py-2.5 rounded-full text-xs font-bold tracking-wider uppercase hover:bg-accent hover:text-white transition-all duration-300"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {t.nav.cta}
            </a>
          </div>

          <button
            className="md:hidden text-foreground"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label="Menu"
          >
            <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.5">
              {menuOpen ? (
                <path d="M6 6l12 12M6 18L18 6" />
              ) : (
                <>
                  <path d="M4 7h16" />
                  <path d="M4 17h10" />
                </>
              )}
            </svg>
          </button>
        </div>

        {menuOpen && (
          <div className="md:hidden bg-background/95 backdrop-blur-2xl border-b border-border px-6 pb-8 pt-4">
            <div className="flex flex-col gap-6">
              {[
                { href: "#services", label: t.nav.services },
                { href: "#projects", label: t.nav.projects },
                { href: "#about", label: t.nav.about },
                { href: "#contact", label: t.nav.contact },
              ].map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  onClick={() => setMenuOpen(false)}
                  className="text-2xl font-bold text-muted hover:text-foreground transition-colors"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {link.label}
                </a>
              ))}
              <div className="flex gap-3 pt-2">
                {(["nl", "en"] as const).map((l) => (
                  <button
                    key={l}
                    onClick={() => setLang(l)}
                    className={`px-4 py-2 text-sm font-bold uppercase tracking-wider ${
                      lang === l ? "text-foreground border-b-2 border-accent" : "text-muted"
                    }`}
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    {l}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </nav>

      {/* ── HERO ── */}
      <section className="min-h-screen flex flex-col justify-center relative overflow-hidden pt-20">
        {/* Background gradient orbs */}
        <div
          className="absolute w-[800px] h-[800px] rounded-full blur-[200px] pointer-events-none opacity-[0.07]"
          style={{
            background: "radial-gradient(circle, #2E8AFF, transparent 70%)",
            top: "10%",
            left: "50%",
            transform: `translate(-50%, 0) translate(${mounted ? (mouse.x - 700) * 0.02 : 0}px, ${mounted ? (mouse.y - 400) * 0.02 : 0}px)`,
            transition: "transform 0.3s ease-out",
          }}
        />
        <div
          className="absolute w-[500px] h-[500px] rounded-full blur-[150px] pointer-events-none opacity-[0.04]"
          style={{
            background: "radial-gradient(circle, #a855f7, transparent 70%)",
            bottom: "10%",
            right: "10%",
          }}
        />

        <div className="max-w-7xl mx-auto px-6 relative z-10 w-full">
          {/* Badge */}
          <div
            className={`flex items-center gap-3 mb-10 transition-all duration-700 ${
              mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"
            }`}
          >
            <div className="w-12 h-px bg-accent" />
            <span
              className="text-xs tracking-[0.3em] uppercase text-muted"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {t.hero.badge}
            </span>
          </div>

          {/* Main heading */}
          <h1 className="mb-10">
            <span
              className={`block text-[clamp(3rem,10vw,8rem)] font-extrabold leading-[0.9] tracking-tight transition-all duration-700 ${
                mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-12"
              }`}
              style={{ fontFamily: "var(--font-display)", transitionDelay: "100ms" }}
            >
              {t.hero.title1}
            </span>
            <span
              className={`block text-[clamp(3rem,10vw,8rem)] leading-[0.9] tracking-tight gradient-text transition-all duration-700`}
              style={{
                fontFamily: "var(--font-serif)",
                fontStyle: "italic",
                transitionDelay: "250ms",
                opacity: mounted ? 1 : 0,
                transform: mounted ? "translateY(0)" : "translateY(12px)",
              }}
            >
              {t.hero.title2}
            </span>
            <span
              className={`block text-[clamp(3rem,10vw,8rem)] font-extrabold leading-[0.9] tracking-tight transition-all duration-700`}
              style={{
                fontFamily: "var(--font-display)",
                transitionDelay: "400ms",
                opacity: mounted ? 1 : 0,
                transform: mounted ? "translateY(0)" : "translateY(12px)",
              }}
            >
              {t.hero.title3}
            </span>
          </h1>

          {/* Subtitle & CTA row */}
          <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-8">
            <p
              className={`text-muted text-lg max-w-lg leading-relaxed transition-all duration-700`}
              style={{
                transitionDelay: "550ms",
                opacity: mounted ? 1 : 0,
                transform: mounted ? "translateY(0)" : "translateY(20px)",
              }}
            >
              {t.hero.subtitle}
            </p>

            <div
              className={`flex gap-4 transition-all duration-700`}
              style={{
                transitionDelay: "700ms",
                opacity: mounted ? 1 : 0,
                transform: mounted ? "translateY(0)" : "translateY(20px)",
              }}
            >
              <a
                href="#projects"
                data-hover
                className="magnetic-btn bg-foreground text-background px-8 py-4 rounded-full font-bold text-sm tracking-wider uppercase hover:bg-accent hover:text-white transition-all duration-300"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {t.hero.cta1}
              </a>
              <a
                href="#contact"
                data-hover
                className="magnetic-btn border border-border/60 text-foreground px-8 py-4 rounded-full font-medium text-sm tracking-wider uppercase hover:border-accent/50 hover:text-accent transition-all duration-300"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {t.hero.cta2}
              </a>
            </div>
          </div>
        </div>

        {/* Scroll indicator */}
        <div className="absolute bottom-8 left-1/2 -translate-x-1/2" style={{ animation: "float 3s ease-in-out infinite" }}>
          <div className="w-5 h-8 border border-border/60 rounded-full flex justify-center pt-2">
            <div className="w-0.5 h-1.5 bg-muted/60 rounded-full animate-pulse" />
          </div>
        </div>
      </section>

      {/* ── MARQUEE ── */}
      <MarqueeStrip items={t.services.items.map((s) => s.title)} />

      {/* ── SERVICES ── */}
      <ServicesSection t={t} />

      {/* ── PROJECTS ── */}
      <ProjectsSection t={t} />

      {/* ── MARQUEE 2 ── */}
      <MarqueeStrip
        items={["NEXT.JS", "REACT", "FIGMA", "TAILWIND", "AI", "NODE.JS", "TYPESCRIPT", "VERCEL", "PYTHON", "SUPABASE"]}
      />

      {/* ── ABOUT ── */}
      <AboutSection t={t} />

      {/* ── CONTACT ── */}
      <ContactSection t={t} />

      {/* ── FOOTER ── */}
      <footer className="border-t border-border/30 py-16 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-8">
            <div>
              <div className="flex items-center gap-3 mb-3">
                <Image src="/logo-light.png" alt="B" width={24} height={24} className="rounded-full" />
                <span
                  className="font-bold text-xs tracking-[0.2em] uppercase"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  The Bair Company
                </span>
              </div>
              <p className="text-muted text-xs tracking-wide">{t.footer.tagline}</p>
            </div>
            <p className="text-muted/40 text-xs tracking-wider">
              &copy; {new Date().getFullYear()} The Bair Company. {t.footer.rights}
            </p>
          </div>
        </div>
      </footer>
    </>
  );
}

/* ═══════════════════════════════════════════════
   SERVICES
   ═══════════════════════════════════════════════ */
function ServicesSection({ t }: { t: (typeof translations)["nl"] }) {
  const { ref, visible } = useInView();
  return (
    <section id="services" ref={ref} className="py-32 px-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6 mb-20">
          <div>
            <div
              className={`flex items-center gap-3 mb-6 transition-all duration-700 ${
                visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"
              }`}
            >
              <div className="w-12 h-px bg-accent" />
              <span
                className="text-xs tracking-[0.3em] uppercase text-accent"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {t.services.badge}
              </span>
            </div>
            <h2
              className={`text-4xl sm:text-6xl font-extrabold tracking-tight transition-all duration-700 ${
                visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
              }`}
              style={{ fontFamily: "var(--font-display)", transitionDelay: "100ms" }}
            >
              {t.services.title}
            </h2>
          </div>
          <p
            className={`text-muted max-w-md text-base leading-relaxed transition-all duration-700 ${
              visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
            }`}
            style={{ transitionDelay: "200ms" }}
          >
            {t.services.subtitle}
          </p>
        </div>

        {/* Bento grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {t.services.items.map((item, i) => (
            <div
              key={i}
              data-hover
              className={`service-card bg-surface border border-border/50 rounded-2xl p-8 group ${
                visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
              }`}
              style={{
                transition: "all 0.5s cubic-bezier(0.22, 1, 0.36, 1)",
                transitionDelay: visible ? `${150 + i * 80}ms` : "0ms",
              }}
            >
              <div className="flex items-start justify-between mb-8">
                <span className="text-3xl">{item.icon}</span>
                <span
                  className="text-xs text-muted/30 font-bold tracking-wider"
                  style={{ fontFamily: "var(--font-mono)" }}
                >
                  0{i + 1}
                </span>
              </div>
              <h3
                className="text-lg font-bold mb-3 group-hover:text-accent transition-colors duration-300"
                style={{ fontFamily: "var(--font-display)" }}
              >
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

/* ═══════════════════════════════════════════════
   PROJECTS
   ═══════════════════════════════════════════════ */
function ProjectsSection({ t }: { t: (typeof translations)["nl"] }) {
  const { ref, visible } = useInView();
  return (
    <section id="projects" ref={ref} className="py-32 px-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6 mb-20">
          <div>
            <div
              className={`flex items-center gap-3 mb-6 transition-all duration-700 ${
                visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"
              }`}
            >
              <div className="w-12 h-px bg-accent" />
              <span
                className="text-xs tracking-[0.3em] uppercase text-accent"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {t.projects.badge}
              </span>
            </div>
            <h2
              className={`text-4xl sm:text-6xl font-extrabold tracking-tight transition-all duration-700 ${
                visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
              }`}
              style={{ fontFamily: "var(--font-display)", transitionDelay: "100ms" }}
            >
              {t.projects.title}
            </h2>
          </div>
          <p
            className={`text-muted max-w-md text-base leading-relaxed transition-all duration-700 ${
              visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
            }`}
            style={{ transitionDelay: "200ms" }}
          >
            {t.projects.subtitle}
          </p>
        </div>

        {/* Project cards - full width stacked */}
        <div className="flex flex-col gap-6">
          {t.projects.items.map((project, i) => (
            <a
              key={i}
              href={project.url}
              target="_blank"
              rel="noopener noreferrer"
              data-hover
              className={`project-card group bg-surface border border-border/50 rounded-2xl flex flex-col lg:flex-row transition-all duration-700 hover:border-accent/20 ${
                visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
              }`}
              style={{ transitionDelay: visible ? `${200 + i * 150}ms` : "0ms" }}
            >
              {/* Color block */}
              <div
                className={`project-image lg:w-2/5 h-64 lg:h-auto bg-gradient-to-br ${project.color} flex items-center justify-center rounded-t-2xl lg:rounded-l-2xl lg:rounded-tr-none relative overflow-hidden`}
              >
                <span
                  className="text-[8rem] font-extrabold text-white/[0.05] group-hover:text-white/[0.1] transition-all duration-700 select-none"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {project.title.charAt(0)}
                </span>
                {/* Arrow icon overlay */}
                <div className="absolute top-6 right-6 w-10 h-10 rounded-full bg-white/10 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-300 group-hover:translate-x-1 group-hover:-translate-y-1">
                  <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path d="M7 17L17 7M17 7H7M17 7v10" />
                  </svg>
                </div>
              </div>

              {/* Content */}
              <div className="lg:w-3/5 p-8 lg:p-12 flex flex-col justify-center">
                <h3
                  className="text-2xl lg:text-3xl font-extrabold group-hover:text-accent transition-colors duration-300 mb-4"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {project.title}
                </h3>
                <p className="text-muted leading-relaxed mb-6 max-w-lg">{project.description}</p>
                <div className="flex flex-wrap gap-2">
                  {project.tags.map((tag) => (
                    <span
                      key={tag}
                      className="bg-border/30 text-muted text-xs px-3 py-1.5 rounded-full tracking-wide uppercase"
                      style={{ fontFamily: "var(--font-display)", fontSize: "0.65rem" }}
                    >
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

/* ═══════════════════════════════════════════════
   ABOUT
   ═══════════════════════════════════════════════ */
function AboutSection({ t }: { t: (typeof translations)["nl"] }) {
  const { ref, visible } = useInView();
  return (
    <section id="about" ref={ref} className="py-32 px-6">
      <div className="max-w-7xl mx-auto">
        <div className="flex flex-col lg:flex-row gap-16 lg:gap-24">
          {/* Left: text */}
          <div className="lg:w-3/5">
            <div
              className={`flex items-center gap-3 mb-6 transition-all duration-700 ${
                visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"
              }`}
            >
              <div className="w-12 h-px bg-accent" />
              <span
                className="text-xs tracking-[0.3em] uppercase text-accent"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {t.about.badge}
              </span>
            </div>

            <h2
              className={`text-4xl sm:text-6xl font-extrabold tracking-tight mb-10 transition-all duration-700 ${
                visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
              }`}
              style={{ fontFamily: "var(--font-display)", transitionDelay: "100ms" }}
            >
              {t.about.title.split(".")[0]}.
              <br />
              <span
                className="gradient-text"
                style={{ fontFamily: "var(--font-serif)", fontStyle: "italic" }}
              >
                {t.about.title.split(".")[1]?.trim() || ""}
              </span>
            </h2>

            <div className="space-y-5">
              <p
                className={`text-muted text-lg leading-relaxed transition-all duration-700 ${
                  visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
                }`}
                style={{ transitionDelay: "200ms" }}
              >
                {t.about.p1}
              </p>
              <p
                className={`text-muted text-lg leading-relaxed transition-all duration-700 ${
                  visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
                }`}
                style={{ transitionDelay: "300ms" }}
              >
                {t.about.p2}
              </p>
            </div>
          </div>

          {/* Right: stats */}
          <div className="lg:w-2/5 flex flex-col gap-5 lg:pt-24">
            {[
              { num: "2+", label: t.about.stat1label },
              { num: "2+", label: t.about.stat2label },
              { num: "\u221E", label: t.about.stat3label },
            ].map((stat, i) => (
              <div
                key={i}
                className={`border-l-2 border-accent/30 pl-8 py-4 transition-all duration-700 ${
                  visible ? "opacity-100 translate-x-0" : "opacity-0 translate-x-8"
                }`}
                style={{ transitionDelay: `${300 + i * 100}ms` }}
              >
                <span
                  className="text-5xl font-extrabold gradient-text block"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {stat.num}
                </span>
                <span
                  className="text-muted text-xs tracking-[0.2em] uppercase mt-2 block"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {stat.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════
   CONTACT
   ═══════════════════════════════════════════════ */
function ContactSection({ t }: { t: (typeof translations)["nl"] }) {
  const { ref, visible } = useInView();
  return (
    <section id="contact" ref={ref} className="py-32 px-6">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-16">
          <div
            className={`flex items-center justify-center gap-3 mb-6 transition-all duration-700 ${
              visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"
            }`}
          >
            <div className="w-12 h-px bg-accent" />
            <span
              className="text-xs tracking-[0.3em] uppercase text-accent"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {t.contact.badge}
            </span>
            <div className="w-12 h-px bg-accent" />
          </div>
          <h2
            className={`text-4xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight mb-4 transition-all duration-700 ${
              visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
            }`}
            style={{ fontFamily: "var(--font-display)", transitionDelay: "100ms" }}
          >
            {t.contact.title}
          </h2>
          <p
            className={`text-muted text-lg transition-all duration-700 ${
              visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
            }`}
            style={{ transitionDelay: "200ms" }}
          >
            {t.contact.subtitle}
          </p>
        </div>

        <form
          className={`bg-surface border border-border/50 rounded-3xl p-8 sm:p-12 transition-all duration-700 ${
            visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
          }`}
          style={{ transitionDelay: "300ms" }}
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
              <label
                className="text-xs tracking-wider uppercase text-muted block mb-3"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {t.contact.name}
              </label>
              <input
                name="name"
                type="text"
                required
                className="w-full bg-background border border-border/50 rounded-xl px-5 py-3.5 text-sm text-foreground placeholder:text-muted/30 focus:outline-none focus:border-accent/50 transition-all duration-300"
                placeholder="Jan Janssen"
              />
            </div>
            <div>
              <label
                className="text-xs tracking-wider uppercase text-muted block mb-3"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {t.contact.email}
              </label>
              <input
                name="email"
                type="email"
                required
                className="w-full bg-background border border-border/50 rounded-xl px-5 py-3.5 text-sm text-foreground placeholder:text-muted/30 focus:outline-none focus:border-accent/50 transition-all duration-300"
                placeholder="jan@voorbeeld.be"
              />
            </div>
          </div>
          <div className="mb-8">
            <label
              className="text-xs tracking-wider uppercase text-muted block mb-3"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {t.contact.message}
            </label>
            <textarea
              name="message"
              required
              rows={5}
              className="w-full bg-background border border-border/50 rounded-xl px-5 py-3.5 text-sm text-foreground placeholder:text-muted/30 focus:outline-none focus:border-accent/50 transition-all duration-300 resize-none"
              placeholder="..."
            />
          </div>
          <button
            type="submit"
            data-hover
            className="magnetic-btn w-full bg-foreground text-background py-4 rounded-full font-bold text-sm tracking-wider uppercase hover:bg-accent hover:text-white transition-all duration-300"
            style={{ fontFamily: "var(--font-display)" }}
          >
            {t.contact.send}
          </button>
          <p className="text-center text-muted/40 text-xs mt-5 tracking-wide">
            {t.contact.or}{" "}
            <a href="mailto:kristofbogaerts@hotmail.com" data-hover className="text-accent hover:text-accent-light transition-colors">
              kristofbogaerts@hotmail.com
            </a>
          </p>
        </form>
      </div>
    </section>
  );
}
