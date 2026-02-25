"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Image from "next/image";

/* ═══════════════════════════════════════════════════════════
   TYPES & DATA
   ═══════════════════════════════════════════════════════════ */

interface CollageImage {
  src: string;
  alt: string;
  w: number;
  h: number;
  className: string;
}

const HERO_IMAGES: CollageImage[] = [
  {
    src: "https://images.unsplash.com/photo-1558618666-fcd25c85f82e?w=600&q=80",
    alt: "Branding project",
    w: 600, h: 750,
    className: "col-img col-img-1",
  },
  {
    src: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=500&q=80",
    alt: "Digital dashboard",
    w: 500, h: 340,
    className: "col-img col-img-2",
  },
  {
    src: "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=450&q=80",
    alt: "Abstract art",
    w: 450, h: 600,
    className: "col-img col-img-3",
  },
  {
    src: "https://images.unsplash.com/photo-1555421689-d68471e189f2?w=550&q=80",
    alt: "Creative workspace",
    w: 550, h: 370,
    className: "col-img col-img-4",
  },
  {
    src: "https://images.unsplash.com/photo-1561070791-2526d30994b5?w=400&q=80",
    alt: "Typography design",
    w: 400, h: 530,
    className: "col-img col-img-5",
  },
  {
    src: "https://images.unsplash.com/photo-1542744094-3a31f272c490?w=480&q=80",
    alt: "Mobile app design",
    w: 480, h: 320,
    className: "col-img col-img-6",
  },
];

const PROJECTS = [
  {
    title: "GiGi Money",
    tag: "Fintech · Web App",
    src: "https://images.unsplash.com/photo-1563986768609-322da13575f2?w=800&q=80",
    color: "#6C5CE7",
  },
  {
    title: "Artoah",
    tag: "Branding · Website",
    src: "https://images.unsplash.com/photo-1500595046743-cd271d694d30?w=800&q=80",
    color: "#00B894",
  },
  {
    title: "Mooi Studio",
    tag: "E-commerce · Design",
    src: "https://images.unsplash.com/photo-1558591710-4b4a1ae0f04d?w=800&q=80",
    color: "#E17055",
  },
  {
    title: "Pulse Digital",
    tag: "SaaS · Dashboard",
    src: "https://images.unsplash.com/photo-1551650975-87deedd944c3?w=800&q=80",
    color: "#0984E3",
  },
];

const SERVICES = [
  { icon: "✦", title: "Websites", desc: "Visueel krachtige, razendsnelle websites die converteren." },
  { icon: "◈", title: "Apps", desc: "Mobiele en web apps die aanvoelen als magie." },
  { icon: "◉", title: "Branding", desc: "Merken bouwen die in het geheugen blijven hangen." },
  { icon: "◎", title: "Social Media", desc: "Content die stopt, raakt en aanzet tot actie." },
  { icon: "✧", title: "Marketing", desc: "Strategieën die groeien vanuit data en creativiteit." },
  { icon: "◇", title: "Workshops", desc: "Leer het zelf — of laat ons het samen doen." },
];

/* ═══════════════════════════════════════════════════════════
   HOOKS
   ═══════════════════════════════════════════════════════════ */

