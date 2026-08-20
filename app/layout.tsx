import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { EntrancePreloader } from "./components/entrance-preloader";
import { PreferencesProvider } from "./components/preferences";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL ??
  process.env.DEPLOY_PRIME_URL ??
  process.env.URL ??
  "http://127.0.0.1:3000";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "DolosMeta — Universal File Metadata Analyzer",
    template: "%s",
  },
  description:
    "Inspect metadata, embedded information, file structure, privacy exposure, timestamps, and forensic indicators.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
  openGraph: {
    type: "website",
    title: "DolosMeta — See what your files reveal",
    description:
      "Inspect hidden metadata, timestamps, privacy exposure, and file structure with a native, local-first analysis engine.",
  },
  twitter: {
    card: "summary",
    title: "DolosMeta — See what your files reveal",
    description:
      "Inspect hidden metadata, timestamps, privacy exposure, and file structure with a native, local-first analysis engine.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <PreferencesProvider>
          {children}
          <EntrancePreloader />
        </PreferencesProvider>
      </body>
    </html>
  );
}
