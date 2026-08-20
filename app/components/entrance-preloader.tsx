"use client";

import { useEffect, useState } from "react";
import { usePreferences } from "./preferences";

const DURATION_MS = 10_000;

export function EntrancePreloader() {
  const { t } = usePreferences();
  const [visible, setVisible] = useState(true);
  const [remaining, setRemaining] = useState(10);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (window.sessionStorage.getItem("dolosmeta-entrance-seen") === "1") {
      const hideTimer = window.setTimeout(() => setVisible(false), 0);
      return () => window.clearTimeout(hideTimer);
    }

    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      const elapsed = Date.now() - startedAt;
      const nextProgress = Math.min(1, elapsed / DURATION_MS);
      setProgress(nextProgress);
      setRemaining(Math.max(0, Math.ceil((DURATION_MS - elapsed) / 1000)));
      if (nextProgress >= 1) {
        window.clearInterval(timer);
        window.sessionStorage.setItem("dolosmeta-entrance-seen", "1");
        setVisible(false);
      }
    }, 100);

    return () => window.clearInterval(timer);
  }, []);

  function skip() {
    window.sessionStorage.setItem("dolosmeta-entrance-seen", "1");
    setVisible(false);
  }

  if (!visible) return null;

  return (
    <div className="entrance-preloader" role="dialog" aria-modal="true" aria-labelledby="entrance-title">
      <div className="entrance-grid" aria-hidden="true" />
      <div className="entrance-content">
        <div className="entrance-mark" aria-hidden="true">D</div>
        <p className="eyebrow"><span aria-hidden="true" /> {t("localFileIntelligence")}</p>
        <h1 id="entrance-title">{t("entranceTitle")}</h1>
        <p className="entrance-copy">{t("entranceCopy")}</p>
        <div className="entrance-capabilities" aria-label={t("capabilities")}>
          <span>{t("identify")}</span>
          <span>{t("inspect")}</span>
          <span>{t("compare")}</span>
          <span>{t("clean")}</span>
        </div>
        <div className="entrance-progress" aria-hidden="true">
          <i style={{ transform: `scaleX(${progress})` }} />
        </div>
        <div className="entrance-status">
          <span>{t("preparing")}</span>
          <strong>{remaining}s</strong>
        </div>
        <button className="entrance-skip" type="button" onClick={skip}>{t("skipIntro")}</button>
      </div>
    </div>
  );
}