function useInView(threshold = 0.1) {
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

function useParallax() {
  const [scrollY, setScrollY] = useState(0);
  useEffect(() => {
    const handler = () => setScrollY(window.scrollY);
    window.addEventListener("scroll", handler, { passive: true });
    return () => window.removeEventListener("scroll", handler);
  }, []);
  return scrollY;
}

/* ═══════════════════════════════════════════════════════════
   INTRO LOADER
   ═══════════════════════════════════════════════════════════ */

function IntroLoader({ onDone }: { onDone: () => void }) {
  const [phase, setPhase] = useState<"loading" | "reveal" | "done">("loading");

  useEffect(() => {
    const t1 = setTimeout(() => setPhase("reveal"), 1200);
    const t2 = setTimeout(() => { setPhase("done"); onDone(); }, 2200);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [onDone]);

  if (phase === "done") return null;

  return (
    <div className={`intro-overlay ${phase === "reveal" ? "revealed" : ""}`}>
      <div className="intro-half intro-half--top" />
      <div className="intro-half intro-half--bottom" />
      <div className="intro-center">
        <div
          className="font-display text-3xl font-bold tracking-tight"
          style={{ opacity: phase === "loading" ? 1 : 0, transition: "opacity 0.4s ease" }}
        >
          THE BAIR COMPANY
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   NAVIGATION
   ═══════════════════════════════════════════════════════════ */

function Nav() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 60);
    window.addEventListener("scroll", handler, { passive: true });
    return () => window.removeEventListener("scroll", handler);
  }, []);

  const links = [
    { label: "Work", href: "#work" },
    { label: "Services", href: "#services" },
    { label: "About", href: "#about" },
    { label: "Contact", href: "#contact" },
  ];

  return (
    <>
      <header
        className={`fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 md:px-10 transition-all duration-500 ${
          scrolled ? "py-4 nav-bg-blur" : "py-6"
        }`}
      >
        <a href="#" className="font-display text-sm font-bold tracking-[0.2em] uppercase">
          TBC<span className="text-accent">.</span>
        </a>

        <button
          onClick={() => setOpen(!open)}
          className="w-10 h-10 flex flex-col items-center justify-center gap-[6px] group z-[90]"
          aria-label="Menu"
        >
          <span className={`block w-6 h-[1.5px] bg-foreground transition-all duration-300 ${open ? "rotate-45 translate-y-[3.75px]" : "group-hover:w-5"}`} />
          <span className={`block w-6 h-[1.5px] bg-foreground transition-all duration-300 ${open ? "-rotate-45 -translate-y-[3.75px]" : "group-hover:w-7"}`} />
        </button>
      </header>

      <div className={`fs-nav ${open ? "open" : ""}`}>
        <nav className="w-full px-8 md:px-16">
          {links.map((l, i) => (
            <a
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              className="fs-nav-link"
              style={{ transitionDelay: open ? `${i * 0.08}s` : "0s" }}
            >
              <span className="fs-nav-num">{String(i + 1).padStart(2, "0")}</span>
              {l.label}
            </a>
          ))}
          <div className="mt-12 flex gap-6 text-sm text-muted">
            <a href="mailto:hello@thebaircompany.com" className="hover:text-foreground transition-colors">hello@thebaircompany.com</a>
          </div>
        </nav>
      </div>
    </>
  );
}

/* ═══════════════════════════════════════════════════════════
   HERO — Scattered Image Collage
   ═══════════════════════════════════════════════════════════ */

