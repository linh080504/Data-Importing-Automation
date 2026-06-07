import type { CsvHeader, CsvRecord } from "@/lib/csv/schema";

export type EvidenceType = "wikipedia" | "wikidata" | "official" | "official_page" | "estimated";
export type QualityStatus = "Verified" | "Probable" | "Needs Review" | "Risky";
export type ReviewStatus = "Unreviewed" | "Approved" | "Needs Review" | "Risky" | "Rejected";
export type FindingSeverity = "critical" | "major" | "minor";

export interface CountryOption {
  name: string;
  code: number;
  phonePrefix: string;
  currencyLabel: string;
  defaultFinancials: string;
  listPageCandidates: string[];
}

export interface EvidenceLink {
  type: EvidenceType;
  label: string;
  url: string;
}

export interface QualityFinding {
  field: CsvHeader | "source_evidence" | "duplicate" | "contact" | "crawler";
  severity: FindingSeverity;
  ruleId: string;
  message: string;
  evidenceUrl?: string;
}

export interface QualityComponents {
  schemaTypeValidity: number;
  fieldCompleteness: number;
  sourceEvidenceStrength: number;
  websiteContactVerification: number;
  consistencyOutliers: number;
  duplicateSlugUniqueness: number;
}

export interface QualityResult {
  score: number;
  status: QualityStatus;
  truthStatus: QualityStatus;
  exportReady: boolean;
  components: QualityComponents;
  findings: QualityFinding[];
  riskyFlags: string[];
}

export type ScraplingFetchMode = "auto" | "http" | "dynamic" | "stealthy";
export type MajorCrawlMode = "discover" | "verify";
export type UniversityExportMode = "all-valid" | "approved-only";

export interface ScraplingCrawlConfig {
  fetchMode: ScraplingFetchMode;
  requestTimeout: number;
  browserTimeoutMs: number;
  maxOfficialPages: number;
  maxAcademicPages: number;
  maxBrowserFallbacks: number;
  skipGuessedPagesOnFailure: boolean;
  networkIdle: boolean;
  disableResources: boolean;
  realChrome: boolean;
  solveCloudflare: boolean;
}

export interface UniversityMajorMatch {
  universityName: string;
  majorName: string;
  sourceUrl: string;
  sourceType?: "program_page" | "academic_table" | "official_document";
  programCode?: string;
  degreeLevel?: string;
  evidenceText?: string;
}

export interface UniversityRecord extends CsvRecord {
  crawlerVersion?: number;
  countryName: string;
  countryValidation?: {
    status: "verified" | "list_evidence" | "rejected";
    reason: string;
    evidenceUrl: string;
    evidenceText?: string;
  };
  officialValidation?: {
    status: "verified" | "unreachable" | "missing" | "rejected";
    reason: string;
    canonicalUrl?: string;
  };
  sourceTitle: string;
  wikipediaUrl: string;
  wikidataId?: string;
  officialPages: string[];
  officialPageFailures?: Array<{
    url: string;
    reason: string;
    guessed?: boolean;
    browserAttempted?: boolean;
  }>;
  majorMatches?: UniversityMajorMatch[];
  academicStats?: {
    checked: number;
    discovered: number;
    extracted: number;
  };
  evidence: EvidenceLink[];
  estimatedFields: CsvHeader[];
  rawFields?: Partial<Record<CsvHeader | string, string>>;
  sourceUrls?: Record<string, string>;
  fieldSources?: Record<string, string>;
  fieldEvidence?: Record<
    string,
    {
      sourceUrl: string;
      evidenceText: string;
      rule: string;
      checkedAt: string;
    }
  >;
  fieldWarnings?: Partial<Record<CsvHeader | string, string[]>>;
  reviewStatus: ReviewStatus;
  reviewer?: string;
  reviewerNote?: string;
  createdAt: string;
  updatedAt: string;
  quality: QualityResult;
}

export interface CrawlRunMeta {
  id: string;
  country: string;
  countryCode: number;
  startedAt: string;
  finishedAt?: string;
  status: "running" | "completed" | "failed";
  requestedLimit: number;
  discoveredCount: number;
  recordCount: number;
  crawlerVersion?: number;
  attemptedCount?: number;
  rejectedCount?: number;
  rejectedCandidates?: Array<{
    title: string;
    url: string;
    status: string;
    reason: string;
    evidenceUrl?: string;
    evidenceText?: string;
  }>;
  error?: string;
}

export interface CrawlJob {
  runId: string;
  status: "queued" | "running" | "completed" | "failed";
  pid?: number;
  country: string;
  countryCode: number;
  limit: number;
  listPage?: string;
  config?: ScraplingCrawlConfig;
  requestedMajors?: string[];
  majorMode?: MajorCrawlMode;
  startedAt: string;
  finishedAt?: string;
  current?: string;
  discoveredCount: number;
  successCount: number;
  failureCount: number;
  academicPagesChecked?: number;
  majorMatchesCount?: number;
  attemptedCount?: number;
  rejectedCount?: number;
  crawlerVersion?: number;
  logs: string[];
  errors: string[];
}

export interface AuditEntry {
  id: string;
  targetSlug: string;
  action: "record_update" | "bulk_status_update";
  user: string;
  timestamp: string;
  before: Partial<UniversityRecord>;
  after: Partial<UniversityRecord>;
  note?: string;
}

export interface RunFile {
  run: CrawlRunMeta;
  job?: CrawlJob;
  records: UniversityRecord[];
  audit: AuditEntry[];
}

export interface DashboardSummary {
  total: number;
  countries: number;
  verified: number;
  probable: number;
  needsReview: number;
  risky: number;
  completenessScore: number;
  duplicateCount: number;
  exportReady: number;
  exportBlocked: number;
}
