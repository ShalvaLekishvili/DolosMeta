"use client";

import { asArray, asRecord, normalizeAnalysisPayload } from "./format";
import type { AnalysisResult, ParserCapability } from "./types";

const configuredApiBase =
  typeof process !== "undefined" ? process.env.NEXT_PUBLIC_API_BASE_URL?.trim() : undefined;

const fallbackApiBase =
  typeof process !== "undefined" && process.env.NODE_ENV === "development"
    ? "http://127.0.0.1:8000"
    : "";

export const API_BASE_URL = (configuredApiBase || fallbackApiBase).replace(/\/$/, "");

function apiUrl(path: string): string {
  if (!API_BASE_URL) {
    throw new Error(
      "The DolosMeta analysis API is not configured for this deployment. Set NEXT_PUBLIC_API_BASE_URL to the public HTTPS URL of the FastAPI backend and redeploy the site.",
    );
  }
  return API_BASE_URL + (path.startsWith("/") ? path : "/" + path);
}

async function messageFrom(response: Response): Promise<string> {
  try {
    const body = asRecord(await response.json());
    const detail = body.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          const record = asRecord(item);
          return typeof record.msg === "string" ? record.msg : "";
        })
        .filter(Boolean)
        .join(". ");
    }
    if (typeof body.message === "string") return body.message;
  } catch {
    // The response was not JSON.
  }
  if (response.status === 413) return "This file is larger than the server permits.";
  if (response.status === 429) return "The analyzer is busy. Please try again shortly.";
  return "The analyzer could not complete this request.";
}

async function checkedJson(response: Response): Promise<unknown> {
  if (!response.ok) throw new Error(await messageFrom(response));
  return response.json();
}

export async function analyzeFile(file: File, signal?: AbortSignal): Promise<AnalysisResult> {
  const form = new FormData();
  form.append("file", file, file.name);
  const payload = await checkedJson(
    await fetch(apiUrl("/api/v1/analyze"), {
      method: "POST",
      body: form,
      signal,
    }),
  );
  return normalizeAnalysisPayload(payload, file);
}

export async function analyzeBatch(
  files: File[],
  signal?: AbortSignal,
): Promise<AnalysisResult[]> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file, file.name));
  const response = await fetch(apiUrl("/api/v1/analyze/batch"), {
    method: "POST",
    body: form,
    signal,
  });

  if (response.status === 404 || response.status === 405) {
    const results: AnalysisResult[] = [];
    for (const file of files) results.push(await analyzeFile(file, signal));
    return results;
  }

  const payload = await checkedJson(response);
  const record = asRecord(payload);
  const values = Array.isArray(payload)
    ? payload
    : asArray(record.results).length
      ? asArray(record.results)
      : asArray(record.analyses);
  return values.map((item, index) => normalizeAnalysisPayload(item, files[index]));
}

export async function compareFiles(
  fileA: File,
  fileB: File,
  signal?: AbortSignal,
): Promise<{ resultA: AnalysisResult; resultB: AnalysisResult; serverComparison?: unknown }> {
  const form = new FormData();
  form.append("file_a", fileA, fileA.name);
  form.append("file_b", fileB, fileB.name);
  const response = await fetch(apiUrl("/api/v1/compare"), {
    method: "POST",
    body: form,
    signal,
  });

  if (response.status !== 404 && response.status !== 405) {
    const payload = await checkedJson(response);
    const record = asRecord(payload);
    const rawA = record.file_a ?? record.result_a ?? record.analysis_a ?? record.left;
    const rawB = record.file_b ?? record.result_b ?? record.analysis_b ?? record.right;
    if (rawA && rawB) {
      return {
        resultA: normalizeAnalysisPayload(rawA, fileA),
        resultB: normalizeAnalysisPayload(rawB, fileB),
        serverComparison: record.comparison ?? record.diff,
      };
    }
  }

  const [resultA, resultB] = await Promise.all([
    analyzeFile(fileA, signal),
    analyzeFile(fileB, signal),
  ]);
  return { resultA, resultB };
}

export async function getAnalysis(id: string, signal?: AbortSignal): Promise<AnalysisResult> {
  const payload = await checkedJson(
    await fetch(apiUrl("/api/v1/analysis/" + encodeURIComponent(id)), { signal }),
  );
  return normalizeAnalysisPayload(payload);
}

export async function getAnalysisSection(
  id: string,
  section: "metadata" | "structure" | "strings",
  signal?: AbortSignal,
): Promise<unknown> {
  return checkedJson(
    await fetch(
      apiUrl("/api/v1/analysis/" + encodeURIComponent(id) + "/" + section),
      { signal },
    ),
  );
}

export async function getHex(
  id: string,
  offset: number,
  length = 512,
  signal?: AbortSignal,
): Promise<unknown> {
  const query = new URLSearchParams({ offset: String(offset), length: String(length) });
  return checkedJson(
    await fetch(
      apiUrl("/api/v1/analysis/" + encodeURIComponent(id) + "/hex?" + query),
      { signal },
    ),
  );
}

export async function getParsers(signal?: AbortSignal): Promise<ParserCapability[]> {
  const payload = await checkedJson(await fetch(apiUrl("/api/v1/parsers"), { signal }));
  const record = asRecord(payload);
  const parsers = Array.isArray(payload) ? payload : record.parsers;
  return asArray<ParserCapability>(parsers);
}

export async function downloadCleanFile(
  id: string,
  originalName: string,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(apiUrl("/api/v1/analysis/" + encodeURIComponent(id) + "/clean"), {
    signal,
  });
  if (!response.ok) throw new Error(await messageFrom(response));
  const blob = await response.blob();
  const cleanName = originalName.replace(/(\.[^.]+)?$/, ".clean$1");
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = cleanName;
  link.click();
  URL.revokeObjectURL(objectUrl);
}
