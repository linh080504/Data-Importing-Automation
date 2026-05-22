import Link from "next/link";

import { type ActivityItem, type CleanDataResponse, type CrawledFieldSnapshot, type ExportReadinessResponse, type JobDetailHeader, type OverviewResponse, type ReviewField, type ReviewQueueData } from "@/lib/types";
import { Card, DonutStat, LinkButton, MetricCard, PageHeader, PriorityColumnHeader, StatusBadge, Stepper } from "@/components/ui";
import { DeleteJobAction } from "@/components/delete-job-action";
import { ExportAction } from "@/components/export-action";
import { FieldIssueBreakdown } from "@/components/field-issue-breakdown";
import { FocusFieldSelector } from "@/components/focus-field-selector";
import { ImportAction } from "@/components/import-action";
import { JobTabs } from "@/components/job-tabs";
import { OnboardingGuide } from "@/components/onboarding-guide";
import { ReviewActionPanel } from "@/components/review-action-panel";
import { RunJobAction } from "@/components/run-job-action";
import { BeforeAfterBars, ComparisonBars } from "@/components/simple-chart";

function formatFieldValue(value: string | number | boolean | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return <span className="inline-flex rounded-md bg-slate-100 border border-slate-200 px-2 py-0.5 text-xs font-bold text-slate-500 uppercase tracking-wider">Blank</span>;
  }
  return String(value);
}

function hasEvidence(field: ReviewField) {
  return Boolean(field.sourceExcerpt || field.evidenceUrl || field.evidenceSource || field.mergeSourceName);
}

function fieldStatusTone(status: string) {
  if (status === "captured") return "bg-emerald-50 text-emerald-700 border border-emerald-200";
  if (status === "missing") return "bg-rose-50 text-rose-700 border border-rose-200";
  return "bg-amber-50 text-amber-700 border border-amber-200";
}

function formatStatusLabel(status: string) {
  return status.replaceAll("_", " ");
}

function fieldDecisionTone(field: ReviewField) {
  if (field.issueType === "missing") return "bg-rose-50 text-rose-700 border border-rose-200";
  if (hasEvidence(field)) return "bg-emerald-50 text-emerald-700 border border-emerald-200";
  return "bg-amber-50 text-amber-700 border border-amber-200";
}

function fieldDomId(fieldName: string) {
  return `review-field-${fieldName.replace(/[^a-zA-Z0-9_-]+/g, "-")}`;
}

