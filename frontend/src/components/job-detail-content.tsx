import Link from "next/link";

import { type ActivityItem, type CleanDataResponse, type ExportReadinessResponse, type JobDetailHeader, type OverviewResponse, type ReviewQueueData } from "@/lib/types";
import { Card, DonutStat, LinkButton, MetricCard, PageHeader, PriorityColumnHeader, StatusBadge, Stepper } from "@/components/ui";
import { ExportAction } from "@/components/export-action";
import { FieldIssueBreakdown } from "@/components/field-issue-breakdown";
import { FocusFieldSelector } from "@/components/focus-field-selector";
import { ImportAction } from "@/components/import-action";
import { JobTabs } from "@/components/job-tabs";
import { OnboardingGuide } from "@/components/onboarding-guide";
import { ReviewActionPanel } from "@/components/review-action-panel";
import { RunJobAction } from "@/components/run-job-action";
import { BeforeAfterBars, ComparisonBars } from "@/components/simple-chart";

function OverviewTab({ overviewData }: { overviewData: OverviewResponse }) {
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

  return (
    <div className="grid gap-6 xl:grid-cols-[0.7fr_1.3fr]">
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
                href={`/crawl-jobs/${jobId}?tab=review&record=${item.recordId}`}
                className={`block rounded-2xl border px-4 py-3 transition ${
                  isSelected ? "border-sky-300 bg-sky-50" : "border-slate-200 bg-white hover:bg-slate-50"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-slate-900">{item.displayName}</p>
                    <p className="mt-1 text-sm text-slate-500">Unique key: {item.uniqueKey}</p>
                  </div>
                  <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
                    {item.flaggedFieldCount} fields
                  </span>
                </div>
                <div className="mt-3 flex items-center justify-between text-sm text-slate-600">
                  <span>Confidence: {item.confidence === null ? "—" : `${item.confidence}%`}</span>
                  {isSelected ? <span className="font-semibold text-sky-700">Viewing</span> : null}
                </div>
              </Link>
            );
          })}
        </div>
      </Card>

      <div className="space-y-6">
        <Card title="Record needing review">
          <div className="space-y-3 text-sm text-slate-600">
            <p className="text-lg font-semibold text-slate-950">{reviewDetail.displayName}</p>
            <p>Record ID: {reviewDetail.recordId}</p>
            <p>Unique key: {reviewDetail.uniqueKey}</p>
            <p>Confidence: {reviewDetail.confidence === null ? "—" : `${reviewDetail.confidence}%`}</p>
            <StatusBadge status={status} />
          </div>
        </Card>

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
            {reviewDetail.fields.map((field) => (
              <div key={field.fieldName} className="rounded-2xl border border-slate-200 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold text-slate-900">{field.fieldName}</p>
                  <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
                    {field.issueType}
                  </span>
                </div>
                <div className="mt-3 grid gap-3 text-sm md:grid-cols-3">
                  <div>
                    <p className="text-slate-500">Raw</p>
                    <p className="mt-1 rounded-xl bg-slate-50 px-3 py-2 text-slate-800">{String(field.rawValue)}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Suggested</p>
                    <p className="mt-1 rounded-xl bg-sky-50 px-3 py-2 text-slate-800">{String(field.suggestedValue)}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Final</p>
                    <p className="mt-1 rounded-xl bg-emerald-50 px-3 py-2 text-slate-800">{String(field.finalValue)}</p>
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
                          <span className="font-medium text-slate-900">{conflict.value === null ? "—" : String(conflict.value)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
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
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard label="Completeness" value={`${cleanData.summary.completeness}%`} subtext="Structured candidate fields that already have values" />
        <MetricCard label="Approved rows" value={String(cleanData.summary.readyCount)} subtext="Judge-approved rows that can be exported now" />
        <MetricCard label="Pending rows" value={String(cleanData.summary.incompleteCount)} subtext="Rows still blocked by missing values or review" />
        <MetricCard label="Quality score" value={`${cleanData.summary.qualityScore}%`} subtext="Overall confidence after shaping and judging" />
        <MetricCard label="Secondary fills" value={String(cleanData.summary.secondaryFieldCount)} subtext="Values carried from supporting sources" />
        <MetricCard label="Source conflicts" value={String(cleanData.summary.conflictFieldCount)} subtext="Merged fields that still disagree" />
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
                      {row[column] === null ? "—" : String(row[column])}
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
          ? "Clean data is ready. Continue to Export when you want to generate the final file."
          : `There are still ${cleanData.summary.incompleteCount} incomplete rows to resolve before export.`}
      </div>
    </div>
  );
}

function ExportTab({ jobId, exportReadiness }: { jobId: string; exportReadiness: ExportReadinessResponse }) {
  const isReadyToExport = exportReadiness.isReady;
  const nextStepMessage = isReadyToExport
    ? "Export the clean file now, then upload it into BeyondDegree admin."
    : exportReadiness.blockers[0]
      ? `Resolve ${exportReadiness.blockers[0].label.toLowerCase()} before exporting this file.`
      : "Review the checklist below before exporting this file.";

  return (
    <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <Card title="Export readiness">
        <div className="space-y-4">
          <DonutStat label="Ready for import" value={exportReadiness.readinessScore} hint="Closer to 100% means fewer issues before BeyondDegree import format." />
          <div className={`rounded-2xl p-4 text-sm ${exportReadiness.mergeRisk.riskLevel === "high" ? "bg-rose-50 text-rose-700" : exportReadiness.mergeRisk.riskLevel === "medium" ? "bg-amber-50 text-amber-900" : "bg-emerald-50 text-emerald-800"}`}>
            <p className="font-semibold">Merge risk</p>
            <p className="mt-1">
              {exportReadiness.mergeRisk.conflictFieldCount} conflicting fields · {exportReadiness.mergeRisk.secondaryFieldCount} fields filled from secondary sources
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
    ? "Run the import now to send the clean dataset into BeyondDegree."
    : exportReadiness.blockers[0]
      ? `Resolve ${exportReadiness.blockers[0].label.toLowerCase()} before starting the import.`
      : "Review the checklist below before importing this file.";

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
              {exportReadiness.mergeRisk.conflictFieldCount} conflicting fields · {exportReadiness.mergeRisk.secondaryFieldCount} fields filled from secondary sources
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
  reviewQueue: ReviewQueueData;
  overviewData: OverviewResponse;
  cleanData: CleanDataResponse;
  activityItems: ActivityItem[];
  exportReadiness: ExportReadinessResponse;
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
      ? "Prompt mode is AI-first: the system uses your strategy prompt to propose structured candidate rows, then judge and human review decide what is usable."
      : jobHeader.crawlMode === "supplemental_discovery"
        ? "Supplemental crawl is source-based: the system collects live rows from broader sources, shapes them toward the selected template, then judge and review decide what can ship."
        : "Trusted-source crawl is source-based: the system collects live rows from the country plan, shapes them toward the selected template, then judge and review decide what can ship.";
  const progressSummary = `${jobHeader.progress.crawled} collected · ${jobHeader.progress.processed ?? jobHeader.progress.extracted} processed · ${jobHeader.progress.cleanCandidates ?? jobHeader.progress.cleaned} clean candidates · ${jobHeader.progress.approved ?? 0} approved · ${jobHeader.progress.needsReview} in review · ${jobHeader.progress.skipped ?? 0} skipped`;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Crawl job"
        title={jobHeader.jobName}
        description={`Mode: ${crawlModeLabel} · Sources: ${sourceSummary} · Country: ${jobHeader.country} · Template: ${jobHeader.templateName}`}
        action={
          <div className="flex items-start gap-3">
            <div className="space-y-2 text-right">
              <p className="text-xs text-slate-500">{jobHeader.sourceNames.length > 1 ? `${jobHeader.sourceNames.length} sources selected` : "1 source selected"}</p>
              <p className="text-xs text-slate-500">This page reflects direct backend processing. Use rerun only when you want to process the selected sources again.</p>
              <RunJobAction jobId={jobHeader.id} initialStatus={jobHeader.status} initialProgress={jobHeader.progress} />
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
            Auto-approval needs at least 85% overall confidence and required fields above 80%. Lower-confidence or conflicting candidates stay in review instead of being treated as ready rows.
          </p>
        </div>
      </Card>
      {jobHeader.sourceNames.length > 1 ? (
        <Card title="Selected sources">
          <div className="flex flex-wrap gap-2">
            {jobHeader.sourceNames.map((sourceName, index) => (
              <span key={sourceName} className={`rounded-full px-3 py-1 text-sm font-medium ${index === 0 ? "bg-sky-100 text-sky-800" : "bg-slate-100 text-slate-700"}`}>
                {sourceName}
                {index === 0 ? " · Primary" : ""}
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
        availableFields={cleanData.columns}
        initialFocusFields={jobHeader.criticalFields}
      />

      <JobTabs />

      {activeTab === "review" ? <ReviewTab status={jobHeader.status} reviewQueue={reviewQueue} jobId={jobHeader.id} /> : null}
      {activeTab === "clean" ? <CleanTab cleanData={cleanData} criticalFields={jobHeader.criticalFields} /> : null}
      {activeTab === "export" ? <ExportTab jobId={jobHeader.id} exportReadiness={exportReadiness} /> : null}
      {activeTab === "import" ? <ImportTab jobId={jobHeader.id} exportReadiness={exportReadiness} /> : null}
      {activeTab === "activity" ? <ActivityTab activityItems={activityItems} /> : null}
      {activeTab === "overview" ? <OverviewTab overviewData={overviewData} /> : null}
    </div>
  );
}
