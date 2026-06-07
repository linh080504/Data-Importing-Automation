import {
  BINARY_FIELDS,
  CSV_HEADERS,
  INTEGER_FIELDS,
  isBinary,
  isEmail,
  isIntegerLike,
  isPhone,
  isUrl,
} from "@/lib/csv/schema";
import type {
  DashboardSummary,
  EvidenceLink,
  QualityComponents,
  QualityFinding,
  QualityResult,
  UniversityRecord,
} from "@/lib/types";

const NUMERIC_RANGES = {
  number_of_students: [50, 500000],
  student_to_faculty_ratio: [3, 80],
  international_student_ratio: [0, 100],
  university_campuses: [1, 200],
} as const;

function issue(
  field: QualityFinding["field"],
  severity: QualityFinding["severity"],
  ruleId: string,
  message: string,
  evidenceUrl?: string,
): QualityFinding {
  return { field, severity, ruleId, message, evidenceUrl };
}

function domainOf(url: string) {
  if (!isUrl(url, true) || !url) return "";
  try {
    return new URL(url).hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return "";
  }
}

function rootDomain(domain: string) {
  const parts = domain.split(".").filter(Boolean);
  if (parts.length <= 2) return parts.join(".");
  return parts.slice(-2).join(".");
}

function sameRootDomain(left: string, right: string) {
  if (!left || !right) return false;
  return rootDomain(left) === rootDomain(right);
}

function emailDomain(email: string) {
  if (!isEmail(email, true) || !email) return "";
  return email.split("@").pop()?.toLowerCase() ?? "";
}

function evidenceTypes(evidence: EvidenceLink[]) {
  return new Set(evidence.map((entry) => entry.type));
}

function hasCritical(findings: QualityFinding[]) {
  return findings.some((finding) => finding.severity === "critical");
}

function missingImportant(findings: QualityFinding[]) {
  return findings.some((finding) => finding.ruleId.endsWith(".missing") && finding.severity === "critical");
}

const CORE_EXPORT_FIELDS = new Set<string>(["name", "location", "description", "slug"]);

