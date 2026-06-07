import { z } from "zod";

export const CSV_HEADERS = [
  "id",
  "name",
  "location",
  "description",
  "slug",
  "sponsored",
  "website",
  "global_rank",
  "financials",
  "student_loan_available",
  "campus_student_life",
  "number_of_students",
  "student_to_faculty_ratio",
  "international_student_ratio",
  "housing_availability",
  "admissions_contact",
  "admissions_phone",
  "contact_person",
  "admissions_page_link",
  "immigration_support",
  "university_campuses",
] as const;

export const FIXED_CSV_HEADER = CSV_HEADERS.join(",");

export type CsvHeader = (typeof CSV_HEADERS)[number];
export type CsvRecord = Record<CsvHeader, string>;

export const OPTIONAL_EXPORT_FIELDS = new Set<CsvHeader>(["id", "global_rank", "contact_person"]);
export const BINARY_FIELDS = new Set<CsvHeader>([
  "sponsored",
  "student_loan_available",
  "housing_availability",
  "immigration_support",
]);
export const INTEGER_FIELDS = new Set<CsvHeader>([
  "location",
  "global_rank",
  "number_of_students",
  "student_to_faculty_ratio",
  "international_student_ratio",
  "university_campuses",
]);

export const CSV_RECORD_SCHEMA = z.object(
  CSV_HEADERS.reduce(
    (shape, header) => {
      shape[header] = z.string();
      return shape;
    },
    {} as Record<CsvHeader, z.ZodString>,
  ),
);

export function emptyCsvRecord(): CsvRecord {
  return CSV_HEADERS.reduce((record, header) => {
    record[header] = "";
    return record;
  }, {} as CsvRecord);
}

export function normalizeCsvRecord(input: Partial<Record<CsvHeader, unknown>>): CsvRecord {
  const record = emptyCsvRecord();
  for (const header of CSV_HEADERS) {
    const value = input[header];
    record[header] = value === null || value === undefined ? "" : String(value).trim();
  }
  return record;
}

export function isIntegerLike(value: string, allowBlank = false) {
  if (allowBlank && value.trim() === "") return true;
  return /^-?\d+$/.test(value.trim());
}

export function isBinary(value: string) {
  return value === "0" || value === "1";
}

export function isUrl(value: string, allowBlank = true) {
  if (allowBlank && value.trim() === "") return true;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function isEmail(value: string, allowBlank = true) {
  if (allowBlank && value.trim() === "") return true;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

export function isPhone(value: string, allowBlank = true) {
  if (allowBlank && value.trim() === "") return true;
  return /^\+\d[\d\s().-]{6,24}$/.test(value.trim());
}

export function slugify(value: string) {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-");
}
