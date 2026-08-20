import type { Metadata } from "next";
import { AnalyzerWorkspace } from "./components/analyzer-workspace";
import { AppShell } from "./components/app-shell";

export const metadata: Metadata = {
  title: "DolosMeta — Universal File Metadata Analyzer",
  description:
    "Inspect hidden metadata, file structure, privacy exposure, and forensic indicators without third-party analysis services.",
};

export default function Home() {
  return (
    <AppShell active="analyze" wide>
      <AnalyzerWorkspace />
    </AppShell>
  );
}
