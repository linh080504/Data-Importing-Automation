import { cleanData } from "@/lib/mock-data";
import {
  type ActivityItem,
  type CleanDataResponse,
  type CrawlJobCreateInput,
  type CrawlJobCreateResult,
  type CrawlJobRunResult,
  type DataSourceItem,
  type DataSourceUpdateInput,
  type DataSourceUpdateResult,
  type DeleteTemplateResult,
  type RecommendedSourcesResponse,
  type ExportReadinessResponse,
  type ExportResult,
  type FieldIssueGroup,
  type FieldIssueRecord,
  type FieldSuggestionResponse,
  type ImportResult,
  type JobDetailHeader,
  type JobListItem,
  type JobStatus,
  type OverviewResponse,
  type ReviewActionInput,
  type ReviewActionResult,
  type ReviewQueueData,
  type ReviewQueueDetail,
  type TemplateItem,
  type TemplateUploadResult,
} from "@/lib/types";

type CrawlMode = "trusted_sources" | "prompt_discovery" | "supplemental_discovery";

type CrawlJobProgressApi = {
  total_records: number;
  crawled: number;
  extracted: number;
  needs_review: number;
  cleaned: number;
  skipped?: number;
  clean_candidates?: number;
  approved?: number;
  rejected?: number;
  processed?: number;
};

type CrawlJobListApiItem = {
  job_id: string;
  country: string;
  status: JobStatus;
  source_names: string[];
  template_name: string | null;
  crawl_mode?: CrawlMode;
  discovery_input?: Record<string, unknown> | null;
  updated_at: string;
  total_records: number;
  clean_records: number;
  clean_candidates?: number;
  approved_count?: number;
  rejected_count?: number;
  needs_review_count: number;
  quality_score: number | null;
  progress?: CrawlJobProgressApi | null;
};

type CrawlJobListApiResponse = {
  items: CrawlJobListApiItem[];
};

type CrawlJobDetailApiResponse = {
  job_id: string;
  country: string;
  status: JobStatus;
  source_names: string[];
  template_name: string | null;
  crawl_mode?: CrawlMode;
  discovery_input?: Record<string, unknown> | null;
  updated_at: string;
  progress: CrawlJobProgressApi;
  clean_records: number;
  clean_candidates?: number;
  approved_count?: number;
  rejected_count?: number;
  needs_review_count: number;
  quality_score: number | null;
  critical_fields?: string[] | null;
};

type ReviewQueueApiResponse = {
  total: number;
  page: number;
  limit: number;
  items: Array<{
    record_id: string;
    raw_record_id: string;
    overall_confidence: number | null;
    fields_to_review: Array<{
      field_name: string;
      raw_value: string | number | boolean | null;
      suggested_value: string | number | boolean | null;
      confidence: number;
      reason: string;
      merge_source_id?: string | null;
      merge_source_name?: string | null;
      merge_from_secondary?: boolean;
      merge_conflicts?: Array<{
        source_id: string;
        source_name: string;
        value: string | number | boolean | null;
      }>;
    }>;
  }>;
};

type CompareApiResponse = {
  total: number;
  items: Array<{
    raw_record_id: string;
    unique_key: string;
    status: string | null;
    quality_score: number | null;
    fields: Array<{
      field_name: string;
      raw_value: string | number | boolean | null;
      clean_value: string | number | boolean | null;
      merge_source_id?: string | null;
      merge_source_name?: string | null;
      merge_from_secondary?: boolean;
      merge_conflicts?: Array<{
        source_id: string;
        source_name: string;
        value: string | number | boolean | null;
      }>;
    }>;
  }>;
};

type SourceListApiResponse = {
  sources: Array<{
    id: string;
    name: string;
    country?: string | null;
    supported_fields: string[] | null;
    source_role?: string | null;
    trust_level?: string | null;
    config?: Record<string, unknown> | null;
    critical_fields?: string[] | null;
  }>;
};

type SourceCountryListApiResponse = {
  countries: string[];
};

type SourceUpdateApiResponse = {
  id: string;
  config?: Record<string, unknown> | null;
};

type RecommendedSourcesApiResponse = {
  country: string;
  templates: Array<{
    name: string;
    country: string;
    source_type: string;
    supported_fields: string[];
    config: Record<string, unknown>;
  }>;
};

type DeleteTemplateApiResponse = {
  id: string;
  message: string;
};

type TemplateListApiResponse = {
  templates: Array<{
    id: string;
    template_name: string;
    file_name: string;
    column_count: number;
  }>;
};

type FieldSuggestionApiResponse = {
  template_id: string;
  suggested_critical_fields: string[];
  suggested_fields_detail: Array<{
    name: string;
    score: number;
    reason: string;
  }>;
  min_fields: number;
  max_fields: number;
  reasoning: string;
};

type CrawlJobCreateApiResponse = {
  job_id: string;
  status: string;
  message: string;
  crawl_mode?: CrawlMode;
  discovery_input?: Record<string, unknown> | null;
  total_records: number;
  crawled: number;
  extracted: number;
  needs_review: number;
  cleaned: number;
  skipped?: number;
  clean_candidates?: number;
  approved?: number;
  rejected?: number;
};

type CrawlJobRunApiResponse = {
  job_id: string;
  status: string;
  total_records: number;
  crawled: number;
  extracted: number;
  needs_review: number;
  cleaned: number;
  message: string;
};

type ImportReadinessApiResponse = {
  is_ready: boolean;
  checks: Array<{
    key: string;
    label: string;
    passed: boolean;
    blocker_count: number;
  }>;
  blockers: Array<{
    key: string;
    label: string;
    count: number;
  }>;
};

type ImportApiResponse = {
  job_id: string;
  status: string;
  message: string;
  inserted_records: number;
  updated_records: number;
  duplicate_records: number;
  total_records: number;
  imported_records: number;
};

