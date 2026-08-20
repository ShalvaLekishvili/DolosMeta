import type {
  AnalysisResult,
  CompareRow,
  Finding,
  JsonRecord,
  MetadataEntry,
  StructureNode,
} from "./types";

const categoryHints: Array<[string, string[]]> = [
  ["location", ["gps", "latitude", "longitude", "altitude", "location"]],
  ["camera", ["camera", "lens", "exif", "make", "model", "exposure", "focal", "iso"]],
  ["time", ["time", "date", "created", "modified", "captured"]],
  ["author", ["author", "artist", "owner", "creator", "by-line", "company"]],
  ["software", ["software", "producer", "application", "encoder"]],
  ["document", ["document", "pdf", "office", "page", "word", "slide", "sheet"]],
  ["media", ["media", "image", "video", "audio", "duration", "codec", "dimension"]],
  ["security", ["security", "privacy", "warning", "anomaly", "active", "signature"]],
];

export function asRecord(value: unknown): JsonRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

export function asArray<T = Finding | string>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

export function analysisId(result?: AnalysisResult): string | undefined {
  return result?.id ?? result?.analysis_id;
}

export function normalizeAnalysisPayload(payload: unknown, file?: File): AnalysisResult {
  const envelope = asRecord(payload);
  const candidate =
    asRecord(envelope.result).file || asRecord(envelope.result).metadata
      ? asRecord(envelope.result)
      : asRecord(envelope.analysis).file || asRecord(envelope.analysis).metadata
        ? asRecord(envelope.analysis)
        : envelope;
  const result = candidate as AnalysisResult;
  const receivedFile = asRecord(result.file);

  return {
    ...result,
    id:
      typeof result.id === "string"
        ? result.id
        : typeof envelope.id === "string"
          ? envelope.id
          : undefined,
    analysis_id:
      typeof result.analysis_id === "string"
        ? result.analysis_id
        : typeof envelope.analysis_id === "string"
          ? envelope.analysis_id
          : undefined,
    file: {
      ...receivedFile,
      name: typeof receivedFile.name === "string" ? receivedFile.name : file?.name,
      size: typeof receivedFile.size === "number" ? receivedFile.size : file?.size,
      mime:
        typeof receivedFile.mime === "string"
          ? receivedFile.mime
          : file?.type || undefined,
      extension:
        typeof receivedFile.extension === "string"
          ? receivedFile.extension
          : file?.name.includes(".")
            ? "." + file.name.split(".").pop()?.toLowerCase()
            : "",
    },
  };
}

export function formatBytes(value?: number): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  if (value === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  const number = value / 1024 ** exponent;
  return (number >= 10 || exponent === 0 ? number.toFixed(0) : number.toFixed(1)) + " " + units[exponent];
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(6)));
  if (typeof value === "string") return value;
  try {
    const encoded = JSON.stringify(value);
    return encoded.length > 320 ? encoded.slice(0, 317) + "…" : encoded;
  } catch {
    return String(value);
  }
}

