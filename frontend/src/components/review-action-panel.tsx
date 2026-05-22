"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { submitReviewAction } from "@/lib/api";
import { type ReviewField } from "@/lib/types";

const successActions = {
  ACCEPT: "Suggestion accepted.",
  EDIT: "Edit saved.",
  REJECT: "Field rejected.",
  UNKNOWN: "Field marked unknown.",
} as const;

export function ReviewActionPanel({ recordId, field }: { recordId: string; field: ReviewField }) {
  const router = useRouter();
  const [finalValue, setFinalValue] = useState(field.finalValue === null ? "" : String(field.finalValue));
  const [note, setNote] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [savedValue, setSavedValue] = useState<string | number | boolean | null>(field.finalValue);
  const [isSaving, setIsSaving] = useState(false);

  async function handleAction(action: "ACCEPT" | "EDIT" | "REJECT" | "UNKNOWN") {
    setIsSaving(true);
    setMessage(null);
    const result = await submitReviewAction({
      recordId,
      fieldName: field.fieldName,
      action,
      newValue: action === "EDIT" ? finalValue : null,
      note: note || undefined,
    });
    setIsSaving(false);

    if (!result) {
      setMessage("Review action could not be saved right now.");
      return;
    }

    setSavedValue(result.finalValue);
    setMessage(`${successActions[action]} Final value: ${result.finalValue === null ? "Blank" : String(result.finalValue)}`);
    setNote("");
    router.refresh();
  }

  return (
    <div className="mt-4 space-y-3 rounded-2xl bg-slate-50 p-4">
      <label className="block text-sm">
        <span className="font-medium text-slate-700">Final value</span>
        <input
          value={finalValue}
          onChange={(event) => setFinalValue(event.target.value)}
          className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-slate-900"
        />
      </label>
      <label className="block text-sm">
        <span className="font-medium text-slate-700">Reviewer note</span>
        <textarea
          value={note}
          onChange={(event) => setNote(event.target.value)}
          className="mt-2 min-h-20 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-slate-900"
          placeholder="Optional note for the review log"
        />
      </label>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => handleAction("ACCEPT")}
          disabled={isSaving}
          className="rounded-xl bg-emerald-700 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60"
        >
          Accept suggestion
        </button>
        <button
          type="button"
          onClick={() => handleAction("EDIT")}
          disabled={isSaving}
          className="rounded-xl bg-sky-700 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60"
        >
          Save edit
        </button>
        <button
          type="button"
          onClick={() => handleAction("REJECT")}
          disabled={isSaving}
          className="rounded-xl border border-rose-300 px-3 py-2 text-sm font-semibold text-rose-700 disabled:opacity-60"
        >
          Reject field
        </button>
        <button
          type="button"
          onClick={() => handleAction("UNKNOWN")}
          disabled={isSaving}
          className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 disabled:opacity-60"
        >
          Mark unknown
        </button>
      </div>
      {message ? <p className="text-sm text-slate-600">{message}</p> : null}
      {savedValue !== null ? (
        <p className="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          Saved in clean record: <span className="font-semibold">{String(savedValue)}</span>
        </p>
      ) : null}
      {isSaving ? <p className="text-sm text-slate-500">Refreshing review queue...</p> : null}
    </div>
  );
}
