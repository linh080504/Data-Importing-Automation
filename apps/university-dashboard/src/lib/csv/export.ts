import { CSV_HEADERS, FIXED_CSV_HEADER } from "@/lib/csv/schema";
import type { UniversityRecord } from "@/lib/types";
import type { UniversityExportMode } from "@/lib/types";
import { toAsciiText } from "@/lib/text/ascii";

function escapeCsv(value: string) {
  if (/[",\r\n]/.test(value)) return `"${value.replace(/"/g, '""')}"`;
  return value;
}

export function getExportableRecords(records: UniversityRecord[], mode: UniversityExportMode = "all-valid") {
  return records.filter(
    (record) => record.quality.exportReady && (mode !== "approved-only" || record.reviewStatus === "Approved"),
  );
}

const ASCII_EXPORT_FIELDS = new Set([
  "name",
  "description",
  "financials",
  "campus_student_life",
  "contact_person",
]);

export function buildUniversityCsv(records: UniversityRecord[], mode: UniversityExportMode = "all-valid") {
  const exportable = getExportableRecords(records, mode);
  const lines = [FIXED_CSV_HEADER];
  for (const record of exportable) {
    lines.push(
      CSV_HEADERS.map((header) => {
        const value = record[header] ?? "";
        return escapeCsv(ASCII_EXPORT_FIELDS.has(header) ? toAsciiText(value) : value);
      }).join(","),
    );
  }
  return `\uFEFF${lines.join("\r\n")}\r\n`;
}

export function validateCsvHeader() {
  return (
    FIXED_CSV_HEADER ===
    "id,name,location,description,slug,sponsored,website,global_rank,financials,student_loan_available,campus_student_life,number_of_students,student_to_faculty_ratio,international_student_ratio,housing_availability,admissions_contact,admissions_phone,contact_person,admissions_page_link,immigration_support,university_campuses"
  );
}
