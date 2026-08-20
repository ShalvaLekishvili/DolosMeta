export type JsonRecord = Record<string, unknown>;

export type Severity = "info" | "low" | "moderate" | "medium" | "high" | "critical" | "warning" | "error";

export interface FileInfo extends JsonRecord {
  name?: string;
  size?: number;
  extension?: string;
  mime?: string;
  declared_mime?: string;
  detected_mime?: string;
  detected_format?: string;
  format?: string;
  signature_match?: boolean;
}

export interface Finding extends JsonRecord {
  code?: string;
  title?: string;
  message?: string;
  description?: string;
  category?: string;
  severity?: Severity | string;
  points?: number;
}

export interface TimelineEvent extends JsonRecord {
  timestamp?: string;
  date?: string;
  label?: string;
  title?: string;
  description?: string;
  source?: string;
  kind?: "observed" | "derived" | "inference" | string;
  confidence?: string;
}

export interface StructureNode extends JsonRecord {
  name?: string;
  label?: string;
  type?: string;
  offset?: number;
  size?: number;
  length?: number;
  description?: string;
  children?: StructureNode[];
}

export interface PrivacyResult extends JsonRecord {
  score?: number;
  level?: string;
  findings?: Array<Finding | string>;
}

export interface ForensicsResult extends JsonRecord {
  findings?: Array<Finding | string>;
  warnings?: Array<Finding | string>;
  anomalies?: Array<Finding | string>;
}

export interface AnalysisResult extends JsonRecord {
  id?: string;
  analysis_id?: string;
  analysis_version?: string;
  file?: FileInfo;
  hashes?: Record<string, string>;
  metadata?: JsonRecord;
  normalized?: JsonRecord;
  raw?: unknown;
  raw_metadata?: unknown;
  structure?: StructureNode[];
  timeline?: TimelineEvent[];
  strings?: unknown[];
  hex?: unknown;
  privacy?: PrivacyResult;
  forensics?: ForensicsResult;
  warnings?: Array<Finding | string>;
  parser?: {
    name?: string;
    version?: string;
    [key: string]: unknown;
  };
  engine?: {
    name?: string;
    version?: string;
    [key: string]: unknown;
  };
}

export interface MetadataEntry {
  path: string;
  label: string;
  category: string;
  value: unknown;
  displayValue: string;
  source: string;
}

export interface ParserCapability extends JsonRecord {
  name?: string;
  parser?: string;
  format?: string;
  formats?: string[];
  extensions?: string[];
  mime_types?: string[];
  metadata?: string | boolean;
  structure?: string | boolean;
  privacy?: string | boolean;
  version?: string;
}

export interface CompareRow {
  path: string;
  label: string;
  category: string;
  valueA?: unknown;
  valueB?: unknown;
  displayA: string;
  displayB: string;
  status: "added" | "removed" | "changed" | "same";
}

export interface BatchItem {
  key: string;
  file: File;
  status: "queued" | "analyzing" | "complete" | "error";
  result?: AnalysisResult;
  error?: string;
}
