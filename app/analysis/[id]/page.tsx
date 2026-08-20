import type { Metadata } from "next";
import { AppShell } from "../../components/app-shell";
import { AnalysisLoader } from "../../components/analyzer-workspace";

export const metadata: Metadata = {
  title: "Session analysis — DolosMeta",
  description: "A temporary DolosMeta analysis result.",
  robots: { index: false, follow: false },
  openGraph: {
    title: "Session analysis — DolosMeta",
    description: "A temporary DolosMeta analysis result.",
    images: [],
  },
  twitter: {
    card: "summary",
    title: "Session analysis — DolosMeta",
    description: "A temporary DolosMeta analysis result.",
    images: [],
  },
};

export default async function AnalysisPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <AppShell active="analyze" wide>
      <AnalysisLoader id={id} />
    </AppShell>
  );
}
