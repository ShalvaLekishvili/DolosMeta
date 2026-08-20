"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { downloadCleanFile, getAnalysisSection, getHex } from "../lib/api";
import { copyText, exportAnalysis } from "../lib/export";
import {
  analysisId,
  asArray,
  asRecord,
  countStructure,
  findingDetail,
  findingSeverity,
  findingText,
  findingsFrom,
  flattenMetadata,
  formatBytes,
  formatValue,
  getFileFormat,
  getPrivacyLevel,
  safeJson,
} from "../lib/format";
import type {
  AnalysisResult,
  Finding,
  MetadataEntry,
  StructureNode,
  TimelineEvent,
} from "../lib/types";
import { usePreferences } from "./preferences";

type TabId =
  | "overview"
  | "exif"
  | "gps"
  | "metadata"
  | "timeline"
  | "structure"
  | "strings"
  | "hex"
  | "forensics"
  | "raw";

interface TabDefinition {
  id: TabId;
  label: string;
}

function firstEntry(entries: MetadataEntry[], hints: string[]): MetadataEntry | undefined {
  return entries.find((entry) => {
    const path = entry.path.toLowerCase();
    return hints.some((hint) => path.includes(hint));
  });
}

function severityClass(value: string): string {
  const normalized = value.toLowerCase();
  if (["critical", "high", "error", "danger"].some((item) => normalized.includes(item))) return "danger";
  if (["moderate", "medium", "warning", "caution"].some((item) => normalized.includes(item))) return "warning";
  if (["low", "success", "safe"].some((item) => normalized.includes(item))) return "success";
  return "info";
}

function CopyButton({
  value,
  label,
  onCopied,
  compact = false,
}: {
  value: string;
  label: string;
  onCopied: (message: string) => void;
  compact?: boolean;
}) {
  return (
    <button
      className={compact ? "copy-button copy-button-compact" : "copy-button"}
      type="button"
      onClick={async () => {
        try {
          await copyText(value);
          onCopied(label + " copied");
        } catch {
          onCopied("Copy is unavailable in this browser");
        }
      }}
      aria-label={"Copy " + label.toLowerCase()}
    >
      Copy
    </button>
  );
}

function ExportMenu({ result }: { result: AnalysisResult }) {
  const { t } = usePreferences();
  return (
    <details className="action-menu">
      <summary className="button button-secondary">{t("exportReport")}</summary>
      <div className="action-menu-panel" role="group" aria-label="Export formats">
        {(["json", "csv", "txt", "html"] as const).map((format) => (
          <button
            key={format}
            type="button"
            onClick={(event) => {
              exportAnalysis(result, format);
              event.currentTarget.closest("details")?.removeAttribute("open");
            }}
          >
            {format.toUpperCase()}
          </button>
        ))}
      </div>
    </details>
  );
}