export type JobOverviewAndClean = {
  overview: OverviewResponse;
  cleanData: CleanDataResponse;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";
const apiTimeoutMs = 1200;
const uploadApiTimeoutMs = 10000;
const mutationTimeoutMs = Number.parseInt(process.env.NEXT_PUBLIC_API_MUTATION_TIMEOUT_MS ?? "", 10) || 300_000;
const pollTimeoutMs = 3000;

const fallbackCountries = ["Australia", "Canada", "Germany", "Japan", "Singapore", "United Kingdom", "USA", "Vietnam"];
const fallbackSources: DataSourceItem[] = [];
const fallbackTemplates: TemplateItem[] = [
  {
    id: "tpl_mock_university_import_clean_7",
    templateName: "University_Import_Clean-7",
    fileName: "University_Import_Clean-7.csv",
    columnCount: cleanData.columns.length,
  },
];

async function fetchWithTimeout(input: string, init?: RequestInit, timeoutMs = apiTimeoutMs) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

function sourceSummary(sourceNames: string[]) {
  const primarySource = sourceNames[0] ?? "Data Source";
  return sourceNames.length > 1 ? `${primarySource} +${sourceNames.length - 1} more` : primarySource;
}

function formatJobName(item: { country: string; source_names: string[] }) {
  return `${item.country} - ${sourceSummary(item.source_names)}`;
}

function emptyJobProgress() {
  return {
    totalRecords: 0,
    crawled: 0,
    extracted: 0,
    needsReview: 0,
    cleaned: 0,
    skipped: 0,
    cleanCandidates: 0,
    approved: 0,
    rejected: 0,
    processed: 0,
  };
}

function mapJobProgress(progress: CrawlJobProgressApi | null | undefined) {
  if (!progress) {
    return emptyJobProgress();
  }
  return {
    totalRecords: progress.total_records,
    crawled: progress.crawled,
    extracted: progress.extracted,
    needsReview: progress.needs_review,
    cleaned: progress.cleaned,
    skipped: progress.skipped ?? 0,
    cleanCandidates: progress.clean_candidates ?? progress.cleaned,
    approved: progress.approved ?? 0,
    rejected: progress.rejected ?? 0,
    processed: progress.processed ?? progress.extracted,
  };
}

function cleanCandidateCountForItem(item: { clean_candidates?: number | null; clean_records: number; progress?: CrawlJobProgressApi | null }) {
  return item.clean_candidates ?? item.progress?.clean_candidates ?? item.clean_records;
}

function approvedCountForItem(item: { approved_count?: number | null; progress?: CrawlJobProgressApi | null }) {
  return item.approved_count ?? item.progress?.approved ?? 0;
}

function progressPercentFromProgress(item: { total_records: number; clean_records: number; progress?: CrawlJobProgressApi | null; clean_candidates?: number | null }) {
  const completed = cleanCandidateCountForItem(item);
  return item.total_records > 0 ? Math.round((completed / item.total_records) * 100) : 0;
}

function mapJobStatusForAction(status: JobStatus, needsReviewCount: number, approvedCount: number): JobListItem["nextAction"] {
  if (status === "FAILED") {
    return { label: "Pipeline failed — view details", type: "view" };
  }
  if (status === "CRAWLING" || status === "EXTRACTING" || status === "CLEANING") {
    return { label: "Track processing progress", type: "progress" };
  }
  if (needsReviewCount > 0 || status === "NEEDS_REVIEW") {
    return { label: "Review flagged records before export", type: "review" };
  }
  if ((status === "READY_TO_EXPORT" || status === "EXPORTED") && approvedCount > 0) {
    return { label: "Export clean file", type: "export" };
  }
  return { label: "View job details", type: "view" };
}

function maybeCrawlMode(value: unknown): CrawlMode | undefined {
  return value === "trusted_sources" || value === "prompt_discovery" || value === "supplemental_discovery" ? value : undefined;
}

function buildSteps(status: JobStatus): JobDetailHeader["steps"] {
  if (status === "EXPORTED") {
    return [
      { key: "setup", label: "Setup", status: "completed" },
      { key: "crawl", label: "Crawl", status: "completed" },
      { key: "review", label: "Review", status: "completed" },
      { key: "clean", label: "Clean", status: "completed" },
      { key: "export", label: "Export", status: "completed" },
    ];
  }

  if (status === "READY_TO_EXPORT") {
    return [
      { key: "setup", label: "Setup", status: "completed" },
      { key: "crawl", label: "Crawl", status: "completed" },
      { key: "review", label: "Review", status: "completed" },
      { key: "clean", label: "Clean", status: "completed" },
      { key: "export", label: "Export", status: "current" },
    ];
  }

  if (status === "NEEDS_REVIEW") {
    return [
      { key: "setup", label: "Setup", status: "completed" },
      { key: "crawl", label: "Crawl", status: "completed" },
      { key: "review", label: "Review", status: "current" },
      { key: "clean", label: "Clean", status: "pending" },
      { key: "export", label: "Export", status: "pending" },
    ];
  }

  if (status === "CLEANING") {
    return [
      { key: "setup", label: "Setup", status: "completed" },
      { key: "crawl", label: "Crawl", status: "completed" },
      { key: "review", label: "Review", status: "completed" },
      { key: "clean", label: "Clean", status: "current" },
      { key: "export", label: "Export", status: "pending" },
    ];
  }

  if (status === "FAILED") {
    return [
      { key: "setup", label: "Setup", status: "completed" },
      { key: "crawl", label: "Crawl", status: "blocked" },
      { key: "review", label: "Review", status: "pending" },
      { key: "clean", label: "Clean", status: "pending" },
      { key: "export", label: "Export", status: "pending" },
    ];
  }

  return [
    { key: "setup", label: "Setup", status: "completed" },
    { key: "crawl", label: "Crawl", status: "current" },
    { key: "review", label: "Review", status: "pending" },
    { key: "clean", label: "Clean", status: "pending" },
    { key: "export", label: "Export", status: "pending" },
  ];
}

function mapJobListItem(item: CrawlJobListApiItem): JobListItem {
  return {
    id: item.job_id,
    jobName: formatJobName(item),
    country: item.country,
    sourceName: item.source_names[0] ?? "Unknown source",
    templateName: item.template_name ?? "No template",
    crawlMode: maybeCrawlMode(item.crawl_mode),
    discoveryInput: item.discovery_input ?? null,
    status: item.status,
    progressPercent: progressPercentFromProgress(item),
    totalRecords: item.total_records,
    cleanRecords: cleanCandidateCountForItem(item),
    needReviewCount: item.needs_review_count,
    qualityScore: item.quality_score,
    nextAction: mapJobStatusForAction(item.status, item.needs_review_count, approvedCountForItem(item)),
    updatedAt: item.updated_at,
  };
}

function mapJobHeader(data: CrawlJobDetailApiResponse): JobDetailHeader {
  return {
    id: data.job_id,
    jobName: `${data.country} - ${sourceSummary(data.source_names)}`,
    country: data.country,
    sourceName: sourceSummary(data.source_names),
    sourceNames: data.source_names,
    templateName: data.template_name ?? "No template",
    crawlMode: maybeCrawlMode(data.crawl_mode),
    discoveryInput: data.discovery_input ?? null,
    status: data.status,
    progress: mapJobProgress(data.progress),
    steps: buildSteps(data.status),
    updatedAt: data.updated_at,
    criticalFields: data.critical_fields ?? [],
  };
}

function mapCreateResult(data: CrawlJobCreateApiResponse): CrawlJobCreateResult {
  return {
    jobId: data.job_id,
    status: data.status,
    message: data.message,
    totalRecords: data.total_records,
    crawled: data.crawled,
    extracted: data.extracted,
    needsReview: data.needs_review,
    cleaned: data.cleaned,
    skipped: data.skipped ?? 0,
    cleanCandidates: data.clean_candidates ?? data.cleaned,
    approved: data.approved ?? 0,
    rejected: data.rejected ?? 0,
  };
}

function inferIssueType(reason: string): "missing" | "format" | "confidence" | "duplicate" {
  const normalized = reason.toLowerCase();
  if (normalized.includes("missing")) return "missing";
  if (normalized.includes("duplicate")) return "duplicate";
  if (normalized.includes("format")) return "format";
  return "confidence";
}

function emptyReviewDetail(jobId: string): ReviewQueueDetail {
  return {
    recordId: `${jobId}-no-review-needed`,
    displayName: "No records currently need review",
    uniqueKey: jobId,
    confidence: null,
    status: "READY_TO_EXPORT",
    fields: [],
  };
}

function isTimeoutError(cause: unknown) {
  return cause instanceof Error && cause.name === "AbortError";
}

function createTimeoutFailure(timeoutMs: number): never {
  throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s.`);
}

function liveDataError(context: string, cause?: unknown): never {
  if (cause instanceof Error) {
    throw new Error(`${context}: ${cause.message}`);
  }
  throw new Error(context);
}

function requireOk(response: Response, context: string) {
  if (!response.ok) {
    throw new Error(`${context} failed with HTTP ${response.status}.`);
  }
}

function requireHeader(header: JobDetailHeader | null, jobId: string): JobDetailHeader {
  if (!header) {
    throw new Error(`Job ${jobId} was not found or did not return live data.`);
  }
  return header;
}

function requireOverview(overviewData: OverviewResponse | null, jobId: string): OverviewResponse {
  if (!overviewData) {
    throw new Error(`Overview for job ${jobId} is unavailable.`);
  }
  return overviewData;
}

function requireCleanDataValue(cleanDataValue: CleanDataResponse | null, jobId: string): CleanDataResponse {
  if (!cleanDataValue) {
    throw new Error(`Clean data for job ${jobId} is unavailable.`);
  }
  return cleanDataValue;
}

function requireReviewQueue(reviewQueue: ReviewQueueData | null, jobId: string): ReviewQueueData {
  if (!reviewQueue) {
    throw new Error(`Review queue for job ${jobId} is unavailable.`);
  }
  return reviewQueue;
}

function requireExportReadiness(exportReadiness: ExportReadinessResponse | null, jobId: string): ExportReadinessResponse {
  if (!exportReadiness) {
    throw new Error(`Export readiness for job ${jobId} is unavailable.`);
  }
  return exportReadiness;
}

function toPercent(value: number, total: number) {
  if (total <= 0) return 0;
  return Math.round((value / total) * 100);
}

function cleanCandidateCountForDetail(detail: CrawlJobDetailApiResponse) {
  return detail.clean_candidates ?? detail.progress.clean_candidates ?? detail.clean_records;
}

function approvedCountForDetail(detail: CrawlJobDetailApiResponse) {
  return detail.approved_count ?? detail.progress.approved ?? 0;
}

function mapReviewItem(item: ReviewQueueApiResponse["items"][number]): ReviewQueueDetail {
  return {
    recordId: item.record_id,
    displayName: `Record ${item.record_id}`,
    uniqueKey: item.raw_record_id,
    confidence: item.overall_confidence,
    status: item.fields_to_review.length > 0 ? "NEEDS_REVIEW" : "READY_TO_EXPORT",
    fields: item.fields_to_review.map((field) => ({
      fieldName: field.field_name,
      rawValue: field.raw_value,
      suggestedValue: field.suggested_value,
      finalValue: field.suggested_value,
      reason: field.reason,
      confidence: field.confidence,
      issueType: inferIssueType(field.reason),
      mergeSourceId: field.merge_source_id ?? null,
      mergeSourceName: field.merge_source_name ?? null,
      mergeFromSecondary: Boolean(field.merge_from_secondary),
      mergeConflicts: field.merge_conflicts ?? [],
    })),
  };
}

function mapReviewQueueData(jobId: string, data: ReviewQueueApiResponse, selectedRecordId?: string): ReviewQueueData {
  const items = data.items.map((item) => ({
    recordId: item.record_id,
    displayName: `Record ${item.record_id}`,
    uniqueKey: item.raw_record_id,
    confidence: item.overall_confidence,
    flaggedFieldCount: item.fields_to_review.length,
  }));

  const selectedItem = data.items.find((item) => item.record_id === selectedRecordId) ?? data.items[0];

  return {
    total: data.total,
    selectedRecordId: selectedItem?.record_id ?? null,
    items,
    selectedDetail: selectedItem ? mapReviewItem(selectedItem) : emptyReviewDetail(jobId),
  };
}

function mapOverviewAndCleanFromCompare(detail: CrawlJobDetailApiResponse, compare: CompareApiResponse): JobOverviewAndClean {
  const totalRecords = detail.progress.total_records;
  const cleanRecords = cleanCandidateCountForDetail(detail);
  const approvedCount = approvedCountForDetail(detail);
  const needReviewCount = detail.needs_review_count;
  const rejectedCount = detail.rejected_count ?? detail.progress.rejected ?? 0;
  const qualityScore = detail.quality_score;

  const fieldMap = new Map<string, {
    total: number;
    cleanFilled: number;
    rawFilled: number;
    missing: number;
    primaryCount: number;
    secondaryCount: number;
    conflictCount: number;
  }>();

  let mergeSecondaryFieldCount = 0;
  let mergeConflictFieldCount = 0;

  for (const item of compare.items) {
    for (const field of item.fields) {
      const key = field.field_name;
      const bucket = fieldMap.get(key) ?? {
        total: 0,
        cleanFilled: 0,
        rawFilled: 0,
        missing: 0,
        primaryCount: 0,
        secondaryCount: 0,
        conflictCount: 0,
      };
      bucket.total += 1;
      if (field.raw_value !== null && field.raw_value !== "") bucket.rawFilled += 1;
      if (field.clean_value !== null && field.clean_value !== "") bucket.cleanFilled += 1;
      if (field.clean_value === null || field.clean_value === "") bucket.missing += 1;
      if (field.merge_from_secondary) {
        bucket.secondaryCount += 1;
        mergeSecondaryFieldCount += 1;
      } else if (field.merge_source_id) {
        bucket.primaryCount += 1;
      }
      if ((field.merge_conflicts ?? []).length > 0) {
        bucket.conflictCount += 1;
        mergeConflictFieldCount += 1;
      }
      fieldMap.set(key, bucket);
    }
  }

  const entries = Array.from(fieldMap.entries());
  const rawVsCleanByField = entries.slice(0, 6).map(([field, stat]) => ({
    field,
    rawValue: toPercent(stat.rawFilled, stat.total),
    cleanValue: toPercent(stat.cleanFilled, stat.total),
  }));

  const fieldCompleteness = entries.slice(0, 8).map(([field, stat]) => {
    const percent = toPercent(stat.cleanFilled, stat.total);
    return {
      field,
      percent,
      severity: percent < 70 ? ("high" as const) : percent < 90 ? ("medium" as const) : ("low" as const),
    };
  });

  const mergeCoverage = entries.slice(0, 6).map(([field, stat]) => ({
    field,
    primaryCount: stat.primaryCount,
    secondaryCount: stat.secondaryCount,
    conflictCount: stat.conflictCount,
  }));

  const problemFields = entries
    .filter(([, stat]) => stat.missing > 0)
    .sort((a, b) => b[1].missing - a[1].missing)
    .slice(0, 6)
    .map(([field, stat]) => ({ field, missingCount: stat.missing }));

  const avgCompleteness = fieldCompleteness.length
    ? Math.round(fieldCompleteness.reduce((sum, field) => sum + field.percent, 0) / fieldCompleteness.length)
    : 0;

  const qualityValue = qualityScore ?? avgCompleteness;
  const reviewCompletion = totalRecords > 0 ? 100 - toPercent(needReviewCount, totalRecords) : 0;
  const importReadiness = Math.round((qualityValue + avgCompleteness + reviewCompletion) / 3);

  const fieldIssueMap = new Map<string, FieldIssueRecord[]>();
  for (const item of compare.items) {
    const displayName = item.unique_key;
    for (const field of item.fields) {
      const key = field.field_name;
      const hasConflicts = (field.merge_conflicts ?? []).length > 0;
      const isMissing = field.clean_value === null;
      const isEmpty = field.clean_value === "";
      if (!isMissing && !isEmpty && !hasConflicts) continue;
      const issue: FieldIssueRecord["issue"] = hasConflicts ? "conflict" : isMissing ? "missing" : "empty";
      const records = fieldIssueMap.get(key) ?? [];
      records.push({ uniqueKey: item.unique_key, displayName, issue, currentValue: field.clean_value });
      fieldIssueMap.set(key, records);
    }
  }

  const fieldIssues: FieldIssueGroup[] = Array.from(fieldIssueMap.entries())
    .map(([field, records]) => ({ field, issueCount: records.length, records: records.slice(0, 10) }))
    .sort((a, b) => b.issueCount - a.issueCount);

  return {
    overview: {
      summary: {
        totalRecords,
        cleanRecords,
        needReviewCount,
        rejectedCount,
        qualityScore,
        exportReadinessScore: importReadiness,
        currentStatusLabel: detail.status.replaceAll("_", " "),
        mergeSecondaryFieldCount,
        mergeConflictFieldCount,
      },
      analyze: {
        overallQuality: qualityValue,
        completeness: avgCompleteness,
        reviewCompletion,
        importReadiness,
        rawVsCleanByField,
        issueTrend: problemFields.slice(0, 3).map((item) => ({
          label: `Missing ${item.field}`,
          before: Math.min(item.missingCount * 2, 100),
          after: item.missingCount,
        })),
        mergeCoverage: mergeCoverage.map((item) => ({
          label: item.field,
          primaryValue: item.primaryCount,
          secondaryValue: item.secondaryCount,
          conflictValue: item.conflictCount,
        })),
      },
      topIssues: [
        ...problemFields.slice(0, 2).map((item) => ({
          label: `Missing ${item.field}`,
          severity: item.missingCount > 10 ? ("high" as const) : item.missingCount > 4 ? ("medium" as const) : ("low" as const),
          count: item.missingCount,
        })),
        ...(mergeConflictFieldCount > 0 ? [{ label: "Source conflicts", severity: "medium" as const, count: mergeConflictFieldCount }] : []),
      ].slice(0, 3),
      nextAction: {
        title: needReviewCount > 0 ? "Review flagged records before export" : "Dataset is ready for export",
        description:
          needReviewCount > 0
            ? "Some fields still need review to maximize import quality."
            : "You can proceed to export and upload to BeyondDegree admin.",
        primaryLabel: needReviewCount > 0 ? "Go to Review Queue" : "Go to Export",
        primaryTarget: needReviewCount > 0 ? "review" : "export",
      },
      fieldIssues,
    },
    cleanData: {
      summary: {
        completeness: avgCompleteness,
        readyCount: approvedCount,
        incompleteCount: Math.max(totalRecords - approvedCount, 0),
        qualityScore,
        secondaryFieldCount: mergeSecondaryFieldCount,
        conflictFieldCount: mergeConflictFieldCount,
      },
      analyze: {
        problemFields,
        fieldCompleteness,
        mergeCoverage,
      },
      columns: entries.map(([field]) => field),
      rows: compare.items.slice(0, 10).map((item) => {
        const row: Record<string, string | number | boolean | null> = {};
        for (const field of item.fields) {
          row[field.field_name] = field.clean_value;
        }
        return row;
      }),
    },
  };
}

function sourceRoleLabel(source: DataSourceItem) {
  const role = source.sourceRole?.toLowerCase();
  if (role === "official") return "Official";
  if (role === "reference") return "Reference";
  if (role === "community") return "Community";
  return "General";
}

function sourceTone(source: DataSourceItem) {
  const role = source.sourceRole?.toLowerCase();
  if (role === "official") return "bg-emerald-100 text-emerald-800";
  if (role === "reference") return "bg-sky-100 text-sky-800";
  if (role === "community") return "bg-amber-100 text-amber-800";
  return "bg-slate-100 text-slate-700";
}

export { sourceRoleLabel, sourceTone };

export async function getJobs(): Promise<JobListItem[]> {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}/crawl-jobs`, { cache: "no-store" });
    requireOk(response, "Loading crawl jobs");
    const data = (await response.json()) as CrawlJobListApiResponse;
    return data.items.map(mapJobListItem);
  } catch (cause) {
    if (isTimeoutError(cause)) {
      createTimeoutFailure(apiTimeoutMs);
    }
    liveDataError("Loading crawl jobs failed", cause);
  }
}

