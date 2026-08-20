import type { Metadata } from "next";
import { AppShell, PageIntro } from "../components/app-shell";
import { Translated } from "../components/preferences";

export const metadata: Metadata = {
  title: "Metadata engine — DolosMeta",
  description: "Learn how DolosMeta identifies files and inspects their structures without the ExifTool executable.",
};

const stages = [
  ["01", "stageIdentify", "stageIdentifyCopy"],
  ["02", "stageInspect", "stageInspectCopy"],
  ["03", "stageParse", "stageParseCopy"],
  ["04", "stageNormalize", "stageNormalizeCopy"],
  ["05", "stageAnalyze", "stageAnalyzeCopy"],
  ["06", "stagePresent", "stagePresentCopy"],
];

export default function EnginePage() {
  return (
    <AppShell active="engine">
      <PageIntro
        eyebrow={<Translated id="engineEyebrow" />}
        title={<Translated id="engineTitle" />}
        description={<Translated id="engineDescription" />}
      />
      <section className="engine-flow" aria-labelledby="engine-flow-title">
        <div className="panel-heading">
          <div><p className="section-kicker"><Translated id="analysisPath" /></p><h2 id="engine-flow-title"><Translated id="analysisPathTitle" /></h2></div>
        </div>
        <ol>
          {stages.map(([number, title, description]) => (
            <li key={number}>
              <span>{number}</span>
              <div><h3><Translated id={title} /></h3><p><Translated id={description} /></p></div>
            </li>
          ))}
        </ol>
      </section>
      <div className="info-grid">
        <section className="panel">
          <p className="section-kicker"><Translated id="boundedDefault" /></p>
          <h2><Translated id="boundedTitle" /></h2>
          <p><Translated id="untrustedCopy" /></p>
        </section>
        <section className="panel">
          <p className="section-kicker"><Translated id="evidenceAware" /></p>
          <h2><Translated id="evidenceTitle" /></h2>
          <p><Translated id="evidenceAwareCopy" /></p>
        </section>
        <section className="panel">
          <p className="section-kicker"><Translated id="extensibleRegistry" /></p>
          <h2><Translated id="independentTitle" /></h2>
          <p><Translated id="parsersCopy" /></p>
          <a className="text-link" href="/formats"><Translated id="registryLink" /></a>
        </section>
      </div>
    </AppShell>
  );
}
