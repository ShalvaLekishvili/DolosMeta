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

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://127.0.0.1:3000"),
  title: {
    default: "DolosMeta — Universal File Metadata Analyzer",
    template: "%s",
  },
  description: "Inspect metadata, embedded information, file structure, privacy exposure, timestamps, and forensic indicators.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
  openGraph: {
    type: "website",
    title: "DolosMeta — See what your files reveal",
    description: "Inspect hidden metadata, timestamps, privacy exposure, and file structure with a native, local-first analysis engine.",
    images: [{ url: "/og.png", width: 1731, height: 909, alt: "DolosMeta — See what your files reveal" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "DolosMeta — See what your files reveal",
    description: "Inspect hidden metadata, timestamps, privacy exposure, and file structure with a native, local-first analysis engine.",
    images: ["/og.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <PreferencesProvider>
          {children}
          <EntrancePreloader />
        </PreferencesProvider>
      </body>
    </html>
  );
}