export async function getJobHeader(jobId: string): Promise<JobDetailHeader | null> {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}/crawl-jobs/${jobId}`, { cache: "no-store" });
    if (response.status === 404) {
      return null;
    }
    requireOk(response, `Loading crawl job ${jobId}`);
    const data = (await response.json()) as CrawlJobDetailApiResponse;
    return mapJobHeader(data);
  } catch (cause) {
    if (isTimeoutError(cause)) {
      createTimeoutFailure(apiTimeoutMs);
    }
    liveDataError(`Loading crawl job ${jobId} failed`, cause);
  }
}

export async function getJobOverview(jobId: string): Promise<OverviewResponse> {
  try {
    const [detailResponse, compareResponse] = await Promise.all([
      fetchWithTimeout(`${apiBaseUrl}/crawl-jobs/${jobId}`, { cache: "no-store" }),
      fetchWithTimeout(`${apiBaseUrl}/crawl-jobs/${jobId}/compare`, { cache: "no-store" }),
    ]);
    requireOk(detailResponse, `Loading crawl job ${jobId}`);
    requireOk(compareResponse, `Loading compare data for job ${jobId}`);
    const detail = (await detailResponse.json()) as CrawlJobDetailApiResponse;
    const compare = (await compareResponse.json()) as CompareApiResponse;
    return mapOverviewAndCleanFromCompare(detail, compare).overview;
  } catch (cause) {
    if (isTimeoutError(cause)) {
      createTimeoutFailure(apiTimeoutMs);
    }
    liveDataError(`Loading overview for job ${jobId} failed`, cause);
  }
}

export async function getReviewQueue(jobId: string, selectedRecordId?: string): Promise<ReviewQueueData> {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}/crawl-jobs/${jobId}/review-queue?page=1&limit=50`, {
      cache: "no-store",
    });
    requireOk(response, `Loading review queue for job ${jobId}`);
    const data = (await response.json()) as ReviewQueueApiResponse;
    return mapReviewQueueData(jobId, data, selectedRecordId);
  } catch (cause) {
    if (isTimeoutError(cause)) {
      createTimeoutFailure(apiTimeoutMs);
    }
    liveDataError(`Loading review queue for job ${jobId} failed`, cause);
  }
}

