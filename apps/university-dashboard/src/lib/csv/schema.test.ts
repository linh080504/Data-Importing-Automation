import { describe, expect, it } from "vitest";
import { CSV_HEADERS, FIXED_CSV_HEADER, isBinary, isEmail, isIntegerLike, isPhone, isUrl, slugify } from "@/lib/csv/schema";
import { validateCsvHeader } from "@/lib/csv/export";

describe("CSV schema", () => {
  it("keeps the fixed import header order", () => {
    expect(CSV_HEADERS).toHaveLength(21);
    expect(FIXED_CSV_HEADER).toBe(
      "id,name,location,description,slug,sponsored,website,global_rank,financials,student_loan_available,campus_student_life,number_of_students,student_to_faculty_ratio,international_student_ratio,housing_availability,admissions_contact,admissions_phone,contact_person,admissions_page_link,immigration_support,university_campuses",
    );
    expect(validateCsvHeader()).toBe(true);
  });

  it("validates scalar field formats", () => {
    expect(isBinary("0")).toBe(true);
    expect(isBinary("2")).toBe(false);
    expect(isIntegerLike("356")).toBe(true);
    expect(isIntegerLike("", true)).toBe(true);
    expect(isUrl("https://example.edu")).toBe(true);
    expect(isEmail("admissions@example.edu")).toBe(true);
    expect(isPhone("+914712232240")).toBe(true);
  });

  it("slugifies institution names consistently", () => {
    expect(slugify("VTM NSS College, Dhanuvachapuram")).toBe("vtm-nss-college-dhanuvachapuram");
  });
});