function ResultHeader({
  result,
  onReset,
  onCopied,
}: {
  result: AnalysisResult;
  onReset?: () => void;
  onCopied: (message: string) => void;
}) {
  const { t } = usePreferences();
  const file = result.file ?? {};
  const sha256 = result.hashes?.sha256 ?? result.hashes?.["SHA-256"];
  const mismatch = file.signature_match === false;
  const [cleaning, setCleaning] = useState(false);
  const [cleanError, setCleanError] = useState("");
  const id = analysisId(result);
  const filename = String(file.name ?? "analyzed-file");

  async function clearMetadata() {
    if (!id) return;
    setCleaning(true);
    setCleanError("");
    try {
      await downloadCleanFile(id, filename);
      onCopied("Clean file downloaded");
    } catch (error) {
      setCleanError(error instanceof Error ? error.message : "The clean file could not be created.");
    } finally {
      setCleaning(false);
    }
  }

  return (
    <>
      {mismatch && (
        <div className="alert alert-danger" role="alert">
          <span aria-hidden="true">!</span>
          <div>
            <strong>File extension does not match the detected format.</strong>
            <p>DolosMeta selected its parser from the file signature rather than the filename.</p>
          </div>
        </div>
      )}
      <header className="result-header">
        <div className="file-emblem" aria-hidden="true">
          {getFileFormat(result).slice(0, 4).toUpperCase()}
        </div>
        <div className="result-title">
          <p className="eyebrow"><span aria-hidden="true" /> {t("analysisComplete")}</p>
          <h1>{String(file.name ?? "Analyzed file")}</h1>
          <div className="file-facts">
            <span>{getFileFormat(result)}</span>
            <span>{formatBytes(file.size)}</span>
            {file.detected_mime && <span>{String(file.detected_mime)}</span>}
            {result.parser?.name && <span>{String(result.parser.name)}</span>}
          </div>
          {sha256 && (
            <div className="fingerprint-line">
              <span>SHA-256</span>
              <code title={sha256}>{sha256}</code>
              <CopyButton value={sha256} label="SHA-256" onCopied={onCopied} compact />
            </div>
          )}
        </div>
        <div className="result-actions">
          <ExportMenu result={result} />
          <button
            className="button button-primary"
            type="button"
            disabled={!id || cleaning}
            onClick={() => void clearMetadata()}
          >
            {cleaning ? t("clearingMetadata") : t("clearMetadata")}
          </button>
          {onReset && (
            <button className="button button-quiet" type="button" onClick={onReset}>
              {t("analyzeAnother")}
            </button>
          )}
        </div>
      </header>
      {cleanError && <p className="inline-error" role="alert">{cleanError}</p>}
    </>
  );
}

function SummaryCards({
  result,
  entries,
}: {
  result: AnalysisResult;
  entries: MetadataEntry[];
}) {
  const camera = firstEntry(entries, ["camera.model", "model", "camera.make", "make"]);
  const captured = firstEntry(entries, ["datetimeoriginal", "captured", "created", "creationdate"]);
  const hasLocation = entries.some((entry) => entry.category === "location");
  const score = result.privacy?.score;
  const privacy = getPrivacyLevel(result);
  const values = [
    { label: "File", value: getFileFormat(result), tone: "neutral" },
    { label: "Source", value: camera?.displayValue ?? "Not reported", tone: "neutral" },
    { label: "Captured / created", value: captured?.displayValue ?? "Not reported", tone: "neutral" },
    { label: "Location", value: hasLocation ? "Detected" : "Not detected", tone: hasLocation ? "warning" : "neutral" },
    {
      label: "Privacy",
      value: privacy + (typeof score === "number" ? " · " + score + "/100" : ""),
      tone: severityClass(privacy),
    },
  ];

  return (
    <section className="summary-grid" aria-label="Analysis summary">
      {values.map((item) => (
        <div className={"summary-card tone-" + item.tone} key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      ))}
    </section>
  );
}

