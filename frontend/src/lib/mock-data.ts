import {
  type ActivityItem,
  type CleanDataResponse,
  type ExportReadinessResponse,
  type ImportResult,
  type JobDetailHeader,
  type JobListItem,
  type OverviewResponse,
  type ReviewQueueData,
  type ReviewQueueDetail,
} from "@/lib/types";

export const jobs: JobListItem[] = [
  {
    id: "job_001",
    jobName: "Vietnam - Government Registry",
    country: "Vietnam",
    sourceName: "Government Registry",
    templateName: "University_Import_Clean-7",
    status: "NEEDS_REVIEW",
    progressPercent: 80,
    totalRecords: 520,
    cleanRecords: 478,
    needReviewCount: 42,
    qualityScore: 74,
    nextAction: {
      label: "Review flagged records before export",
      type: "review",
    },
    updatedAt: "2026-05-10T11:20:00Z",
  },
  {
    id: "job_002",
    jobName: "USA - Business Directory",
    country: "USA",
    sourceName: "Business Directory",
    templateName: "University_Import_Clean-7",
    status: "READY_TO_EXPORT",
    progressPercent: 100,
    totalRecords: 890,
    cleanRecords: 890,
    needReviewCount: 0,
    qualityScore: 93,
    nextAction: {
      label: "Export clean file",
      type: "export",
    },
    updatedAt: "2026-05-10T09:45:00Z",
  },
];

export const jobHeader: JobDetailHeader = {
  id: "job_001",
  jobName: "Vietnam - Government Registry +1 more",
  country: "Vietnam",
  sourceName: "Government Registry +1 more",
  sourceNames: ["Government Registry", "Wikipedia"],
  templateName: "University_Import_Clean-7",
  status: "NEEDS_REVIEW",
  progress: {
    totalRecords: 520,
    crawled: 520,
    extracted: 520,
    needsReview: 42,
    cleaned: 478,
  },
  steps: [
    { key: "setup", label: "Setup", status: "completed" },
    { key: "crawl", label: "Crawl", status: "completed" },
    { key: "review", label: "Review", status: "current" },
    { key: "clean", label: "Clean", status: "pending" },
    { key: "export", label: "Export", status: "pending" },
  ],
  updatedAt: "2026-05-10T11:20:00Z",
  criticalFields: ["name", "website", "location", "financials"],
};

export const overview: OverviewResponse = {
  summary: {
    totalRecords: 520,
    cleanRecords: 478,
    needReviewCount: 42,
    rejectedCount: 8,
    qualityScore: 86,
    exportReadinessScore: 78,
    currentStatusLabel: "Needs Review",
    mergeSecondaryFieldCount: 57,
    mergeConflictFieldCount: 9,
  },
  analyze: {
    overallQuality: 86,
    completeness: 81,
    reviewCompletion: 92,
    importReadiness: 78,
    rawVsCleanByField: [
      { field: "Name", rawValue: 85, cleanValue: 98 },
      { field: "Website", rawValue: 45, cleanValue: 76 },
      { field: "Location", rawValue: 68, cleanValue: 91 },
      { field: "Admissions Link", rawValue: 22, cleanValue: 61 },
    ],
    issueTrend: [
      { label: "Missing values", before: 82, after: 18 },
      { label: "Wrong format", before: 44, after: 9 },
      { label: "Low confidence", before: 51, after: 11 },
    ],
    mergeCoverage: [
      { label: "Website", primaryValue: 38, secondaryValue: 12, conflictValue: 2 },
      { label: "Location", primaryValue: 44, secondaryValue: 8, conflictValue: 4 },
      { label: "Admissions Link", primaryValue: 21, secondaryValue: 17, conflictValue: 3 },
    ],
  },
  topIssues: [
    { label: "Missing website", severity: "high", count: 12 },
    { label: "Low-confidence location", severity: "medium", count: 9 },
    { label: "Missing admissions link", severity: "medium", count: 3 },
  ],
  nextAction: {
    title: "Review flagged records before export",
    description:
      "A few fields still need attention before the file is ready for BeyondDegree import.",
    primaryLabel: "Go to Review Queue",
    primaryTarget: "review",
  },
  fieldIssues: [],
};