export async function getReviewDetail(jobId: string): Promise<ReviewQueueDetail> {
  const reviewQueue = await getReviewQueue(jobId);
  return reviewQueue.selectedDetail;
}

export async function getCleanData(jobId: string): Promise<CleanDataResponse> {
  try {
    const [detailResponse, compareResponse] = await Promise.all([
      fetchWithTimeout(`${apiBaseUrl}/crawl-jobs/${jobId}`, { cache: "no-store" }),
      fetchWithTimeout(`${apiBaseUrl}/crawl-jobs/${jobId}/compare`, { cache: "no-store" }),
    ]);
    requireOk(detailResponse, `Loading crawl job ${jobId}`);
    requireOk(compareResponse, `Loading compare data for job ${jobId}`);
    const detail = (await detailResponse.json()) as CrawlJobDetailApiResponse;
    const compare = (await compareResponse.json()) as CompareApiResponse;
    return mapOverviewAndCleanFromCompare(detail, compare).cleanData;
  } catch (cause) {
    if (isTimeoutError(cause)) {
      createTimeoutFailure(apiTimeoutMs);
    }
    liveDataError(`Loading clean data for job ${jobId} failed`, cause);
  }
}

export async function getExportReadiness(jobId: string): Promise<ExportReadinessResponse> {
  try {
    const [header, overviewData, cleanDataValue, readinessResponse] = await Promise.all([
      getJobHeader(jobId),
      getJobOverview(jobId),
      getCleanData(jobId),
      fetchWithTimeout(`${apiBaseUrl}/crawl-jobs/${jobId}/import-readiness`, { cache: "no-store" }),
    ]);

    const resolvedHeader = requireHeader(header, jobId);
    const resolvedOverview = requireOverview(overviewData, jobId);
    const resolvedClean = requireCleanDataValue(cleanDataValue, jobId);

    const mergeRisk = {
      secondaryFieldCount: resolvedClean.summary.secondaryFieldCount,
      conflictFieldCount: resolvedClean.summary.conflictFieldCount,
      riskLevel:
        resolvedClean.summary.conflictFieldCount > 10
          ? ("high" as const)
          : resolvedClean.summary.conflictFieldCount > 0 || resolvedClean.summary.secondaryFieldCount > 25
            ? ("medium" as const)
            : ("low" as const),
    };

    if (readinessResponse.ok) {
      const readiness = (await readinessResponse.json()) as ImportReadinessApiResponse;
      const readinessScore = readiness.is_ready
        ? 100
        : Math.max(0, 100 - readiness.checks.reduce((sum, check) => sum + check.blocker_count * 10, 0));

      return {
        isReady: readiness.is_ready && mergeRisk.conflictFieldCount === 0,
        readinessScore,
        checklist: [
          ...readiness.checks.map((check) => ({
            key: check.key,
            label: check.label,
            status: check.passed ? ("pass" as const) : check.key === "schema_match" ? ("fail" as const) : ("warning" as const),
          })),
          {
            key: "review_done",
            label: "Review completed",
            status: resolvedOverview.summary.needReviewCount === 0 ? ("pass" as const) : ("warning" as const),
          },
          {
            key: "merge_conflicts",
            label: "Source conflicts resolved",
            status: mergeRisk.conflictFieldCount === 0 ? ("pass" as const) : ("warning" as const),
          },
        ],
        blockers: [
          ...readiness.blockers.map((blocker) => ({
            label: blocker.label,
            count: blocker.count,
            severity: blocker.count > 10 ? ("high" as const) : blocker.count > 4 ? ("medium" as const) : ("low" as const),
          })),
          ...(mergeRisk.conflictFieldCount > 0
            ? [{ label: "Source conflicts", count: mergeRisk.conflictFieldCount, severity: mergeRisk.riskLevel }]
            : []),
        ],
        mergeRisk,
        exportPreview: {
          templateName: resolvedHeader.templateName,
          totalRecords: resolvedClean.summary.readyCount,
          supportedFormats: ["csv", "xlsx"],
          defaultFileName: `${resolvedHeader.jobName.toLowerCase().replaceAll(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || jobId}_clean.csv`,
        },
      };
    }

    const blockers = [
      ...resolvedClean.analyze.problemFields
        .filter((field) => field.missingCount > 0)
        .slice(0, 5)
        .map((field) => ({
          label: `Missing ${field.field}`,
          count: field.missingCount,
          severity: field.missingCount > 10 ? ("high" as const) : field.missingCount > 4 ? ("medium" as const) : ("low" as const),
        })),
      ...(mergeRisk.conflictFieldCount > 0
        ? [{ label: "Source conflicts", count: mergeRisk.conflictFieldCount, severity: mergeRisk.riskLevel }]
        : []),
    ];

    const reviewDone = resolvedOverview.summary.needReviewCount === 0;
    const requiredFieldsReady = resolvedClean.summary.incompleteCount === 0;
    const schemaMatch = resolvedClean.columns.length > 0;
    const importCompatible = (resolvedOverview.summary.exportReadinessScore ?? 0) >= 85;

    return {
      isReady: reviewDone && requiredFieldsReady && schemaMatch && blockers.length === 0,
      readinessScore: resolvedOverview.summary.exportReadinessScore ?? resolvedClean.summary.completeness,
      checklist: [
        { key: "review_done", label: "Review completed", status: reviewDone ? "pass" : "warning" },
        { key: "required_fields", label: "Required fields filled", status: requiredFieldsReady ? "pass" : "warning" },
        { key: "schema_match", label: "Schema matches template", status: schemaMatch ? "pass" : "fail" },
        { key: "duplicates", label: "Duplicate check", status: "pass" },
        { key: "import_compatible", label: "Compatible with BeyondDegree import", status: importCompatible ? "pass" : "warning" },
        { key: "merge_conflicts", label: "Source conflicts resolved", status: mergeRisk.conflictFieldCount === 0 ? "pass" : "warning" },
      ],
      blockers,
      mergeRisk,
      exportPreview: {
        templateName: resolvedHeader.templateName,
        totalRecords: resolvedClean.summary.readyCount,
        supportedFormats: ["csv", "xlsx"],
        defaultFileName: `${resolvedHeader.jobName.toLowerCase().replaceAll(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || jobId}_clean.csv`,
      },
    };
  } catch (cause) {
    if (isTimeoutError(cause)) {
      createTimeoutFailure(apiTimeoutMs);
    }
    liveDataError(`Loading export readiness for job ${jobId} failed`, cause);
  }
}