function FieldDecisionSummary({ fields }: { fields: ReviewField[] }) {
  if (fields.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-100 text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-4 py-3 text-left font-bold uppercase tracking-wider text-xs">Field</th>
              <th className="px-4 py-3 text-left font-bold uppercase tracking-wider text-xs">Problem</th>
              <th className="min-w-[14rem] px-4 py-3 text-left font-bold uppercase tracking-wider text-xs">Suggested value</th>
              <th className="px-4 py-3 text-left font-bold uppercase tracking-wider text-xs">Evidence</th>
              <th className="px-4 py-3 text-left font-bold uppercase tracking-wider text-xs">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {fields.map((field) => (
              <tr key={field.fieldName} className="hover:bg-slate-50/50 transition-colors">
                <td className="px-4 py-3 font-bold text-slate-900">{field.fieldName}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider ${fieldDecisionTone(field)}`}>
                    {field.issueType}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-700">
                  <div className="max-w-sm whitespace-pre-wrap break-words font-medium">{formatFieldValue(field.suggestedValue)}</div>
                </td>
                <td className="px-4 py-3 text-slate-700">
                  {field.evidenceUrl ? (
                    <a 
                      href={field.evidenceUrl} 
                      target="_blank" 
                      rel="noreferrer" 
                      className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 border border-emerald-200 px-2.5 py-1 text-xs font-bold text-emerald-700 hover:bg-emerald-100 transition-all"
                    >
                      <span>🌐 Link</span>
                    </a>
                  ) : hasEvidence(field) ? (
                    <span className="text-xs font-semibold text-slate-600 bg-slate-100 border border-slate-200 rounded-md px-2 py-0.5">{field.evidenceSource ?? "Excerpt Attached"}</span>
                  ) : (
                    <span className="text-xs font-semibold text-slate-500">None</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <a href={`#${fieldDomId(field.fieldName)}`} className="text-xs font-bold text-sky-600 hover:text-sky-700 hover:underline">
                    Go Review
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CrawledDataCard({ fields }: { fields: CrawledFieldSnapshot[] }) {
  return (
    <Card title="Crawled school data" aside={<span className="text-xs font-bold uppercase tracking-wider text-slate-500 bg-slate-100 border border-slate-200 px-2.5 py-1 rounded-md">{fields.length} fields</span>}>
      {fields.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-500 text-center">
          No crawled field snapshot is available for this record.
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="w-44 px-4 py-3 text-left font-bold uppercase tracking-wider text-xs">Field</th>
                  <th className="min-w-[16rem] px-4 py-3 text-left font-bold uppercase tracking-wider text-xs">Crawled value</th>
                  <th className="min-w-[16rem] px-4 py-3 text-left font-bold uppercase tracking-wider text-xs">Source / Evidence</th>
                  <th className="w-48 px-4 py-3 text-left font-bold uppercase tracking-wider text-xs">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {fields.map((field) => (
                  <tr key={field.fieldName} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-4 py-3 font-bold text-slate-900 align-top">{field.fieldName}</td>
                    <td className="px-4 py-3 text-slate-700 align-top">
                      <div className="max-w-xl whitespace-pre-wrap break-words font-medium">{formatFieldValue(field.value)}</div>
                    </td>
                    <td className="px-4 py-3 text-slate-700 align-top">
                      <div className="max-w-xl space-y-2 break-words">
                        {field.sourceName ? <p className="font-bold text-slate-600 text-xs uppercase tracking-wider bg-slate-100 border border-slate-200 inline-block px-2.5 py-0.5 rounded-md">{field.sourceName}</p> : null}
                        {field.sourceUrl ? (
                          <div className="mt-1">
                            <a 
                              href={field.sourceUrl} 
                              target="_blank" 
                              rel="noreferrer" 
                              className="inline-flex items-center gap-1 rounded-lg bg-sky-50 border border-sky-200 px-2.5 py-1 text-xs font-bold text-sky-700 hover:bg-sky-100 transition-all"
                            >
                              <span>🌐 Open evidence source</span>
                            </a>
                          </div>
                        ) : null}
                        {field.sourceExcerpt ? (
                          <div className="relative overflow-hidden rounded-lg bg-slate-50 border border-slate-200 p-3 mt-1.5">
                            <div className="absolute left-0 top-0 bottom-0 w-1 bg-sky-500" />
                            <p className="text-[11px] leading-relaxed text-slate-600 italic">"{field.sourceExcerpt}"</p>
                          </div>
                        ) : null}
                        {!field.sourceName && !field.sourceUrl && !field.sourceExcerpt ? <span className="text-slate-400 text-xs">No evidence attached</span> : null}
                      </div>
                    </td>
                    <td className="px-4 py-3 align-top">
                      <span className={`inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider ${fieldStatusTone(field.status)}`}>
                        {formatStatusLabel(field.status)}
                      </span>
                      {field.reason ? <p className="mt-2 text-xs leading-relaxed text-slate-500 font-medium">{field.reason}</p> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
}

function CrawledRecordsPanel({ jobId, records }: { jobId: string; records: OverviewResponse["crawledRecords"] }) {
  const selected = records.selectedDetail;
  const totalPages = Math.max(1, Math.ceil(records.total / records.pageSize));
  const previousPage = Math.max(1, records.page - 1);
  const nextPage = Math.min(totalPages, records.page + 1);

  return (
    <Card title="All crawled records" aside={<span className="text-xs font-bold uppercase tracking-wider text-slate-500 bg-slate-100 border border-slate-200 px-2 py-1 rounded-md">{records.total} collected / 6 per page</span>}>
      <div className="grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
        <div className="space-y-3">
          {records.items.length === 0 ? (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-500 text-center">
              No crawled records are available yet.
            </div>
          ) : null}
          {records.items.map((record) => {
            const isSelected = record.rawRecordId === records.selectedRecordId;
            return (
              <Link
                key={record.rawRecordId}
                href={`/crawl-jobs/${jobId}?tab=overview&recordPage=${records.page}&rawRecord=${record.rawRecordId}`}
                className={`block rounded-2xl border p-4 transition-all duration-200 ${
                  isSelected 
                    ? "border-sky-500 bg-sky-50/60 shadow-sm" 
                    : "border-slate-200 bg-white hover:bg-slate-50 hover:translate-x-1"
                }`}
              >
                <p className="break-words font-bold text-slate-900 text-base">{record.displayName}</p>
                <div className="mt-2 space-y-1 text-xs text-slate-500">
                  {record.country ? <p className="flex items-center gap-1">📍 {record.country}</p> : null}
                  {record.sourceName ? <p className="flex items-center gap-1">🔗 Source: {record.sourceName}</p> : null}
                  <p className="break-all font-mono text-[10px] opacity-75">ID: {record.uniqueKey}</p>
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs">
                  <span className="rounded-full bg-slate-100 border border-slate-200 px-2.5 py-0.5 font-bold uppercase text-[10px] text-slate-600">
                    {record.status ?? "NO STATUS"}
                  </span>
                  <span className="font-bold text-sky-700 bg-sky-50 border border-sky-200 px-2 py-0.5 rounded-md text-[10px] uppercase tracking-wider">
                    Score: {record.qualityScore === null ? "N/A" : `${record.qualityScore}%`}
                  </span>
                </div>
              </Link>
            );
          })}
          <div className="flex items-center justify-between gap-3 text-sm pt-2">
            <Link
              href={`/crawl-jobs/${jobId}?tab=overview&recordPage=${previousPage}`}
              className={`rounded-xl border px-3 py-2 text-xs font-bold uppercase tracking-wider transition ${records.page <= 1 ? "pointer-events-none border-slate-200 text-slate-400" : "border-slate-200 text-slate-600 bg-white hover:bg-slate-50"}`}
            >
              Previous
            </Link>
            <span className="text-xs font-semibold text-slate-500">Page {records.page} / {totalPages}</span>
            <Link
              href={`/crawl-jobs/${jobId}?tab=overview&recordPage=${nextPage}`}
              className={`rounded-xl border px-3 py-2 text-xs font-bold uppercase tracking-wider transition ${records.page >= totalPages ? "pointer-events-none border-slate-200 text-slate-400" : "border-slate-200 text-slate-600 bg-white hover:bg-slate-50"}`}
            >
              Next
            </Link>
          </div>
        </div>

        <div className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          {selected ? (
            <div className="space-y-4">
              <div className="border-b border-slate-100 pb-4">
                <p className="break-words text-xl font-bold tracking-tight text-slate-900">{selected.displayName}</p>
                <div className="mt-2 space-y-1.5 text-xs text-slate-500">
                  <p className="font-mono">Raw record: {selected.rawRecordId}</p>
                  {selected.sourceUrl ? (
                    <div className="mt-2">
                      <a 
                        href={selected.sourceUrl} 
                        target="_blank" 
                        rel="noreferrer" 
                        className="inline-flex items-center gap-1.5 rounded-lg bg-sky-50 border border-sky-200 px-3 py-1.5 text-xs font-bold text-sky-700 hover:bg-sky-100 transition-all"
                      >
                        <span>🌐 Open original page source</span>
                      </a>
                    </div>
                  ) : null}
                </div>
              </div>
              <div className="max-h-[34rem] overflow-auto rounded-xl border border-slate-200 bg-slate-50/50">
                <table className="min-w-full divide-y divide-slate-100 text-sm">
                  <thead className="sticky top-0 bg-slate-100 text-slate-600">
                    <tr>
                      <th className="w-48 px-4 py-3 text-left font-bold text-slate-500 uppercase tracking-wider text-xs">Field</th>
                      <th className="min-w-[14rem] px-4 py-3 text-left font-bold text-slate-500 uppercase tracking-wider text-xs">Clean</th>
                      <th className="min-w-[14rem] px-4 py-3 text-left font-bold text-slate-500 uppercase tracking-wider text-xs">Raw</th>
                      <th className="w-48 px-4 py-3 text-left font-bold text-slate-500 uppercase tracking-wider text-xs">Source info</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {selected.fields.map((field) => (
                      <tr key={field.fieldName} className="hover:bg-slate-50 transition-colors">
                        <td className="px-4 py-3 font-bold text-slate-900">{field.fieldName}</td>
                        <td className="px-4 py-3 text-slate-700">
                          <div className="max-w-md whitespace-pre-wrap break-words font-medium">{formatFieldValue(field.cleanValue)}</div>
                        </td>
                        <td className="px-4 py-3 text-slate-500">
                          <div className="max-w-md whitespace-pre-wrap break-words font-medium text-xs">{formatFieldValue(field.rawValue)}</div>
                        </td>
                        <td className="px-4 py-3 text-slate-500">
                          <div className="space-y-1 text-xs">
                            {field.sourceName ? <p className="font-semibold text-slate-600">{field.sourceName}</p> : <p className="text-slate-400">No source field</p>}
                            {field.fromSecondary ? <p className="text-[10px] font-bold text-sky-600 uppercase tracking-wider">Secondary fill</p> : null}
                            {field.conflicts.length > 0 ? <p className="text-[10px] font-bold text-amber-600 uppercase tracking-wider">{field.conflicts.length} conflicts</p> : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center rounded-xl bg-slate-50 border border-dashed border-slate-200 p-8 text-sm text-slate-400">
              Select a crawled record to inspect its fields.
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

function OverviewTab({ overviewData, jobId }: { overviewData: OverviewResponse; jobId: string }) {
  return (
    <div className="space-y-6">
      {/* 1. Stat cards grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <MetricCard label="Collected rows" value={String(overviewData.summary.totalRecords)} subtext="Live rows collected from active sources" />
        <MetricCard label="Clean candidates" value={String(overviewData.summary.cleanRecords)} subtext="Structured rows shaped to template schema" />
        <MetricCard label="Need review" value={String(overviewData.summary.needReviewCount)} subtext="Blocked candidates requiring validation" />
        <MetricCard label="Rejected" value={String(overviewData.summary.rejectedCount)} subtext="Excluded candidates" />
        <MetricCard label="Secondary fills" value={String(overviewData.summary.mergeSecondaryFieldCount)} subtext="Values populated from supporting sites" />
        <MetricCard label="Conflicts" value={String(overviewData.summary.mergeConflictFieldCount)} subtext="Fields with source disagreements" />
      </div>

      {/* 2. Side-by-side Top Quality Chart and Next Action Banner */}
      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card title="Quality and import readiness">
          <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
              <DonutStat label="Overall quality" value={overviewData.analyze.overallQuality} hint="Completeness and standardization score." />
              <DonutStat label="Import readiness" value={overviewData.analyze.importReadiness} hint="Proximity to BeyondDegree CSV import layout." />
            </div>
            <ComparisonBars
              items={overviewData.analyze.rawVsCleanByField.map((item) => ({
                label: item.field,
                leftLabel: "Raw",
                leftValue: item.rawValue,
                rightLabel: "Clean",
                rightValue: item.cleanValue,
              }))}
            />
          </div>
        </Card>

        <Card title="Next recommended action">
          <div className="space-y-5">
            <div className="rounded-2xl bg-gradient-to-r from-sky-50/50 via-indigo-50/30 to-white border border-sky-200/60 p-5 shadow-sm">
              <div className="flex items-center gap-3">
                <span className="text-2xl">⚡</span>
                <div>
                  <p className="text-base font-bold text-slate-900 tracking-tight">{overviewData.nextAction.title}</p>
                  <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{overviewData.nextAction.description}</p>
                </div>
              </div>
              <div className="mt-4">
                <LinkButton href={`?tab=${overviewData.nextAction.primaryTarget}`}>{overviewData.nextAction.primaryLabel}</LinkButton>
              </div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">Top issues to focus on</p>
              <div className="space-y-2.5">
                {overviewData.topIssues.map((issue) => (
                  <div key={issue.label} className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50/80 px-3.5 py-2.5 text-xs shadow-sm">
                    <span className="font-semibold text-slate-700">{issue.label}</span>
                    <span className="font-extrabold text-slate-800 bg-slate-100 border border-slate-200 rounded-md px-2 py-0.5">{issue.count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* 3. All crawled records browser */}
      <CrawledRecordsPanel jobId={jobId} records={overviewData.crawledRecords} />

      {/* 4. Secondary metrics */}
      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Issue trend after cleaning">
          <BeforeAfterBars items={overviewData.analyze.issueTrend} />
        </Card>

        <Card title="Source contribution by field">
          <ComparisonBars
            items={overviewData.analyze.mergeCoverage.map((item) => ({
              label: item.label,
              leftLabel: "Primary",
              leftValue: item.primaryValue,
              rightLabel: "Secondary",
              rightValue: item.secondaryValue,
            }))}
          />
          <div className="mt-5 space-y-2.5 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-xs">
            <p className="font-bold text-slate-700 uppercase tracking-wider text-[11px] mb-1">Conflicts requiring attention</p>
            {overviewData.analyze.mergeCoverage.map((item) => (
              <div key={item.label} className="flex items-center justify-between rounded-xl border border-slate-100 bg-white px-3.5 py-2.5 shadow-sm">
                <span className="font-semibold text-slate-600">{item.label}</span>
                <span className={`font-bold rounded-md px-2 py-0.5 ${item.conflictValue > 0 ? "text-amber-700 bg-amber-50 border border-amber-200" : "text-slate-500 bg-slate-100 border border-slate-200"}`}>
                  {item.conflictValue} conflict{item.conflictValue !== 1 ? "s" : ""}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {overviewData.fieldIssues.length > 0 ? (
        <Card title="Field issue breakdown" aside={<span className="text-xs font-bold uppercase tracking-wider text-slate-500 bg-slate-100 border border-slate-200 px-2 py-1 rounded-md">{overviewData.fieldIssues.length} issues</span>}>
          <FieldIssueBreakdown fieldIssues={overviewData.fieldIssues} />
        </Card>
      ) : null}
    </div>
  );
}

function ReviewTab({
  status,
  reviewQueue,
  jobId,
}: {
  status: JobDetailHeader["status"];
  reviewQueue: ReviewQueueData;
  jobId: string;
}) {
  const reviewDetail = reviewQueue.selectedDetail;
  const reviewTotalPages = Math.max(1, Math.ceil(reviewQueue.total / reviewQueue.limit));
  const previousReviewPage = Math.max(1, reviewQueue.page - 1);
  const nextReviewPage = Math.min(reviewTotalPages, reviewQueue.page + 1);

  return (
    <div className="grid min-w-0 max-w-full gap-6 xl:grid-cols-[minmax(20rem,25rem)_minmax(0,1fr)]">
      {/* LEFT COL: REVIEW QUEUE */}
      <Card title="Review queue" aside={<span className="text-xs font-bold uppercase tracking-wider text-slate-500 bg-slate-100 border border-slate-200 px-2 py-1 rounded-md">{reviewQueue.total} records</span>}>
        <div className="space-y-3">
          {reviewQueue.items.length === 0 ? (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-500 text-center">
              No records currently need manual review.
            </div>
          ) : null}
          {reviewQueue.items.map((item) => {
            const isSelected = item.recordId === reviewQueue.selectedRecordId;
            return (
              <Link
                key={item.recordId}
                href={`/crawl-jobs/${jobId}?tab=review&reviewPage=${reviewQueue.page}&record=${item.recordId}`}
                className={`block rounded-2xl border p-4 transition-all duration-200 ${
                  isSelected 
                    ? "border-sky-500 bg-sky-50/60 shadow-sm" 
                    : "border-slate-200 bg-white hover:bg-slate-50 hover:translate-x-1"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="break-words font-bold text-slate-900 text-base leading-snug">{item.displayName}</p>
                    <p className="mt-1.5 break-all font-mono text-[10px] text-slate-500 opacity-75">Source key: {item.uniqueKey}</p>
                    {item.sourceName ? <p className="mt-1 text-xs text-slate-500 font-medium">🌐 {item.sourceName}</p> : null}
                  </div>
                  <span className="rounded-full bg-rose-50 border border-rose-200 px-2.5 py-0.5 text-[10px] font-extrabold uppercase text-rose-700 shrink-0">
                    {item.flaggedFieldCount} issue{item.flaggedFieldCount !== 1 ? "s" : ""}
                  </span>
                </div>
                <div className="mt-4 flex items-center justify-between text-xs font-semibold">
                  <span className="text-sky-700 bg-sky-50 border border-sky-200 px-2 py-0.5 rounded-md text-[10px] uppercase tracking-wider">
                    Confidence: {item.confidence === null ? "N/A" : `${item.confidence}%`}
                  </span>
                  {isSelected ? <span className="font-bold text-sky-600 animate-pulse uppercase tracking-wider text-[10px]">Active</span> : null}
                </div>
              </Link>
            );
          })}
          {reviewQueue.total > reviewQueue.limit ? (
            <div className="flex items-center justify-between gap-3 text-sm pt-2">
              <Link
                href={`/crawl-jobs/${jobId}?tab=review&reviewPage=${previousReviewPage}`}
                className={`rounded-xl border px-3 py-2 text-xs font-bold uppercase tracking-wider transition ${reviewQueue.page <= 1 ? "pointer-events-none border-slate-200 text-slate-400" : "border-slate-200 text-slate-600 bg-white hover:bg-slate-50"}`}
              >
                Previous
              </Link>
              <span className="text-xs font-semibold text-slate-500">Page {reviewQueue.page} / {reviewTotalPages}</span>
              <Link
                href={`/crawl-jobs/${jobId}?tab=review&reviewPage=${nextReviewPage}`}
                className={`rounded-xl border px-3 py-2 text-xs font-bold uppercase tracking-wider transition ${reviewQueue.page >= reviewTotalPages ? "pointer-events-none border-slate-200 text-slate-400" : "border-slate-200 text-slate-600 bg-white hover:bg-slate-50"}`}
              >
                Next
              </Link>
            </div>
          ) : null}
        </div>
      </Card>

      {/* RIGHT COL: WORKSPACE */}
      <div className="min-w-0 space-y-6">
        {/* Detail Header Hero */}
        <div className="rounded-2xl border border-slate-200 bg-gradient-to-r from-slate-50 via-indigo-50/20 to-white p-6 shadow-sm">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div className="min-w-0">
              <p className="text-xs uppercase tracking-[0.2em] text-sky-600 font-bold">Record Needing Review</p>
              <h3 className="text-2xl font-extrabold text-slate-950 mt-1 break-words leading-tight">{reviewDetail.displayName}</h3>
              <div className="flex flex-wrap items-center gap-3 mt-3 text-xs">
                {reviewDetail.sourceName && (
                  <span className="rounded-full bg-slate-100 px-3 py-1 font-bold border border-slate-200 text-slate-600">Source: {reviewDetail.sourceName}</span>
                )}
                <span className="font-mono text-slate-500 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded-md">Key: {reviewDetail.uniqueKey}</span>
                {reviewDetail.confidence !== null && (
                  <span className="rounded-full bg-sky-50 px-3 py-1 font-bold text-sky-700 border border-sky-200">Confidence: {reviewDetail.confidence}%</span>
                )}
                <span className="text-[10px] text-slate-400 font-mono">ID: {reviewDetail.recordId}</span>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2.5 shrink-0">
              {reviewDetail.sourceUrl && (
                <a 
                  href={reviewDetail.sourceUrl} 
                  target="_blank" 
                  rel="noreferrer" 
                  className="inline-flex items-center gap-1.5 rounded-xl bg-sky-50 border border-sky-200 px-4 py-2.5 text-xs font-bold text-sky-700 hover:bg-sky-100 transition-all shadow-sm"
                >
                  <span>🌐 Open crawled source</span>
                  <span>↗️</span>
                </a>
              )}
              <StatusBadge status={status} />
            </div>
          </div>
        </div>

        {/* Crawled raw field details */}
        <CrawledDataCard fields={reviewDetail.crawledFields} />

        {/* Proposed decisions list */}
        <Card
          title="Field decisions"
          aside={
            reviewQueue.items.length === 0 ? <LinkButton href={`?tab=clean`}>Open Clean Data</LinkButton> : null
          }
        >
          <div className="space-y-6">
            {reviewDetail.fields.length === 0 ? (
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-500 text-center">
                No fields currently need manual review. You can move on to the clean data view.
              </div>
            ) : null}
            {reviewQueue.items.length > 0 ? (
              <div className="rounded-2xl bg-amber-50 border border-amber-200 p-4 text-xs font-bold text-amber-800 uppercase tracking-wider flex items-center gap-2">
                <span>⚠️ Action Required:</span>
                <span>Review and resolve the flagged field decisions below, then proceed to Clean Data.</span>
              </div>
            ) : null}
            
            <FieldDecisionSummary fields={reviewDetail.fields} />
            
            <div className="space-y-6 pt-4 border-t border-slate-100">
              {reviewDetail.fields.map((field) => (
                <div id={fieldDomId(field.fieldName)} key={field.fieldName} className="scroll-mt-6 rounded-2xl border border-slate-200 bg-slate-50/50 p-5 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
                    <p className="font-extrabold text-slate-900 text-lg tracking-tight">{field.fieldName}</p>
                    <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider ${fieldDecisionTone(field)}`}>
                      {field.issueType}
                    </span>
                  </div>

                  {/* Comparisons columns */}
                  <div className="mt-4 grid gap-4 text-xs md:grid-cols-3">
                    <div className="rounded-xl border border-slate-200 bg-white p-3.5">
                      <p className="font-bold text-slate-500 uppercase tracking-wider text-[10px] mb-1.5">Raw value</p>
                      <div className="rounded-lg bg-slate-50 border border-slate-200 px-3 py-2 text-slate-700 break-words font-semibold">{formatFieldValue(field.rawValue)}</div>
                    </div>
                    <div className="rounded-xl border border-sky-100 bg-sky-50/30 p-3.5">
                      <p className="font-bold text-sky-600 uppercase tracking-wider text-[10px] mb-1.5">Suggested value</p>
                      <div className="rounded-lg bg-sky-50 border border-sky-200 px-3 py-2 text-sky-700 break-words font-semibold">{formatFieldValue(field.suggestedValue)}</div>
                    </div>
                    <div className="rounded-xl border border-emerald-100 bg-emerald-50/30 p-3.5">
                      <p className="font-bold text-emerald-600 uppercase tracking-wider text-[10px] mb-1.5">Final value</p>
                      <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 text-emerald-700 break-words font-semibold">{formatFieldValue(field.finalValue)}</div>
                    </div>
                  </div>

                  {/* Reason explanation */}
                  {field.reason && (
                    <div className="mt-3.5 text-xs bg-slate-100 border border-slate-200 rounded-xl px-4 py-3 text-slate-700 leading-relaxed">
                      <span className="font-bold text-slate-500 block mb-1">Judge diagnosis:</span>
                      {field.reason}
                    </div>
                  )}

                  {/* Source details */}
                  {field.mergeSourceName ? (
                    <div className={`mt-3.5 rounded-xl border px-3.5 py-2.5 text-xs font-semibold ${field.mergeFromSecondary ? "border-sky-200 bg-sky-50 text-sky-700" : "border-slate-200 bg-slate-50 text-slate-700"}`}>
                      Chosen source: <span className="font-bold uppercase tracking-wider text-slate-700 bg-slate-100 px-2 py-0.5 rounded border border-slate-200 ml-1">{field.mergeSourceName}</span>
                      {field.mergeFromSecondary ? " (filled from secondary backup source)" : ""}
                    </div>
                  ) : null}

                  {/* Merge conflicts resolve list */}
                  {field.mergeConflicts.length > 0 ? (
                    <div className="mt-3.5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3.5 text-xs text-amber-800">
                      <p className="font-bold uppercase tracking-wider text-[10px] mb-2">⚠️ Source disagreement detected</p>
                      <div className="space-y-2">
                        {field.mergeConflicts.map((conflict) => (
                          <div key={`${conflict.source_id}-${String(conflict.value)}`} className="flex items-center justify-between gap-3 rounded-lg bg-white border border-slate-200 px-3 py-2">
                            <span className="font-bold text-slate-650">{conflict.source_name}</span>
                            <span className="font-semibold text-slate-900">{formatFieldValue(conflict.value)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {/* Evidence verification layout (Critical for financials & proof URLs) */}
                  <div className={`mt-4 rounded-xl border p-4 text-xs backdrop-blur-sm transition-all duration-300 ${
                    hasEvidence(field)
                      ? "bg-emerald-50 border-emerald-200 text-emerald-800 shadow-sm"
                      : field.evidenceRequired
                        ? "bg-rose-50 border-rose-200 text-rose-800 shadow-sm animate-pulse"
                        : "bg-slate-50 border-slate-200 text-slate-700"
                  }`}>
                    <div className={`flex flex-wrap items-center justify-between gap-2 border-b ${hasEvidence(field) ? "border-emerald-200" : field.evidenceRequired ? "border-rose-200" : "border-slate-200"} pb-2 mb-3`}>
                      <div className="flex items-center gap-2">
                        <span className="text-base">📄</span>
                        <p className="font-bold tracking-wide uppercase text-xs">Verification Evidence</p>
                      </div>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider ${
                        field.evidenceRequired 
                          ? "bg-rose-100 text-rose-800 border border-rose-200" 
                          : "bg-slate-100 text-slate-600 border border-slate-200"
                      }`}>
                        {field.evidenceRequired ? "Required" : "Optional"}
                      </span>
                    </div>
                    
                    <p className="text-xs leading-relaxed opacity-95">
                      {hasEvidence(field)
                        ? "✅ Verifiable source evidence is attached. Please review the excerpt below to confirm value accuracy."
                        : field.evidenceRequired
                          ? "⚠️ Critical focus field: No supporting evidence attached. Row cannot auto-approve without evidence."
                          : "💡 No evidence attached for this optional field."}
                    </p>

                    {field.evidenceUrl && (
                      <div className="mt-3">
                        <a 
                          href={field.evidenceUrl} 
                          target="_blank" 
                          rel="noreferrer" 
                          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-100 border border-emerald-200 px-3 py-2 text-xs font-bold text-emerald-800 hover:bg-emerald-200 transition-all shadow-sm"
                        >
                          <span>🌐 Visit Source:</span>
                          <span className="underline break-all font-mono text-[11px] max-w-xs truncate">{field.evidenceSource || "Evidence Link"}</span>
                          <span>↗️</span>
                        </a>
                      </div>
                    )}

                    {field.sourceExcerpt && (
                      <div className="mt-3 relative overflow-hidden rounded-lg bg-white border border-slate-200 p-3.5 shadow-sm">
                        <div className="absolute left-0 top-0 bottom-0 w-1 bg-emerald-500" />
                        <p className="text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wider text-[9px]">Source Excerpt</p>
                        <blockquote className="text-xs leading-relaxed text-slate-800 italic font-medium pl-1">
                          "{field.sourceExcerpt}"
                        </blockquote>
                      </div>
                    )}
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-100">
                    <ReviewActionPanel recordId={reviewDetail.recordId} field={field} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

function CleanTab({ cleanData, criticalFields }: { cleanData: CleanDataResponse; criticalFields: string[] }) {
  return (
    <div className="min-w-0 max-w-full space-y-6">
      {/* Stats row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <MetricCard label="Completeness" value={`${cleanData.summary.completeness}%`} subtext="Template columns already populated" />
        <MetricCard label="Approved rows" value={String(cleanData.summary.readyCount)} subtext="Rows successfully cleared for export" />
        <MetricCard label="Pending rows" value={String(cleanData.summary.incompleteCount)} subtext="Rows blocked by errors or review" />
        <MetricCard label="Quality score" value={`${cleanData.summary.qualityScore}%`} subtext="Combined reliability indicator" />
        <MetricCard label="Secondary fills" value={String(cleanData.summary.secondaryFieldCount)} subtext="Merged values from secondary sources" />
        <MetricCard label="Source conflicts" value={String(cleanData.summary.conflictFieldCount)} subtext="Remaining merged conflicts" />
      </div>

      <div className="rounded-2xl border border-sky-200 bg-sky-50 p-4 text-xs font-semibold text-sky-700">
        📌 Focus columns are highlighted in the grid below. Unsupported optional fields remain blank/null to ensure a clean template structure without guessing values.
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Field completeness">
          <ComparisonBars
            items={cleanData.analyze.fieldCompleteness.map((field) => ({
              label: field.field,
              leftLabel: "Missing",
              leftValue: 100 - field.percent,
              rightLabel: "Complete",
              rightValue: field.percent,
            }))}
          />
        </Card>

        <Card title="Fields causing the most issues">
          <div className="space-y-2.5">
            {cleanData.analyze.problemFields.map((field) => (
              <div key={field.field} className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs">
                <span className="font-bold text-slate-700">{field.field}</span>
                <span className="font-extrabold text-rose-700 bg-rose-50 border border-rose-200 rounded-md px-2 py-0.5">{field.missingCount} missing</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card title="Merge contribution by field">
        <ComparisonBars
          items={cleanData.analyze.mergeCoverage.map((field) => ({
            label: field.field,
            leftLabel: "Primary",
            leftValue: field.primaryCount,
            rightLabel: "Secondary",
            rightValue: field.secondaryCount,
          }))}
        />
        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {cleanData.analyze.mergeCoverage.map((field) => (
            <div key={field.field} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs">
              <p className="font-bold text-slate-800 text-sm">{field.field}</p>
              <p className="mt-1.5 text-slate-500 font-medium">Conflicts: <span className="font-extrabold text-amber-700">{field.conflictCount}</span></p>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Clean data preview" aside={cleanData.summary.incompleteCount === 0 ? <LinkButton href={`?tab=export`}>Open Export</LinkButton> : null}>
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  {cleanData.columns.map((column) => (
                    <th key={column} className={`px-4 py-3 text-left font-bold text-slate-500 uppercase tracking-wider text-xs ${criticalFields.includes(column) ? "bg-amber-50/60" : ""}`}>
                      <PriorityColumnHeader isPriority={criticalFields.includes(column)}>
                        {column}
                      </PriorityColumnHeader>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {cleanData.rows.map((row, index) => (
                  <tr key={`${row.name}-${index}`} className="hover:bg-slate-50/80 transition-colors">
                    {cleanData.columns.map((column) => (
                      <td key={column} className="px-4 py-3 text-slate-700 font-medium">
                        {formatFieldValue(row[column])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Card>

      <div className={`rounded-2xl border p-4 text-xs font-bold uppercase tracking-wider ${cleanData.summary.incompleteCount === 0 ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}>
        {cleanData.summary.incompleteCount === 0
          ? "✅ Clean dataset prepared. Ready to export."
          : `⚠️ Resolve the remaining ${cleanData.summary.incompleteCount} incomplete records before export.`}
      </div>
    </div>
  );
}

function ExportTab({ jobId, exportReadiness }: { jobId: string; exportReadiness: ExportReadinessResponse }) {
  const isReadyToExport = exportReadiness.isReady;
  const nextStepMessage = isReadyToExport
    ? "Export the evidence-backed clean file now. Unsupported values remain blank/null, and rule-derived fields use accepted values only."
    : exportReadiness.blockers[0]
      ? `Resolve ${exportReadiness.blockers[0].label.toLowerCase()} before exporting this file.`
      : "Review the checklist below before exporting this file.";

  return (
    <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <Card title="Export readiness">
        <div className="space-y-4">
          <DonutStat label="Ready for import" value={exportReadiness.readinessScore} hint="Measures conformance to BeyondDegree schema rules." />
          <div className={`rounded-2xl border p-4 text-xs ${exportReadiness.mergeRisk.riskLevel === "high" ? "border-rose-200 bg-rose-50 text-rose-800" : exportReadiness.mergeRisk.riskLevel === "medium" ? "border-amber-200 bg-amber-50 text-amber-800" : "border-emerald-200 bg-emerald-50 text-emerald-800"}`}>
            <p className="font-bold uppercase tracking-wider text-[10px] mb-1">Merge risk level: {exportReadiness.mergeRisk.riskLevel}</p>
            <p className="font-medium opacity-90">
              {exportReadiness.mergeRisk.conflictFieldCount} conflicting fields / {exportReadiness.mergeRisk.secondaryFieldCount} secondary fields
            </p>
          </div>
          <div className="space-y-2.5">
            {exportReadiness.checklist.map((item) => {
              const tone =
                item.status === "pass"
                  ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                  : item.status === "warning"
                    ? "bg-amber-50 border-amber-200 text-amber-800"
                    : "bg-rose-50 border-rose-200 text-rose-800";

              return (
                <div key={item.key} className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-4 py-3.5 text-xs">
                  <span className="font-semibold text-slate-700">{item.label}</span>
                  <span className={`rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${tone}`}>{item.status}</span>
                </div>
              );
            })}
          </div>
        </div>
      </Card>

      <div className="space-y-6">
        <Card title="Remaining blockers">
          <div className="space-y-2.5">
            {exportReadiness.blockers.length === 0 ? (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-bold text-emerald-800">
                No blockers detected. Clear to export.
              </div>
            ) : null}
            {exportReadiness.blockers.map((blocker) => (
              <div key={blocker.label} className="flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50 px-4 py-3.5 text-xs">
                <span className="font-semibold text-slate-700">{blocker.label}</span>
                <span className="font-extrabold text-amber-900 bg-amber-100 border border-amber-300 rounded-md px-2 py-0.5">{blocker.count}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Export file details">
          <div className="space-y-4 text-xs font-semibold text-slate-700">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <span className="text-[10px] text-slate-500 block uppercase mb-1 font-bold">Target Template</span>
                <span className="text-slate-900 text-sm font-bold">{exportReadiness.exportPreview.templateName}</span>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <span className="text-[10px] text-slate-500 block uppercase mb-1 font-bold">Prepared Rows</span>
                <span className="text-slate-900 text-sm font-bold">{exportReadiness.exportPreview.totalRecords}</span>
              </div>
            </div>
            <p>
              <span className="text-slate-550">Supported Formats:</span> {exportReadiness.exportPreview.supportedFormats.join(", ")}
            </p>
            <p>
              <span className="text-slate-550">Filename:</span> <span className="font-mono text-slate-800 text-xs bg-slate-100 px-2 py-1 border border-slate-200 rounded">{exportReadiness.exportPreview.defaultFileName}</span>
            </p>
            <p className="rounded-xl border border-slate-200 bg-slate-50/50 p-4 leading-relaxed font-normal text-slate-600">
              💡 Export uses evidence-safe template validation. Non-validated optional fields remain empty to ensure strict schema consistency.
            </p>
            <div className={`rounded-xl border p-4 ${isReadyToExport ? "border-emerald-200 bg-emerald-50/50 text-emerald-800" : "border-slate-200 bg-slate-50 text-slate-600"}`}>
              <p className="font-bold text-slate-800 uppercase text-[10px] tracking-wider mb-1">Next actions</p>
              <p className="font-medium leading-relaxed">{nextStepMessage}</p>
            </div>
            <div className="pt-2">
              <ExportAction jobId={jobId} exportReadiness={exportReadiness} />
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

function ImportTab({ jobId, exportReadiness }: { jobId: string; exportReadiness: ExportReadinessResponse }) {
  const isReadyToImport = exportReadiness.isReady;
  const nextStepMessage = isReadyToImport
    ? "Run the import process now to write cleaned records into the primary BeyondDegree database."
    : exportReadiness.blockers[0]
      ? `Resolve ${exportReadiness.blockers[0].label.toLowerCase()} before starting database import.`
      : "Check validation requirements below.";

  return (
    <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <Card title="Import readiness">
        <div className="space-y-4">
          <DonutStat label="Database alignment" value={exportReadiness.readinessScore} hint="Uses identical rules as the CSV export layout check." />
          <div className={`rounded-2xl border p-4 text-xs ${isReadyToImport ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}>
            <p className="font-bold uppercase tracking-wider text-[10px] mb-1">{isReadyToImport ? "Clear to import" : "Blockers remaining"}</p>
            <p className="font-medium leading-relaxed">{nextStepMessage}</p>
          </div>
          <div className={`rounded-2xl border p-4 text-xs ${exportReadiness.mergeRisk.riskLevel === "high" ? "border-rose-200 bg-rose-50 text-rose-800" : exportReadiness.mergeRisk.riskLevel === "medium" ? "border-amber-200 bg-amber-50 text-amber-800" : "border-emerald-200 bg-emerald-50 text-emerald-800"}`}>
            <p className="font-bold uppercase tracking-wider text-[10px] mb-1">Merge Risk: {exportReadiness.mergeRisk.riskLevel}</p>
            <p className="font-medium opacity-90">
              {exportReadiness.mergeRisk.conflictFieldCount} conflicts / {exportReadiness.mergeRisk.secondaryFieldCount} secondary fills
            </p>
          </div>
          <div className="space-y-2.5">
            {exportReadiness.checklist.map((item) => {
              const tone =
                item.status === "pass"
                  ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                  : item.status === "warning"
                    ? "bg-amber-50 border-amber-200 text-amber-800"
                    : "bg-rose-50 border-rose-200 text-rose-800";

              return (
                <div key={item.key} className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-4 py-3.5 text-xs">
                  <span className="font-semibold text-slate-700">{item.label}</span>
                  <span className={`rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${tone}`}>{item.status}</span>
                </div>
              );
            })}
          </div>
        </div>
      </Card>

      <div className="space-y-6">
        <Card title="Import preview">
          <div className="space-y-4 text-xs font-semibold text-slate-700">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <span className="text-[10px] text-slate-550 block uppercase mb-1 font-bold">Template</span>
                <span className="text-slate-900 text-sm font-bold">{exportReadiness.exportPreview.templateName}</span>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <span className="text-[10px] text-slate-550 block uppercase mb-1 font-bold">Prepared Rows</span>
                <span className="text-slate-900 text-sm font-bold">{exportReadiness.exportPreview.totalRecords}</span>
              </div>
            </div>
            <p className="rounded-xl border border-slate-200 bg-slate-50/50 p-4 leading-relaxed font-normal text-slate-600">
              📝 Direct database writes map fields using exact template rules. Unsupported parameters remain blank.
            </p>
            <div className={`rounded-xl border p-4 ${isReadyToImport ? "border-emerald-200 bg-emerald-50/50 text-emerald-800" : "border-slate-200 bg-slate-50 text-slate-600"}`}>
              <p className="font-bold text-slate-800 uppercase text-[10px] tracking-wider mb-1">Actions</p>
              <p className="font-medium leading-relaxed">{nextStepMessage}</p>
            </div>
            <div className="pt-2">
              <ImportAction jobId={jobId} exportReadiness={exportReadiness} />
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

function ActivityTab({ activityItems }: { activityItems: ActivityItem[] }) {
  return (
    <Card title="Recent activity" aside={<span className="text-xs font-bold uppercase tracking-wider text-slate-500 bg-slate-100 border border-slate-200 px-2 py-1 rounded-md">{activityItems.length} logs</span>}>
      <div className="space-y-3">
        {activityItems.map((item) => (
          <div key={item.id} className="flex items-start justify-between gap-4 rounded-2xl border border-slate-200 bg-white px-4 py-4 hover:bg-slate-50 transition-all duration-200 shadow-sm">
            <div>
              <p className="font-bold text-slate-900 text-sm">{item.title}</p>
              <p className="mt-1 text-xs text-slate-600 font-medium">{item.detail}</p>
            </div>
            <div className="text-right text-xs text-slate-500 shrink-0 font-semibold">
              <p>{item.time}</p>
              <p className="mt-1.5 uppercase text-[9px] bg-slate-100 px-2 py-0.5 rounded border border-slate-200 tracking-wider inline-block text-slate-600">{item.type}</p>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

export function JobDetailContent({
  activeTab,
  jobHeader,
  reviewQueue,
  overviewData,
  cleanData,
  activityItems,
  exportReadiness,
}: {
  activeTab: string;
  jobHeader: JobDetailHeader;
  reviewQueue: ReviewQueueData | null;
  overviewData: OverviewResponse | null;
  cleanData: CleanDataResponse | null;
  activityItems: ActivityItem[];
  exportReadiness: ExportReadinessResponse | null;
}) {
  const sourceSummary = jobHeader.sourceNames.length > 1 ? `${jobHeader.sourceNames[0]} + ${jobHeader.sourceNames.length - 1} more` : jobHeader.sourceNames[0] ?? jobHeader.sourceName;
  const crawlModeLabel = jobHeader.crawlMode === "prompt_discovery"
    ? "Prompt / PDF discovery"
    : jobHeader.crawlMode === "supplemental_discovery"
      ? "Supplemental coverage crawl"
      : "Trusted sources crawl";
  const promptText = typeof jobHeader.discoveryInput?.prompt_text === "string" ? jobHeader.discoveryInput.prompt_text : null;
  const modeExplanation =
    jobHeader.crawlMode === "prompt_discovery"
      ? "Prompt mode is AI-first: the system uses your strategy prompt to propose structured candidate rows, attaches evidence when available, then judge and human review decide what is usable."
      : jobHeader.crawlMode === "supplemental_discovery"
        ? "Supplemental crawl is source-based: the system collects live rows from broader sources, prioritizes focus fields, then judge and review decide what can ship."
        : "Trusted-source crawl is source-based: the system collects live rows from the country plan, prioritizes focus fields, then judge and review decide what can ship.";
  const progressSummary = `${jobHeader.progress.crawled} collected / ${jobHeader.progress.processed ?? jobHeader.progress.extracted} processed / ${jobHeader.progress.cleanCandidates ?? jobHeader.progress.cleaned} clean candidates / ${jobHeader.progress.approved ?? 0} approved / ${jobHeader.progress.needsReview} in review / ${jobHeader.progress.skipped ?? 0} skipped`;
  const runActionProgress = {
    totalRecords: jobHeader.progress.totalRecords,
    crawled: jobHeader.progress.crawled,
    extracted: jobHeader.progress.extracted,
    needsReview: jobHeader.progress.needsReview,
    cleaned: jobHeader.progress.cleaned,
    skipped: jobHeader.progress.skipped ?? 0,
    cleanCandidates: jobHeader.progress.cleanCandidates ?? jobHeader.progress.cleaned,
    approved: jobHeader.progress.approved ?? 0,
    rejected: jobHeader.progress.rejected ?? 0,
    processed: jobHeader.progress.processed ?? jobHeader.progress.extracted,
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Crawl job"
        title={jobHeader.jobName}
        description={`Mode: ${crawlModeLabel} / Sources: ${sourceSummary} / Country: ${jobHeader.country} / Template: ${jobHeader.templateName}`}
        action={
          <div className="flex max-w-full flex-wrap items-start justify-end gap-3">
            <div className="min-w-0 space-y-2 text-right">
              <p className="text-xs text-slate-500 font-semibold uppercase tracking-wider">{jobHeader.sourceNames.length > 1 ? `${jobHeader.sourceNames.length} sources selected` : "1 source selected"}</p>
              <p className="max-w-md text-[10px] text-slate-600 font-medium leading-relaxed">This page reflects direct backend processing. Use rerun only when you want to process the selected sources again.</p>
              <div className="flex flex-col items-end gap-2">
                <RunJobAction jobId={jobHeader.id} initialStatus={jobHeader.status} initialProgress={runActionProgress} />
                <DeleteJobAction jobId={jobHeader.id} redirectTo="/crawl-jobs" />
              </div>
            </div>
            <StatusBadge status={jobHeader.status} />
          </div>
        }
      />
      <Card title="Collection mode" aside={<span className="text-xs font-bold text-sky-700 bg-sky-50 border border-sky-200 px-2 py-0.5 rounded uppercase tracking-wider">Configuration</span>}>
        <div className="space-y-3 text-sm text-slate-700">
          <p><span className="font-bold text-slate-900">Mode:</span> {crawlModeLabel}</p>
          <p className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 leading-relaxed font-medium text-xs text-slate-600">{modeExplanation}</p>
          {promptText ? (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 mt-2 shadow-sm">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider font-extrabold block mb-1">Prompt rules</span>
              <p className="font-mono text-xs break-words text-slate-700 bg-white p-2.5 border border-slate-200 rounded">{promptText}</p>
            </div>
          ) : null}
          <p className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 leading-relaxed text-xs text-sky-700 font-medium">
            💡 Auto-approval needs confidence, required focus fields, and source evidence. Lower-confidence, conflicting, or unsupported candidates stay in review or remain blank/null instead of being treated as ready rows.
          </p>
        </div>
      </Card>
      {jobHeader.sourceNames.length > 1 ? (
        <Card title="Backend source plan" aside={<span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Read-only</span>}>
          <div className="flex min-w-0 flex-wrap gap-2">
            {jobHeader.sourceNames.map((sourceName, index) => (
              <span key={sourceName} className={`max-w-full break-words rounded-full px-3.5 py-1 text-xs font-bold uppercase tracking-wider ${index === 0 ? "bg-sky-50 text-sky-700 border border-sky-200 shadow-sm" : "bg-slate-100 text-slate-600 border border-slate-200"}`}>
                {sourceName}
                {index === 0 ? " / Primary" : ""}
              </span>
            ))}
          </div>
        </Card>
      ) : null}

      <Card title="Job progress">
        <div className="space-y-4">
          <Stepper steps={jobHeader.steps} />
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-xs font-bold text-slate-700 uppercase tracking-wider shadow-sm">
            <p className="text-slate-900 text-[11px] mb-1.5 font-bold uppercase tracking-wider">Live progress summary</p>
            <p className="font-mono text-slate-800 leading-relaxed font-semibold">{progressSummary}</p>
          </div>
          <p className="text-xs text-slate-500 font-semibold tracking-wider uppercase text-[10px]">Last updated: {jobHeader.updatedAt}</p>
        </div>
      </Card>

      <OnboardingGuide />

      <FocusFieldSelector
        jobId={jobHeader.id}
        availableFields={jobHeader.templateColumns}
        initialFocusFields={jobHeader.criticalFields}
      />

      <JobTabs />

      {activeTab === "review" && reviewQueue ? <ReviewTab status={jobHeader.status} reviewQueue={reviewQueue} jobId={jobHeader.id} /> : null}
      {activeTab === "clean" && cleanData ? <CleanTab cleanData={cleanData} criticalFields={jobHeader.criticalFields} /> : null}
      {activeTab === "export" && exportReadiness ? <ExportTab jobId={jobHeader.id} exportReadiness={exportReadiness} /> : null}
      {activeTab === "import" && exportReadiness ? <ImportTab jobId={jobHeader.id} exportReadiness={exportReadiness} /> : null}
      {activeTab === "activity" ? <ActivityTab activityItems={activityItems} /> : null}
      {activeTab === "overview" && overviewData ? <OverviewTab overviewData={overviewData} jobId={jobHeader.id} /> : null}
    </div>
  );
}
