export type CrawlMode = "trusted_sources" | "prompt_discovery" | "supplemental_discovery";

export type CrawlDiscoveryInput = Record<string, unknown>;

export type DataSourceItem = {
  id: string;
  name: string;
  country?: string;
  supportedFields: string[];
  sourceRole?: string | null;
  trustLevel?: string | null;
  config?: Record<string, unknown> | null;
  criticalFields?: string[] | null;
};

export type DataSourceUpdateInput = {
  sourceId: string;
  sourceRole?: string | null;
  trustLevel?: string | null;
  sourceType?: string | null;
  urlTemplate?: string | null;
  itemsPath?: string | null;
  fieldMap?: Record<string, string | string[]> | null;
};

export type DataSourceUpdateResult = {
  id: string;
  sourceRole?: string | null;
  trustLevel?: string | null;
  config?: Record<string, unknown> | null;
};

export type RecommendedSourceTemplate = {
  name: string;
  country: string;
  sourceType: string;
  supportedFields: string[];
  config: Record<string, unknown>;
};

export type RecommendedSourcesResponse = {
  country: string;
  templates: RecommendedSourceTemplate[];
};

export type TemplateItem = {
  id: string;
  templateName: string;
  fileName: string;
  columnCount: number;
};

export type TemplateUploadResult = {
  template: TemplateItem | null;
  error: string | null;
};

export type DeleteTemplateResult = {
  id: string | null;
  message: string | null;
  error: string | null;
};

export type DeleteCrawlJobResult = {
  jobId: string | null;
  message: string | null;
  deletedRawRecords: number;
  deletedAiLogs: number;
  deletedCleanRecords: number;
  deletedReviewActions: number;
  error: string | null;
};

export type FieldSuggestion = {
  name: string;
  score: number;
  reason: string;
};

export type FieldSuggestionResponse = {
  templateId: string;
  templateColumns: string[];
  suggestedCriticalFields: string[];
  suggestedFieldsDetail: FieldSuggestion[];
  minFields: number;
  maxFields: number;
  reasoning: string;
};

export type CrawlJobCreateInput = {
  country: string;
  sourceIds: string[];
  crawlMode: CrawlMode;
  discoveryInput?: CrawlDiscoveryInput | null;
  criticalFields: string[];
  cleanTemplateId: string;
  aiAssist: boolean;
};

export type CrawlJobCreateResult = {
  jobId: string;
  status: string;
  message: string;
  totalRecords: number;
  crawled: number;
  extracted: number;
  needsReview: number;
  cleaned: number;
  skipped?: number;
  cleanCandidates?: number;
  approved?: number;
  rejected?: number;
};
export type CrawlJobRunResult = {
  jobId: string;
  status: string;
  totalRecords: number;
  crawled: number;
  extracted: number;
  needsReview: number;
  cleaned: number;
  message: string;
};

export type JobStatus =
  | "QUEUED"
  | "CRAWLING"
  | "EXTRACTING"
  | "NEEDS_REVIEW"
  | "CLEANING"
  | "READY_TO_EXPORT"
  | "EXPORTED"
  | "FAILED";

export type StepStatus = "completed" | "current" | "pending" | "blocked";

export type JobListItem = {
  id: string;
  jobName: string;
  country: string;
  sourceName: string;
  templateName: string;
  crawlMode?: CrawlMode;
  discoveryInput?: CrawlDiscoveryInput | null;
  status: JobStatus;
  progressPercent: number;
  totalRecords: number;
  cleanRecords: number;
  needReviewCount: number;
  qualityScore: number | null;
  nextAction: {
    label: string;
    type: "review" | "export" | "progress" | "view";
  };
  updatedAt: string;
};

export type JobDetailHeader = {
  id: string;
  jobName: string;
  country: string;
  sourceName: string;
  sourceNames: string[];
  templateName: string;
  templateColumns: string[];
  crawlMode?: CrawlMode;
  discoveryInput?: CrawlDiscoveryInput | null;
  status: JobStatus;
  progress: {
    totalRecords: number;
    crawled: number;
    extracted: number;
    needsReview: number;
    cleaned: number;
    skipped?: number;
    cleanCandidates?: number;
    approved?: number;
    rejected?: number;
    processed?: number;
  };
  steps: {
    key: "setup" | "crawl" | "review" | "clean" | "export";
    label: string;
    status: StepStatus;
  }[];
  updatedAt: string;
  criticalFields: string[];
};

export type OverviewResponse = {
  summary: {
    totalRecords: number;
    cleanRecords: number;
    needReviewCount: number;
    rejectedCount: number;
    qualityScore: number | null;
    exportReadinessScore: number | null;
    currentStatusLabel: string;
    mergeSecondaryFieldCount: number;
    mergeConflictFieldCount: number;
  };
  analyze: {
    overallQuality: number;
    completeness: number;
    reviewCompletion: number;
    importReadiness: number;
    rawVsCleanByField: {
      field: string;
      rawValue: number;
      cleanValue: number;
    }[];
    issueTrend: {
      label: string;
      before: number;
      after: number;
    }[];
    mergeCoverage: {
      label: string;
      primaryValue: number;
      secondaryValue: number;
      conflictValue: number;
    }[];
  };
  topIssues: {
    label: string;
    severity: "low" | "medium" | "high";
    count: number;
  }[];
  nextAction: {
    title: string;
    description: string;
    primaryLabel: string;
    primaryTarget: "review" | "clean" | "export";
  };
  fieldIssues: FieldIssueGroup[];
  crawledRecords: CrawledRecordsPage;
};