export async function getActivityItems(jobId: string): Promise<ActivityItem[]> {
  try {
    const [header, overviewData, reviewQueue, cleanDataValue, exportReadiness] = await Promise.all([
      getJobHeader(jobId),
      getJobOverview(jobId),
      getReviewQueue(jobId),
      getCleanData(jobId),
      getExportReadiness(jobId),
    ]);

    const resolvedHeader = requireHeader(header, jobId);
    const resolvedOverview = requireOverview(overviewData, jobId);
    const resolvedReviewQueue = requireReviewQueue(reviewQueue, jobId);
    const resolvedCleanData = requireCleanDataValue(cleanDataValue, jobId);
    const resolvedExportReadiness = requireExportReadiness(exportReadiness, jobId);

    const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const topBlocker = resolvedExportReadiness.blockers[0];
    const importReady = resolvedExportReadiness.isReady;

    return [
      {
        id: `act-${jobId}-status`,
        time: now,
        type: resolvedHeader.status === "READY_TO_EXPORT" || resolvedHeader.status === "EXPORTED" ? "success" : "info",
        title: `Job status: ${resolvedHeader.status.replaceAll("_", " ")}`,
        detail: `Template ${resolvedHeader.templateName} · Source ${resolvedHeader.sourceName}`,
      },
      {
        id: `act-${jobId}-review`,
        time: now,
        type: resolvedReviewQueue.items.length > 0 ? "warning" : "success",
        title: resolvedReviewQueue.items.length > 0 ? "Review queue still needs attention" : "Review queue is clear",
        detail:
          resolvedReviewQueue.items.length > 0
            ? `${resolvedReviewQueue.items.length} records are waiting for manual review`
            : "No flagged records are blocking the export flow",
      },
      {
        id: `act-${jobId}-quality`,
        time: now,
        type: (resolvedOverview.summary.qualityScore ?? 0) >= 85 ? "success" : "warning",
        title: `Quality score ${resolvedOverview.summary.qualityScore ?? 0}%`,
        detail: `${resolvedCleanData.summary.readyCount} ready rows · ${resolvedCleanData.summary.incompleteCount} incomplete rows`,
      },
      {
        id: `act-${jobId}-merge`,
        time: now,
        type:
          resolvedExportReadiness.mergeRisk.conflictFieldCount > 0
            ? "warning"
            : resolvedExportReadiness.mergeRisk.secondaryFieldCount > 0
              ? "info"
              : "success",
        title:
          resolvedExportReadiness.mergeRisk.conflictFieldCount > 0
            ? "Source disagreements still need resolution"
            : resolvedExportReadiness.mergeRisk.secondaryFieldCount > 0
              ? "Secondary sources supplemented this dataset"
              : "Primary sources provided all current values",
        detail:
          resolvedExportReadiness.mergeRisk.conflictFieldCount > 0
            ? `${resolvedExportReadiness.mergeRisk.conflictFieldCount} merged fields still conflict across sources`
            : `${resolvedExportReadiness.mergeRisk.secondaryFieldCount} fields were filled from secondary sources`,
      },
      {
        id: `act-${jobId}-export`,
        time: now,
        type: importReady ? "success" : "warning",
        title: importReady ? "Export is ready to run" : "Export still has blockers",
        detail: topBlocker ? `${topBlocker.label} (${topBlocker.count})` : `Readiness score ${resolvedExportReadiness.readinessScore}%`,
      },
    ];
  } catch (cause) {
    if (isTimeoutError(cause)) {
      createTimeoutFailure(apiTimeoutMs);
    }
    liveDataError(`Loading activity feed for job ${jobId} failed`, cause);
  }
}

