"use client";

import { useRef, useState } from "react";
import { usePreferences } from "./preferences";

export function FileDropzone({
  id,
  multiple = false,
  disabled = false,
  compact = false,
  title,
  description,
  onFiles,
}: {
  id: string;
  multiple?: boolean;
  disabled?: boolean;
  compact?: boolean;
  title: string;
  description: string;
  onFiles: (files: File[]) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const { t } = usePreferences();

  function choose(files: FileList | null) {
    if (!files?.length) return;
    onFiles(Array.from(files));
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div className={"dropzone-wrap" + (compact ? " dropzone-compact" : "")}>
      <input ref={inputRef} className="sr-only" id={id} type="file" multiple={multiple} disabled={disabled} onChange={(event) => choose(event.target.files)} aria-describedby={id + "-description"} />
      <button
        className={"dropzone" + (dragging ? " is-dragging" : "")}
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(event) => { event.preventDefault(); if (!disabled) setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }}
        onDrop={(event) => { event.preventDefault(); setDragging(false); if (!disabled) choose(event.dataTransfer.files); }}
      >
        <span className="dropzone-icon" aria-hidden="true">↑</span>
        <strong>{dragging ? t("releaseInspect") : title}</strong>
        <span id={id + "-description"}>{description}</span>
        {!compact && <span className="format-list" aria-hidden="true">{["images", "documents", "video", "audio", "archives", "binaries"].map((item) => <i key={item}>{t(item)}</i>)}</span>}
      </button>
    </div>
  );
}

export function AnalysisProgress({ filename, onCancel, message = "The server is identifying, hashing, and inspecting this file." }: { filename: string; onCancel: () => void; message?: string }) {
  const { t } = usePreferences();
  return (
    <section className="progress-card" aria-labelledby="analysis-progress-title">
      <div className="progress-orbit" aria-hidden="true"><i /></div>
      <div>
        <p className="eyebrow"><span aria-hidden="true" /> {t("analysisInProgress")}</p>
        <h2 id="analysis-progress-title">{filename}</h2>
        <p>{message === "The server is identifying, hashing, and inspecting this file." ? t("serverInspecting") : message}</p>
        <div className="progress-track" aria-hidden="true"><i /></div>
        <p className="progress-note">{t("activeRequest")}</p>
      </div>
      <button className="button button-quiet" type="button" onClick={onCancel}>{t("cancel")}</button>
    </section>
  );
}
