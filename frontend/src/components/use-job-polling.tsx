"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getJobProgress, type JobProgressPoll } from "@/lib/api";
import { type JobStatus } from "@/lib/types";

const POLL_INTERVAL_MS = 2000;
const MAX_POLL_DURATION_MS = 10 * 60 * 1000;

function isTerminalStatus(status: JobStatus): boolean {
  return !["QUEUED", "CRAWLING", "EXTRACTING", "CLEANING"].includes(status);
}

export type PollingState = {
  isPolling: boolean;
  status: JobStatus | null;
  progress: JobProgressPoll["progress"] | null;
  error: string | null;
};

/**
 * Poll the job detail endpoint at a fixed interval while the job is being
 * processed. Automatically stops when the job reaches a terminal status
 * (READY_TO_EXPORT, NEEDS_REVIEW, EXPORTED, FAILED) or when the maximum
 * polling duration is exceeded.
 *
 * Follows the same API layer conventions as the rest of the frontend — all
 * data fetching goes through ``@/lib/api`` functions.
 */
export function useJobPolling(
  jobId: string,
  initialStatus: JobStatus,
  initialProgress?: JobProgressPoll["progress"],
  onComplete?: () => void,
): PollingState {
  const [state, setState] = useState<PollingState>({
    isPolling: !isTerminalStatus(initialStatus),
    status: initialStatus,
    progress: initialProgress ?? null,
    error: initialStatus === "FAILED" ? "Pipeline failed. Check backend logs." : null,
  });

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startedRef = useRef<number>(0);
  const mountedRef = useRef(true);

  const stopPolling = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (mountedRef.current) {
      setState((prev) => ({ ...prev, isPolling: false }));
    }
  }, []);

  const poll = useCallback(async () => {
    if (!mountedRef.current) return;

    if (Date.now() - startedRef.current > MAX_POLL_DURATION_MS) {
      stopPolling();
      setState((prev) => ({ ...prev, error: "Polling timed out." }));
      return;
    }

    const result = await getJobProgress(jobId);
    if (!mountedRef.current) return;

    if (result === null) {
      return;
    }

    setState((prev) => ({
      ...prev,
      status: result.status,
      progress: result.progress,
      error: result.status === "FAILED" ? "Pipeline failed. Check backend logs." : null,
    }));

    if (isTerminalStatus(result.status)) {
      stopPolling();
      onComplete?.();
    }
  }, [jobId, stopPolling, onComplete]);

  useEffect(() => {
    mountedRef.current = true;
    startedRef.current = Date.now();

    if (isTerminalStatus(initialStatus)) {
      return;
    }

    timerRef.current = setInterval(poll, POLL_INTERVAL_MS);
    const initialPollTimer = setTimeout(poll, 0);

    return () => {
      mountedRef.current = false;
      clearTimeout(initialPollTimer);
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [jobId, initialStatus, poll]);

  return state;
}
