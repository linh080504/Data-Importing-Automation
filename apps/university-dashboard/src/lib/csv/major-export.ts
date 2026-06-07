import type { UniversityMajorMatch, UniversityRecord } from "@/lib/types";
import type { MajorCrawlMode } from "@/lib/types";
import { toAsciiText } from "@/lib/text/ascii";

export const MAJOR_CSV_HEADERS = ["University Name", "Major Name", "Source URL (Optional)"] as const;
export const FIXED_MAJOR_CSV_HEADER = MAJOR_CSV_HEADERS.join(",");
export const CURRENT_CRAWLER_VERSION = 2;

function escapeCsv(value: string) {
  if (/[",\r\n]/.test(value)) return `"${value.replace(/"/g, '""')}"`;
  return value;
}

function hostnameOf(value: string) {
  try {
    return new URL(value).hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return "";
  }
}

function isOfficialSource(record: UniversityRecord, sourceUrl: string) {
  const officialHost = hostnameOf(record.website || record.sourceUrls?.official || "");
  const sourceHost = hostnameOf(sourceUrl);
  return Boolean(
    officialHost &&
      sourceHost &&
      (officialHost === sourceHost ||
        officialHost.endsWith(`.${sourceHost}`) ||
        sourceHost.endsWith(`.${officialHost}`)),
  );
}

function isAcademicEvidence(match: UniversityMajorMatch) {
  return Boolean(
    match.sourceType ||
      /academic|program|programme|degree|curriculum|department|faculty|school|major|undergraduate|graduate|education|training|\.(pdf|docx?|xlsx?)(?:$|[?#])/i.test(
        match.sourceUrl,
      ),
  );
}

function sourcePriority(match: UniversityMajorMatch) {
  if (match.sourceType === "program_page") return 3;
  if (match.sourceType === "official_document") return 2;
  return 1;
}

export function getVerifiedMajorMatches(
  records: UniversityRecord[],
  requestedMajors: string[] = [],
  majorMode: MajorCrawlMode = "verify",
) {
  const requested = new Set(requestedMajors.map((major) => major.trim().toLowerCase()).filter(Boolean));
  const unique = new Map<string, UniversityMajorMatch>();

  for (const record of records) {
    if (
      record.countryValidation?.status === "rejected" ||
      (record.officialValidation && record.officialValidation.status !== "verified")
    ) {
      continue;
    }
    for (const match of record.majorMatches ?? []) {
      const universityName = match.universityName.trim();
      const majorName = match.majorName.trim();
      const sourceUrl = match.sourceUrl.trim();
      if (!universityName || !majorName || !sourceUrl) continue;
      if (majorMode === "verify" && !requested.has(majorName.toLowerCase())) continue;
      if (!isOfficialSource(record, sourceUrl) || !isAcademicEvidence(match)) continue;
      const key = `${universityName.toLowerCase()}\u0000${toAsciiText(majorName).toLowerCase()}`;
      const candidate = { ...match, universityName, majorName: toAsciiText(majorName), sourceUrl };
      const existing = unique.get(key);
      if (!existing || sourcePriority(candidate) > sourcePriority(existing)) unique.set(key, candidate);
    }
  }

  return [...unique.values()].sort(
    (left, right) =>
      left.universityName.localeCompare(right.universityName) ||
      left.majorName.localeCompare(right.majorName) ||
      left.sourceUrl.localeCompare(right.sourceUrl),
  );
}

export function buildMajorCsv(
  records: UniversityRecord[],
  requestedMajors: string[] = [],
  majorMode: MajorCrawlMode = "verify",
) {
  const lines = [FIXED_MAJOR_CSV_HEADER];
  for (const match of getVerifiedMajorMatches(records, requestedMajors, majorMode)) {
    lines.push([toAsciiText(match.universityName), toAsciiText(match.majorName), match.sourceUrl].map(escapeCsv).join(","));
  }
  return `\uFEFF${lines.join("\r\n")}\r\n`;
}

export function validateMajorCsvHeader() {
  return FIXED_MAJOR_CSV_HEADER === "University Name,Major Name,Source URL (Optional)";
}

export function majorExportBlockReason(
  crawlerVersion: number | undefined,
  records: UniversityRecord[],
) {
  if (!crawlerVersion || crawlerVersion < CURRENT_CRAWLER_VERSION) {
    return "This is a legacy run created before country-safe major crawling. Re-crawl the universities before exporting majors.";
  }
  const invalidCountry = records.find(
    (record) => record.countryValidation?.status === "rejected" || !record.countryValidation,
  );
  if (invalidCountry) {
    return `Major export is blocked because country validation is missing or rejected for ${invalidCountry.name}.`;
  }
  return "";
}