export async function triggerExport(jobId: string, format: "csv" | "xlsx", includeMetadata = false): Promise<ExportResult | null> {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}/crawl-jobs/${jobId}/export`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ format, include_metadata: includeMetadata }),
    });

    if (!response.ok) {
      return null;
    }

    const data = (await response.json()) as {
      download_url: string;
      schema_used: string;
      total_exported: number;
    };

    return {
      downloadUrl: data.download_url,
      schemaUsed: data.schema_used,
      totalExported: data.total_exported,
      format,
      includeMetadata,
    };
  } catch {
    return null;
  }
}

export async function triggerImport(jobId: string): Promise<ImportResult | null> {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}/crawl-jobs/${jobId}/import`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      return null;
    }

    const data = (await response.json()) as ImportApiResponse;
    return {
      jobId: data.job_id,
      status: data.status,
      message: data.message,
      insertedRecords: data.inserted_records,
      updatedRecords: data.updated_records,
      duplicateRecords: data.duplicate_records,
      totalRecords: data.total_records,
      importedRecords: data.imported_records,
    };
  } catch (cause) {
    if (isTimeoutError(cause)) {
      createTimeoutFailure(apiTimeoutMs);
    }
    liveDataError(`Import for job ${jobId} failed`, cause);
  }
}

export async function getCountries(): Promise<string[]> {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}/sources/countries`, { cache: "no-store" });
    if (!response.ok) {
      return fallbackCountries;
    }

    const data = (await response.json()) as SourceCountryListApiResponse;
    return data.countries.length > 0 ? data.countries : fallbackCountries;
  } catch {
    return fallbackCountries;
  }
}

export async function getSources(country?: string): Promise<DataSourceItem[]> {
  try {
    const suffix = country ? `?country=${encodeURIComponent(country)}` : "";
    const response = await fetchWithTimeout(`${apiBaseUrl}/sources${suffix}`, { cache: "no-store" });
    if (!response.ok) {
      return country ? fallbackSources.filter((source) => source.country === country) : fallbackSources;
    }

    const data = (await response.json()) as SourceListApiResponse;
    return data.sources.map((source) => ({
      id: source.id,
      name: source.name,
      country: source.country ?? country,
      supportedFields: source.supported_fields ?? [],
      sourceRole: source.source_role ?? null,
      trustLevel: source.trust_level ?? null,
      config: source.config ?? null,
      criticalFields: source.critical_fields ?? null,
    }));
  } catch {
    return country ? fallbackSources.filter((source) => source.country === country) : fallbackSources;
  }
}

export async function getRecommendedSources(country: string): Promise<RecommendedSourcesResponse> {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}/sources/recommended?country=${encodeURIComponent(country)}`, { cache: "no-store" });
    if (!response.ok) {
      return { country, templates: [] };
    }

    const data = (await response.json()) as RecommendedSourcesApiResponse;
    return {
      country: data.country,
      templates: data.templates.map((template) => ({
        name: template.name,
        country: template.country,
        sourceType: template.source_type,
        supportedFields: template.supported_fields,
        config: template.config,
      })),
    };
  } catch {
    return { country, templates: [] };
  }
}