export type FieldIssueRecord = {
  uniqueKey: string;
  displayName: string;
  issue: "missing" | "empty" | "conflict";
  currentValue: string | number | boolean | null;
};

export type FieldIssueGroup = {
  field: string;
  issueCount: number;
  records: FieldIssueRecord[];
};

export type MergeConflict = {
  source_id: string;
  source_name: string;
  value: string | number | boolean | null;
};

export type CrawledRecordField = {
  fieldName: string;
  rawValue: string | number | boolean | null;
  cleanValue: string | number | boolean | null;
  sourceName?: string | null;
  fromSecondary: boolean;
  conflicts: MergeConflict[];
};

export type CrawledRecordListItem = {
  rawRecordId: string;
  displayName: string;
  uniqueKey: string;
  country?: string | null;
  sourceUrl?: string | null;
  sourceName?: string | null;
  status: string | null;
  qualityScore: number | null;
};

export type CrawledRecordDetail = CrawledRecordListItem & {
  fields: CrawledRecordField[];
};

export type CrawledRecordsPage = {
  total: number;
  page: number;
  pageSize: number;
  items: CrawledRecordListItem[];
  selectedRecordId: string | null;
  selectedDetail: CrawledRecordDetail | null;
};

export type CrawledFieldSnapshot = {
  fieldName: string;
  value: string | number | boolean | null;
  sourceUrl?: string | null;
  sourceName?: string | null;
  sourceExcerpt?: string | null;
  status: "captured" | "missing" | "needs_review" | string;
  reason?: string | null;
};

export type ReviewQueueDetail = {
  recordId: string;
  displayName: string;
  uniqueKey: string;
  sourceUrl?: string | null;
  sourceName?: string | null;
  confidence: number | null;
  status: string;
  crawledFields: CrawledFieldSnapshot[];
  fields: {
    fieldName: string;
    rawValue: string | number | boolean | null;
    suggestedValue: string | number | boolean | null;
    finalValue: string | number | boolean | null;
    reason: string;
    confidence: number | null;
    issueType: "missing" | "format" | "confidence" | "duplicate";
    sourceExcerpt?: string | null;
    evidenceUrl?: string | null;
    evidenceSource?: string | null;
    evidenceRequired?: boolean;
    mergeSourceId: string | null;
    mergeSourceName: string | null;
    mergeFromSecondary: boolean;
    mergeConflicts: MergeConflict[];
  }[];
};

export type ReviewQueueListItem = {
  recordId: string;
  displayName: string;
  uniqueKey: string;
  sourceUrl?: string | null;
  sourceName?: string | null;
  confidence: number | null;
  flaggedFieldCount: number;
  crawledFields: CrawledFieldSnapshot[];
};

export type ReviewQueueData = {
  total: number;
  page: number;
  limit: number;
  selectedRecordId: string | null;
  items: ReviewQueueListItem[];
  selectedDetail: ReviewQueueDetail;
};

export type ReviewField = ReviewQueueDetail["fields"][number];

export type ReviewActionInput = {
  recordId: string;
  fieldName: string;
  action: "ACCEPT" | "EDIT" | "REJECT" | "UNKNOWN";
  newValue?: string | null;
  note?: string;
};

export type ReviewActionResult = {
  status: string;
  message: string;
  reviewActionId: string | null;
};

export type CleanDataResponse = {
  summary: {
    completeness: number;
    readyCount: number;
    incompleteCount: number;
    qualityScore: number | null;
    secondaryFieldCount: number;
    conflictFieldCount: number;
  };
  analyze: {
    problemFields: {
      field: string;
      missingCount: number;
    }[];
    fieldCompleteness: {
      field: string;
      percent: number;
      severity: "low" | "medium" | "high";
    }[];
    mergeCoverage: {
      field: string;
      primaryCount: number;
      secondaryCount: number;
      conflictCount: number;
    }[];
  };
  columns: string[];
  rows: Record<string, string | number | boolean | null>[];
};

export type ExportReadinessResponse = {
  isReady: boolean;
  readinessScore: number;
  checklist: {
    key: string;
    label: string;
    status: "pass" | "warning" | "fail";
  }[];
  blockers: {
    label: string;
    count: number;
    severity: "low" | "medium" | "high";
  }[];
  mergeRisk: {
    secondaryFieldCount: number;
    conflictFieldCount: number;
    riskLevel: "low" | "medium" | "high";
  };
  exportPreview: {
    templateName: string;
    totalRecords: number;
    supportedFormats: ("csv" | "xlsx")[];
    defaultFileName: string;
  };
};

export type ExportResult = {
  downloadUrl: string;
  schemaUsed: string;
  totalExported: number;
  format: "csv" | "xlsx";
  includeMetadata: boolean;
};

export type ImportResult = {
  jobId: string;
  status: string;
  message: string;
  insertedRecords: number;
  updatedRecords: number;
  duplicateRecords: number;
  totalRecords: number;
  importedRecords: number;
};

export type ActivityItem = {
  id: string;
  time: string;
  type: "info" | "success" | "warning" | "error";
  title: string;
  detail?: string;
};
