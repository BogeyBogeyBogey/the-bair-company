"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Image from "next/image";
import { translations, Lang } from "../lib/translations";

/* ═══════════════════════════════════════════════════════════
   HOOKS
   ═══════════════════════════════════════════════════════════ */

function useInView(threshold = 0.15) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setVisible(true);
          obs.disconnect();
        }
      },
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

/* ═══════════════════════════════════════════════════════════
   INTRO LOADER — Curtain split reveal
   ═══════════════════════════════════════════════════════════ */

function IntroLoader({ onDone }: { onDone: () => void }) {
  const [phase, setPhase] = useState<"loading" | "reveal" | "done">("loading");

  useEffect(() => {
    const t1 = setTimeout(() => setPhase("reveal"), 1400);
    const t2 = setTimeout(() => {
      setPhase("done");
      onDone();
    }, 2800);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [onDone]);

  if (phase === "done") return null;

  return (
    <div className={`intro-overlay ${phase === "reveal" ? "revealed" : ""}`}>
      <div className="intro-half intro-half--top" />
      <div className="intro-half intro-half--bottom" />
      <div className="intro-center">
        <Image
          src="/logo-light.png"
          alt="B"
          width={48}
          height={48}
          className="rounded-full mb-6"
          style={{ animation: "breathe 2s ease infinite" }}
        />
        <div
          className="text-[0.6rem] tracking-[0.4em] uppercase text-muted/60"
          style={{ fontFamily: "var(--font-display)" }}
        >
          THE BAIR COMPANY
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   CUSTOM CURSOR — Dot + Ring with hover detection
   ═══════════════════════════════════════════════════════════ */

function CustomCursor() {
  const dotRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let mouseX = 0,
      mouseY = 0;
    let dotX = 0,
      dotY = 0,
      ringX = 0,
      ringY = 0;
    let hovering = false;
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
        const s = hovering ? 64 : 40;
        ringRef.current.style.transform = `translate(${ringX - s / 2}px, ${ringY - s / 2}px)`;
      }
      rafId = requestAnimationFrame(animate);
    };

    window.addEventListener("mousemove", onMove);
    rafId = requestAnimationFrame(animate);

    const onEnter = () => {
      hovering = true;
      ringRef.current?.classList.add("hovering");
    };
    const onLeave = () => {
      hovering = false;
      ringRef.current?.classList.remove("hovering");
    };

    const attach = () => {
      document.querySelectorAll("a, button, [data-hover]").forEach((el) => {
        el.addEventListener("mouseenter", onEnter);
        el.addEventListener("mouseleave", onLeave);
      });
    };
    attach();
    const obs = new MutationObserver(attach);
    obs.observe(document.body, { childList: true, subtree: true });

    return () => {
      window.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(rafId);
      obs.disconnect();
    };
  }, []);

  return (
    <>
      <div ref={dotRef} className="cursor-dot hidden md:block" />
      <div ref={ringRef} className="cursor-ring hidden md:block" />
    </>
  );
}

/* ═══════════════════════════════════════════════════════════
   FULLSCREEN NAV — Circle clip-path reveal
   ═══════════════════════════════════════════════════════════ */

