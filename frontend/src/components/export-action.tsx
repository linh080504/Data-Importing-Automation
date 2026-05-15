"use client";

import { useState } from "react";

import { triggerExport } from "@/lib/api";
import { type ExportReadinessResponse, type ExportResult } from "@/lib/types";

export function ExportAction({
  jobId,
  exportReadiness,
}: {
  jobId: string;
  exportReadiness: ExportReadinessResponse;
}) {
  const [isLoading, setIsLoading] = useState(false);
  const [includeMetadata, setIncludeMetadata] = useState(false);
  const [result, setResult] = useState<ExportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isReadyToExport = exportReadiness.isReady;
  const primaryBlocker = exportReadiness.blockers[0];

  async function handleExport(format: "csv" | "xlsx") {
    if (!isReadyToExport) {
      setError(primaryBlocker ? `Resolve ${primaryBlocker.label.toLowerCase()} before exporting.` : "This job is not ready for export yet.");
      return;
    }

    setIsLoading(true);
    setError(null);
    const exportResult = await triggerExport(jobId, format, includeMetadata);
    setIsLoading(false);

    if (!exportResult) {
      setError("Export could not be completed right now.");
      return;
    }

    setResult(exportResult);
  }

  return (
    <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <p className="text-sm font-semibold text-slate-900">Generate export file</p>
        <p className="mt-1 text-sm text-slate-600">Create the clean file for BeyondDegree import.</p>
      </div>

      <div className={`rounded-2xl p-4 text-sm ${isReadyToExport ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"}`}>
        <p className="font-semibold">{isReadyToExport ? "This job is ready for export." : "This job still has blockers."}</p>
        <p className="mt-1">
          {isReadyToExport
            ? `You can export ${exportReadiness.exportPreview.totalRecords} ready rows now.`
            : primaryBlocker
              ? `${primaryBlocker.label} is still affecting ${primaryBlocker.count} rows.`
              : "Finish the remaining required fields before exporting."}
        </p>
      </div>

      <label className="flex items-center gap-3 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={includeMetadata}
          onChange={(event) => setIncludeMetadata(event.target.checked)}
          className="h-4 w-4 rounded border-slate-300"
        />
        Include metadata in the export request
      </label>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => handleExport("csv")}
          disabled={isLoading || !isReadyToExport}
          className="rounded-xl bg-sky-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isLoading ? "Exporting..." : "Export CSV"}
        </button>
        <button
          type="button"
          onClick={() => handleExport("xlsx")}
          disabled={isLoading || !isReadyToExport}
          className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isLoading ? "Exporting..." : "Export XLSX"}
        </button>
      </div>

      {error ? <p className="text-sm text-rose-600">{error}</p> : null}

      {result ? (
        <div className="rounded-2xl bg-emerald-50 p-4 text-sm text-slate-700">
          <p className="font-semibold text-emerald-800">Export created</p>
          <p className="mt-2">Format: {result.format.toUpperCase()}</p>
          <p>Schema: {result.schemaUsed}</p>
          <p>Rows exported: {result.totalExported}</p>
          <p>Metadata included: {result.includeMetadata ? "Yes" : "No"}</p>
          <a href={result.downloadUrl} target="_blank" rel="noreferrer" className="mt-2 inline-block font-semibold text-sky-700 underline">
            Download export file
          </a>
          <p className="mt-2 break-all text-xs text-slate-500">{result.downloadUrl}</p>
        </div>
      ) : null}
    </div>
  );
}