function scoreSingle(
  record: UniversityRecord,
  slugCounts: Record<string, number>,
  nameCounts: Record<string, number>,
): QualityResult {
  const findings: QualityFinding[] = [];
  let schemaErrors = 0;
  let schemaWarnings = 0;

  if (record.id) {
    findings.push(issue("id", "minor", "csv.id.must_be_blank", "id must be empty for import rows."));
    schemaWarnings += 1;
  }

  for (const header of CSV_HEADERS) {
    if (!record[header]) {
      const severity = CORE_EXPORT_FIELDS.has(header) ? "critical" : "minor";
      findings.push(issue(header, severity, `csv.${header}.missing`, `${header} is blank because no source evidence was found.`));
      if (severity === "critical") schemaErrors += 1;
    }
  }

  for (const header of BINARY_FIELDS) {
    if (!isBinary(record[header])) {
      findings.push(issue(header, "critical", `csv.${header}.binary`, `${header} must be 0 or 1.`));
      schemaErrors += 1;
    }
  }

  for (const header of INTEGER_FIELDS) {
    const allowBlank = header !== "location";
    if (!isIntegerLike(record[header], allowBlank)) {
      findings.push(issue(header, "critical", `csv.${header}.integer`, `${header} must be a plain integer.`));
      schemaErrors += 1;
    }
  }

  if (!isUrl(record.website, true)) {
    findings.push(issue("website", "major", "csv.website.url", "website must be a full http(s) URL."));
    schemaWarnings += 1;
  }
  if (!isUrl(record.admissions_page_link, true)) {
    findings.push(
      issue("admissions_page_link", "major", "csv.admissions_page_link.url", "admissions page must be a full http(s) URL."),
    );
    schemaWarnings += 1;
  }
  if (!isEmail(record.admissions_contact, true)) {
    findings.push(issue("admissions_contact", "major", "csv.admissions_contact.email", "admissions_contact must be a real email."));
    schemaWarnings += 1;
  }
  if (!isPhone(record.admissions_phone, true)) {
    findings.push(
      issue("admissions_phone", "major", "csv.admissions_phone.phone", "admissions_phone must start with a country code."),
    );
    schemaWarnings += 1;
  }

  const schemaTypeValidity = Math.max(0, 20 - schemaErrors * 5 - schemaWarnings * 2);
  const fieldCompleteness = Math.round((CSV_HEADERS.filter((header) => Boolean(record[header])).length / CSV_HEADERS.length) * 20);

  const types = evidenceTypes(record.evidence);
  let sourceEvidenceStrength = 0;
  if (types.has("official") || types.has("official_page")) sourceEvidenceStrength += 11;
  if (types.has("wikidata")) sourceEvidenceStrength += 7;
  if (types.has("wikipedia")) sourceEvidenceStrength += 5;
  sourceEvidenceStrength += Math.min(2, record.evidence.length);
  sourceEvidenceStrength = Math.min(25, sourceEvidenceStrength);
  if (sourceEvidenceStrength < 8) {
    findings.push(issue("source_evidence", "major", "evidence.weak", "Source evidence is weak or absent."));
  }

  const websiteDomain = domainOf(record.website);
  const admissionsDomain = domainOf(record.admissions_page_link);
  const mailDomain = emailDomain(record.admissions_contact);
  let websiteContactVerification = 0;
  if (isUrl(record.website, false)) websiteContactVerification += 4;
  if (isUrl(record.admissions_page_link, false)) websiteContactVerification += 4;
  if (isEmail(record.admissions_contact, false)) websiteContactVerification += 3;
  if (isPhone(record.admissions_phone, false)) websiteContactVerification += 2;
  if (
    (websiteDomain && admissionsDomain && sameRootDomain(websiteDomain, admissionsDomain)) ||
    (websiteDomain && mailDomain && sameRootDomain(websiteDomain, mailDomain))
  ) {
    websiteContactVerification += 2;
  }
  if (websiteDomain && admissionsDomain && !sameRootDomain(websiteDomain, admissionsDomain)) {
    findings.push(
      issue(
        "admissions_page_link",
        "major",
        "contact.domain_mismatch",
        "Admissions page domain does not match official website.",
        record.admissions_page_link,
      ),
    );
  }
  if (websiteDomain && mailDomain && !sameRootDomain(websiteDomain, mailDomain)) {
    findings.push(
      issue("admissions_contact", "minor", "contact.email_domain_mismatch", "Admissions email domain differs from official website."),
    );
  }
  websiteContactVerification = Math.min(15, websiteContactVerification);

  let consistencyOutliers = 10;
  for (const [field, range] of Object.entries(NUMERIC_RANGES)) {
    const value = Number(record[field as keyof typeof NUMERIC_RANGES]);
    if (!Number.isFinite(value)) continue;
    if (value < range[0] || value > range[1]) {
      findings.push(
        issue(
          field as keyof typeof NUMERIC_RANGES,
          field === "international_student_ratio" ? "critical" : "major",
          `outlier.${field}`,
          `${field} is outside the expected range ${range[0]}-${range[1]}.`,
        ),
      );
      consistencyOutliers -= field === "international_student_ratio" ? 4 : 2;
    }
  }
  consistencyOutliers = Math.max(0, consistencyOutliers);

  const duplicateSlug = record.slug && slugCounts[record.slug] > 1;
  const duplicateName = record.name && nameCounts[record.name.toLowerCase()] > 1;
  let duplicateSlugUniqueness = 10;
  if (duplicateSlug) {
    findings.push(issue("slug", "critical", "duplicate.slug", "Duplicate slug conflict."));
    duplicateSlugUniqueness = 0;
  } else if (duplicateName) {
    findings.push(issue("name", "major", "duplicate.name", "Duplicate institution name requires slug disambiguation."));
    duplicateSlugUniqueness = 6;
  }

  for (const estimatedField of record.estimatedFields) {
    findings.push(issue(estimatedField, "minor", `estimate.${estimatedField}`, `${estimatedField} uses a conservative estimate.`));
  }

  for (const [field, warnings] of Object.entries(record.fieldWarnings ?? {})) {
    for (const warning of warnings ?? []) {
      findings.push(
        issue(
          field as QualityFinding["field"],
          warning.includes("export value is blank") || warning.includes("omitted from export") ? "major" : "minor",
          `raw.${field}.warning`,
          warning,
          record.fieldSources?.[field] ?? record.sourceUrls?.[field],
        ),
      );
    }
  }

  const components: QualityComponents = {
    schemaTypeValidity,
    fieldCompleteness,
    sourceEvidenceStrength,
    websiteContactVerification,
    consistencyOutliers,
    duplicateSlugUniqueness,
  };
  const score = Object.values(components).reduce((sum, value) => sum + value, 0);
  const critical = hasCritical(findings);
  let status: QualityResult["status"] = "Risky";
  if (duplicateSlug || score < 45) status = "Risky";
  else if (score >= 85 && (types.has("official") || types.has("official_page") || types.has("wikidata"))) status = "Verified";
  else if (score >= 70 && !critical) status = "Probable";
  else if (score >= 45 || missingImportant(findings)) status = "Needs Review";

  const validUrls =
    isUrl(record.website, true) &&
    isUrl(record.admissions_page_link, true) &&
    isEmail(record.admissions_contact, true) &&
    isPhone(record.admissions_phone, true);
  const hasCoreFields = Boolean(record.name && record.location && record.description && record.slug && record.wikipediaUrl);
  const exportReady = hasCoreFields && validUrls && !duplicateSlug && !critical && record.reviewStatus !== "Rejected";

  return {
    score,
    status,
    truthStatus: status,
    exportReady,
    components,
    findings,
    riskyFlags: findings.filter((finding) => finding.severity !== "minor").map((finding) => finding.ruleId),
  };
}

