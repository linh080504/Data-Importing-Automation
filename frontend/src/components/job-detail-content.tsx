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
  if (value === null || value === undefined || value === "") return "Blank";
  return String(value);
}

function hasEvidence(field: ReviewField) {
  return Boolean(field.sourceExcerpt || field.evidenceUrl || field.evidenceSource || field.mergeSourceName);
}

function fieldStatusTone(status: string) {
  if (status === "captured") return "bg-emerald-50 text-emerald-800";
  if (status === "missing") return "bg-rose-50 text-rose-700";
  return "bg-amber-50 text-amber-800";
}

function formatStatusLabel(status: string) {
  return status.replaceAll("_", " ");
}

function fieldDecisionTone(field: ReviewField) {
  if (field.issueType === "missing") return "bg-rose-50 text-rose-700";
  if (hasEvidence(field)) return "bg-emerald-50 text-emerald-800";
  return "bg-amber-50 text-amber-800";
}

function fieldDomId(fieldName: string) {
  return `review-field-${fieldName.replace(/[^a-zA-Z0-9_-]+/g, "-")}`;
}

function FieldDecisionSummary({ fields }: { fields: ReviewField[] }) {
  if (fields.length === 0) return null;

  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            <th className="px-4 py-3 text-left font-semibold text-slate-500">Field</th>
            <th className="px-4 py-3 text-left font-semibold text-slate-500">Problem</th>
            <th className="min-w-[14rem] px-4 py-3 text-left font-semibold text-slate-500">Suggested value</th>
            <th className="px-4 py-3 text-left font-semibold text-slate-500">Evidence</th>
            <th className="px-4 py-3 text-left font-semibold text-slate-500">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {fields.map((field) => (
            <tr key={field.fieldName}>
              <td className="px-4 py-3 font-medium text-slate-900">{field.fieldName}</td>
              <td className="px-4 py-3">
                <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold uppercase ${fieldDecisionTone(field)}`}>
                  {field.issueType}
                </span>
              </td>
              <td className="px-4 py-3 text-slate-700">
                <div className="max-w-sm whitespace-pre-wrap break-words">{formatFieldValue(field.suggestedValue)}</div>
              </td>
              <td className="px-4 py-3 text-slate-600">
                {field.evidenceUrl ? (
                  <a href={field.evidenceUrl} target="_blank" rel="noreferrer" className="font-semibold text-sky-700 underline">
                    Open source
                  </a>
                ) : hasEvidence(field) ? (
                  <span>{field.evidenceSource ?? "Evidence attached"}</span>
                ) : (
                  <span className="text-slate-400">Missing</span>
                )}
              </td>
              <td className="px-4 py-3">
                <a href={`#${fieldDomId(field.fieldName)}`} className="font-semibold text-sky-700 underline">
                  Review
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CrawledDataCard({ fields }: { fields: CrawledFieldSnapshot[] }) {
  return (
    <Card title="Crawled school data" aside={<span className="text-sm text-slate-500">{fields.length} fields</span>}>
      {fields.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
          No crawled field snapshot is available for this record.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="w-44 px-4 py-3 text-left font-semibold text-slate-500">Field</th>
                <th className="min-w-[16rem] px-4 py-3 text-left font-semibold text-slate-500">Crawled value</th>
                <th className="min-w-[16rem] px-4 py-3 text-left font-semibold text-slate-500">Source</th>
                <th className="w-48 px-4 py-3 text-left font-semibold text-slate-500">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {fields.map((field) => (
                <tr key={field.fieldName}>
                  <td className="px-4 py-3 font-medium text-slate-900">{field.fieldName}</td>
                  <td className="px-4 py-3 text-slate-700">
                    <div className="max-w-xl whitespace-pre-wrap break-words">{formatFieldValue(field.value)}</div>
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    <div className="max-w-xl space-y-1 break-words">
                      {field.sourceName ? <p className="font-medium text-slate-700">{field.sourceName}</p> : null}
                      {field.sourceUrl ? (
                        <a href={field.sourceUrl} target="_blank" rel="noreferrer" className="block break-all font-semibold text-sky-700 underline">
                          Open evidence
                        </a>
                      ) : null}
                      {field.sourceExcerpt ? <p className="rounded-lg bg-slate-50 px-3 py-2 text-slate-600">{field.sourceExcerpt}</p> : null}
                      {!field.sourceName && !field.sourceUrl && !field.sourceExcerpt ? <span className="text-slate-400">No evidence</span> : null}
                    </div>
                  </td>
                  <td className="px-4 py-3 align-top">
                    <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold uppercase ${fieldStatusTone(field.status)}`}>
                      {formatStatusLabel(field.status)}
                    </span>
                    {field.reason ? <p className="mt-2 text-xs leading-5 text-slate-500">{field.reason}</p> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
    <Card title="Crawled records" aside={<span className="text-sm text-slate-500">{records.total} collected</span>}>
      <div className="grid gap-5 xl:grid-cols-[0.75fr_1.25fr]">
        <div className="space-y-3">
          {records.items.length === 0 ? (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              No crawled records are available yet.
            </div>
          ) : null}
          {records.items.map((record) => {
            const isSelected = record.rawRecordId === records.selectedRecordId;
            return (
              <Link
                key={record.rawRecordId}
                href={`/crawl-jobs/${jobId}?tab=overview&recordPage=${records.page}&rawRecord=${record.rawRecordId}`}
                className={`block rounded-2xl border px-4 py-3 transition ${
                  isSelected ? "border-sky-300 bg-sky-50" : "border-slate-200 bg-white hover:bg-slate-50"
                }`}
              >
                <p className="break-words font-semibold text-slate-900">{record.displayName}</p>
                <div className="mt-2 space-y-1 text-sm text-slate-500">
                  {record.country ? <p>{record.country}</p> : null}
                  {record.sourceName ? <p>{record.sourceName}</p> : null}
                  <p className="break-all">Key: {record.uniqueKey}</p>
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs">
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 font-semibold text-slate-700">
                    {record.status ?? "NO STATUS"}
                  </span>
                  <span className="font-semibold text-slate-600">
                    Score: {record.qualityScore === null ? "N/A" : record.qualityScore}
                  </span>
                </div>
              </Link>
            );
          })}
          <div className="flex items-center justify-between gap-3 text-sm">
            <Link
              href={`/crawl-jobs/${jobId}?tab=overview&recordPage=${previousPage}`}
              className={`rounded-xl border px-3 py-2 font-semibold ${records.page <= 1 ? "pointer-events-none border-slate-200 text-slate-300" : "border-slate-300 text-slate-700 hover:bg-slate-50"}`}
            >
              Previous
            </Link>
            <span className="text-slate-500">Page {records.page} / {totalPages}</span>
            <Link
              href={`/crawl-jobs/${jobId}?tab=overview&recordPage=${nextPage}`}
              className={`rounded-xl border px-3 py-2 font-semibold ${records.page >= totalPages ? "pointer-events-none border-slate-200 text-slate-300" : "border-slate-300 text-slate-700 hover:bg-slate-50"}`}
            >
              Next
            </Link>
          </div>
        </div>

        <div className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4">
          {selected ? (
            <div className="space-y-4">
              <div>
                <p className="break-words text-lg font-semibold text-slate-950">{selected.displayName}</p>
                <div className="mt-2 space-y-1 text-sm text-slate-500">
                  <p className="break-all">Raw record: {selected.rawRecordId}</p>
                  {selected.sourceUrl ? (
                    <a href={selected.sourceUrl} target="_blank" rel="noreferrer" className="block break-all font-semibold text-sky-700 underline">
                      Open source
                    </a>
                  ) : null}
                </div>
              </div>
              <div className="max-h-[34rem] overflow-auto rounded-xl border border-slate-200">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="sticky top-0 bg-slate-50">
                    <tr>
                      <th className="w-48 px-4 py-3 text-left font-semibold text-slate-500">Field</th>
                      <th className="min-w-[14rem] px-4 py-3 text-left font-semibold text-slate-500">Clean</th>
                      <th className="min-w-[14rem] px-4 py-3 text-left font-semibold text-slate-500">Raw</th>
                      <th className="w-48 px-4 py-3 text-left font-semibold text-slate-500">Source</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {selected.fields.map((field) => (
                      <tr key={field.fieldName}>
                        <td className="px-4 py-3 font-medium text-slate-900">{field.fieldName}</td>
                        <td className="px-4 py-3 text-slate-700">
                          <div className="max-w-md whitespace-pre-wrap break-words">{formatFieldValue(field.cleanValue)}</div>
                        </td>
                        <td className="px-4 py-3 text-slate-600">
                          <div className="max-w-md whitespace-pre-wrap break-words">{formatFieldValue(field.rawValue)}</div>
                        </td>
                        <td className="px-4 py-3 text-slate-500">
                          <div className="space-y-1">
                            {field.sourceName ? <p>{field.sourceName}</p> : <p>No source field</p>}
                            {field.fromSecondary ? <p className="text-xs font-semibold text-sky-700">Secondary fill</p> : null}
                            {field.conflicts.length > 0 ? <p className="text-xs font-semibold text-amber-700">{field.conflicts.length} conflicts</p> : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-600">Select a crawled record to inspect its fields.</div>
          )}
        </div>
      </div>
    </Card>
  );
}

function OverviewTab({ overviewData, jobId }: { overviewData: OverviewResponse; jobId: string }) {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard label="Collected rows" value={String(overviewData.summary.totalRecords)} subtext="Live rows collected from the active sources" />
        <MetricCard label="Clean candidates" value={String(overviewData.summary.cleanRecords)} subtext="Structured rows shaped toward the template schema" />
        <MetricCard label="Need review" value={String(overviewData.summary.needReviewCount)} subtext="Candidates the judge could not approve automatically" />
        <MetricCard label="Rejected" value={String(overviewData.summary.rejectedCount)} subtext="Excluded from final export" />
        <MetricCard label="Secondary fills" value={String(overviewData.summary.mergeSecondaryFieldCount)} subtext="Values filled from supporting sources" />
        <MetricCard label="Source conflicts" value={String(overviewData.summary.mergeConflictFieldCount)} subtext="Fields with source disagreements" />
      </div>

      <CrawledRecordsPanel jobId={jobId} records={overviewData.crawledRecords} />

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card title="Analyze quality and readiness">
          <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
              <DonutStat label="Overall quality" value={overviewData.analyze.overallQuality} hint="How complete and standardized the dataset is." />
              <DonutStat label="Import readiness" value={overviewData.analyze.importReadiness} hint="How close the file is to BeyondDegree import format." />
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
          <div className="space-y-4">
            <div>
              <p className="text-lg font-semibold text-slate-950">{overviewData.nextAction.title}</p>
              <p className="mt-2 text-sm leading-6 text-slate-600">{overviewData.nextAction.description}</p>
            </div>
            <LinkButton href={`?tab=${overviewData.nextAction.primaryTarget}`}>{overviewData.nextAction.primaryLabel}</LinkButton>
            <div className="rounded-2xl bg-slate-50 p-4">
              <p className="text-sm font-semibold text-slate-700">Top issues to focus on</p>
              <div className="mt-3 space-y-3">
                {overviewData.topIssues.map((issue) => (
                  <div key={issue.label} className="flex items-center justify-between rounded-xl bg-white px-3 py-2 text-sm shadow-sm">
                    <span className="text-slate-700">{issue.label}</span>
                    <span className="font-semibold text-slate-900">{issue.count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>
      </div>

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
          <div className="mt-4 space-y-2 rounded-2xl bg-amber-50 p-4 text-sm text-amber-900">
            <p className="font-semibold">Conflicts requiring attention</p>
            {overviewData.analyze.mergeCoverage.map((item) => (
              <div key={item.label} className="flex items-center justify-between rounded-lg bg-white px-3 py-2">
                <span>{item.label}</span>
                <span className="font-medium text-slate-900">{item.conflictValue}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {overviewData.fieldIssues.length > 0 ? (
        <Card title="Field issue breakdown" aside={<span className="text-sm text-slate-500">{overviewData.fieldIssues.length} fields with issues</span>}>
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
    <div className="grid min-w-0 max-w-full gap-6 xl:grid-cols-[minmax(20rem,26rem)_minmax(0,1fr)]">
      <Card title="Review queue" aside={<span className="text-sm text-slate-500">{reviewQueue.total} records</span>}>
        <div className="space-y-3">
          {reviewQueue.items.length === 0 ? (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              No records currently need manual review.
            </div>
          ) : null}
          {reviewQueue.items.map((item) => {
            const isSelected = item.recordId === reviewQueue.selectedRecordId;
            return (
              <Link
                key={item.recordId}
                href={`/crawl-jobs/${jobId}?tab=review&reviewPage=${reviewQueue.page}&record=${item.recordId}`}
                className={`block rounded-2xl border px-4 py-3 transition ${
                  isSelected ? "border-sky-300 bg-sky-50" : "border-slate-200 bg-white hover:bg-slate-50"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="break-words font-semibold text-slate-900">{item.displayName}</p>
                    <p className="mt-1 break-all text-sm text-slate-500">Source key: {item.uniqueKey}</p>
                    {item.sourceName ? <p className="mt-1 text-xs text-slate-500">{item.sourceName}</p> : null}
                  </div>
                  <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
                    {item.flaggedFieldCount} fields
                  </span>
                </div>
                <div className="mt-3 flex items-center justify-between text-sm text-slate-600">
                  <span>Confidence: {item.confidence === null ? "N/A" : `${item.confidence}%`}</span>
                  {isSelected ? <span className="font-semibold text-sky-700">Viewing</span> : null}
                </div>
              </Link>
            );
          })}
          {reviewQueue.total > reviewQueue.limit ? (
            <div className="flex items-center justify-between gap-3 text-sm">
              <Link
                href={`/crawl-jobs/${jobId}?tab=review&reviewPage=${previousReviewPage}`}
                className={`rounded-xl border px-3 py-2 font-semibold ${reviewQueue.page <= 1 ? "pointer-events-none border-slate-200 text-slate-300" : "border-slate-300 text-slate-700 hover:bg-slate-50"}`}
              >
                Previous
              </Link>
              <span className="text-slate-500">Page {reviewQueue.page} / {reviewTotalPages}</span>
              <Link
                href={`/crawl-jobs/${jobId}?tab=review&reviewPage=${nextReviewPage}`}
                className={`rounded-xl border px-3 py-2 font-semibold ${reviewQueue.page >= reviewTotalPages ? "pointer-events-none border-slate-200 text-slate-300" : "border-slate-300 text-slate-700 hover:bg-slate-50"}`}
              >
                Next
              </Link>
            </div>
          ) : null}
        </div>
      </Card>

      <div className="min-w-0 space-y-6">
        <Card title="Record needing review">
          <div className="space-y-3 text-sm text-slate-600">
            <p className="text-lg font-semibold text-slate-950">{reviewDetail.displayName}</p>
            {reviewDetail.sourceName ? <p>Source: {reviewDetail.sourceName}</p> : null}
            <p>Source key: {reviewDetail.uniqueKey}</p>
            {reviewDetail.sourceUrl ? (
              <a href={reviewDetail.sourceUrl} target="_blank" rel="noreferrer" className="block break-all font-semibold text-sky-700 underline">
                Open crawled source
              </a>
            ) : null}
            <p>Confidence: {reviewDetail.confidence === null ? "N/A" : `${reviewDetail.confidence}%`}</p>
            <p className="text-xs text-slate-400">Audit ID: {reviewDetail.recordId}</p>
            <StatusBadge status={status} />
          </div>
        </Card>

        <CrawledDataCard fields={reviewDetail.crawledFields} />

        <Card
          title="Field decisions"
          aside={
            reviewQueue.items.length === 0 ? <LinkButton href={`?tab=clean`}>Open Clean Data</LinkButton> : null
          }
        >
          <div className="space-y-4">
            {reviewDetail.fields.length === 0 ? (
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                No fields currently need manual review. You can move on to the clean data view.
              </div>
            ) : null}
            {reviewQueue.items.length > 0 ? (
              <div className="rounded-2xl bg-amber-50 p-4 text-sm text-amber-800">
                Finish the flagged field decisions below, then continue to Clean Data.
              </div>
            ) : null}
            <FieldDecisionSummary fields={reviewDetail.fields} />
            {reviewDetail.fields.map((field) => (
              <div id={fieldDomId(field.fieldName)} key={field.fieldName} className="scroll-mt-6 rounded-2xl border border-slate-200 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold text-slate-900">{field.fieldName}</p>
                  <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
                    {field.issueType}
                  </span>
                </div>
                <div className="mt-3 grid gap-3 text-sm md:grid-cols-3">
                  <div>
                    <p className="text-slate-500">Raw</p>
                    <p className="mt-1 rounded-xl bg-slate-50 px-3 py-2 text-slate-800">{formatFieldValue(field.rawValue)}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Suggested</p>
                    <p className="mt-1 rounded-xl bg-sky-50 px-3 py-2 text-slate-800">{formatFieldValue(field.suggestedValue)}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Final</p>
                    <p className="mt-1 rounded-xl bg-emerald-50 px-3 py-2 text-slate-800">{formatFieldValue(field.finalValue)}</p>
                  </div>
                </div>
                <p className="mt-3 text-sm text-slate-600">{field.reason}</p>
                {field.mergeSourceName ? (
                  <div className={`mt-3 rounded-xl px-3 py-2 text-sm ${field.mergeFromSecondary ? "bg-sky-50 text-sky-800" : "bg-slate-50 text-slate-700"}`}>
                    Chosen source: <span className="font-semibold">{field.mergeSourceName}</span>
                    {field.mergeFromSecondary ? " (filled from a secondary source)" : ""}
                  </div>
                ) : null}
                {field.mergeConflicts.length > 0 ? (
                  <div className="mt-3 rounded-xl bg-amber-50 px-3 py-3 text-sm text-amber-900">
                    <p className="font-semibold">Source disagreement detected</p>
                    <div className="mt-2 space-y-2">
                      {field.mergeConflicts.map((conflict) => (
                        <div key={`${conflict.source_id}-${String(conflict.value)}`} className="flex items-center justify-between gap-3 rounded-lg bg-white px-3 py-2">
                          <span>{conflict.source_name}</span>
                          <span className="font-medium text-slate-900">{formatFieldValue(conflict.value)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className={`mt-3 rounded-xl px-3 py-3 text-sm ${
                  hasEvidence(field)
                    ? "bg-emerald-50 text-emerald-800"
                    : field.evidenceRequired
                      ? "bg-rose-50 text-rose-700"
                      : "bg-slate-50 text-slate-700"
                }`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-semibold">Evidence</p>
                    <span className="rounded-full bg-white/70 px-2 py-0.5 text-xs font-semibold">
                      {field.evidenceRequired ? "Required" : "Optional"}
                    </span>
                  </div>
                  <p className="mt-1">
                    {hasEvidence(field)
                      ? "Evidence is attached. Accept only if the value matches the source."
                      : field.evidenceRequired
                        ? "No supporting evidence is attached. Keep this blank/null unless you add a verified value."
                        : "No evidence was attached for this optional field."}
                  </p>
                  {field.evidenceSource ? (
                    <p className="mt-2"><span className="font-semibold">Source:</span> {field.evidenceSource}</p>
                  ) : null}
                  {field.evidenceUrl ? (
                    <a href={field.evidenceUrl} target="_blank" rel="noreferrer" className="mt-2 block break-all font-semibold underline">
                      Open evidence source
                    </a>
                  ) : null}
                  {field.sourceExcerpt ? (
                    <p className="mt-2 rounded-lg bg-white/70 px-3 py-2 text-slate-700">{field.sourceExcerpt}</p>
                  ) : null}
                </div>
                <ReviewActionPanel recordId={reviewDetail.recordId} field={field} />
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function CleanTab({ cleanData, criticalFields }: { cleanData: CleanDataResponse; criticalFields: string[] }) {
  return (
    <div className="min-w-0 max-w-full space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard label="Completeness" value={`${cleanData.summary.completeness}%`} subtext="Structured candidate fields that already have values" />
        <MetricCard label="Approved rows" value={String(cleanData.summary.readyCount)} subtext="Judge-approved rows that can be exported now" />
        <MetricCard label="Pending rows" value={String(cleanData.summary.incompleteCount)} subtext="Rows still blocked by missing values or review" />
        <MetricCard label="Quality score" value={`${cleanData.summary.qualityScore}%`} subtext="Overall confidence after shaping and judging" />
        <MetricCard label="Secondary fills" value={String(cleanData.summary.secondaryFieldCount)} subtext="Values carried from supporting sources" />
        <MetricCard label="Source conflicts" value={String(cleanData.summary.conflictFieldCount)} subtext="Merged fields that still disagree" />
      </div>

      <div className="rounded-2xl bg-sky-50 p-4 text-sm text-sky-900">
        Focus columns are highlighted. Non-focus columns can still be exported when source evidence exists; otherwise they stay blank/null so the CSV shape remains correct without invented values.
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
          <div className="space-y-3">
            {cleanData.analyze.problemFields.map((field) => (
              <div key={field.field} className="flex items-center justify-between rounded-xl border border-slate-200 px-4 py-3 text-sm">
                <span className="font-medium text-slate-700">{field.field}</span>
                <span className="font-semibold text-slate-900">{field.missingCount} missing</span>
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
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {cleanData.analyze.mergeCoverage.map((field) => (
            <div key={field.field} className="rounded-xl border border-slate-200 px-4 py-3 text-sm">
              <p className="font-medium text-slate-700">{field.field}</p>
              <p className="mt-2 text-slate-500">Conflicts: <span className="font-semibold text-slate-900">{field.conflictCount}</span></p>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Clean data preview" aside={cleanData.summary.incompleteCount === 0 ? <LinkButton href={`?tab=export`}>Open Export</LinkButton> : null}>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                {cleanData.columns.map((column) => (
                  <th key={column} className={`px-4 py-3 text-left font-semibold text-slate-500 ${criticalFields.includes(column) ? "bg-amber-50/50" : ""}`}>
                    <PriorityColumnHeader isPriority={criticalFields.includes(column)}>
                      {column}
                    </PriorityColumnHeader>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {cleanData.rows.map((row, index) => (
                <tr key={`${row.name}-${index}`}>
                  {cleanData.columns.map((column) => (
                    <td key={column} className="px-4 py-3 text-slate-700">
                      {formatFieldValue(row[column])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className={`rounded-2xl p-4 text-sm ${cleanData.summary.incompleteCount === 0 ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"}`}>
        {cleanData.summary.incompleteCount === 0
          ? "Clean data is ready. Export will keep unsupported fields blank/null instead of filling defaults without evidence."
          : `There are still ${cleanData.summary.incompleteCount} incomplete rows to resolve before export.`}
      </div>
    </div>
  );
}

function ExportTab({ jobId, exportReadiness }: { jobId: string; exportReadiness: ExportReadinessResponse }) {
  const isReadyToExport = exportReadiness.isReady;
  const nextStepMessage = isReadyToExport
    ? "Export the evidence-safe clean file now. Unsupported values remain blank/null, and rule-derived fields use accepted source values only."
    : exportReadiness.blockers[0]
      ? `Resolve ${exportReadiness.blockers[0].label.toLowerCase()} before exporting this file.`
      : "Review the evidence and checklist below before exporting this file.";

  return (
    <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <Card title="Export readiness">
        <div className="space-y-4">
          <DonutStat label="Ready for import" value={exportReadiness.readinessScore} hint="Closer to 100% means fewer issues before BeyondDegree import format." />
          <div className={`rounded-2xl p-4 text-sm ${exportReadiness.mergeRisk.riskLevel === "high" ? "bg-rose-50 text-rose-700" : exportReadiness.mergeRisk.riskLevel === "medium" ? "bg-amber-50 text-amber-900" : "bg-emerald-50 text-emerald-800"}`}>
            <p className="font-semibold">Merge risk</p>
            <p className="mt-1">
              {exportReadiness.mergeRisk.conflictFieldCount} conflicting fields / {exportReadiness.mergeRisk.secondaryFieldCount} fields filled from secondary sources
            </p>
          </div>
          <div className="space-y-3">
            {exportReadiness.checklist.map((item) => {
              const tone =
                item.status === "pass"
                  ? "bg-emerald-50 text-emerald-800"
                  : item.status === "warning"
                    ? "bg-amber-50 text-amber-800"
                    : "bg-rose-50 text-rose-700";

              return (
                <div key={item.key} className="flex items-center justify-between rounded-xl border border-slate-200 px-4 py-3 text-sm">
                  <span className="text-slate-700">{item.label}</span>
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase ${tone}`}>{item.status}</span>
                </div>
              );
            })}
          </div>
        </div>
      </Card>

      <div className="space-y-6">
        <Card title="Remaining blockers">
          <div className="space-y-3">
            {exportReadiness.blockers.length === 0 ? (
              <div className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                No blockers are currently stopping this export.
              </div>
            ) : null}
            {exportReadiness.blockers.map((blocker) => (
              <div key={blocker.label} className="flex items-center justify-between rounded-xl bg-amber-50 px-4 py-3 text-sm">
                <span className="text-slate-700">{blocker.label}</span>
                <span className="font-semibold text-amber-800">{blocker.count}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Export file preview">
          <div className="space-y-3 text-sm text-slate-600">
            <p>
              <span className="font-semibold text-slate-900">Template:</span> {exportReadiness.exportPreview.templateName}
            </p>
            <p>
              <span className="font-semibold text-slate-900">Rows ready:</span> {exportReadiness.exportPreview.totalRecords}
            </p>
            <p>
              <span className="font-semibold text-slate-900">Formats:</span> {exportReadiness.exportPreview.supportedFormats.join(", ")}
            </p>
            <p>
              <span className="font-semibold text-slate-900">Default file name:</span> {exportReadiness.exportPreview.defaultFileName}
            </p>
            <p className="rounded-2xl bg-slate-50 p-4 leading-6 text-slate-700">
              Export uses evidence-safe mapping. Fields without evidence stay blank/null instead of being filled by generic defaults.
            </p>
            <div className={`rounded-2xl p-4 ${isReadyToExport ? "bg-emerald-50" : "bg-slate-50"}`}>
              <p className="font-semibold text-slate-900">What to do next</p>
              <p className="mt-2 leading-6">{nextStepMessage}</p>
            </div>
            <ExportAction jobId={jobId} exportReadiness={exportReadiness} />
          </div>
        </Card>
      </div>
    </div>
  );
}

function ImportTab({ jobId, exportReadiness }: { jobId: string; exportReadiness: ExportReadinessResponse }) {
  const isReadyToImport = exportReadiness.isReady;
  const nextStepMessage = isReadyToImport
    ? "Run the import now to send the evidence-safe clean dataset into BeyondDegree."
    : exportReadiness.blockers[0]
      ? `Resolve ${exportReadiness.blockers[0].label.toLowerCase()} before starting the import.`
      : "Review the evidence and checklist below before importing this file.";

  return (
    <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <Card title="Import readiness">
        <div className="space-y-4">
          <DonutStat label="Ready to import" value={exportReadiness.readinessScore} hint="Import uses the same readiness rules as the final export gate." />
          <div className={`rounded-2xl p-4 text-sm ${isReadyToImport ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"}`}>
            <p className="font-semibold">{isReadyToImport ? "This job can be imported now." : "This job still has import blockers."}</p>
            <p className="mt-1">{nextStepMessage}</p>
          </div>
          <div className={`rounded-2xl p-4 text-sm ${exportReadiness.mergeRisk.riskLevel === "high" ? "bg-rose-50 text-rose-700" : exportReadiness.mergeRisk.riskLevel === "medium" ? "bg-amber-50 text-amber-900" : "bg-emerald-50 text-emerald-800"}`}>
            <p className="font-semibold">Merge risk before import</p>
            <p className="mt-1">
              {exportReadiness.mergeRisk.conflictFieldCount} conflicting fields / {exportReadiness.mergeRisk.secondaryFieldCount} fields filled from secondary sources
            </p>
          </div>
          <div className="space-y-3">
            {exportReadiness.checklist.map((item) => {
              const tone =
                item.status === "pass"
                  ? "bg-emerald-50 text-emerald-800"
                  : item.status === "warning"
                    ? "bg-amber-50 text-amber-800"
                    : "bg-rose-50 text-rose-700";

              return (
                <div key={item.key} className="flex items-center justify-between rounded-xl border border-slate-200 px-4 py-3 text-sm">
                  <span className="text-slate-700">{item.label}</span>
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase ${tone}`}>{item.status}</span>
                </div>
              );
            })}
          </div>
        </div>
      </Card>

      <div className="space-y-6">
        <Card title="Import summary">
          <div className="space-y-3 text-sm text-slate-600">
            <p>
              <span className="font-semibold text-slate-900">Template:</span> {exportReadiness.exportPreview.templateName}
            </p>
            <p>
              <span className="font-semibold text-slate-900">Rows prepared:</span> {exportReadiness.exportPreview.totalRecords}
            </p>
            <p className="rounded-2xl bg-slate-50 p-4 leading-6 text-slate-700">
              Import uses the same evidence-safe template mapping as export, so unsupported optional values remain blank/null.
            </p>
            <div className={`rounded-2xl p-4 ${isReadyToImport ? "bg-emerald-50" : "bg-slate-50"}`}>
              <p className="font-semibold text-slate-900">What to do next</p>
              <p className="mt-2 leading-6">{nextStepMessage}</p>
            </div>
            <ImportAction jobId={jobId} exportReadiness={exportReadiness} />
          </div>
        </Card>
      </div>
    </div>
  );
}

function ActivityTab({ activityItems }: { activityItems: ActivityItem[] }) {
  return (
    <Card title="Recent activity">
      <div className="space-y-4">
        {activityItems.map((item) => (
          <div key={item.id} className="flex items-start justify-between gap-4 rounded-2xl border border-slate-200 px-4 py-4">
            <div>
              <p className="font-semibold text-slate-900">{item.title}</p>
              <p className="mt-1 text-sm text-slate-600">{item.detail}</p>
            </div>
            <div className="text-right text-sm text-slate-500">
              <p>{item.time}</p>
              <p className="mt-1 uppercase tracking-wide">{item.type}</p>
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
              <p className="text-xs text-slate-500">{jobHeader.sourceNames.length > 1 ? `${jobHeader.sourceNames.length} sources selected` : "1 source selected"}</p>
              <p className="max-w-md text-xs text-slate-500">This page reflects direct backend processing. Use rerun only when you want to process the selected sources again.</p>
              <div className="flex flex-col items-end gap-2">
                <RunJobAction jobId={jobHeader.id} initialStatus={jobHeader.status} initialProgress={runActionProgress} />
                <DeleteJobAction jobId={jobHeader.id} redirectTo="/crawl-jobs" />
              </div>
            </div>
            <StatusBadge status={jobHeader.status} />
          </div>
        }
      />
      <Card title="Collection mode">
        <div className="space-y-3 text-sm text-slate-600">
          <p><span className="font-semibold text-slate-900">Mode:</span> {crawlModeLabel}</p>
          <p className="rounded-xl bg-slate-50 px-3 py-2">{modeExplanation}</p>
          {promptText ? <p><span className="font-semibold text-slate-900">Prompt:</span> {promptText}</p> : null}
          <p className="rounded-xl bg-sky-50 px-3 py-2 text-sky-900">
            Auto-approval needs confidence, required focus fields, and source evidence. Lower-confidence, conflicting, or unsupported candidates stay in review or remain blank/null instead of being treated as ready rows.
          </p>
        </div>
      </Card>
      {jobHeader.sourceNames.length > 1 ? (
        <Card title="Backend source plan" aside={<span className="text-sm font-medium text-slate-500">Read-only</span>}>
          <div className="flex min-w-0 flex-wrap gap-2">
            {jobHeader.sourceNames.map((sourceName, index) => (
              <span key={sourceName} className={`max-w-full break-words rounded-full px-3 py-1 text-sm font-medium ${index === 0 ? "bg-sky-100 text-sky-800" : "bg-slate-100 text-slate-700"}`}>
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
          <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-700">
            <p className="font-semibold text-slate-900">Live progress summary</p>
            <p className="mt-2">{progressSummary}</p>
          </div>
          <p className="text-sm text-slate-500">Last updated: {jobHeader.updatedAt}</p>
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