function FullScreenNav({
  open,
  onClose,
  lang,
  setLang,
  t,
}: {
  open: boolean;
  onClose: () => void;
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (typeof translations)["nl"];
}) {
  const links = [
    { href: "#services", label: t.nav.services, num: "01" },
    { href: "#projects", label: t.nav.projects, num: "02" },
    { href: "#about", label: t.nav.about, num: "03" },
    { href: "#contact", label: t.nav.contact, num: "04" },
  ];

  return (
    <div className={`fs-nav ${open ? "open" : ""}`}>
      <div className="w-full px-6 md:px-[5vw] flex flex-col lg:flex-row lg:items-center">
        <div className="flex-1">
          {links.map((link, i) => (
            <a
              key={link.href}
              href={link.href}
              className="fs-nav-link"
              data-hover
              onClick={onClose}
              style={{
                transitionDelay: open ? `${0.1 + i * 0.05}s` : "0s",
              }}
            >
              <span className="fs-nav-num">{link.num}</span>
              {link.label}
            </a>
          ))}
        </div>
        <div className="flex flex-col gap-6 pt-12 lg:pt-0 lg:pl-12">
          <div className="flex gap-4">
            {(["nl", "en"] as const).map((l) => (
              <button
                key={l}
                onClick={() => setLang(l)}
                data-hover
                className={`text-sm uppercase tracking-widest transition-colors ${
                  lang === l ? "text-foreground" : "text-muted/30 hover:text-muted"
                }`}
                style={{ fontFamily: "var(--font-display)" }}
              >
                {l}
              </button>
            ))}
          </div>
          <a
            href="mailto:kristofbogaerts@hotmail.com"
            data-hover
            className="text-muted/40 hover:text-accent transition-colors text-sm"
          >
            kristofbogaerts@hotmail.com
          </a>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MARQUEE — Diagonal scrolling text strip
   ═══════════════════════════════════════════════════════════ */

function MarqueeStrip({ items, reverse = false }: { items: string[]; reverse?: boolean }) {
  const content = [...items, ...items];
  return (
    <div
      className="marquee-wrap py-6 md:py-8 border-y border-border/20"
      style={{
        transform: `rotate(${reverse ? "1" : "-1"}deg)`,
        margin: "0 -3vw",
      }}
    >
      <div className={`marquee-track ${reverse ? "reverse" : ""}`}>
        {content.map((item, i) => (
          <span key={i} className="inline-flex items-center gap-5 md:gap-8 px-5 md:px-8">
            <span
              className="text-xs md:text-sm font-semibold tracking-[0.2em] uppercase text-muted/30"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {item}
            </span>
            <span className="w-1.5 h-1.5 rounded-full bg-accent/30" />
          </span>
        ))}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   HERO — Giant viewport-filling typography
   ═══════════════════════════════════════════════════════════ */

function HeroSection({
  t,
  ready,
  mouse,
}: {
  t: (typeof translations)["nl"];
  ready: boolean;
  mouse: { x: number; y: number };
}) {
  return (
    <section className="h-screen flex flex-col justify-center relative overflow-hidden">
      {/* Gradient orbs following mouse */}
      <div
        className="glow-orb w-[60vw] h-[60vw] max-w-[800px] max-h-[800px] absolute opacity-[0.06]"
        style={{
          background: "radial-gradient(circle, #2E8AFF, transparent 70%)",
          top: "-10%",
          left: "30%",
          transform: `translate(${ready ? (mouse.x - 500) * 0.02 : 0}px, ${ready ? (mouse.y - 300) * 0.02 : 0}px)`,
          transition: "transform 0.5s ease-out",
        }}
      />
      <div
        className="glow-orb w-[40vw] h-[40vw] max-w-[500px] max-h-[500px] absolute opacity-[0.04]"
        style={{
          background: "radial-gradient(circle, #FF6B35, transparent 70%)",
          bottom: "0",
          right: "10%",
          transform: `translate(${ready ? (mouse.x - 500) * -0.01 : 0}px, ${ready ? (mouse.y - 300) * -0.01 : 0}px)`,
          transition: "transform 0.5s ease-out",
        }}
      />

      <div className="relative z-10 px-6 md:px-[5vw] w-full">
        {/* Badge */}
        <div
          className="mb-8 md:mb-12"
          style={{
            opacity: ready ? 1 : 0,
            transform: ready ? "translateY(0)" : "translateY(20px)",
            transition: "all 0.8s cubic-bezier(0.22,1,0.36,1) 0.3s",
          }}
        >
          <span
            className="text-[0.6rem] md:text-xs tracking-[0.3em] uppercase text-muted/50"
            style={{ fontFamily: "var(--font-display)" }}
          >
            ◆ {t.hero.badge}
          </span>
        </div>

        {/* GIANT TEXT */}
        <h1 className="leading-[0.85]">
          {/* Line 1 — bold */}
          <span
            className="block text-[14vw] md:text-[11vw] font-extrabold tracking-[-0.03em]"
            style={{
              fontFamily: "var(--font-display)",
              opacity: ready ? 1 : 0,
              transform: ready ? "translateY(0)" : "translateY(80px)",
              transition: "all 1s cubic-bezier(0.22,1,0.36,1) 0.4s",
            }}
          >
            {t.hero.title1}
          </span>

          {/* Line 2 — outlined / stroke */}
          <span
            className="block text-[18vw] md:text-[15vw] font-extrabold tracking-[-0.03em] text-stroke"
            style={{
              fontFamily: "var(--font-display)",
              opacity: ready ? 1 : 0,
              transform: ready ? "translateY(0)" : "translateY(80px)",
              transition: "all 1s cubic-bezier(0.22,1,0.36,1) 0.55s",
            }}
          >
            {t.hero.title2}
          </span>

          {/* Line 3 — gradient fill */}
          <span
            className="block text-[14vw] md:text-[11vw] font-extrabold tracking-[-0.03em] gradient-text"
            style={{
              fontFamily: "var(--font-display)",
              opacity: ready ? 1 : 0,
              transform: ready ? "translateY(0)" : "translateY(80px)",
              transition: "all 1s cubic-bezier(0.22,1,0.36,1) 0.7s",
            }}
          >
            {t.hero.title3}
          </span>
        </h1>

        {/* Bottom row */}
        <div
          className="flex flex-col md:flex-row md:items-end md:justify-between gap-6 mt-8 md:mt-12"
          style={{
            opacity: ready ? 1 : 0,
            transform: ready ? "translateY(0)" : "translateY(30px)",
            transition: "all 0.8s cubic-bezier(0.22,1,0.36,1) 0.9s",
          }}
        >
          <p className="text-muted text-sm md:text-base max-w-md leading-relaxed">{t.hero.subtitle}</p>
          <div className="flex gap-3">
            <a
              href="#projects"
              data-hover
              className="mag-btn bg-foreground text-background px-6 md:px-8 py-3 md:py-4 rounded-full text-xs md:text-sm font-bold tracking-wider uppercase"
              style={{ fontFamily: "var(--font-display)" }}
            >
              <span>{t.hero.cta1}</span>
            </a>
            <a
              href="#contact"
              data-hover
              className="border border-border/50 text-foreground px-6 md:px-8 py-3 md:py-4 rounded-full text-xs md:text-sm font-medium tracking-wider uppercase hover:border-accent/50 hover:text-accent transition-all duration-300"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {t.hero.cta2}
            </a>
          </div>
        </div>
      </div>

      {/* Scroll indicator */}
      <div
        className="absolute bottom-8 left-1/2 -translate-x-1/2"
        style={{
          animation: "float 3s ease-in-out infinite",
          opacity: ready ? 0.4 : 0,
          transition: "opacity 1s ease 1.2s",
        }}
      >
        <div className="flex flex-col items-center gap-2">
          <span
            className="text-[0.55rem] tracking-[0.3em] uppercase text-muted/40"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Scroll
          </span>
          <div className="w-px h-8 bg-gradient-to-b from-muted/40 to-transparent" />
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════
   SERVICES — Editorial list with hover reveals
   ═══════════════════════════════════════════════════════════ */

function ServicesSection({ t }: { t: (typeof translations)["nl"] }) {
  const { ref, visible } = useInView(0.1);

  return (
    <section id="services" ref={ref} className="py-24 md:py-40 px-6 md:px-[5vw]">
      {/* Badge */}
      <div
        className="flex items-center gap-4 mb-6"
        style={{
          opacity: visible ? 1 : 0,
          transform: visible ? "translateY(0)" : "translateY(20px)",
          transition: "all 0.7s cubic-bezier(0.22,1,0.36,1)",
        }}
      >
        <div className="w-12 h-px bg-accent" />
        <span
          className="text-xs tracking-[0.3em] uppercase text-accent"
          style={{ fontFamily: "var(--font-display)" }}
        >
          {t.services.badge}
        </span>
      </div>

      {/* Title — split at period, second part in serif italic gradient */}
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6 mb-16 md:mb-24">
        <h2
          className="text-4xl md:text-6xl lg:text-7xl font-extrabold tracking-tight leading-[0.9]"
          style={{
            fontFamily: "var(--font-display)",
            opacity: visible ? 1 : 0,
            transform: visible ? "translateY(0)" : "translateY(30px)",
            transition: "all 0.8s cubic-bezier(0.22,1,0.36,1) 0.1s",
          }}
        >
          {t.services.title.split(",")[0]},
          <br />
          <span className="gradient-text" style={{ fontFamily: "var(--font-serif)", fontStyle: "italic" }}>
            {t.services.title.split(",")[1]?.trim() || t.services.title.split(".")[1]?.trim() || ""}
          </span>
        </h2>
        <p
          className="text-muted max-w-md text-sm md:text-base leading-relaxed"
          style={{
            opacity: visible ? 1 : 0,
            transform: visible ? "translateY(0)" : "translateY(20px)",
            transition: "all 0.7s cubic-bezier(0.22,1,0.36,1) 0.2s",
          }}
        >
          {t.services.subtitle}
        </p>
      </div>

      {/* Service rows — editorial list */}
      <div>
        {t.services.items.map((item, i) => (
          <div
            key={i}
            className="service-row"
            data-hover
            style={{
              opacity: visible ? 1 : 0,
              transform: visible ? "translateY(0)" : "translateY(20px)",
              transition: `all 0.6s cubic-bezier(0.22,1,0.36,1) ${0.3 + i * 0.08}s`,
            }}
          >
            <span className="sr-num">0{i + 1}</span>
            <span className="sr-title">{item.title}</span>
            <span className="sr-desc hidden lg:block">{item.description}</span>
            <span className="sr-arrow">
              <svg width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
                <path d="M7 17L17 7M17 7H7M17 7v10" />
              </svg>
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════
   PROJECTS — Horizontal scroll on desktop, stacked on mobile
   ═══════════════════════════════════════════════════════════ */

function ProjectsSection({ t }: { t: (typeof translations)["nl"] }) {
  const { ref: headerRef, visible: headerVisible } = useInView(0.1);
  const sectionRef = useRef<HTMLDivElement>(null);
  const [progress, setProgress] = useState(0);
  const panels = t.projects.items;

  useEffect(() => {
    const handleScroll = () => {
      if (!sectionRef.current) return;
      const rect = sectionRef.current.getBoundingClientRect();
      const scrollable = sectionRef.current.offsetHeight - window.innerHeight;
      if (scrollable <= 0) return;
      const p = Math.max(0, Math.min(1, -rect.top / scrollable));
      setProgress(p);
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const moveX = progress * (panels.length - 1) * 84;

  return (
    <section id="projects">
      {/* Section header */}
      <div ref={headerRef} className="px-6 md:px-[5vw] pt-24 md:pt-40 pb-12">
        <div
          className="flex items-center gap-4 mb-6"
          style={{
            opacity: headerVisible ? 1 : 0,
            transform: headerVisible ? "translateY(0)" : "translateY(20px)",
            transition: "all 0.7s cubic-bezier(0.22,1,0.36,1)",
          }}
        >
          <div className="w-12 h-px bg-accent" />
          <span
            className="text-xs tracking-[0.3em] uppercase text-accent"
            style={{ fontFamily: "var(--font-display)" }}
          >
            {t.projects.badge}
          </span>
        </div>
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6">
          <h2
            className="text-4xl md:text-6xl lg:text-7xl font-extrabold tracking-tight"
            style={{
              fontFamily: "var(--font-display)",
              opacity: headerVisible ? 1 : 0,
              transform: headerVisible ? "translateY(0)" : "translateY(30px)",
              transition: "all 0.8s cubic-bezier(0.22,1,0.36,1) 0.1s",
            }}
          >
            {t.projects.title}
          </h2>
          <p
            className="text-muted max-w-md text-sm md:text-base leading-relaxed"
            style={{
              opacity: headerVisible ? 1 : 0,
              transition: "opacity 0.7s ease 0.2s",
            }}
          >
            {t.projects.subtitle}
          </p>
        </div>
      </div>

      {/* Desktop: Horizontal scroll */}
      <div
        ref={sectionRef}
        className="hidden md:block"
        style={{ height: `${(panels.length + 1) * 100}vh` }}
      >
        <div className="sticky top-0 h-screen overflow-hidden flex items-center">
          <div
            className="h-scroll-track pl-[5vw]"
            style={{
              transform: `translateX(-${moveX}vw)`,
            }}
          >
            {panels.map((project, i) => (
              <a
                key={i}
                href={project.url}
                target="_blank"
                rel="noopener noreferrer"
                data-hover
                className={`h-panel bg-gradient-to-br ${project.color} group`}
              >
                {/* Huge background letter */}
                <span
                  className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[25vw] font-extrabold text-white/[0.03] group-hover:text-white/[0.07] transition-all duration-700 select-none"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {project.title.charAt(0)}
                </span>

                {/* Arrow */}
                <div className="absolute top-8 right-8 w-12 h-12 rounded-full border border-white/10 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-300 group-hover:translate-x-1 group-hover:-translate-y-1">
                  <svg
                    className="w-5 h-5 text-white/70"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={1.5}
                  >
                    <path d="M7 17L17 7M17 7H7M17 7v10" />
                  </svg>
                </div>

                {/* Content */}
                <div className="relative z-10">
                  <div className="flex flex-wrap gap-2 mb-4">
                    {project.tags.map((tag) => (
                      <span
                        key={tag}
                        className="text-[0.6rem] tracking-widest uppercase text-white/30 bg-white/5 px-3 py-1 rounded-full"
                        style={{ fontFamily: "var(--font-display)" }}
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                  <h3
                    className="text-3xl md:text-5xl font-extrabold text-white/80 mb-3 group-hover:text-white transition-colors duration-300"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    {project.title}
                  </h3>
                  <p className="text-white/40 max-w-lg text-sm leading-relaxed group-hover:text-white/60 transition-colors duration-300">
                    {project.description}
                  </p>
                </div>
              </a>
            ))}
          </div>

          {/* Progress bar */}
          <div className="absolute bottom-8 left-[5vw] right-[5vw] h-px bg-border/20">
            <div
              className="h-full bg-accent/60 transition-[width] duration-100"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
        </div>
      </div>

      {/* Mobile: Vertical stacked cards */}
      <div className="md:hidden px-6 pb-12 flex flex-col gap-6">
        {panels.map((project, i) => (
          <a
            key={i}
            href={project.url}
            target="_blank"
            rel="noopener noreferrer"
            className={`rounded-2xl bg-gradient-to-br ${project.color} p-6 min-h-[50vh] flex flex-col justify-end relative overflow-hidden`}
          >
            <span
              className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[40vw] font-extrabold text-white/[0.03] select-none"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {project.title.charAt(0)}
            </span>
            <div className="relative z-10">
              <div className="flex flex-wrap gap-2 mb-3">
                {project.tags.map((tag) => (
                  <span
                    key={tag}
                    className="text-[0.55rem] tracking-widest uppercase text-white/30 bg-white/5 px-2 py-1 rounded-full"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    {tag}
                  </span>
                ))}
              </div>
              <h3
                className="text-2xl font-extrabold text-white/80 mb-2"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {project.title}
              </h3>
              <p className="text-white/40 text-sm leading-relaxed">{project.description}</p>
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════
   ABOUT — Large title + stats
   ═══════════════════════════════════════════════════════════ */

function AboutSection({ t }: { t: (typeof translations)["nl"] }) {
  const { ref, visible } = useInView(0.1);

  return (
    <section id="about" ref={ref} className="py-24 md:py-40 px-6 md:px-[5vw]">
      {/* Badge */}
      <div
        className="flex items-center gap-4 mb-6"
        style={{
          opacity: visible ? 1 : 0,
          transform: visible ? "translateY(0)" : "translateY(20px)",
          transition: "all 0.7s cubic-bezier(0.22,1,0.36,1)",
        }}
      >
        <div className="w-12 h-px bg-accent" />
        <span
          className="text-xs tracking-[0.3em] uppercase text-accent"
          style={{ fontFamily: "var(--font-display)" }}
        >
          {t.about.badge}
        </span>
      </div>

      {/* Giant title */}
      <h2
        className="text-4xl md:text-7xl lg:text-8xl font-extrabold tracking-tight mb-16 md:mb-24 leading-[0.9]"
        style={{
          fontFamily: "var(--font-display)",
          opacity: visible ? 1 : 0,
          transform: visible ? "translateY(0)" : "translateY(40px)",
          transition: "all 0.9s cubic-bezier(0.22,1,0.36,1) 0.1s",
        }}
      >
        {t.about.title.split(".")[0]}.
        <br />
        <span className="gradient-text" style={{ fontFamily: "var(--font-serif)", fontStyle: "italic" }}>
          {t.about.title.split(".")[1]?.trim() || ""}
        </span>
      </h2>

      <div className="flex flex-col lg:flex-row gap-16 lg:gap-24">
        {/* Text */}
        <div className="lg:w-3/5 space-y-6">
          <p
            className="text-muted text-base md:text-lg leading-relaxed"
            style={{
              opacity: visible ? 1 : 0,
              transform: visible ? "translateY(0)" : "translateY(20px)",
              transition: "all 0.7s cubic-bezier(0.22,1,0.36,1) 0.2s",
            }}
          >
            {t.about.p1}
          </p>
          <p
            className="text-muted text-base md:text-lg leading-relaxed"
            style={{
              opacity: visible ? 1 : 0,
              transform: visible ? "translateY(0)" : "translateY(20px)",
              transition: "all 0.7s cubic-bezier(0.22,1,0.36,1) 0.3s",
            }}
          >
            {t.about.p2}
          </p>
        </div>

        {/* Stats — oversized numbers */}
        <div className="lg:w-2/5 flex flex-col gap-10">
          {[
            { num: "2+", label: t.about.stat1label },
            { num: "2+", label: t.about.stat2label },
            { num: "\u221E", label: t.about.stat3label },
          ].map((stat, i) => (
            <div
              key={i}
              style={{
                opacity: visible ? 1 : 0,
                transform: visible ? "translateX(0)" : "translateX(30px)",
                transition: `all 0.7s cubic-bezier(0.22,1,0.36,1) ${0.3 + i * 0.1}s`,
              }}
            >
              <span
                className="text-6xl md:text-8xl font-extrabold gradient-text block leading-none"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {stat.num}
              </span>
              <span
                className="text-muted/60 text-xs tracking-[0.2em] uppercase mt-2 block"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {stat.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════
   CONTACT — Dramatic heading + clean form
   ═══════════════════════════════════════════════════════════ */

function ContactSection({ t }: { t: (typeof translations)["nl"] }) {
  const { ref, visible } = useInView(0.1);

  return (
    <section id="contact" ref={ref} className="py-24 md:py-40 px-6 md:px-[5vw]">
      <div className="max-w-5xl mx-auto">
        {/* Giant heading */}
        <h2
          className="text-4xl md:text-7xl lg:text-[5.5rem] font-extrabold tracking-tight mb-4 text-center leading-[0.9]"
          style={{
            fontFamily: "var(--font-display)",
            opacity: visible ? 1 : 0,
            transform: visible ? "translateY(0) scale(1)" : "translateY(40px) scale(0.95)",
            transition: "all 1s cubic-bezier(0.22,1,0.36,1)",
          }}
        >
          {t.contact.title}
        </h2>
        <p
          className="text-muted text-center text-sm md:text-base mb-12 md:mb-16"
          style={{
            opacity: visible ? 1 : 0,
            transition: "opacity 0.7s ease 0.2s",
          }}
        >
          {t.contact.subtitle}
        </p>

        {/* Form */}
        <form
          className="bg-surface/50 border border-border/20 rounded-3xl p-6 sm:p-10 md:p-12 backdrop-blur-sm"
          style={{
            opacity: visible ? 1 : 0,
            transform: visible ? "translateY(0)" : "translateY(30px)",
            transition: "all 0.8s cubic-bezier(0.22,1,0.36,1) 0.3s",
          }}
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.target as HTMLFormElement;
            const name = (form.elements.namedItem("name") as HTMLInputElement).value;
            const email = (form.elements.namedItem("email") as HTMLInputElement).value;
            const message = (form.elements.namedItem("message") as HTMLTextAreaElement).value;
            window.location.href = `mailto:kristofbogaerts@hotmail.com?subject=Contact via The Bair Company — ${name}&body=${encodeURIComponent(`Van: ${name}\nEmail: ${email}\n\n${message}`)}`;
          }}
        >
          <div className="grid sm:grid-cols-2 gap-4 mb-4">
            <div>
              <label
                className="text-[0.6rem] tracking-[0.2em] uppercase text-muted/50 block mb-2"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {t.contact.name}
              </label>
              <input
                name="name"
                type="text"
                required
                className="w-full bg-background/80 border border-border/20 rounded-xl px-5 py-3.5 text-sm text-foreground placeholder:text-muted/15 focus:outline-none focus:border-accent/30 transition-all duration-300"
                placeholder="Jan Janssen"
              />
            </div>
            <div>
              <label
                className="text-[0.6rem] tracking-[0.2em] uppercase text-muted/50 block mb-2"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {t.contact.email}
              </label>
              <input
                name="email"
                type="email"
                required
                className="w-full bg-background/80 border border-border/20 rounded-xl px-5 py-3.5 text-sm text-foreground placeholder:text-muted/15 focus:outline-none focus:border-accent/30 transition-all duration-300"
                placeholder="jan@voorbeeld.be"
              />
            </div>
          </div>
          <div className="mb-6">
            <label
              className="text-[0.6rem] tracking-[0.2em] uppercase text-muted/50 block mb-2"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {t.contact.message}
            </label>
            <textarea
              name="message"
              required
              rows={5}
              className="w-full bg-background/80 border border-border/20 rounded-xl px-5 py-3.5 text-sm text-foreground placeholder:text-muted/15 focus:outline-none focus:border-accent/30 transition-all duration-300 resize-none"
              placeholder="..."
            />
          </div>
          <button
            type="submit"
            data-hover
            className="mag-btn w-full bg-foreground text-background py-4 rounded-full font-bold text-sm tracking-wider uppercase"
            style={{ fontFamily: "var(--font-display)" }}
          >
            <span>{t.contact.send}</span>
          </button>
          <p className="text-center text-muted/25 text-xs mt-4 tracking-wide">
            {t.contact.or}{" "}
            <a
              href="mailto:kristofbogaerts@hotmail.com"
              data-hover
              className="text-accent/60 hover:text-accent transition-colors"
            >
              kristofbogaerts@hotmail.com
            </a>
          </p>
        </form>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════
   MAIN PAGE — Orchestrator
   ═══════════════════════════════════════════════════════════ */

export default function Home() {
  const [lang, setLang] = useState<Lang>("nl");
  const [navOpen, setNavOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [ready, setReady] = useState(false);
  const t = translations[lang];
  const mouse = useMousePosition();

  const handleIntroDone = useCallback(() => setReady(true), []);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 60);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Lock body scroll when nav is open
  useEffect(() => {
    document.body.style.overflow = navOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [navOpen]);

  return (
    <>
      {/* ── LAYERS ── */}
      <div className="noise" />
      <CustomCursor />
      <IntroLoader onDone={handleIntroDone} />
      <FullScreenNav open={navOpen} onClose={() => setNavOpen(false)} lang={lang} setLang={setLang} t={t} />

      {/* ── FIXED NAV BAR ── */}
      <nav
        className={`fixed top-0 left-0 right-0 z-[85] px-6 md:px-[5vw] h-20 flex items-center justify-between transition-all duration-500 ${
          scrolled ? "bg-background/60 backdrop-blur-2xl" : ""
        }`}
      >
        <a href="#" className="flex items-center gap-3 group" data-hover>
          <Image
            src="/logo-light.png"
            alt="The Bair Company"
            width={28}
            height={28}
            className="rounded-full transition-transform duration-300 group-hover:scale-110"
          />
          <span
            className="font-bold text-[0.6rem] tracking-[0.2em] uppercase hidden sm:inline text-foreground/70"
            style={{ fontFamily: "var(--font-display)" }}
          >
            The Bair Company
          </span>
        </a>

        <div className="flex items-center gap-6">
          {/* Desktop language toggle */}
          <div className="hidden md:flex items-center gap-1">
            {(["nl", "en"] as const).map((l) => (
              <button
                key={l}
                onClick={() => setLang(l)}
                data-hover
                className={`px-2 py-1 text-[0.6rem] tracking-[0.15em] uppercase transition-colors ${
                  lang === l ? "text-foreground" : "text-muted/25 hover:text-muted"
                }`}
                style={{ fontFamily: "var(--font-display)" }}
              >
                {l}
              </button>
            ))}
          </div>

          {/* Hamburger */}
          <button
            onClick={() => setNavOpen(!navOpen)}
            className="relative z-[90] w-10 h-10 flex flex-col items-center justify-center gap-[6px]"
            data-hover
            aria-label="Menu"
          >
            <span
              className={`block w-6 h-[1.5px] bg-foreground transition-all duration-300 origin-center ${
                navOpen ? "rotate-45 translate-y-[7.5px]" : ""
              }`}
            />
            <span
              className={`block w-4 h-[1.5px] bg-foreground transition-all duration-300 ${
                navOpen ? "opacity-0 scale-0" : ""
              }`}
            />
            <span
              className={`block w-6 h-[1.5px] bg-foreground transition-all duration-300 origin-center ${
                navOpen ? "-rotate-45 -translate-y-[7.5px]" : ""
              }`}
            />
          </button>
        </div>
      </nav>

      {/* ── CONTENT ── */}
      <main>
        <HeroSection t={t} ready={ready} mouse={mouse} />

        <MarqueeStrip items={t.services.items.map((s) => s.title)} />

        <ServicesSection t={t} />

        <ProjectsSection t={t} />

        <MarqueeStrip
          items={["NEXT.JS", "REACT", "FIGMA", "TAILWIND", "AI", "NODE.JS", "TYPESCRIPT", "VERCEL"]}
          reverse
        />

        <AboutSection t={t} />

        <ContactSection t={t} />
      </main>

      {/* ── FOOTER ── */}
      <footer className="border-t border-border/15 py-12 px-6 md:px-[5vw]">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
          <div className="flex items-center gap-3">
            <Image src="/logo-light.png" alt="B" width={20} height={20} className="rounded-full opacity-50" />
            <span
              className="text-[0.55rem] tracking-[0.2em] uppercase text-muted/30"
              style={{ fontFamily: "var(--font-display)" }}
            >
              The Bair Company — {t.footer.tagline}
            </span>
          </div>
          <p className="text-muted/20 text-[0.55rem] tracking-wider">
            &copy; {new Date().getFullYear()} {t.footer.rights}
          </p>
        </div>
      </footer>
    </>
  );
}
