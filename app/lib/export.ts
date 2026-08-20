"use client";

import { flattenMetadata, formatBytes, getFileFormat, getPrivacyLevel, safeJson } from "./format";
import type { AnalysisResult } from "./types";

type ExportFormat = "json" | "csv" | "txt" | "html";

function escapeCsv(value: unknown): string {
  const text = String(value ?? "");
  return '"' + text.replace(/"/g, '""') + '"';
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function safeFilename(value: string): string {
  const normalized = value.replace(/[^a-z0-9._-]+/gi, "-").replace(/^-+|-+$/g, "");
  return normalized || "dolosmeta-analysis";
}

function download(name: string, contents: string, type: string): void {
  const blob = new Blob([contents], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function singleCsv(result: AnalysisResult): string {
  const rows = [["JSON path", "Field", "Category", "Source", "Value"]];
  flattenMetadata(result).forEach((entry) => {
    rows.push([entry.path, entry.label, entry.category, entry.source, entry.displayValue]);
  });
  return rows.map((row) => row.map(escapeCsv).join(",")).join("\n");
}

function singleText(result: AnalysisResult): string {
  const file = result.file ?? {};
  const lines = [
    "DolosMeta analysis",
    "",
    "File: " + (file.name ?? "Unknown"),
    "Format: " + getFileFormat(result),
    "Size: " + formatBytes(file.size),
    "Privacy: " + getPrivacyLevel(result),
    "",
    "Metadata",
    "--------",
  ];
  flattenMetadata(result).forEach((entry) => {
    lines.push(entry.path + ": " + entry.displayValue);
  });
  return lines.join("\n");
}

function singleHtml(result: AnalysisResult): string {
  const file = result.file ?? {};
  const rows = flattenMetadata(result)
    .map(
      (entry) =>
        "<tr><th>" +
        escapeHtml(entry.path) +
        "</th><td>" +
        escapeHtml(entry.displayValue) +
        "</td><td>" +
        escapeHtml(entry.source) +
        "</td></tr>",
    )
    .join("");
  return (
    "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">" +
    "<title>DolosMeta report — " +
    escapeHtml(file.name ?? "file") +
    "</title><style>body{font:15px system-ui;margin:40px;color:#17202a}" +
    "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd3da;padding:9px;text-align:left;vertical-align:top}" +
    "th{width:34%;background:#f3f5f7}code{overflow-wrap:anywhere}</style><body>" +
    "<h1>DolosMeta analysis</h1><p><strong>File:</strong> " +
    escapeHtml(file.name ?? "Unknown") +
    "<br><strong>Detected format:</strong> " +
    escapeHtml(getFileFormat(result)) +
    "<br><strong>Privacy:</strong> " +
    escapeHtml(getPrivacyLevel(result)) +
    "</p><table><thead><tr><th>Field</th><th>Value</th><th>Source</th></tr></thead><tbody>" +
    rows +
    "</tbody></table><p>Metadata reports embedded values and should not be treated as independently verified evidence.</p></body></html>"
  );
}

export function exportAnalysis(result: AnalysisResult, format: ExportFormat): void {
  const stem = safeFilename(String(result.file?.name ?? "analysis"));
  if (format === "json") {
    download(stem + ".dolosmeta.json", safeJson(result), "application/json");
  } else if (format === "csv") {
    download(stem + ".dolosmeta.csv", singleCsv(result), "text/csv;charset=utf-8");
  } else if (format === "txt") {
    download(stem + ".dolosmeta.txt", singleText(result), "text/plain;charset=utf-8");
  } else {
    download(stem + ".dolosmeta.html", singleHtml(result), "text/html;charset=utf-8");
  }
}

export function exportBatch(results: AnalysisResult[], format: "json" | "csv"): void {
  if (format === "json") {
    download("dolosmeta-batch.json", safeJson({ analyses: results }), "application/json");
    return;
  }
  const rows = [
    ["Filename", "Detected format", "Size", "Metadata fields", "GPS", "Privacy", "Warnings", "SHA-256"],
    ...results.map((result) => {
      const entries = flattenMetadata(result);
      const hasGps = entries.some((entry) => entry.category === "location");
      const warnings =
        (result.forensics?.warnings?.length ?? 0) +
        (result.forensics?.anomalies?.length ?? 0) +
        (result.warnings?.length ?? 0);
      return [
        result.file?.name ?? "Unknown",
        getFileFormat(result),
        result.file?.size ?? "",
        entries.length,
        hasGps ? "Detected" : "Not detected",
        getPrivacyLevel(result),
        warnings,
        result.hashes?.sha256 ?? result.hashes?.["SHA-256"] ?? "",
      ];
    }),
  ];
  download(
    "dolosmeta-batch.csv",
    rows.map((row) => row.map(escapeCsv).join(",")).join("\n"),
    "text/csv;charset=utf-8",
  );
}

export async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("Copy is unavailable in this browser.");
}
