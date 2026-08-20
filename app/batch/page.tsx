import type { Metadata } from "next";
import { AppShell, PageIntro } from "../components/app-shell";
import { BatchWorkspace } from "../components/batch-workspace";
import { Translated } from "../components/preferences";

export const metadata: Metadata = {
  title: "Batch analysis — DolosMeta",
  description: "Analyze multiple files and review metadata, location exposure, warnings, and fingerprints together.",
};

export default function BatchPage() {
  return (
    <AppShell active="batch" wide>
      <PageIntro
        eyebrow={<Translated id="batchEyebrow" />}
        title={<Translated id="batchTitle" />}
        description={<Translated id="batchDescription" />}
      />
      <BatchWorkspace />
    </AppShell>
  );
}
