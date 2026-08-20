import type { Metadata } from "next";
import { AppShell, PageIntro } from "../components/app-shell";
import { FormatRegistry } from "../components/format-registry";
import { Translated } from "../components/preferences";

export const metadata: Metadata = {
  title: "Supported formats — DolosMeta",
  description: "View the parsers and metadata capabilities reported by the active DolosMeta engine.",
};

export default function FormatsPage() {
  return (
    <AppShell active="formats" wide>
      <PageIntro
        eyebrow={<Translated id="formatsEyebrow" />}
        title={<Translated id="formatsTitle" />}
        description={<Translated id="formatsDescription" />}
      />
      <FormatRegistry />
    </AppShell>
  );
}
