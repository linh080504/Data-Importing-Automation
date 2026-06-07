import { describe, expect, it } from "vitest";
import {
  buildMajorCsv,
  FIXED_MAJOR_CSV_HEADER,
  getVerifiedMajorMatches,
  majorExportBlockReason,
  validateMajorCsvHeader,
} from "@/lib/csv/major-export";
import type { UniversityRecord } from "@/lib/types";

function record(overrides: Partial<UniversityRecord>): UniversityRecord {
  return {
    id: "",
    name: "Hanoi University of Science and Technology, Vietnam",
    location: "704",
    description: "University description",
    slug: "hust-vietnam",
    sponsored: "0",
    website: "https://hust.edu.vn/",
    global_rank: "",
    financials: "",
    student_loan_available: "0",
    campus_student_life: "",
    number_of_students: "",
    student_to_faculty_ratio: "",
    international_student_ratio: "",
    housing_availability: "0",
    admissions_contact: "",
    admissions_phone: "",
    contact_person: "",
    admissions_page_link: "",
    immigration_support: "0",
    university_campuses: "",
    countryName: "Vietnam",
    sourceTitle: "Hanoi University of Science and Technology",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Hanoi_University_of_Science_and_Technology",
    officialPages: [],
    evidence: [],
    estimatedFields: [],
    reviewStatus: "Unreviewed",
    createdAt: "2026-06-07T00:00:00.000Z",
    updatedAt: "2026-06-07T00:00:00.000Z",
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

describe("major CSV export", () => {
  it("keeps the fixed three-column header and UTF-8 BOM", () => {
    expect(FIXED_MAJOR_CSV_HEADER).toBe("University Name,Major Name,Source URL (Optional)");
    expect(validateMajorCsvHeader()).toBe(true);
    expect(buildMajorCsv([]).startsWith("\uFEFF")).toBe(true);
  });

  it("exports one row per verified major and removes duplicates", () => {
    const source = "https://hust.edu.vn/uploads/programs-2026.pdf";
    const records = [
      record({
        majorMatches: [
          { universityName: "HUST, Vietnam", majorName: "Bioengineering", sourceUrl: source },
          { universityName: "HUST, Vietnam", majorName: "Food Engineering", sourceUrl: source },
          { universityName: "HUST, Vietnam", majorName: "Bioengineering", sourceUrl: source },
        ],
      }),
    ];
    const matches = getVerifiedMajorMatches(records, ["Bioengineering", "Food Engineering"]);
    expect(matches).toHaveLength(2);
    expect(buildMajorCsv(records, ["Bioengineering", "Food Engineering"]).split("\r\n")).toHaveLength(4);
  });

  it("keeps the same major as separate rows for different universities", () => {
    const records = [
      record({
        majorMatches: [
          { universityName: "HUST, Vietnam", majorName: "Chemistry", sourceUrl: "https://hust.edu.vn/academic/chemistry" },
        ],
      }),
      record({
        name: "University B, Vietnam",
        slug: "university-b-vietnam",
        website: "https://university-b.edu.vn/",
        majorMatches: [
          { universityName: "University B, Vietnam", majorName: "Chemistry", sourceUrl: "https://university-b.edu.vn/programs/chemistry" },
        ],
      }),
    ];
    expect(getVerifiedMajorMatches(records, ["Chemistry"])).toHaveLength(2);
  });

  it("rejects unrequested majors and non-official source domains", () => {
    const records = [
      record({
        majorMatches: [
          { universityName: "HUST, Vietnam", majorName: "Chemistry", sourceUrl: "https://example.com/program.pdf" },
          { universityName: "HUST, Vietnam", majorName: "Physics", sourceUrl: "https://hust.edu.vn/academic/physics" },
        ],
      }),
    ];
    expect(getVerifiedMajorMatches(records, ["Chemistry"])).toEqual([]);
  });

  it("escapes commas and quotes", () => {
    const records = [
      record({
        majorMatches: [
          {
            universityName: 'University "A", Vietnam',
            majorName: "Chemical Engineering",
            sourceUrl: "https://hust.edu.vn/academic/program?id=1,2",
          },
        ],
      }),
    ];
    const csv = buildMajorCsv(records, ["Chemical Engineering"]);
    expect(csv).toContain('"University ""A"", Vietnam"');
    expect(csv).toContain('"https://hust.edu.vn/academic/program?id=1,2"');
  });

  it("discovers all stored majors without a requested-major list", () => {
    const records = [
      record({
        website: "https://en.dut.udn.vn/",
        majorMatches: [
          {
            universityName: "Đại học Bách khoa Đà Nẵng, Vietnam",
            majorName: "Kỹ thuật Hóa học",
            sourceUrl: "https://en.dut.udn.vn/academic/training-programs",
            sourceType: "academic_table",
          },
          {
            universityName: "Đại học Bách khoa Đà Nẵng, Vietnam",
            majorName: "Computer Engineering",
            sourceUrl: "https://en.dut.udn.vn/academic/computer-engineering",
            sourceType: "program_page",
          },
        ],
      }),
    ];
    const matches = getVerifiedMajorMatches(records, [], "discover");
    expect(matches).toHaveLength(2);
    expect(buildMajorCsv(records, [], "discover")).toContain("Dai hoc Bach khoa Da Nang");
  });

  it("deduplicates a university-major pair and keeps the stronger program page", () => {
    const records = [
      record({
        majorMatches: [
          {
            universityName: "HUST, Vietnam",
            majorName: "Chemical Engineering",
            sourceUrl: "https://hust.edu.vn/academic/program-list",
            sourceType: "academic_table",
          },
          {
            universityName: "HUST, Vietnam",
            majorName: "Chemical Engineering",
            sourceUrl: "https://hust.edu.vn/academic/chemical-engineering",
            sourceType: "program_page",
          },
        ],
      }),
    ];
    const matches = getVerifiedMajorMatches(records, [], "discover");
    expect(matches).toHaveLength(1);
    expect(matches[0].sourceUrl).toContain("chemical-engineering");
  });

  it("does not treat unrelated edu.vn domains as the same official site", () => {
    const records = [
      record({
        website: "https://dut.udn.vn/",
        majorMatches: [
          {
            universityName: "DUT, Vietnam",
            majorName: "Chemical Engineering",
            sourceUrl: "https://other.edu.vn/programs/chemical-engineering",
            sourceType: "program_page",
          },
        ],
      }),
    ];
    expect(getVerifiedMajorMatches(records, [], "discover")).toEqual([]);
  });

  it("blocks legacy major export until country-safe recrawl", () => {
    expect(majorExportBlockReason(undefined, [record({})])).toContain("legacy run");
    expect(
      majorExportBlockReason(2, [
        record({
          countryValidation: {
            status: "verified",
            reason: "Vietnam location",
            evidenceUrl: "https://en.wikipedia.org/wiki/Test",
          },
        }),
      ]),
    ).toBe("");
  });
});
