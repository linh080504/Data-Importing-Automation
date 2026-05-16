"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { deleteCrawlJob } from "@/lib/api";

export function DeleteJobAction({
  jobId,
  redirectTo,
  compact = false,
}: {
  jobId: string;
  redirectTo?: string;
  compact?: boolean;
}) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function handleDelete() {
    setError(null);
    const confirmed = window.confirm(
      "Delete this crawl job and its raw records, AI logs, clean records, and review actions? This cannot be undone.",
    );
    if (!confirmed) return;

    startTransition(async () => {
      const result = await deleteCrawlJob(jobId);
      if (result.error) {
        setError(result.error);
        return;
      }
      if (redirectTo) {
        router.push(redirectTo);
        router.refresh();
        return;
      }
      router.refresh();
    });
  }

  return (
    <div className={compact ? "space-y-1" : "space-y-2 text-right"}>
      <button
        type="button"
        onClick={handleDelete}
        disabled={isPending}
        className={`rounded-xl border border-rose-200 font-semibold text-rose-700 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60 ${
          compact ? "px-3 py-1 text-xs" : "px-4 py-2 text-sm"
        }`}
      >
        {isPending ? "Deleting..." : "Delete"}
      </button>
      {error ? <p className="max-w-xs text-xs leading-5 text-rose-700">{error}</p> : null}
    </div>
  );
}