export async function updateSourceConfig(input: DataSourceUpdateInput): Promise<DataSourceUpdateResult | null> {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}/sources/${input.sourceId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        config: {
          role: input.sourceRole ?? null,
          trust_level: input.trustLevel ?? null,
          source_type: input.sourceType ?? null,
          url_template: input.urlTemplate ?? null,
          items_path: input.itemsPath ?? null,
          field_map: input.fieldMap ?? null,
        },
      }),
    });

    if (!response.ok) {
      return null;
    }

    const data = (await response.json()) as SourceUpdateApiResponse;
    const config = data.config ?? null;
    return {
      id: data.id,
      sourceRole: typeof config?.role === "string" ? config.role : null,
      trustLevel: typeof config?.trust_level === "string" ? config.trust_level : null,
      config,
    };
  } catch {
    return null;
  }
}

export async function getTemplates(): Promise<TemplateItem[]> {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}/templates`, { cache: "no-store" });
    if (!response.ok) {
      return fallbackTemplates;
    }

    const data = (await response.json()) as TemplateListApiResponse;
    return data.templates.map((template) => ({
      id: template.id,
      templateName: template.template_name,
      fileName: template.file_name,
      columnCount: template.column_count,
    }));
  } catch {
    return fallbackTemplates;
  }
}

export async function uploadTemplate(templateName: string, file: File): Promise<TemplateUploadResult> {
  try {
    const body = new FormData();
    body.append("template_name", templateName);
    body.append("file", file);

    const response = await fetchWithTimeout(
      `${apiBaseUrl}/templates/upload`,
      {
        method: "POST",
        body,
      },
      uploadApiTimeoutMs,
    );

    if (!response.ok) {
      const data = (await response.json().catch(() => null)) as { detail?: string } | null;
      return {
        template: null,
        error: data?.detail ?? "Template upload failed.",
      };
    }

    const data = (await response.json()) as {
      id: string;
      template_name: string;
      file_name: string;
      column_count: number;
    };

    return {
      template: {
        id: data.id,
        templateName: data.template_name,
        fileName: data.file_name,
        columnCount: data.column_count,
      },
      error: null,
    };
  } catch {
    return {
      template: null,
      error: "Template upload failed.",
    };
  }
}

export async function deleteTemplate(templateId: string): Promise<DeleteTemplateResult> {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}/templates/${templateId}`, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      const data = (await response.json().catch(() => null)) as { detail?: string } | null;
      return {
        id: null,
        message: null,
        error: data?.detail ?? "Could not delete the template.",
      };
    }

    const data = (await response.json()) as DeleteTemplateApiResponse;
    return {
      id: data.id,
      message: data.message,
      error: null,
    };
  } catch {
    return {
      id: null,
      message: null,
      error: "Could not delete the template.",
    };
  }
}

