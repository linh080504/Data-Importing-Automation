"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";

import { runCrawlJob } from "@/lib/api";
import { type JobStatus } from "@/lib/types";
import { useJobPolling } from "@/components/use-job-polling";

function ProgressBar({ value, max }: { value: number; max: number }) {
  const percent = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>
          {value} / {max} records
        </span>
        <span>{percent}%</span>
      </div>
      <div className="h-2.5 w-full rounded-full bg-slate-200">
        <div
          className="h-2.5 rounded-full bg-sky-600 transition-all duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

function phaseLabel(status: JobStatus | null): string {
  if (status === "CRAWLING") return "Crawling sources…";
  if (status === "EXTRACTING") return "Extracting fields…";
  if (status === "CLEANING") return "Cleaning records…";
  return "Processing…";
}

export function RunJobAction({
  jobId,
  initialStatus,
  initialProgress,
}: {
  jobId: string;
  initialStatus: JobStatus;
  initialProgress?: Parameters<typeof useJobPolling>[2];
}) {
  const router = useRouter();
  const [isStarting, setIsStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [triggered, setTriggered] = useState(false);

  const effectiveInitialStatus = triggered ? "CRAWLING" as JobStatus : initialStatus;

  const handleComplete = useCallback(() => {
    router.refresh();
  }, [router]);

  const polling = useJobPolling(jobId, effectiveInitialStatus, triggered ? undefined : initialProgress, handleComplete);

  async function handleRun() {
    setIsStarting(true);
    setStartError(null);

    const outcome = await runCrawlJob(jobId);
    setIsStarting(false);

    if (!outcome.ok) {
      setStartError(outcome.error);
      return;
    }

    setTriggered(true);
  }

  const isProcessing = polling.isPolling || isStarting;
  const progress = polling.progress;

  return (
    <div className="flex w-full max-w-md flex-col items-stretch gap-3 sm:items-end">
      <div className="flex flex-col gap-2 sm:items-end">
        <button
          type="button"
          onClick={handleRun}
          disabled={isProcessing}
          className="rounded-xl bg-sky-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isStarting ? "Starting…" : isProcessing ? "Running pipeline…" : "Run again"}
        </button>
        {!isProcessing ? (
          <p className="text-xs text-slate-500 sm:text-right">
            This button calls the backend to crawl and reprocess your selected sources. The page will
            update automatically while the pipeline runs.
          </p>
        ) : null}
      </div>

      {polling.isPolling && progress ? (
        <div className="w-full space-y-3 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-sky-600" />
            <p className="text-sm font-semibold text-sky-900">{phaseLabel(polling.status)}</p>
          </div>
          <ProgressBar value={progress.extracted} max={progress.totalRecords} />
          <div className="flex flex-wrap gap-3 text-xs text-sky-800">
            <span>Crawled {progress.crawled}</span>
            <span>·</span>
            <span>Extracted {progress.extracted}</span>
            <span>·</span>
            <span>Cleaned {progress.cleaned}</span>
            {progress.needsReview > 0 ? (
              <>
                <span>·</span>
                <span className="font-semibold text-amber-700">
                  {progress.needsReview} need review
                </span>
              </>
            ) : null}
          </div>
        </div>
      ) : null}

      {polling.isPolling && !progress ? (
        <p
          className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900"
          role="status"
          aria-live="polite"
        >
          Waiting for the backend to start processing…
        </p>
      ) : null}

      {polling.status && !polling.isPolling && polling.progress ? (
        <p
          className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900"
          role="status"
          aria-live="polite"
        >
          Pipeline complete. Processed {polling.progress.extracted}/{polling.progress.totalRecords}{" "}
          records, {polling.progress.cleaned} cleaned.
        </p>
      ) : null}

      {polling.error ? (
        <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900" role="alert">
          {polling.error}
        </p>
      ) : null}

      {startError ? (
        <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900" role="alert">
          {startError}
        </p>
      ) : null}
    </div>
  );
}