function HeroCollage() {
  const scrollY = useParallax();

  return (
    <section className="relative min-h-screen overflow-hidden flex items-center justify-center">
      {/* Background grain */}
      <div className="noise" />

      {/* Scattered images with parallax */}
      <div className="collage-container">
        {HERO_IMAGES.map((img, i) => (
          <div
            key={i}
            className={img.className}
            style={{
              transform: `translateY(${scrollY * (0.03 + i * 0.015)}px)`,
            }}
          >
            <Image
              src={img.src}
              alt={img.alt}
              width={img.w}
              height={img.h}
              className="collage-img-inner"
              priority={i < 3}
            />
          </div>
        ))}
      </div>

      {/* Center text overlay */}
      <div className="relative z-10 text-center pointer-events-none hero-text-container">
        <p className="font-mono text-xs tracking-[0.3em] uppercase text-accent mb-6 opacity-80">
          Creatief Digitaal Bureau
        </p>
        <h1 className="font-display hero-title font-extrabold leading-[0.9] tracking-tight">
          <span className="block">The Bair</span>
          <span className="block text-stroke">Company</span>
        </h1>
        <p className="mt-8 text-base md:text-lg text-foreground/60 max-w-md mx-auto font-light leading-relaxed">
          Van idee tot impact — wij maken digitaal tastbaar.
        </p>
      </div>

      {/* Scroll indicator */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-10 flex flex-col items-center gap-2">
        <span className="text-[10px] tracking-[0.3em] uppercase text-muted">Scroll</span>
        <div className="w-[1px] h-8 bg-muted/30 relative overflow-hidden">
          <div className="absolute w-full h-1/2 bg-accent animate-scroll-line" />
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════
   WORK / PROJECTS — Asymmetric Grid
   ═══════════════════════════════════════════════════════════ */

function WorkSection() {
  const { ref, visible } = useInView(0.05);

  return (
    <section id="work" ref={ref} className="py-32 md:py-48 px-6 md:px-10">
      <div className="max-w-7xl mx-auto">
        <div className={`mb-20 transition-all duration-1000 ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
          <span className="font-mono text-xs tracking-[0.3em] uppercase text-accent">
            Selected Work
          </span>
          <h2 className="font-display text-5xl md:text-7xl font-bold mt-4 leading-[1.05]">
            Projecten die<br />
            <span className="font-serif italic font-normal">het verschil</span> maken
          </h2>
        </div>

        <div className="project-grid">
          {PROJECTS.map((p, i) => (
            <div
              key={p.title}
              className={`project-card group transition-all duration-700 ${
                visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-12"
              }`}
              style={{ transitionDelay: `${i * 150}ms` }}
            >
              <div className="project-card-img">
                <Image
                  src={p.src}
                  alt={p.title}
                  width={800}
                  height={600}
                  className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                />
                <div
                  className="absolute inset-0 opacity-0 group-hover:opacity-30 transition-opacity duration-500"
                  style={{ background: p.color }}
                />
              </div>
              <div className="mt-5 flex items-start justify-between">
                <div>
                  <h3 className="font-display text-xl font-bold">{p.title}</h3>
                  <p className="text-sm text-muted mt-1">{p.tag}</p>
                </div>
                <span className="text-muted group-hover:text-accent group-hover:translate-x-1 transition-all duration-300 mt-1">→</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════
   MARQUEE STRIP
   ═══════════════════════════════════════════════════════════ */

function MarqueeStrip() {
  const items = ["Websites", "◈", "Apps", "◈", "Branding", "◈", "Social Media", "◈", "Marketing", "◈", "Workshops", "◈"];
  const track = [...items, ...items, ...items];

  return (
    <div className="marquee-wrap border-y border-border py-5 overflow-hidden">
      <div className="marquee-track">
        {track.map((t, i) => (
          <span key={i} className="font-display text-2xl md:text-4xl font-bold mx-6 md:mx-10 whitespace-nowrap text-foreground/10 hover:text-foreground/40 transition-colors duration-500">
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   SERVICES — Clean minimal list
   ═══════════════════════════════════════════════════════════ */

function ServicesSection() {
  const { ref, visible } = useInView(0.05);

  return (
    <section id="services" ref={ref} className="py-32 md:py-48 px-6 md:px-10">
      <div className="max-w-5xl mx-auto">
        <div className={`mb-16 transition-all duration-1000 ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
          <span className="font-mono text-xs tracking-[0.3em] uppercase text-accent">
            Diensten
          </span>
          <h2 className="font-display text-5xl md:text-7xl font-bold mt-4 leading-[1.05]">
            Wat wij<br />
            <span className="font-serif italic font-normal">voor je</span> doen
          </h2>
        </div>

        <div>
          {SERVICES.map((s, i) => (
            <div
              key={s.title}
              className={`service-row transition-all duration-700 ${
                visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"
              }`}
              style={{ transitionDelay: `${i * 100}ms` }}
            >
              <span className="sr-num">{s.icon}</span>
              <span className="sr-title">{s.title}</span>
              <span className="sr-desc">{s.desc}</span>
              <span className="sr-arrow">→</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════
   IMAGE BAND — Full-width scattered strip
   ═══════════════════════════════════════════════════════════ */

function ImageBand() {
  const scrollY = useParallax();

  const images = [
    "https://images.unsplash.com/photo-1559028012-481c04fa702d?w=500&q=80",
    "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=500&q=80",
    "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=500&q=80",
    "https://images.unsplash.com/photo-1509395176047-4a66953fd231?w=500&q=80",
    "https://images.unsplash.com/photo-1535303311164-664fc9ec6532?w=500&q=80",
  ];

  return (
    <div className="relative py-16 overflow-hidden">
      <div className="flex gap-6 md:gap-8 image-band" style={{ transform: `translateX(${-scrollY * 0.1}px)` }}>
        {[...images, ...images].map((src, i) => (
          <div key={i} className={`flex-none w-48 md:w-72 ${i % 2 === 0 ? "-mt-8" : "mt-8"}`}>
            <div className="relative overflow-hidden rounded-lg aspect-[4/5]">
              <Image
                src={src}
                alt="Creative work"
                fill
                className="object-cover hover:scale-110 transition-transform duration-700"
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   ABOUT
   ═══════════════════════════════════════════════════════════ */

function AboutSection() {
  const { ref, visible } = useInView(0.1);

  return (
    <section id="about" ref={ref} className="py-32 md:py-48 px-6 md:px-10">
      <div className="max-w-6xl mx-auto grid md:grid-cols-2 gap-16 md:gap-24 items-center">
        <div className={`transition-all duration-1000 ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
          <span className="font-mono text-xs tracking-[0.3em] uppercase text-accent">Over ons</span>
          <h2 className="font-display text-4xl md:text-6xl font-bold mt-4 mb-8 leading-[1.1]">
            Creatief<br />
            <span className="font-serif italic font-normal">zonder grenzen</span>
          </h2>
          <div className="space-y-5 text-foreground/60 leading-relaxed">
            <p>
              The Bair Company is een creatief digitaal bureau dat merken helpt groeien
              door middel van design, technologie en strategie. Wij geloven dat de mooiste
              resultaten ontstaan wanneer creativiteit geen grenzen kent.
            </p>
            <p>
              Van branding tot code, van social media tot workshops — wij combineren al
              onze skills onder één dak. Geen gedoe met tien verschillende bureaus. Eén team,
              één visie, onbeperkte mogelijkheden.
            </p>
          </div>
          <div className="mt-10 flex gap-12">
            <div>
              <span className="font-display text-4xl font-bold text-accent">50+</span>
              <p className="text-sm text-muted mt-1">Projecten</p>
            </div>
            <div>
              <span className="font-display text-4xl font-bold text-accent">100%</span>
              <p className="text-sm text-muted mt-1">Passie</p>
            </div>
            <div>
              <span className="font-display text-4xl font-bold text-accent">∞</span>
              <p className="text-sm text-muted mt-1">Creativiteit</p>
            </div>
          </div>
        </div>

        <div className={`relative transition-all duration-1000 delay-200 ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-12"}`}>
          <div className="about-img-collage">
            <div className="about-img-1">
              <Image
                src="https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=600&q=80"
                alt="Team collaboration"
                width={600}
                height={400}
                className="rounded-lg object-cover w-full"
              />
            </div>
            <div className="about-img-2">
              <Image
                src="https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=400&q=80"
                alt="Creative coding"
                width={400}
                height={300}
                className="rounded-lg object-cover w-full"
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════
   CONTACT
   ═══════════════════════════════════════════════════════════ */

function ContactSection() {
  const { ref, visible } = useInView(0.1);

  return (
    <section id="contact" ref={ref} className="py-32 md:py-48 px-6 md:px-10 relative">
      <div className="max-w-4xl mx-auto text-center">
        <div className={`transition-all duration-1000 ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
          <span className="font-mono text-xs tracking-[0.3em] uppercase text-accent">
            Contact
          </span>
          <h2 className="font-display text-5xl md:text-8xl font-bold mt-6 mb-6 leading-[1]">
            Laten we<br />
            <span className="font-serif italic font-normal">iets moois</span><br />
            maken.
          </h2>
          <p className="text-foreground/50 text-lg mb-12 max-w-lg mx-auto">
            Klaar om jouw merk naar het volgende niveau te tillen?
            Stuur ons een bericht.
          </p>
          <a
            href="mailto:hello@thebaircompany.com"
            className="mag-btn inline-flex items-center gap-3 border border-foreground/20 rounded-full px-10 py-4 text-lg font-display font-bold hover:border-accent transition-colors duration-500"
          >
            <span>hello@thebaircompany.com</span>
          </a>

          <div className="mt-16 flex justify-center gap-10 text-sm text-muted">
            <a href="#" className="hover:text-foreground transition-colors">Instagram</a>
            <a href="#" className="hover:text-foreground transition-colors">LinkedIn</a>
            <a href="#" className="hover:text-foreground transition-colors">Behance</a>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════
   FOOTER
   ═══════════════════════════════════════════════════════════ */

function Footer() {
  return (
    <footer className="border-t border-border px-6 md:px-10 py-8">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-muted">
        <span className="font-display font-bold tracking-[0.15em]">
          TBC<span className="text-accent">.</span>
        </span>
        <span>© {new Date().getFullYear()} The Bair Company. Alle rechten voorbehouden.</span>
      </div>
    </footer>
  );
}

/* ═══════════════════════════════════════════════════════════
   HOME
   ═══════════════════════════════════════════════════════════ */

export default function Home() {
  const [loaded, setLoaded] = useState(false);
  const handleDone = useCallback(() => setLoaded(true), []);

  return (
    <>
      <IntroLoader onDone={handleDone} />
      <div className={`transition-opacity duration-1000 ${loaded ? "opacity-100" : "opacity-0"}`}>
        <Nav />
        <main>
          <HeroCollage />
          <MarqueeStrip />
          <WorkSection />
          <ImageBand />
          <ServicesSection />
          <AboutSection />
          <ContactSection />
        </main>
        <Footer />
        <div className="noise" />
      </div>
    </>
  );
}
