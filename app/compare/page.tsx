import type { Metadata } from "next";
import { AppShell, PageIntro } from "../components/app-shell";
import { CompareWorkspace } from "../components/compare-workspace";
import { Translated } from "../components/preferences";

export const metadata: Metadata = {
  title: "Compare file metadata — DolosMeta",
  description: "Compare two files to identify added, removed, changed, and matching metadata fields.",
};

export default function ComparePage() {
  return (
    <AppShell active="compare" wide>
      <PageIntro
        eyebrow={<Translated id="compareEyebrow" />}
        title={<Translated id="compareTitle" />}
        description={<Translated id="compareDescription" />}
      />
      <CompareWorkspace />
    </AppShell>
  );
}