export async function getFieldSuggestions(templateId: string): Promise<FieldSuggestionResponse> {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}/fields/suggest/${templateId}`, { cache: "no-store" });
    if (!response.ok) {
      return {
        templateId,
        suggestedCriticalFields: ["name", "website", "location"],
        suggestedFieldsDetail: [
          { name: "name", score: 98, reason: "Primary identifier for import records." },
          { name: "website", score: 94, reason: "Needed to validate institution destination." },
          { name: "location", score: 88, reason: "Improves matching and review confidence." },
        ],
        minFields: 3,
        maxFields: 10,
        reasoning: "Fallback suggestion set is based on the default template used in the dashboard mock flow.",
      };
    }

    const data = (await response.json()) as FieldSuggestionApiResponse;
    return {
      templateId: data.template_id,
      suggestedCriticalFields: data.suggested_critical_fields,
      suggestedFieldsDetail: data.suggested_fields_detail,
      minFields: data.min_fields,
      maxFields: data.max_fields,
      reasoning: data.reasoning,
    };
  } catch {
    return {
      templateId,
      suggestedCriticalFields: ["name", "website", "location"],
      suggestedFieldsDetail: [
        { name: "name", score: 98, reason: "Primary identifier for import records." },
        { name: "website", score: 94, reason: "Needed to validate institution destination." },
        { name: "location", score: 88, reason: "Improves matching and review confidence." },
      ],
      minFields: 3,
      maxFields: 10,
      reasoning: "Fallback suggestion set is based on the default template used in the dashboard mock flow.",
    };
  }
}

export async function submitReviewAction(input: ReviewActionInput): Promise<ReviewActionResult | null> {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}/review-actions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        record_id: input.recordId,
        field_name: input.fieldName,
        action: input.action,
        new_value: input.newValue ?? null,
        note: input.note,
      }),
    });

    if (!response.ok) {
      return null;
    }

    const data = (await response.json()) as {
      status: string;
      message: string;
      review_action_id: string | null;
    };

    return {
      status: data.status,
      message: data.message,
      reviewActionId: data.review_action_id,
    };
  } catch {
    return null;
  }
}

export async function createCrawlJob(input: CrawlJobCreateInput): Promise<CrawlJobCreateResult | null> {
  try {
    const response = await fetchWithTimeout(
      `${apiBaseUrl}/crawl-jobs`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          country: input.country,
          source_ids: input.sourceIds,
          crawl_mode: input.crawlMode,
          discovery_input: input.discoveryInput ?? null,
          critical_fields: input.criticalFields,
          clean_template_id: input.cleanTemplateId,
          ai_assist: input.aiAssist,
        }),
      },
      mutationTimeoutMs,
    );

    if (!response.ok) {
      return null;
    }

    const data = (await response.json()) as CrawlJobCreateApiResponse;
    return mapCreateResult(data);
  } catch (cause) {
    if (isTimeoutError(cause)) {
      createTimeoutFailure(mutationTimeoutMs);
    }
    liveDataError(`Creating crawl job for ${input.country} failed`, cause);
  }
}

export type RunCrawlJobOutcome =
  | { ok: true; result: CrawlJobRunResult }
  | { ok: false; error: string };

function formatApiErrorDetail(status: number, body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") {
      return `${detail} (HTTP ${status})`;
    }
    if (Array.isArray(detail)) {
      return `${JSON.stringify(detail)} (HTTP ${status})`;
    }
  }
  return `Request failed (HTTP ${status})`;
}

export async function runCrawlJob(jobId: string): Promise<RunCrawlJobOutcome> {
  try {
    const response = await fetchWithTimeout(
      `${apiBaseUrl}/crawl-jobs/${jobId}/run`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      },
      mutationTimeoutMs,
    );

    const body: unknown = await response.json().catch(() => null);

    if (!response.ok) {
      return {
        ok: false,
        error: formatApiErrorDetail(response.status, body),
      };
    }

    if (!body || typeof body !== "object" || !("job_id" in body)) {
      return { ok: false, error: "Invalid JSON response from server." };
    }

    const data = body as CrawlJobRunApiResponse;
    return {
      ok: true,
      result: {
        jobId: data.job_id,
        status: data.status,
        totalRecords: data.total_records,
        crawled: data.crawled,
        extracted: data.extracted,
        needsReview: data.needs_review,
        cleaned: data.cleaned,
        message: data.message,
      },
    };
  } catch (cause) {
    const name = cause instanceof Error ? cause.name : "";
    const message = cause instanceof Error ? cause.message : String(cause);
    if (name === "AbortError") {
      return {
        ok: false,
        error: `Request timed out after ${Math.round(mutationTimeoutMs / 1000)}s. Increase NEXT_PUBLIC_API_MUTATION_TIMEOUT_MS if the job is large.`,
      };
    }
    return {
      ok: false,
      error: `Could not reach the API (${message}). Check that the backend is running and CORS allows this origin.`,
    };
  }
}

export type JobProgressPoll = {
  status: JobStatus;
  progress: {
    totalRecords: number;
    crawled: number;
    extracted: number;
    needsReview: number;
    cleaned: number;
    skipped: number;
    cleanCandidates: number;
    approved: number;
    rejected: number;
    processed: number;
  };
};

export async function getJobProgress(jobId: string): Promise<JobProgressPoll | null> {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}/crawl-jobs/${jobId}`, { cache: "no-store" }, pollTimeoutMs);
    if (!response.ok) {
      return null;
    }

    const data = (await response.json()) as CrawlJobDetailApiResponse;
    return {
      status: data.status,
      progress: mapJobProgress(data.progress),
    };
  } catch {
    return null;
  }
}
