"use client";

import { useState } from "react";

import { triggerImport } from "@/lib/api";
import { type ExportReadinessResponse, type ImportResult } from "@/lib/types";

export function ImportAction({
  jobId,
  exportReadiness,
}: {
  jobId: string;
  exportReadiness: ExportReadinessResponse;
}) {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isReadyToImport = exportReadiness.isReady;
  const primaryBlocker = exportReadiness.blockers[0];

  async function handleImport() {
    if (!isReadyToImport) {
      setError(primaryBlocker ? `Resolve ${primaryBlocker.label.toLowerCase()} before importing.` : "This job is not ready for import yet.");
      return;
    }

    setIsLoading(true);
    setError(null);
    const importExecution = await triggerImport(jobId);
    setIsLoading(false);

    if (!importExecution) {
      setError("Import could not be completed right now.");
      return;
    }

    setResult(importExecution);
  }

  return (
    <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <p className="text-sm font-semibold text-slate-900">Run import</p>
        <p className="mt-1 text-sm text-slate-600">Send the clean dataset into BeyondDegree import flow.</p>
      </div>

      <div className={`rounded-2xl p-4 text-sm ${isReadyToImport ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"}`}>
        <p className="font-semibold">{isReadyToImport ? "This job is ready for import." : "This job still has blockers."}</p>
        <p className="mt-1">
          {isReadyToImport
            ? `You can import ${exportReadiness.exportPreview.totalRecords} prepared rows now.`
            : primaryBlocker
              ? `${primaryBlocker.label} is still affecting ${primaryBlocker.count} rows.`
              : "Finish the remaining required fields before importing."}
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={handleImport}
          disabled={isLoading || !isReadyToImport}
          className="rounded-xl bg-sky-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isLoading ? "Importing..." : "Run Import"}
        </button>
      </div>

      {error ? <p className="text-sm text-rose-600">{error}</p> : null}

      {result ? (
        <div className="rounded-2xl bg-emerald-50 p-4 text-sm text-slate-700">
          <p className="font-semibold text-emerald-800">Import completed</p>
          <p className="mt-2">Status: {result.status}</p>
          <p>Imported records: {result.importedRecords}</p>
          <p>Inserted records: {result.insertedRecords}</p>
          <p>Updated records: {result.updatedRecords}</p>
          <p>Duplicate records: {result.duplicateRecords}</p>
          <p>Total records: {result.totalRecords}</p>
          <p className="mt-2">{result.message}</p>
        </div>
      ) : null}
    </div>
  );
}
