"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePreferences } from "./preferences";

type ActivePage = "analyze" | "batch" | "compare" | "formats" | "engine" | "privacy";

const primaryLinks: Array<{ href: string; label: string; id: ActivePage }> = [
  { href: "/", label: "Analyze", id: "analyze" },
  { href: "/batch", label: "Batch", id: "batch" },
  { href: "/compare", label: "Compare", id: "compare" },
];

const referenceLinks: Array<{ href: string; label: string; id: ActivePage }> = [
  { href: "/formats", label: "Formats", id: "formats" },
  { href: "/engine", label: "Engine", id: "engine" },
  { href: "/privacy", label: "Privacy", id: "privacy" },
];

function NavLink({
  href,
  label,
  active,
}: {
  href: string;
  label: string;
  active: boolean;
}) {
  return (
    <Link href={href} aria-current={active ? "page" : undefined}>
      {label}
    </Link>
  );
}

export function AppShell({
  active,
  children,
  wide = false,
}: {
  active: ActivePage;
  children: ReactNode;
  wide?: boolean;
}) {
  const { language, theme, setLanguage, setTheme, t } = usePreferences();
  const localizedPrimaryLinks = primaryLinks.map((link) => ({ ...link, label: t(link.id) }));
  const localizedReferenceLinks = referenceLinks.map((link) => ({ ...link, label: t(link.id) }));
  return (
    <div className="site-shell">
      <a className="skip-link" href="#main-content">{t("skipToMain")}</a>
      <header className="topbar">
        <Link className="brand" href="/" aria-label={t("home")}>
          <span className="brand-mark" aria-hidden="true">D</span>
          <span>DolosMeta</span>
        </Link>

        <nav className="mode-nav desktop-nav" aria-label={t("analysisModes")}>
          {localizedPrimaryLinks.map((link) => (
            <NavLink key={link.id} {...link} active={active === link.id} />
          ))}
        </nav>

        <div className="topbar-end">
          <nav className="reference-nav desktop-nav" aria-label={t("productInformation")}>
            {localizedReferenceLinks.map((link) => (
              <NavLink key={link.id} {...link} active={active === link.id} />
            ))}
          </nav>
          <span className="local-badge"><i aria-hidden="true" /> {t("localFirst")}</span>
          <div className="preference-controls">
            <label>
              <span className="sr-only">{t("language")}</span>
              <select value={language} onChange={(event) => setLanguage(event.target.value as typeof language)} aria-label={t("language")}>
                <option value="en">EN</option>
                <option value="ka">ქართული</option>
                <option value="ru">Русский</option>
              </select>
            </label>
            <label>
              <span className="sr-only">{t("theme")}</span>
              <select value={theme} onChange={(event) => setTheme(event.target.value as typeof theme)} aria-label={t("theme")}>
                <option value="dark">{t("dark")}</option>
                <option value="light">{t("light")}</option>
                <option value="contrast">{t("contrast")}</option>
              </select>
            </label>
          </div>
          <details className="mobile-menu">
            <summary aria-label={t("menu")}>{t("menu")}</summary>
            <nav aria-label={t("mobileNavigation")}>
              {[...localizedPrimaryLinks, ...localizedReferenceLinks].map((link) => (
                <NavLink key={link.id} {...link} active={active === link.id} />
              ))}
            </nav>
          </details>
        </div>
      </header>
      <main id="main-content" className={wide ? "page-main page-main-wide" : "page-main"}>
        {children}
      </main>
      <footer className="site-footer">
        <span>DolosMeta</span>
        <p>{t("footerNote")}</p>
        <Link href="/privacy">{t("handled")}</Link>
      </footer>
    </div>
  );
}

export function PageIntro({
  eyebrow,
  title,
  description,
}: {
  eyebrow: ReactNode;
  title: ReactNode;
  description: ReactNode;
}) {
  return (
    <header className="page-intro">
      <p className="eyebrow"><span aria-hidden="true" /> {eyebrow}</p>
      <h1>{title}</h1>
      <p>{description}</p>
    </header>
  );
}
