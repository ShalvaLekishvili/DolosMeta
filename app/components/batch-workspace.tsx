"use client";

import { useMemo, useRef, useState } from "react";
import { analyzeBatch } from "../lib/api";
import { copyText, exportBatch } from "../lib/export";
import {
  findingsFrom,
  flattenMetadata,
  formatBytes,
  getFileFormat,
  getPrivacyLevel,
} from "../lib/format";
import type { AnalysisResult, BatchItem } from "../lib/types";
import { FileDropzone } from "./file-dropzone";
import { ResultDashboard } from "./result-dashboard";
import { usePreferences } from "./preferences";

function makeKey(file: File): string {
  return [file.name, file.size, file.lastModified].join(":");
}

function BatchTable({
  results,
  onOpen,
}: {
  results: AnalysisResult[];
  onOpen: (result: AnalysisResult) => void;
}) {
  const { t } = usePreferences();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "warnings" | "gps" | "high">("all");
  const [announcement, setAnnouncement] = useState("");
  const visible = results.filter((result) => {
    const matchesQuery = String(result.file?.name ?? "").toLowerCase().includes(query.toLowerCase());
    const entries = flattenMetadata(result);
    const matchesFilter =
      filter === "all" ||
      (filter === "warnings" && findingsFrom(result).length > 0) ||
      (filter === "gps" && entries.some((entry) => entry.category === "location")) ||
      (filter === "high" && getPrivacyLevel(result).toLowerCase().includes("high"));
    return matchesQuery && matchesFilter;
  });

  return (
    <section className="panel batch-results" aria-labelledby="batch-results-title">
      <div className="panel-heading">
        <div><p className="section-kicker">Cross-file review</p><h2 id="batch-results-title">{t("batchResults")}</h2></div>
        <div className="inline-actions">
          <button className="button button-secondary" type="button" onClick={() => exportBatch(results, "csv")}>Export CSV</button>
          <button className="button button-secondary" type="button" onClick={() => exportBatch(results, "json")}>Export JSON</button>
        </div>
      </div>
      <div className="batch-tools">
        <label className="search-field">
          <span className="sr-only">Search files</span><i aria-hidden="true">⌕</i>
          <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("searchFilenames")} />
        </label>
        <label className="select-field">
          <span>Show</span>
          <select value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)}>
            <option value="all">{t("allFiles")}</option>
            <option value="warnings">{t("withFindings")}</option>
            <option value="gps">{t("withLocation")}</option>
            <option value="high">{t("highPrivacy")}</option>
          </select>
        </label>
      </div>
      <div className="batch-table-wrap">
        <table className="batch-table">
          <thead><tr><th>Filename</th><th>Type / size</th><th>Fields</th><th>GPS</th><th>Privacy</th><th>Findings</th><th>SHA-256</th><th><span className="sr-only">Open</span></th></tr></thead>
          <tbody>
            {visible.map((result, index) => {
              const entries = flattenMetadata(result);
              const hasGps = entries.some((entry) => entry.category === "location");
              const hash = result.hashes?.sha256 ?? result.hashes?.["SHA-256"] ?? "";
              return (
                <tr key={String(result.id ?? result.analysis_id ?? result.file?.name ?? index)}>
                  <th scope="row">{String(result.file?.name ?? "Unknown")}</th>
                  <td><strong>{getFileFormat(result)}</strong><small>{formatBytes(result.file?.size)}</small></td>
                  <td>{entries.length}</td>
                  <td><span className={"status-label " + (hasGps ? "tone-warning" : "")}>{hasGps ? "Detected" : "No"}</span></td>
                  <td><span className={"status-label tone-" + getPrivacyLevel(result).toLowerCase()}>{getPrivacyLevel(result)}</span></td>
                  <td>{findingsFrom(result).length}</td>
                  <td>
                    {hash ? (
                      <button
                        className="hash-copy"
                        type="button"
                        title={hash}
                        onClick={() => copyText(hash).then(() => setAnnouncement("SHA-256 copied"))}
                      >
                        <code>{hash.slice(0, 12)}…</code>
                      </button>
                    ) : "—"}
                  </td>
                  <td><button className="text-button" type="button" onClick={() => onOpen(result)}>{t("inspect")}</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!visible.length && <p className="empty-copy">{t("noMatch")}</p>}
      <p className="sr-only" aria-live="polite">{announcement}</p>
    </section>
  );
}

export function BatchWorkspace() {
  const { t } = usePreferences();
  const [items, setItems] = useState<BatchItem[]>([]);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [openResult, setOpenResult] = useState<AnalysisResult>();
  const controller = useRef<AbortController | null>(null);
  const completeResults = items.flatMap((item) => (item.result ? [item.result] : []));
  const queued = items.filter((item) => item.status === "queued" || item.status === "error");

  const aggregate = useMemo(() => {
    const totalSize = completeResults.reduce((sum, result) => sum + (result.file?.size ?? 0), 0);
    const gps = completeResults.filter((result) => flattenMetadata(result).some((entry) => entry.category === "location")).length;
    const warnings = completeResults.reduce((sum, result) => sum + findingsFrom(result).length, 0);
    const high = completeResults.filter((result) => getPrivacyLevel(result).toLowerCase().includes("high")).length;
    return { totalSize, gps, warnings, high };
  }, [completeResults]);

  function addFiles(files: File[]) {
    setError("");
    setItems((current) => {
      const known = new Set(current.map((item) => item.key));
      return [
        ...current,
        ...files
          .filter((file) => !known.has(makeKey(file)))
          .map((file) => ({ key: makeKey(file), file, status: "queued" as const })),
      ];
    });
  }

  async function runBatch() {
    if (!queued.length) return;
    const current = new AbortController();
    controller.current = current;
    const keys = new Set(queued.map((item) => item.key));
    setWorking(true);
    setError("");
    setItems((all) => all.map((item) => keys.has(item.key) ? { ...item, status: "analyzing", error: undefined } : item));
    try {
      const results = await analyzeBatch(queued.map((item) => item.file), current.signal);
      setItems((all) =>
        all.map((item) => {
          const position = queued.findIndex((queuedItem) => queuedItem.key === item.key);
          if (position < 0) return item;
          const result = results[position];
          return result
            ? { ...item, status: "complete", result, error: undefined }
            : { ...item, status: "error", error: "No result was returned for this file." };
        }),
      );
    } catch (caught) {
      if ((caught as Error).name === "AbortError") {
        setItems((all) => all.map((item) => keys.has(item.key) ? { ...item, status: "queued" } : item));
      } else {
        const message = caught instanceof Error ? caught.message : "The batch could not be analyzed.";
        setError(message);
        setItems((all) => all.map((item) => keys.has(item.key) ? { ...item, status: "error", error: message } : item));
      }
    } finally {
      setWorking(false);
    }
  }

  if (openResult) return <ResultDashboard result={openResult} onReset={() => setOpenResult(undefined)} />;

  return (
    <div className="workspace-stack">
      <FileDropzone
        id="batch-files"
        multiple
        compact={items.length > 0}
        disabled={working}
        title={items.length ? t("addMoreFiles") : t("dropFiles")}
        description={items.length ? "Duplicates stay out of the queue" : t("chooseMultiple")}
        onFiles={addFiles}
      />

      {items.length > 0 && (
        <section className="panel queue-panel" aria-labelledby="queue-title">
          <div className="panel-heading">
            <div><p className="section-kicker">{t("uploadQueue")}</p><h2 id="queue-title">{items.length} {t("files")}</h2></div>
            <div className="inline-actions">
              <button className="button button-quiet" type="button" disabled={working} onClick={() => setItems([])}>{t("clear")}</button>
              <button className="button button-primary" type="button" disabled={working || !queued.length} onClick={() => void runBatch()}>
                {t("analyzeQueued")} {queued.length || ""} {t("files")}
              </button>
            </div>
          </div>
          <ul className="queue-list">
            {items.map((item) => (
              <li key={item.key}>
                <span className={"queue-state is-" + item.status} aria-hidden="true" />
                <div><strong>{item.file.name}</strong><small>{formatBytes(item.file.size)}</small>{item.error && <p>{item.error}</p>}</div>
                <span>{item.status}</span>
                {!working && item.status !== "complete" && (
                  <button className="icon-button" type="button" onClick={() => setItems((all) => all.filter((candidate) => candidate.key !== item.key))} aria-label={"Remove " + item.file.name}>×</button>
                )}
              </li>
            ))}
          </ul>
          {working && (
            <div className="batch-progress" role="status">
              <span className="mini-spinner" aria-hidden="true" />
              The server is analyzing this batch. Per-file results appear only after the API confirms them.
              <button type="button" onClick={() => controller.current?.abort()}>Cancel</button>
            </div>
          )}
          {error && <p className="inline-error" role="alert">{error}</p>}
        </section>
      )}

      {completeResults.length > 0 && (
        <>
          <section className="summary-grid batch-summary" aria-label="Batch summary">
            <div className="summary-card"><span>Analyzed</span><strong>{completeResults.length}</strong></div>
            <div className="summary-card"><span>Total size</span><strong>{formatBytes(aggregate.totalSize)}</strong></div>
            <div className={"summary-card " + (aggregate.gps ? "tone-warning" : "")}><span>Location</span><strong>{aggregate.gps} files</strong></div>
            <div className={"summary-card " + (aggregate.warnings ? "tone-warning" : "")}><span>Findings</span><strong>{aggregate.warnings}</strong></div>
            <div className={"summary-card " + (aggregate.high ? "tone-danger" : "")}><span>High exposure</span><strong>{aggregate.high}</strong></div>
          </section>
          <BatchTable results={completeResults} onOpen={setOpenResult} />
        </>
      )}
    </div>
  );
}