export function titleFromPath(path: string): string {
  const last = path.split(".").pop() ?? path;
  return last
    .replace(/\[(\d+)\]/g, " $1")
    .replace(/[_-]+/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function metadataCategory(path: string): string {
  const lower = path.toLowerCase();
  return categoryHints.find(([, hints]) => hints.some((hint) => lower.includes(hint)))?.[0] ?? "unknown";
}

function flattenInto(
  value: unknown,
  prefix: string,
  entries: MetadataEntry[],
  seen: WeakSet<object>,
): void {
  if (value === null || value === undefined) return;
  if (typeof value !== "object") {
    entries.push({
      path: prefix,
      label: titleFromPath(prefix),
      category: metadataCategory(prefix),
      value,
      displayValue: formatValue(value),
      source: prefix.split(".")[0]?.toUpperCase() || "METADATA",
    });
    return;
  }
  if (seen.has(value as object)) return;
  seen.add(value as object);

  if (Array.isArray(value)) {
    if (value.length === 0) return;
    if (value.every((item) => item === null || typeof item !== "object")) {
      entries.push({
        path: prefix,
        label: titleFromPath(prefix),
        category: metadataCategory(prefix),
        value,
        displayValue: value.map(formatValue).join(", "),
        source: prefix.split(".")[0]?.toUpperCase() || "METADATA",
      });
      return;
    }
    value.slice(0, 500).forEach((item, index) => flattenInto(item, prefix + "[" + index + "]", entries, seen));
    return;
  }

  const record = value as JsonRecord;
  Object.entries(record).slice(0, 3000).forEach(([key, child]) => {
    const path = prefix ? prefix + "." + key : key;
    flattenInto(child, path, entries, seen);
  });
}

export function flattenMetadata(result?: AnalysisResult): MetadataEntry[] {
  if (!result) return [];
  const entries: MetadataEntry[] = [];
  const seen = new WeakSet<object>();
  const sections: Array<[string, unknown]> = [
    ["normalized", result.normalized],
    ["metadata", result.metadata],
  ];
  sections.forEach(([name, value]) => {
    if (value && typeof value === "object") flattenInto(value, name, entries, seen);
  });
  const unique = new Map<string, MetadataEntry>();
  entries.forEach((entry) => {
    const normalizedPath = entry.path.replace(/^(normalized|metadata)\./, "");
    const key = normalizedPath + "\u0000" + entry.displayValue;
    if (!unique.has(key)) {
      unique.set(key, { ...entry, path: normalizedPath, source: entry.path.split(".")[0]?.toUpperCase() || entry.source });
    }
  });
  return [...unique.values()];
}

export function getFileFormat(result?: AnalysisResult): string {
  const file = result?.file;
  return String(file?.detected_format ?? file?.format ?? file?.detected_mime ?? file?.mime ?? "Unknown");
}

export function getPrivacyLevel(result?: AnalysisResult): string {
  const level = result?.privacy?.level;
  if (typeof level === "string" && level.trim()) return level;
  const score = result?.privacy?.score;
  if (typeof score !== "number") return "Not scored";
  if (score >= 70) return "High";
  if (score >= 35) return "Moderate";
  return "Low";
}

export function findingsFrom(result?: AnalysisResult): Array<Finding | string> {
  if (!result) return [];
  return [
    ...asArray<Finding | string>(result.privacy?.findings),
    ...asArray<Finding | string>(result.forensics?.findings),
    ...asArray<Finding | string>(result.forensics?.warnings),
    ...asArray<Finding | string>(result.forensics?.anomalies),
    ...asArray<Finding | string>(result.warnings),
  ];
}

export function findingText(finding: Finding | string): string {
  if (typeof finding === "string") return finding;
  return String(finding.title ?? finding.message ?? finding.description ?? finding.code ?? "Finding");
}

export function findingDetail(finding: Finding | string): string {
  if (typeof finding === "string") return "";
  const primary = findingText(finding);
  const detail = finding.description ?? finding.message;
  return typeof detail === "string" && detail !== primary ? detail : "";
}

export function findingSeverity(finding: Finding | string): string {
  if (typeof finding === "string") return "info";
  return String(finding.severity ?? finding.category ?? "info").toLowerCase();
}

export function countStructure(nodes?: StructureNode[]): number {
  return asArray<StructureNode>(nodes).reduce(
    (count, node) => count + 1 + countStructure(node.children),
    0,
  );
}

export function compareResults(a: AnalysisResult, b: AnalysisResult): CompareRow[] {
  const left = new Map(flattenMetadata(a).map((entry) => [entry.path, entry]));
  const right = new Map(flattenMetadata(b).map((entry) => [entry.path, entry]));
  const paths = [...new Set([...left.keys(), ...right.keys()])].sort((x, y) => x.localeCompare(y));
  return paths.map((path) => {
    const entryA = left.get(path);
    const entryB = right.get(path);
    let status: CompareRow["status"] = "same";
    if (!entryA) status = "added";
    else if (!entryB) status = "removed";
    else if (entryA.displayValue !== entryB.displayValue) status = "changed";
    return {
      path,
      label: entryA?.label ?? entryB?.label ?? titleFromPath(path),
      category: entryA?.category ?? entryB?.category ?? metadataCategory(path),
      valueA: entryA?.value,
      valueB: entryB?.value,
      displayA: entryA?.displayValue ?? "Not present",
      displayB: entryB?.displayValue ?? "Not present",
      status,
    };
  });
}

export function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "{}";
  }
}