export function rescoreRecords(records: UniversityRecord[]) {
  const slugCounts: Record<string, number> = {};
  const nameCounts: Record<string, number> = {};
  for (const record of records) {
    if (record.slug) slugCounts[record.slug] = (slugCounts[record.slug] ?? 0) + 1;
    if (record.name) nameCounts[record.name.toLowerCase()] = (nameCounts[record.name.toLowerCase()] ?? 0) + 1;
  }
  return records.map((record) => {
    const quality = scoreSingle(record, slugCounts, nameCounts);
    return { ...record, quality };
  });
}

export function summarizeRecords(records: UniversityRecord[]): DashboardSummary {
  const total = records.length;
  const fieldCompleteness =
    total === 0
      ? 0
      : Math.round(
          CSV_HEADERS.reduce((sum, header) => sum + records.filter((record) => Boolean(record[header])).length / total, 0) /
            CSV_HEADERS.length *
            100,
        );
  return {
    total,
    countries: new Set(records.map((record) => record.location).filter(Boolean)).size,
    verified: records.filter((record) => record.quality.status === "Verified").length,
    probable: records.filter((record) => record.quality.status === "Probable").length,
    needsReview: records.filter((record) => record.quality.status === "Needs Review").length,
    risky: records.filter((record) => record.quality.status === "Risky").length,
    completenessScore: fieldCompleteness,
    duplicateCount: records.filter((record) => record.quality.riskyFlags.some((flag) => flag.startsWith("duplicate."))).length,
    exportReady: records.filter((record) => record.quality.exportReady).length,
    exportBlocked: records.filter((record) => !record.quality.exportReady).length,
  };
}

export function fieldCompleteness(records: UniversityRecord[]) {
  return CSV_HEADERS.map((header) => {
    const present = records.filter((record) => Boolean(record[header])).length;
    return {
      field: header,
      present,
      missing: records.length - present,
      pct: records.length ? Math.round((present / records.length) * 100) : 0,
    };
  });
}