function FindingList({
  findings,
  limit,
}: {
  findings: Array<Finding | string>;
  limit?: number;
}) {
  const { t } = usePreferences();
  const visible = typeof limit === "number" ? findings.slice(0, limit) : findings;
  if (!visible.length) return <p className="empty-copy">{t("noFindings")}</p>;
  return (
    <ul className="finding-list">
      {visible.map((finding, index) => {
        const severity = findingSeverity(finding);
        const points = typeof finding === "string" ? undefined : finding.points;
        return (
          <li key={(typeof finding === "string" ? finding : finding.code ?? findingText(finding)) + index}>
            <span className={"status-dot tone-" + severityClass(severity)} aria-hidden="true" />
            <div>
              <strong>{findingText(finding)}</strong>
              {findingDetail(finding) && <p>{findingDetail(finding)}</p>}
              <span className="finding-meta">
                {severity !== "info" && severity}
                {typeof points === "number" && (severity !== "info" ? " · " : "") + (points >= 0 ? "+" : "") + points + " points"}
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function HashPanel({
  result,
  onCopied,
}: {
  result: AnalysisResult;
  onCopied: (message: string) => void;
}) {
  const { t } = usePreferences();
  const hashes = Object.entries(result.hashes ?? {});
  return (
    <section className="panel" aria-labelledby="hash-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Identity</p>
          <h2 id="hash-title">{t("fileFingerprints")}</h2>
        </div>
        <span>{hashes.length} algorithms</span>
      </div>
      {hashes.length ? (
        <dl className="hash-list">
          {hashes.map(([algorithm, hash]) => (
            <div key={algorithm}>
              <dt>
                {algorithm.toUpperCase()}
                {["md5", "sha1", "sha-1"].includes(algorithm.toLowerCase()) && <small>Legacy identification</small>}
              </dt>
              <dd><code>{hash}</code></dd>
              <CopyButton value={hash} label={algorithm} onCopied={onCopied} compact />
            </div>
          ))}
        </dl>
      ) : (
        <p className="empty-copy">No fingerprints were returned by the analyzer.</p>
      )}
    </section>
  );
}

function PrivacyPanel({ result }: { result: AnalysisResult }) {
  const { t } = usePreferences();
  const privacy = result.privacy;
  const level = getPrivacyLevel(result);
  const score = privacy?.score;
  const findings = asArray<Finding | string>(privacy?.findings);
  return (
    <section className="panel privacy-panel" aria-labelledby="privacy-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Exposure</p>
          <h2 id="privacy-title">{t("privacyAnalysis")}</h2>
        </div>
        <span className={"risk-pill tone-" + severityClass(level)}>{level}</span>
      </div>
      {typeof score === "number" && (
        <div className="risk-score">
          <strong>{score}</strong>
          <span>/ 100</span>
          <div aria-hidden="true"><i style={{ width: Math.max(0, Math.min(100, score)) + "%" }} /></div>
        </div>
      )}
      <FindingList findings={findings} />
      <p className="evidence-note">Metadata can be changed. These findings describe embedded values, not independently verified facts.</p>
    </section>
  );
}

function TimelineView({ events }: { events?: TimelineEvent[] }) {
  const { t } = usePreferences();
  const items = asArray<TimelineEvent>(events);
  return (
    <section className="panel" aria-labelledby="timeline-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Chronology</p>
          <h2 id="timeline-title">{t("forensicTimeline")}</h2>
        </div>
        <span>{items.length} events</span>
      </div>
      {items.length ? (
        <ol className="timeline">
          {items.map((event, index) => {
            const stamp = String(event.timestamp ?? event.date ?? "Timestamp not reported");
            const label = String(event.label ?? event.title ?? event.description ?? "Metadata event");
            const kind = String(event.kind ?? event.confidence ?? "observed");
            return (
              <li key={stamp + label + index}>
                <time>{stamp}</time>
                <div>
                  <strong>{label}</strong>
                  {event.description && event.description !== label && <p>{String(event.description)}</p>}
                  <span>{kind} {event.source ? "· " + String(event.source) : ""}</span>
                </div>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="empty-copy">The analyzer did not return timestamp events for this file.</p>
      )}
    </section>
  );
}

function Overview({
  result,
  entries,
  onCopied,
  onTab,
}: {
  result: AnalysisResult;
  entries: MetadataEntry[];
  onCopied: (message: string) => void;
  onTab: (tab: TabId) => void;
}) {
  const findings = findingsFrom(result);
  const keyEntries = entries.slice(0, 8);
  return (
    <div className="overview-grid">
      <div className="overview-main">
        {findings.length > 0 && (
          <section className="panel findings-panel" aria-labelledby="priority-findings">
            <div className="panel-heading">
              <div>
                <p className="section-kicker">Review first</p>
                <h2 id="priority-findings">Priority findings</h2>
              </div>
              <button className="text-button" type="button" onClick={() => onTab("forensics")}>View all</button>
            </div>
            <FindingList findings={findings} limit={4} />
          </section>
        )}
        <section className="panel" aria-labelledby="key-metadata-title">
          <div className="panel-heading">
            <div>
              <p className="section-kicker">Reported values</p>
              <h2 id="key-metadata-title">Key metadata</h2>
            </div>
            <button className="text-button" type="button" onClick={() => onTab("metadata")}>Explore all</button>
          </div>
          {keyEntries.length ? (
            <dl className="key-value-list">
              {keyEntries.map((entry) => (
                <div key={entry.path}>
                  <dt>{entry.label}<small>{entry.path}</small></dt>
                  <dd>{entry.displayValue}</dd>
                  <CopyButton value={entry.displayValue} label={entry.label} onCopied={onCopied} compact />
                </div>
              ))}
            </dl>
          ) : (
            <p className="empty-copy">No normalized metadata fields were returned. Generic file details remain available above.</p>
          )}
        </section>
        <TimelineView events={result.timeline} />
      </div>
      <aside className="overview-side" aria-label="Analysis details">
        <PrivacyPanel result={result} />
        <HashPanel result={result} onCopied={onCopied} />
        <section className="panel engine-panel" aria-labelledby="engine-version-title">
          <p className="section-kicker">Reproducibility</p>
          <h2 id="engine-version-title">Analysis engine</h2>
          <dl>
            <div><dt>Engine</dt><dd>{String(result.engine?.name ?? "DolosMeta")}</dd></div>
            <div><dt>Version</dt><dd>{String(result.engine?.version ?? result.analysis_version ?? "Not reported")}</dd></div>
            <div><dt>Parser</dt><dd>{String(result.parser?.name ?? "Generic")}</dd></div>
            <div><dt>Parser version</dt><dd>{String(result.parser?.version ?? "Not reported")}</dd></div>
          </dl>
        </section>
      </aside>
    </div>
  );
}

function Highlight({ text, query }: { text: string; query: string }) {
  if (!query.trim()) return <>{text}</>;
  const lower = text.toLowerCase();
  const needle = query.toLowerCase();
  const parts: Array<{ text: string; match: boolean }> = [];
  let index = 0;
  let match = lower.indexOf(needle);
  while (match >= 0) {
    if (match > index) parts.push({ text: text.slice(index, match), match: false });
    parts.push({ text: text.slice(match, match + needle.length), match: true });
    index = match + needle.length;
    match = lower.indexOf(needle, index);
  }
  if (index < text.length) parts.push({ text: text.slice(index), match: false });
  return (
    <>
      {parts.map((part, partIndex) =>
        part.match ? <mark key={partIndex}>{part.text}</mark> : <Fragment key={partIndex}>{part.text}</Fragment>,
      )}
    </>
  );
}

function MetadataExplorer({
  entries,
  initialCategory = "all",
  onCopied,
}: {
  entries: MetadataEntry[];
  initialCategory?: string;
  onCopied: (message: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(initialCategory);
  const [limit, setLimit] = useState(200);
  const categories = useMemo(
    () => ["all", ...new Set(entries.map((entry) => entry.category))],
    [entries],
  );
  const filtered = useMemo(
    () =>
      entries.filter((entry) => {
        const categoryMatch = category === "all" || entry.category === category;
        const needle = query.trim().toLowerCase();
        const searchMatch =
          !needle ||
          entry.path.toLowerCase().includes(needle) ||
          entry.label.toLowerCase().includes(needle) ||
          entry.displayValue.toLowerCase().includes(needle) ||
          entry.source.toLowerCase().includes(needle);
        return categoryMatch && searchMatch;
      }),
    [category, entries, query],
  );
  const visible = filtered.slice(0, limit);

  return (
    <section className="panel metadata-panel" aria-labelledby="metadata-title">
      <div className="panel-heading metadata-heading">
        <div>
          <p className="section-kicker">Normalized and raw values</p>
          <h2 id="metadata-title">Metadata explorer</h2>
        </div>
        <span>{filtered.length} fields</span>
      </div>
      <div className="metadata-tools">
        <label className="search-field">
          <span className="sr-only">Search metadata</span>
          <i aria-hidden="true">⌕</i>
          <input
            type="search"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setLimit(200);
            }}
            placeholder="Search tags, values, or paths…"
          />
        </label>
        <div className="filter-row" aria-label="Metadata categories">
          {categories.map((item) => (
            <button
              type="button"
              className={category === item ? "is-active" : ""}
              aria-pressed={category === item}
              key={item}
              onClick={() => {
                setCategory(item);
                setLimit(200);
              }}
            >
              {item}
            </button>
          ))}
        </div>
      </div>
      {visible.length ? (
        <>
          <div className="metadata-table-wrap">
            <table className="metadata-table">
              <thead><tr><th>Field</th><th>Value</th><th>Source</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {visible.map((entry) => (
                  <tr key={entry.path + entry.displayValue}>
                    <th scope="row">
                      <span><Highlight text={entry.label} query={query} /></span>
                      <code><Highlight text={entry.path} query={query} /></code>
                    </th>
                    <td><Highlight text={entry.displayValue} query={query} /></td>
                    <td><span className="source-pill">{entry.source}</span></td>
                    <td>
                      <details className="row-menu">
                        <summary aria-label={"Copy options for " + entry.label}>•••</summary>
                        <div>
                          <button type="button" onClick={() => copyText(entry.label).then(() => onCopied("Field name copied"))}>Field</button>
                          <button type="button" onClick={() => copyText(entry.displayValue).then(() => onCopied("Value copied"))}>Value</button>
                          <button type="button" onClick={() => copyText(entry.path).then(() => onCopied("JSON path copied"))}>Path</button>
                        </div>
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filtered.length > visible.length && (
            <button className="button button-secondary load-more" type="button" onClick={() => setLimit((value) => value + 200)}>
              Show {Math.min(200, filtered.length - visible.length)} more
            </button>
          )}
        </>
      ) : (
        <div className="empty-state">
          <strong>No matching metadata</strong>
          <p>Try a broader search or another category.</p>
        </div>
      )}
    </section>
  );
}

function StructureBranch({ node, depth = 0 }: { node: StructureNode; depth?: number }) {
  const children = asArray<StructureNode>(node.children);
  const name = String(node.name ?? node.label ?? node.type ?? "Structure node");
  const details = [
    typeof node.offset === "number" ? "offset " + node.offset : "",
    typeof node.size === "number" ? formatBytes(node.size) : typeof node.length === "number" ? formatBytes(node.length) : "",
  ].filter(Boolean);
  if (!children.length) {
    return (
      <li className="structure-leaf">
        <span>{name}</span>
        {details.length > 0 && <code>{details.join(" · ")}</code>}
      </li>
    );
  }
  return (
    <li>
      <details open={depth < 1}>
        <summary>
          <span>{name}</span>
          <code>{details.join(" · ")}{details.length ? " · " : ""}{children.length} children</code>
        </summary>
        <ul>{children.map((child, index) => <StructureBranch key={name + index} node={child} depth={depth + 1} />)}</ul>
      </details>
    </li>
  );
}

function StructureView({ result }: { result: AnalysisResult }) {
  const { t } = usePreferences();
  const id = analysisId(result);
  const [nodes, setNodes] = useState<StructureNode[]>(asArray<StructureNode>(result.structure));
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">(nodes.length ? "ready" : "idle");

  useEffect(() => {
    if (nodes.length || !id || status !== "idle") return;
    const controller = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setStatus("loading");
    getAnalysisSection(id, "structure", controller.signal)
      .then((payload) => {
        const record = asRecord(payload);
        setNodes(asArray<StructureNode>(Array.isArray(payload) ? payload : record.structure ?? record.nodes));
        setStatus("ready");
      })
      .catch((error: unknown) => {
        if ((error as Error).name !== "AbortError") setStatus("error");
      });
    return () => controller.abort();
  }, [id, nodes.length, status]);

  return (
    <section className="panel" aria-labelledby="structure-title">
      <div className="panel-heading">
        <div><p className="section-kicker">Container map</p><h2 id="structure-title">{t("fileStructure")}</h2></div>
        <span>{countStructure(nodes)} nodes</span>
      </div>
      {status === "loading" && <p className="loading-copy" role="status">Loading structural inventory…</p>}
      {status === "error" && <p className="inline-error">The structural inventory could not be retrieved.</p>}
      {status === "ready" && !nodes.length && <p className="empty-copy">No structural nodes were returned for this format.</p>}
      {nodes.length > 0 && <ul className="structure-tree">{nodes.map((node, index) => <StructureBranch key={index} node={node} />)}</ul>}
    </section>
  );
}

function StringsView({ result }: { result: AnalysisResult }) {
  const { t } = usePreferences();
  const id = analysisId(result);
  const [items, setItems] = useState<unknown[]>(asArray(result.strings));
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">(items.length ? "ready" : "idle");
  const [query, setQuery] = useState("");
  useEffect(() => {
    if (items.length || !id || status !== "idle") return;
    const controller = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setStatus("loading");
    getAnalysisSection(id, "strings", controller.signal)
      .then((payload) => {
        const record = asRecord(payload);
        setItems(asArray(Array.isArray(payload) ? payload : record.strings ?? record.items));
        setStatus("ready");
      })
      .catch((error: unknown) => {
        if ((error as Error).name !== "AbortError") setStatus("error");
      });
    return () => controller.abort();
  }, [id, items.length, status]);

  const normalized = items.map((item, index) => {
    const record = asRecord(item);
    return {
      key: index,
      value: typeof item === "string" ? item : formatValue(record.value ?? record.text ?? item),
      category: typeof record.category === "string" ? record.category : "string",
      offset: typeof record.offset === "number" ? record.offset : undefined,
      encoding: typeof record.encoding === "string" ? record.encoding : undefined,
    };
  });
  const visible = normalized.filter((item) => item.value.toLowerCase().includes(query.toLowerCase()));

  return (
    <section className="panel" aria-labelledby="strings-title">
      <div className="panel-heading">
        <div><p className="section-kicker">Bounded extraction</p><h2 id="strings-title">{t("printableStrings")}</h2></div>
        <span>{visible.length} strings</span>
      </div>
      {items.length > 0 && (
        <label className="search-field strings-search">
          <span className="sr-only">Search extracted strings</span>
          <i aria-hidden="true">⌕</i>
          <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search extracted strings…" />
        </label>
      )}
      {status === "loading" && <p className="loading-copy" role="status">Loading bounded string extraction…</p>}
      {status === "error" && <p className="inline-error">Extracted strings could not be retrieved.</p>}
      {status === "ready" && !items.length && <p className="empty-copy">No printable strings were returned for this file.</p>}
      {visible.length > 0 && (
        <ul className="strings-list">
          {visible.slice(0, 1000).map((item) => (
            <li key={item.key}>
              <span>{item.category}</span>
              <code>{item.value}</code>
              <small>{[item.encoding, typeof item.offset === "number" ? "offset " + item.offset : ""].filter(Boolean).join(" · ")}</small>
            </li>
          ))}
        </ul>
      )}
      <p className="evidence-note">DolosMeta does not connect to discovered URLs, domains, or addresses.</p>
    </section>
  );
}

function bytesToRows(bytes: number[], start: number): Array<{ offset: number; hex: string; ascii: string }> {
  const rows = [];
  for (let index = 0; index < bytes.length; index += 16) {
    const slice = bytes.slice(index, index + 16);
    rows.push({
      offset: start + index,
      hex: slice.map((byte) => byte.toString(16).padStart(2, "0").toUpperCase()).join(" "),
      ascii: slice.map((byte) => (byte >= 32 && byte <= 126 ? String.fromCharCode(byte) : ".")).join(""),
    });
  }
  return rows;
}

function parseHexPayload(payload: unknown, fallbackOffset: number) {
  const record = asRecord(payload);
  const responseOffset = typeof record.offset === "number" ? record.offset : fallbackOffset;
  const directRows = asArray<Record<string, unknown>>(record.rows).map((row) => ({
    offset: typeof row.offset === "number" ? row.offset : responseOffset,
    hex: String(row.hex ?? ""),
    ascii: String(row.ascii ?? ""),
  }));
  if (directRows.length) {
    return {
      rows: directRows,
      total: typeof record.total === "number" ? record.total : undefined,
      length: typeof record.length === "number" ? record.length : directRows.length * 16,
    };
  }
  const numeric = asArray<number>(record.data ?? record.bytes).filter((item) => Number.isInteger(item) && item >= 0 && item <= 255);
  if (numeric.length) return { rows: bytesToRows(numeric, responseOffset), total: record.total as number | undefined, length: numeric.length };
  const hex = typeof record.hex === "string" ? record.hex.replace(/[^0-9a-f]/gi, "") : "";
  const bytes = (hex.match(/.{1,2}/g) ?? []).map((pair) => Number.parseInt(pair, 16));
  return { rows: bytesToRows(bytes, responseOffset), total: record.total as number | undefined, length: bytes.length };
}

function HexView({ result }: { result: AnalysisResult }) {
  const { t } = usePreferences();
  const id = analysisId(result);
  const pageSize = 512;
  const [offset, setOffset] = useState(0);
  const [payload, setPayload] = useState<unknown>(result.hex);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">(result.hex ? "ready" : "idle");

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setStatus("loading");
    getHex(id, offset, pageSize, controller.signal)
      .then((data) => {
        setPayload(data);
        setStatus("ready");
      })
      .catch((error: unknown) => {
        if ((error as Error).name !== "AbortError") setStatus("error");
      });
    return () => controller.abort();
  }, [id, offset]);

  const parsed = parseHexPayload(payload, offset);
  const canNext = typeof parsed.total === "number" ? offset + parsed.length < parsed.total : parsed.length === pageSize;
  return (
    <section className="panel" aria-labelledby="hex-title">
      <div className="panel-heading">
        <div><p className="section-kicker">Bounded byte range</p><h2 id="hex-title">{t("hexViewer")}</h2></div>
        <span>Offset {offset.toString(16).toUpperCase().padStart(8, "0")}</span>
      </div>
      {status === "loading" && <p className="loading-copy" role="status">Reading byte range…</p>}
      {status === "error" && <p className="inline-error">This byte range could not be retrieved.</p>}
      {status === "ready" && !parsed.rows.length && <p className="empty-copy">No hex data was returned for this range.</p>}
      {parsed.rows.length > 0 && (
        <div className="hex-viewer" role="region" aria-label="Hexadecimal byte preview">
          <div className="hex-heading"><span>Offset</span><span>Hex</span><span>ASCII</span></div>
          {parsed.rows.map((row, index) => (
            <div key={row.offset + "-" + index}><span>{row.offset.toString(16).toUpperCase().padStart(8, "0")}</span><code>{row.hex}</code><code>{row.ascii}</code></div>
          ))}
        </div>
      )}
      {id && (
        <div className="pagination">
          <button className="button button-secondary" type="button" disabled={offset === 0 || status === "loading"} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous range</button>
          <button className="button button-secondary" type="button" disabled={!canNext || status === "loading"} onClick={() => setOffset(offset + pageSize)}>Next range</button>
        </div>
      )}
      <p className="evidence-note">Only a small requested range is sent to the browser.</p>
    </section>
  );
}

function ForensicsView({ result }: { result: AnalysisResult }) {
  const groups: Array<[string, Array<Finding | string>]> = [
    ["Privacy exposure", asArray(result.privacy?.findings)],
    ["Forensic observations", asArray(result.forensics?.findings)],
    ["Parser warnings", [...asArray(result.forensics?.warnings), ...asArray(result.warnings)]],
    ["Metadata inconsistencies", asArray(result.forensics?.anomalies)],
  ];
  return (
    <div className="forensics-grid">
      {groups.map(([label, findings]) => (
        <section className="panel" key={label}>
          <div className="panel-heading"><h2>{label}</h2><span>{findings.length}</span></div>
          <FindingList findings={findings} />
        </section>
      ))}
      <section className="panel evidence-principles">
        <p className="section-kicker">Interpretation</p>
        <h2>Evidence principles</h2>
        <p>The file reports these values. Metadata may be edited, copied, removed, or malformed. DolosMeta distinguishes observations from derived values and analytical inferences wherever the parser provides provenance.</p>
      </section>
    </div>
  );
}

function RawView({
  result,
  onCopied,
}: {
  result: AnalysisResult;
  onCopied: (message: string) => void;
}) {
  const text = safeJson(result);
  return (
    <section className="panel" aria-labelledby="raw-title">
      <div className="panel-heading">
        <div><p className="section-kicker">Schema-preserving result</p><h2 id="raw-title">Raw analysis JSON</h2></div>
        <CopyButton value={text} label="all metadata JSON" onCopied={onCopied} />
      </div>
      <pre className="raw-view"><code>{text}</code></pre>
    </section>
  );
}

export function ResultDashboard({
  result,
  onReset,
}: {
  result: AnalysisResult;
  onReset?: () => void;
}) {
  const entries = useMemo(() => flattenMetadata(result), [result]);
  const hasExif = entries.some((entry) => entry.path.toLowerCase().includes("exif") || entry.category === "camera");
  const hasGps = entries.some((entry) => entry.category === "location");
  const hasTimeline = asArray(result.timeline).length > 0;
  const hasFindings = findingsFrom(result).length > 0;
  const id = analysisId(result);
  const tabs = useMemo<TabDefinition[]>(
    () => [
      { id: "overview", label: "Overview" },
      ...(hasExif ? [{ id: "exif" as TabId, label: "EXIF" }] : []),
      ...(hasGps ? [{ id: "gps" as TabId, label: "GPS" }] : []),
      { id: "metadata", label: "Metadata" },
      ...(hasTimeline ? [{ id: "timeline" as TabId, label: "Timeline" }] : []),
      ...(asArray(result.structure).length || id ? [{ id: "structure" as TabId, label: "Structure" }] : []),
      ...(asArray(result.strings).length || id ? [{ id: "strings" as TabId, label: "Strings" }] : []),
      ...(result.hex || id ? [{ id: "hex" as TabId, label: "Hex" }] : []),
      ...(hasFindings ? [{ id: "forensics" as TabId, label: "Forensics" }] : []),
      { id: "raw", label: "Raw" },
    ],
    [hasExif, hasFindings, hasGps, hasTimeline, id, result.hex, result.strings, result.structure],
  );
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [announcement, setAnnouncement] = useState("");

  function announce(message: string) {
    setAnnouncement("");
    window.setTimeout(() => setAnnouncement(message), 10);
  }

  return (
    <article className="result-dashboard">
      <ResultHeader result={result} onReset={onReset} onCopied={announce} />
      <SummaryCards result={result} entries={entries} />
      <nav className="result-tabs" aria-label="Analysis result sections">
        <div role="tablist" aria-label="File analysis">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              id={"tab-" + tab.id}
              role="tab"
              type="button"
              aria-selected={activeTab === tab.id}
              aria-controls={"panel-" + tab.id}
              tabIndex={activeTab === tab.id ? 0 : -1}
              onClick={() => setActiveTab(tab.id)}
              onKeyDown={(event) => {
                if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                event.preventDefault();
                const current = tabs.findIndex((item) => item.id === activeTab);
                const next =
                  event.key === "Home"
                    ? 0
                    : event.key === "End"
                      ? tabs.length - 1
                      : event.key === "ArrowRight"
                        ? (current + 1) % tabs.length
                        : (current - 1 + tabs.length) % tabs.length;
                setActiveTab(tabs[next].id);
                document.getElementById("tab-" + tabs[next].id)?.focus();
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </nav>
      <div className="tab-panel" id={"panel-" + activeTab} role="tabpanel" aria-labelledby={"tab-" + activeTab}>
        {activeTab === "overview" && <Overview result={result} entries={entries} onCopied={announce} onTab={setActiveTab} />}
        {activeTab === "exif" && <MetadataExplorer entries={entries.filter((entry) => entry.category === "camera" || entry.path.toLowerCase().includes("exif"))} onCopied={announce} />}
        {activeTab === "gps" && <MetadataExplorer entries={entries.filter((entry) => entry.category === "location")} initialCategory="location" onCopied={announce} />}
        {activeTab === "metadata" && <MetadataExplorer entries={entries} onCopied={announce} />}
        {activeTab === "timeline" && <TimelineView events={result.timeline} />}
        {activeTab === "structure" && <StructureView result={result} />}
        {activeTab === "strings" && <StringsView result={result} />}
        {activeTab === "hex" && <HexView result={result} />}
        {activeTab === "forensics" && <ForensicsView result={result} />}
        {activeTab === "raw" && <RawView result={result} onCopied={announce} />}
      </div>
      <p className="sr-only" aria-live="polite" aria-atomic="true">{announcement}</p>
    </article>
  );
}
