"use client";

import { useEffect, useState } from "react";
import { getParsers } from "../lib/api";
import { asArray } from "../lib/format";
import type { ParserCapability } from "../lib/types";
import { usePreferences } from "./preferences";

function capabilityValue(value: unknown): string {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" && value.trim()) return value;
  return "Not reported";
}

export function FormatRegistry() {
  const { t } = usePreferences();
  const [parsers, setParsers] = useState<ParserCapability[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");

  function load() {
    const controller = new AbortController();
    setState("loading");
    setError("");
    getParsers(controller.signal)
      .then((available) => {
        setParsers(available);
        setState("ready");
      })
      .catch((caught: unknown) => {
        if ((caught as Error).name === "AbortError") return;
        setError(caught instanceof Error ? caught.message : "The parser registry is unavailable.");
        setState("error");
      });
    return controller;
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    const controller = load();
    return () => controller.abort();
  }, []);

  if (state === "loading") {
    return <div className="registry-status" role="status"><span className="mini-spinner" aria-hidden="true" /> {t("readingRegistry")}</div>;
  }
  if (state === "error") {
    return (
      <div className="registry-status registry-error" role="alert">
        <div><strong>{t("registryUnavailable")}</strong><p>{error} {t("startApi")}</p></div>
        <button className="button button-secondary" type="button" onClick={load}>{t("tryAgain")}</button>
      </div>
    );
  }
  if (!parsers.length) {
    return <p className="registry-status">{t("emptyRegistry")}</p>;
  }

  return (
    <section className="panel format-registry" aria-labelledby="registry-title">
      <div className="panel-heading">
        <div><p className="section-kicker">{t("capabilityRegistry")}</p><h2 id="registry-title">{t("activeParsers")}</h2></div>
        <span>{parsers.length} {t("registered")}</span>
      </div>
      <div className="format-table-wrap">
        <table className="format-table">
          <thead><tr><th>{t("parser")}</th><th>{t("formats")}</th><th>{t("extensions")}</th><th>{t("metadataExplorer")}</th><th>{t("structure")}</th><th>{t("privacy")}</th><th>{t("version")}</th></tr></thead>
          <tbody>
            {parsers.map((parser, index) => {
              const parserName = String(parser.name ?? parser.parser ?? parser.format ?? "Registered parser");
              const formats = asArray<string>(parser.formats);
              const extensions = asArray<string>(parser.extensions);
              return (
                <tr key={parserName + index}>
                  <th scope="row">{parserName}</th>
                  <td>{formats.length ? formats.join(", ") : String(parser.format ?? "—")}</td>
                  <td><code>{extensions.length ? extensions.join(" ") : "—"}</code></td>
                  <td>{capabilityValue(parser.metadata)}</td>
                  <td>{capabilityValue(parser.structure)}</td>
                  <td>{capabilityValue(parser.privacy)}</td>
                  <td>{String(parser.version ?? "—")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="evidence-note">{t("tableEvidence")}</p>
    </section>
  );
}
