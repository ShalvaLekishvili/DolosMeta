import type { Metadata } from "next";
import { AppShell, PageIntro } from "../components/app-shell";
import { Translated } from "../components/preferences";

export const metadata: Metadata = {
  title: "Privacy and file handling — DolosMeta",
  description: "Understand where DolosMeta analyzes files, how temporary uploads are retained, and which network actions it avoids.",
};

const boundaries = [
  ["No third-party analysis", "Uploaded files are not automatically forwarded to VirusTotal, cloud AI, geocoding, OCR, or external metadata services."],
  ["No automatic connections", "DolosMeta does not visit URLs, resolve domains, load remote email images, or request map tiles discovered in a file."],
  ["Temporary handling", "The DolosMeta server uses temporary upload storage or bounded in-memory processing and removes files after its configured retention window."],
  ["No active content", "Uploaded executables, macros, PDF JavaScript, launch actions, attachments, and embedded objects are inspected statically and never executed."],
];

export default function PrivacyPage() {
  return (
    <AppShell active="privacy">
      <PageIntro
        eyebrow={<Translated id="privacyEyebrow" />}
        title={<Translated id="privacyTitle" />}
        description={<Translated id="privacyDescription" />}
      />
      <section className="privacy-promise" aria-labelledby="privacy-promise-title">
        <span aria-hidden="true">◇</span>
        <div>
          <p className="section-kicker"><Translated id="defaultPosture" /></p>
          <h2 id="privacy-promise-title"><Translated id="analyzeSubmitted" /></h2>
          <p><Translated id="analyzeSubmittedCopy" /></p>
        </div>
      </section>
      <div className="privacy-grid">
        {boundaries.map(([title], index) => (
          <section className="panel" key={title}>
            <span className="info-number">0{index + 1}</span>
            <h2><Translated id={{"No third-party analysis":"noThirdParty","No automatic connections":"noConnections","Temporary handling":"temporaryHandling","No active content":"noActiveContent"}[title] ?? "noThirdParty"} /></h2>
            <p><Translated id={{"No third-party analysis":"noThirdPartyCopy","No automatic connections":"noConnectionsCopy","Temporary handling":"temporaryCopy","No active content":"noActiveCopy"}[title] ?? "noThirdPartyCopy"} /></p>
          </section>
        ))}
      </div>
      <section className="panel precise-language">
        <p className="section-kicker"><Translated id="preciseLanguage" /></p>
        <h2><Translated id="serverNotBrowser" /></h2>
        <p><Translated id="serverNotBrowserCopy" /></p>
      </section>
    </AppShell>
  );
}