export const reviewDetail: ReviewQueueDetail = {
  recordId: "rec_001",
  displayName: "Example University",
  uniqueKey: "VN-000124",
  confidence: 74,
  status: "NEEDS_REVIEW",
  fields: [
    {
      fieldName: "website",
      rawValue: "example.edu",
      suggestedValue: "https://example.edu",
      finalValue: "https://example.edu",
      reason: "Website should include https",
      confidence: 82,
      issueType: "format",
      mergeSourceId: "src_wikipedia",
      mergeSourceName: "Wikipedia",
      mergeFromSecondary: true,
      mergeConflicts: [],
    },
    {
      fieldName: "location",
      rawValue: "HCM",
      suggestedValue: "Ho Chi Minh City",
      finalValue: "Ho Chi Minh City",
      reason: "Standardized location naming",
      confidence: 71,
      issueType: "confidence",
      mergeSourceId: "src_registry",
      mergeSourceName: "Government Registry",
      mergeFromSecondary: false,
      mergeConflicts: [
        { source_id: "src_wikipedia", source_name: "Wikipedia", value: "Ho Chi Minh" },
      ],
    },
  ],
};

export const reviewQueueData: ReviewQueueData = {
  total: 2,
  selectedRecordId: reviewDetail.recordId,
  items: [
    {
      recordId: "rec_001",
      displayName: "Example University",
      uniqueKey: "VN-000124",
      confidence: 74,
      flaggedFieldCount: 2,
    },
    {
      recordId: "rec_002",
      displayName: "Sample Institute",
      uniqueKey: "VN-000125",
      confidence: 68,
      flaggedFieldCount: 1,
    },
  ],
  selectedDetail: reviewDetail,
};

export const cleanData: CleanDataResponse = {
  summary: {
    completeness: 81,
    readyCount: 478,
    incompleteCount: 42,
    qualityScore: 86,
    secondaryFieldCount: 57,
    conflictFieldCount: 9,
  },
  analyze: {
    problemFields: [
      { field: "website", missingCount: 12 },
      { field: "admissions_page_link", missingCount: 18 },
      { field: "slug", missingCount: 5 },
    ],
    fieldCompleteness: [
      { field: "name", percent: 98, severity: "low" },
      { field: "website", percent: 76, severity: "medium" },
      { field: "location", percent: 88, severity: "low" },
      { field: "admissions_page_link", percent: 61, severity: "high" },
    ],
    mergeCoverage: [
      { field: "website", primaryCount: 38, secondaryCount: 12, conflictCount: 2 },
      { field: "location", primaryCount: 44, secondaryCount: 8, conflictCount: 4 },
      { field: "admissions_page_link", primaryCount: 21, secondaryCount: 17, conflictCount: 3 },
    ],
  },
  columns: ["name", "slug", "website", "admissions_page_link"],
  rows: [
    {
      name: "Example University",
      slug: "example-university",
      website: "https://example.edu",
      admissions_page_link: "https://example.edu/admissions",
    },
    {
      name: "Sample Institute",
      slug: "sample-institute",
      website: null,
      admissions_page_link: null,
    },
  ],
};

export const exportReadiness: ExportReadinessResponse = {
  isReady: false,
  readinessScore: 78,
  checklist: [
    { key: "review_done", label: "Review completed", status: "pass" },
    { key: "required_fields", label: "Required fields filled", status: "warning" },
    { key: "schema_match", label: "Schema matches template", status: "pass" },
    { key: "duplicates", label: "Duplicate check", status: "pass" },
    {
      key: "import_compatible",
      label: "Compatible with BeyondDegree import",
      status: "warning",
    },
  ],
  blockers: [
    { label: "Missing website", count: 12, severity: "high" },
    { label: "Missing admissions link", count: 3, severity: "medium" },
  ],
  mergeRisk: {
    secondaryFieldCount: 57,
    conflictFieldCount: 9,
    riskLevel: "medium",
  },
  exportPreview: {
    templateName: "University_Import_Clean-7",
    totalRecords: 478,
    supportedFormats: ["csv", "xlsx"],
    defaultFileName: "vietnam_registry_clean.csv",
  },
};

export const importResult: ImportResult = {
  jobId: "job_002",
  status: "COMPLETED",
  message: "Import completed successfully",
  insertedRecords: 890,
  updatedRecords: 0,
  duplicateRecords: 0,
  totalRecords: 890,
  importedRecords: 890,
};

export const activityItems: ActivityItem[] = [
  {
    id: "act_001",
    time: "10:34 AM",
    type: "success",
    title: "Crawl completed",
    detail: "520 records collected",
  },
  {
    id: "act_002",
    time: "10:38 AM",
    type: "warning",
    title: "Records flagged for review",
    detail: "42 records need attention",
  },
  {
    id: "act_003",
    time: "11:12 AM",
    type: "success",
    title: "Export file created",
    detail: "Ready to download",
  },
];
