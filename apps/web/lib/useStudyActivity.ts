"use client";

import { useCallback, useEffect, useRef } from "react";

export const STUDY_IDLE_TIMEOUT_MS = 60_000;

export function useStudyActivity(enabled: boolean) {
  const enabledRef = useRef(enabled);
  const hasActivityRef = useRef(false);
  const lastActivityAtRef = useRef(0);

  useEffect(() => {
    enabledRef.current = enabled;
    if (!enabled) {
      hasActivityRef.current = false;
      lastActivityAtRef.current = 0;
    }
  }, [enabled]);

  const markStudyActivity = useCallback(() => {
    if (!enabledRef.current || document.visibilityState !== "visible" || !document.hasFocus()) return;
    const now = Date.now();
    if (now - lastActivityAtRef.current < 250) return;
    hasActivityRef.current = true;
    lastActivityAtRef.current = now;
  }, []);

  const suspendUntilNextActivity = useCallback(() => {
    lastActivityAtRef.current = 0;
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const activityEvents: Array<keyof WindowEventMap> = [
      "pointerdown",
      "pointermove",
      "keydown",
      "wheel"
    ];
    for (const eventName of activityEvents) {
      window.addEventListener(eventName, markStudyActivity, { passive: true });
    }
    document.addEventListener("input", markStudyActivity, true);
    document.addEventListener("change", markStudyActivity, true);
    document.addEventListener("scroll", markStudyActivity, { capture: true, passive: true });
    window.addEventListener("blur", suspendUntilNextActivity);
    const handleVisibility = () => {
      if (document.visibilityState !== "visible") suspendUntilNextActivity();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      for (const eventName of activityEvents) {
        window.removeEventListener(eventName, markStudyActivity);
      }
      document.removeEventListener("input", markStudyActivity, true);
      document.removeEventListener("change", markStudyActivity, true);
      document.removeEventListener("scroll", markStudyActivity, true);
      window.removeEventListener("blur", suspendUntilNextActivity);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [enabled, markStudyActivity, suspendUntilNextActivity]);

  const shouldCountStudyTime = useCallback(() => (
    enabledRef.current
    && hasActivityRef.current
    && document.visibilityState === "visible"
    && document.hasFocus()
    && Date.now() - lastActivityAtRef.current <= STUDY_IDLE_TIMEOUT_MS
  ), []);

  return { shouldCountStudyTime };
}
