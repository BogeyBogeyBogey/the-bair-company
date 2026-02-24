import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "The Bair Company — Creatief Digitaal Bureau",
  description:
    "Websites, apps, social media, marketing en workshops. Van idee tot impact — wij zijn jouw creatieve digitale partner.",
  keywords: [
    "website",
    "app",
    "social media",
    "marketing",
    "branding",
    "workshops",
    "digital agency",
    "creatief bureau",
    "België",
  ],
  openGraph: {
    title: "The Bair Company — Creatief Digitaal Bureau",
    description:
      "Websites, apps, social media, marketing en workshops. Van idee tot impact.",
    type: "website",
    locale: "nl_BE",
  },
  icons: {
    icon: "/logo-light.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="nl" className="dark">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
