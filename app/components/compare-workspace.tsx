"use client";

import { useMemo, useRef, useState } from "react";
import { compareFiles } from "../lib/api";
import { compareResults, formatBytes, getFileFormat } from "../lib/format";
import type { AnalysisResult, CompareRow } from "../lib/types";
import { AnalysisProgress, FileDropzone } from "./file-dropzone";
import { ResultDashboard } from "./result-dashboard";
import { usePreferences } from "./preferences";

function CompareFileCard({
  label,
  file,
  onFile,
  disabled,
}: {
  label: string;
  file?: File;
  onFile: (file: File) => void;
  disabled: boolean;
}) {
  const { t } = usePreferences();
  return (
    <section className="compare-file">
      <p className="section-kicker">{label}</p>
      <FileDropzone
        id={"compare-" + label.toLowerCase().replace(" ", "-")}
        compact
        disabled={disabled}
        title={file ? t("replace") + " " + file.name : t("chooseFile") + " " + label}
        description={file ? formatBytes(file.size) : t("dropOrChoose")}
        onFiles={(files) => files[0] && onFile(files[0])}
      />
    </section>
  );
}

function CompareTable({
  rows,
  resultA,
  resultB,
  onInspect,
}: {
  rows: CompareRow[];
  resultA: AnalysisResult;
  resultB: AnalysisResult;
  onInspect: (result: AnalysisResult) => void;
}) {
  const { t } = usePreferences();
  const [enabled, setEnabled] = useState<Record<CompareRow["status"], boolean>>({
    added: true,
    removed: true,
    changed: true,
    same: false,
  });
  const [query, setQuery] = useState("");
  const visible = rows.filter((row) => enabled[row.status] && (
    !query ||
    row.path.toLowerCase().includes(query.toLowerCase()) ||
    row.displayA.toLowerCase().includes(query.toLowerCase()) ||
    row.displayB.toLowerCase().includes(query.toLowerCase())
  ));
  const counts = rows.reduce<Record<CompareRow["status"], number>>(
    (all, row) => ({ ...all, [row.status]: all[row.status] + 1 }),
    { added: 0, removed: 0, changed: 0, same: 0 },
  );

  return (
    <section className="panel compare-results" aria-labelledby="comparison-title">
      <div className="compare-identities">
        {[["File A", resultA], ["File B", resultB]].map(([label, result]) => {
          const analysis = result as AnalysisResult;
          return (
            <div key={String(label)}>
              <span>{String(label)}</span>
              <strong>{String(analysis.file?.name ?? "Unknown")}</strong>
              <small>{getFileFormat(analysis)} · {formatBytes(analysis.file?.size)}</small>
              <button className="text-button" type="button" onClick={() => onInspect(analysis)}>{t("inspectFull")}</button>
            </div>
          );
        })}
      </div>
      <div className="panel-heading">
        <div><p className="section-kicker">{t("fieldDifference")}</p><h2 id="comparison-title">{t("metadataComparison")}</h2></div>
        <span>{visible.length} shown</span>
      </div>
      <div className="compare-tools">
        <label className="search-field">
          <span className="sr-only">Search comparison</span><i aria-hidden="true">⌕</i>
          <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("searchCompared")} />
        </label>
        <fieldset className="diff-filters">
          <legend className="sr-only">Difference types</legend>
          {(Object.keys(enabled) as Array<CompareRow["status"]>).map((status) => (
            <label key={status}>
              <input
                type="checkbox"
                checked={enabled[status]}
                onChange={(event) => setEnabled((current) => ({ ...current, [status]: event.target.checked }))}
              />
              <span className={"diff-status is-" + status}>{status}</span>
              <small>{counts[status]}</small>
            </label>
          ))}
        </fieldset>
      </div>
      {visible.length ? (
        <div className="compare-table-wrap">
          <table className="compare-table">
            <thead><tr><th>Field</th><th>{String(resultA.file?.name ?? "File A")}</th><th>{String(resultB.file?.name ?? "File B")}</th><th>Status</th></tr></thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.path}>
                  <th scope="row"><strong>{row.label}</strong><code>{row.path}</code></th>
                  <td>{row.displayA}</td>
                  <td>{row.displayB}</td>
                  <td><span className={"diff-status is-" + row.status}>{row.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="empty-copy">{t("noDifferenceMatch")}</p>
      )}
    </section>
  );
}

export function CompareWorkspace() {
  const { t } = usePreferences();
  const [fileA, setFileA] = useState<File>();
  const [fileB, setFileB] = useState<File>();
  const [resultA, setResultA] = useState<AnalysisResult>();
  const [resultB, setResultB] = useState<AnalysisResult>();
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [inspection, setInspection] = useState<AnalysisResult>();
  const controller = useRef<AbortController | null>(null);
  const rows = useMemo(() => resultA && resultB ? compareResults(resultA, resultB) : [], [resultA, resultB]);

  async function runComparison() {
    if (!fileA || !fileB) return;
    const current = new AbortController();
    controller.current = current;
    setWorking(true);
    setError("");
    setResultA(undefined);
    setResultB(undefined);
    try {
      const compared = await compareFiles(fileA, fileB, current.signal);
      setResultA(compared.resultA);
      setResultB(compared.resultB);
    } catch (caught) {
      if ((caught as Error).name !== "AbortError") {
        setError(caught instanceof Error ? caught.message : "These files could not be compared.");
      }
    } finally {
      setWorking(false);
    }
  }

  if (inspection) return <ResultDashboard result={inspection} onReset={() => setInspection(undefined)} />;

  return (
    <div className="workspace-stack">
      <div className="compare-file-grid">
        <CompareFileCard label={t("fileA")} file={fileA} disabled={working} onFile={(file) => { setFileA(file); setResultA(undefined); setResultB(undefined); }} />
        <CompareFileCard label={t("fileB")} file={fileB} disabled={working} onFile={(file) => { setFileB(file); setResultA(undefined); setResultB(undefined); }} />
      </div>
      <div className="compare-action">
        <button className="button button-primary" type="button" disabled={!fileA || !fileB || working} onClick={() => void runComparison()}>
          {t("compareMetadata")}
        </button>
        <p>{t("compareExplanation")}</p>
      </div>
      {working && fileA && fileB && (
        <AnalysisProgress
          filename={fileA.name + " ↔ " + fileB.name}
          message="The server is analyzing both files before DolosMeta computes their field-level differences."
          onCancel={() => controller.current?.abort()}
        />
      )}
      {error && <p className="inline-error compare-error" role="alert">{error}</p>}
      {resultA && resultB && <CompareTable rows={rows} resultA={resultA} resultB={resultB} onInspect={setInspection} />}
    </div>
  );
}
