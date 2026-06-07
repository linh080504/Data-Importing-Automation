import { describe, expect, it } from "vitest";
import { normalizeCsvRecord } from "@/lib/csv/schema";
import { buildUniversityCsv, getExportableRecords } from "@/lib/csv/export";
import { rescoreRecords } from "@/lib/quality/scoring";
import type { UniversityRecord } from "@/lib/types";

function record(overrides: Partial<UniversityRecord> = {}): UniversityRecord {
  const now = new Date().toISOString();
  return {
    ...normalizeCsvRecord({
      id: "",
      name: "Example University, India",
      location: "356",
      description: "Example University is a public university in India with undergraduate and postgraduate programs.",
      slug: "example-university-india",
      sponsored: "0",
      website: "https://example.edu",
      global_rank: "",
      financials: "INR 50k-250k ($600-3000)",
      student_loan_available: "1",
      campus_student_life: "Library, labs, student clubs, sports facilities",
      number_of_students: "2500",
      student_to_faculty_ratio: "18",
      international_student_ratio: "0",
      housing_availability: "1",
      admissions_contact: "admissions@example.edu",
      admissions_phone: "+911234567890",
      contact_person: "",
      admissions_page_link: "https://example.edu/admissions",
      immigration_support: "0",
      university_campuses: "1",
    }),
    countryName: "India",
    sourceTitle: "Example University",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Example_University",
    officialPages: ["https://example.edu/admissions"],
    evidence: [
      { type: "wikipedia", label: "Wikipedia", url: "https://en.wikipedia.org/wiki/Example_University" },
      { type: "official", label: "Official", url: "https://example.edu" },
    ],
    estimatedFields: [],
    reviewStatus: "Approved",
    createdAt: now,
    updatedAt: now,
    quality: {
      score: 0,
      status: "Risky",
      truthStatus: "Risky",
      exportReady: false,
      components: {
        schemaTypeValidity: 0,
        fieldCompleteness: 0,
        sourceEvidenceStrength: 0,
        websiteContactVerification: 0,
        consistencyOutliers: 0,
        duplicateSlugUniqueness: 0,
      },
      findings: [],
      riskyFlags: [],
    },
    ...overrides,
  };
}

describe("quality scoring", () => {
  it("marks approved high-quality records export-ready", () => {
    const [scored] = rescoreRecords([record()]);
    expect(scored.quality.score).toBeGreaterThanOrEqual(70);
    expect(scored.quality.status).not.toBe("Risky");
    expect(scored.quality.exportReady).toBe(true);
    expect(getExportableRecords([scored])).toHaveLength(1);
    expect(buildUniversityCsv([scored])).toContain("Example University, India");
  });

  it("blocks duplicate slugs", () => {
    const [first, second] = rescoreRecords([record(), record({ name: "Example University Two, India" })]);
    expect(first.quality.status).toBe("Risky");
    expect(second.quality.riskyFlags).toContain("duplicate.slug");
    expect(getExportableRecords([first, second])).toHaveLength(0);
  });

  it("exports valid unreviewed records by default and supports approved-only mode", () => {
    const [scored] = rescoreRecords([record({ reviewStatus: "Unreviewed" })]);
    expect(scored.quality.exportReady).toBe(true);
    expect(getExportableRecords([scored])).toHaveLength(1);
    expect(getExportableRecords([scored], "approved-only")).toHaveLength(0);
  });

  it("transliterates export-facing Vietnamese text without removing the row", () => {
    const [scored] = rescoreRecords([
      record({
        name: "Trường Đại học Bách khoa, Vietnam",
        contact_person: "Vũ Hoàng Linh",
      }),
    ]);
    const csv = buildUniversityCsv([scored]);
    expect(csv).toContain("Truong Dai hoc Bach khoa, Vietnam");
    expect(csv).toContain("Vu Hoang Linh");
  });

  it("keeps the fixed header and starts each blank-id row with a comma", () => {
    const [scored] = rescoreRecords([record()]);
    const lines = buildUniversityCsv([scored]).replace(/^\uFEFF/, "").split("\r\n");
    expect(lines[0]).toBe(
      "id,name,location,description,slug,sponsored,website,global_rank,financials,student_loan_available,campus_student_life,number_of_students,student_to_faculty_ratio,international_student_ratio,housing_availability,admissions_contact,admissions_phone,contact_person,admissions_page_link,immigration_support,university_campuses",
    );
    expect(lines[1].startsWith(",")).toBe(true);
  });
});
