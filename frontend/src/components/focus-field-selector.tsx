"use client";

import { useCallback, useMemo, useState, useTransition } from "react";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");

type FocusFieldSelectorProps = {
  jobId: string;
  /** All available fields from the dataset columns */
  availableFields: string[];
  /** Currently selected focus fields (critical_fields from the job) */
  initialFocusFields: string[];
};

export function FocusFieldSelector({
  jobId,
  availableFields,
  initialFocusFields,
}: FocusFieldSelectorProps) {
  const availableFieldSet = useMemo(() => new Set(availableFields), [availableFields]);
  const initialTemplateFocusFields = useMemo(
    () => initialFocusFields.filter((field) => availableFieldSet.has(field)),
    [availableFieldSet, initialFocusFields],
  );
  const [focusFields, setFocusFields] = useState<Set<string>>(new Set(initialTemplateFocusFields));
  const [isPending, startTransition] = useTransition();
  const [lastSaved, setLastSaved] = useState<string[]>(initialFocusFields);

  const toggle = useCallback(
    (field: string) => {
      setFocusFields((prev) => {
        const next = new Set(prev);
        if (next.has(field)) {
          // Keep at least one focus field so the extractor has a target.
          if (next.size <= 1) return prev;
          next.delete(field);
        } else {
          next.add(field);
        }
        return next;
      });
    },
    [],
  );

  const save = useCallback(() => {
    const fields = Array.from(focusFields).filter((field) => availableFieldSet.has(field));
    startTransition(async () => {
      try {
        const response = await fetch(`${API_BASE}/crawl-jobs/${jobId}/focus-fields`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ focus_fields: fields }),
        });
        if (response.ok) {
          setLastSaved(fields);
        }
      } catch {
        // Keep the unsaved state visible so the user can retry.
      }
    });
  }, [availableFieldSet, focusFields, jobId]);

  const hasChanges = JSON.stringify(Array.from(focusFields).sort()) !== JSON.stringify(lastSaved.slice().sort());

  if (availableFields.length === 0) return null;

  return (
    <div className="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-900">Focus fields</h3>
          <p className="mt-0.5 break-words text-xs text-slate-500">
            Focus fields get deeper crawling, extraction, judging, and review. Non-focus fields are kept only when source evidence exists.
          </p>
        </div>
        {hasChanges ? (
          <button
            type="button"
            onClick={save}
            disabled={isPending}
            className="inline-flex items-center rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-sky-700 disabled:opacity-50"
          >
            {isPending ? "Saving..." : "Save changes"}
          </button>
        ) : null}
      </div>
      <div className="mt-3 flex min-w-0 flex-wrap gap-2">
        {availableFields.map((field) => {
          const isActive = focusFields.has(field);
          return (
            <button
              key={field}
              type="button"
              onClick={() => toggle(field)}
              className={`inline-flex max-w-full items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                isActive
                  ? "border-sky-200 bg-sky-50 text-sky-800 shadow-sm"
                  : "border-slate-200 bg-slate-50 text-slate-500 hover:bg-slate-100"
              }`}
            >
              {isActive ? (
                <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clipRule="evenodd" />
                </svg>
              ) : (
                <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path d="M10 3a.75.75 0 01.75.75v5.5h5.5a.75.75 0 010 1.5h-5.5v5.5a.75.75 0 01-1.5 0v-5.5h-5.5a.75.75 0 010-1.5h5.5v-5.5A.75.75 0 0110 3z" />
                </svg>
              )}
              <span className="min-w-0 break-all">{field}</span>
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-slate-400">
        {focusFields.size}/{availableFields.length} fields focused
      </p>
    </div>
  );
}
