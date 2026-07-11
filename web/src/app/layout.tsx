import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Header from "../components/Header";
import Footer from "../components/Footer";
import CommandPalette from "../components/CommandPalette";
import OnboardingHint from "../components/OnboardingHint";

/**
 * Geist Sans — primary UI typeface.
 * Exposed as the --font-geist-sans CSS variable, consumed in globals.css.
 */
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

/**
 * Geist Mono — monospace typeface for script names, paths, code.
 * Exposed as the --font-geist-mono CSS variable, consumed in globals.css.
 */
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "PyScripts — Python CLI Scripts Library",
    template: "%s | PyScripts",
  },
  description:
    "A curated library of high-quality, fully-tested Python CLI scripts for automation, system tools, data processing, and more.",
  keywords: ["python", "cli", "scripts", "automation", "tools", "open source"],
  openGraph: {
    title: "PyScripts — Python CLI Scripts Library",
    description:
      "A curated library of high-quality, fully-tested Python CLI scripts.",
    url: "https://github.com/WantedChip/python-scripts",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable}`}
    >
      <body
        style={{
          display: "flex",
          flexDirection: "column",
          minHeight: "100vh",
        }}
      >
        <Header />
        <main style={{ flex: 1 }}>{children}</main>
        <Footer />
        <CommandPalette />
        <OnboardingHint />
      </body>
    </html>
  );
}
