"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { analyzeFile, getAnalysis } from "../lib/api";
import type { AnalysisResult } from "../lib/types";
import { AnalysisProgress, FileDropzone } from "./file-dropzone";
import { ResultDashboard } from "./result-dashboard";
import { usePreferences } from "./preferences";

export function AnalyzerWorkspace() {
  const { t } = usePreferences();
  const [state, setState] = useState<"idle" | "analyzing" | "complete" | "error">("idle");
  const [file, setFile] = useState<File>();
  const [result, setResult] = useState<AnalysisResult>();
  const [error, setError] = useState("");
  const controller = useRef<AbortController>();

  async function start(selected: File) {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setFile(selected);
    setResult(undefined);
    setError("");
    setState("analyzing");
    try {
      const analysis = await analyzeFile(selected, current.signal);
      setResult(analysis);
      setState("complete");
    } catch (caught) {
      if ((caught as Error).name === "AbortError") {
        setState("idle");
        return;
      }
      setError(caught instanceof Error ? caught.message : "The file could not be analyzed.");
      setState("error");
    }
  }

  function reset() {
    controller.current?.abort();
    setFile(undefined);
    setResult(undefined);
    setError("");
    setState("idle");
    window.history.replaceState(null, "", "/");
  }

  if (state === "complete" && result) return <ResultDashboard result={result} onReset={reset} />;

  return (
    <section className="hero" aria-labelledby="hero-title">
      {state === "idle" && (
        <>
          <div className="hero-copy-block">
            <p className="eyebrow"><span aria-hidden="true" /> {t("universalIntelligence")}</p>
            <h1 id="hero-title">{t("entranceTitle")}</h1>
            <p className="hero-copy">{t("heroCopy")}</p>
          </div>
          <nav className="workspace-modes" aria-label={t("chooseWorkflow")}>
            <Link className="is-active" aria-current="page" href="/">{t("singleFile")}</Link>
            <Link href="/batch">{t("batch")}</Link>
            <Link href="/compare">{t("compare")}</Link>
          </nav>
          <FileDropzone id="single-file" title={t("dropFile")} description={t("clickChoose")} onFiles={(files) => { if (files[0]) void start(files[0]); }} />
          <p className="retention-note"><span aria-hidden="true">◇</span>{t("retention")}</p>
          <div className="trust-row" aria-label="Analysis guarantees">
            <div><b>01</b><span><strong>{t("nativeParsing")}</strong>{t("noExifTool")}</span></div>
            <div><b>02</b><span><strong>{t("privateByDesign")}</strong>{t("noExternalUploads")}</span></div>
            <div><b>03</b><span><strong>{t("evidenceAware")}</strong>{t("observationsNotVerdicts")}</span></div>
          </div>
        </>
      )}
      {state === "analyzing" && file && <AnalysisProgress filename={file.name} onCancel={reset} />}
      {state === "error" && (
        <section className="request-error" role="alert" aria-labelledby="analysis-error-title">
          <span className="error-mark" aria-hidden="true">!</span>
          <p className="eyebrow"><span aria-hidden="true" /> {t("analysisInterrupted")}</p>
          <h1 id="analysis-error-title">{t("couldNotInspect")}</h1>
          <p>{error}</p>
          <div>
            {file && <button className="button button-primary" type="button" onClick={() => void start(file)}>{t("tryAgain")}</button>}
            <button className="button button-quiet" type="button" onClick={reset}>{t("chooseAnother")}</button>
          </div>
        </section>
      )}
    </section>
  );
}

export function AnalysisLoader({ id }: { id: string }) {
  const { t } = usePreferences();
  const [state, setState] = useState<"loading" | "complete" | "error">("loading");
  const [result, setResult] = useState<AnalysisResult>();
  const [error, setError] = useState("");
  const load = useCallback(() => {
    const controller = new AbortController();
    setState("loading");
    setError("");
    getAnalysis(id, controller.signal).then((analysis) => {
      setResult(analysis);
      setState("complete");
    }).catch((caught: unknown) => {
      if ((caught as Error).name === "AbortError") return;
      setError(caught instanceof Error ? caught.message : "This analysis could not be retrieved.");
      setState("error");
    });
    return controller;
  }, [id]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    const controller = load();
    return () => controller.abort();
  }, [load]);

  if (state === "complete" && result) return <ResultDashboard result={result} />;
  if (state === "error") return <section className="request-error" role="alert"><span className="error-mark" aria-hidden="true">!</span><h1>{t("analysisUnavailable")}</h1><p>{error}</p><button className="button button-primary" type="button" onClick={load}>{t("tryAgain")}</button></section>;
  return <AnalysisProgress filename={t("savedAnalysis")} onCancel={() => window.location.assign("/")} message={t("retrieveAnalysis")} />;
}
