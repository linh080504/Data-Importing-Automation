const UniversityQuality = (() => {
  const CSV_HEADERS = [
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
  ];

  const OPTIONAL_EXPORT_FIELDS = new Set(["id", "global_rank", "contact_person"]);
  const BINARY_FIELDS = [
    "sponsored",
    "student_loan_available",
    "housing_availability",
    "immigration_support",
  ];
  const INTEGER_FIELDS = [
    "location",
    "global_rank",
    "number_of_students",
    "student_to_faculty_ratio",
    "international_student_ratio",
    "university_campuses",
  ];
  const NUMERIC_RANGES = {
    number_of_students: [50, 500000],
    student_to_faculty_ratio: [3, 80],
    international_student_ratio: [0, 100],
    university_campuses: [1, 200],
  };

  const COUNTRY_CODES = {
    Afghanistan: 4,
    Albania: 8,
    Algeria: 12,
    Argentina: 32,
    Australia: 36,
    Austria: 40,
    Bangladesh: 50,
    Belgium: 56,
    Brazil: 76,
    Canada: 124,
    Chile: 152,
    China: 156,
    Colombia: 170,
    Denmark: 208,
    Egypt: 818,
    Finland: 246,
    France: 250,
    Germany: 276,
    Ghana: 288,
    Greece: 300,
    India: 356,
    Indonesia: 360,
    Ireland: 372,
    Israel: 376,
    Italy: 380,
    Japan: 392,
    Kenya: 404,
    Malaysia: 458,
    Mexico: 484,
    Netherlands: 528,
    "New Zealand": 554,
    Nigeria: 566,
    Norway: 578,
    Pakistan: 586,
    Philippines: 608,
    Poland: 616,
    Portugal: 620,
    Romania: 642,
    Singapore: 702,
    "South Africa": 710,
    "South Korea": 410,
    Spain: 724,
    Sweden: 752,
    Switzerland: 756,
    Thailand: 764,
    Turkey: 792,
    Ukraine: 804,
    "United Arab Emirates": 784,
    "United Kingdom": 826,
    "United States": 840,
    Vietnam: 704,
  };

  function toText(value) {
    if (value === null || value === undefined) return "";
    return String(value).trim();
  }

  function isBlank(value) {
    return toText(value) === "";
  }

  function isIntegerLike(value, allowBlank) {
    if (allowBlank && isBlank(value)) return true;
    return /^-?\d+$/.test(toText(value));
  }

  function toInt(value, fallback) {
    if (!isIntegerLike(value, false)) return fallback;
    return Number.parseInt(toText(value), 10);
  }

  function isBinary(value) {
    return toText(value) === "0" || toText(value) === "1" || value === 0 || value === 1;
  }

  function isUrl(value, allowBlank) {
    if (allowBlank && isBlank(value)) return true;
    try {
      const url = new URL(toText(value));
      return url.protocol === "http:" || url.protocol === "https:";
    } catch (_error) {
      return false;
    }
  }

  function isEmail(value, allowBlank) {
    if (allowBlank && isBlank(value)) return true;
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(toText(value));
  }

  function isPhone(value, allowBlank) {
    if (allowBlank && isBlank(value)) return true;
    return /^\+\d[\d\s().-]{6,24}$/.test(toText(value));
  }

  function normalizeDomain(value) {
    if (!isUrl(value, true) || isBlank(value)) return "";
    try {
      return new URL(toText(value)).hostname.toLowerCase().replace(/^www\./, "");
    } catch (_error) {
      return "";
    }
  }

  function emailDomain(email) {
    if (!isEmail(email, true) || isBlank(email)) return "";
    return toText(email).split("@").pop().toLowerCase();
  }

  function rootDomain(domain) {
    const parts = toText(domain).split(".").filter(Boolean);
    if (parts.length <= 2) return parts.join(".");
    return parts.slice(-2).join(".");
  }

  function sameRootDomain(a, b) {
    if (!a || !b) return false;
    return rootDomain(a) === rootDomain(b);
  }

  function slugify(value) {
    return toText(value)
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/&/g, " and ")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .replace(/-{2,}/g, "-");
  }

  function csvEscape(value) {
    const raw = value === null || value === undefined ? "" : String(value);
    if (/[",\r\n]/.test(raw)) return `"${raw.replace(/"/g, '""')}"`;
    return raw;
  }

  function parseEvidence(record) {
    const evidence = [];
    const add = (type, url, label) => {
      if (!isBlank(url)) evidence.push({ type, url: toText(url), label: label || type });
    };

    add("official", record.official_url || record.official_site_evidence, "Official site");
    add("wikipedia", record.wikipedia_url || record.wiki_url || record.source_url, "Wikipedia");
    add("wikidata", record.wikidata_url || record.wikidata, "Wikidata");

    const raw = record.evidence_urls || record.evidence || record.source_evidence;
    if (!isBlank(raw)) {
      if (Array.isArray(raw)) {
        raw.forEach((entry) => {
          if (typeof entry === "string") add("source", entry, "Source");
          else if (entry && typeof entry === "object") add(entry.type || "source", entry.url, entry.label);
        });
      } else {
        try {
          const parsed = JSON.parse(raw);
          if (Array.isArray(parsed)) {
            parsed.forEach((entry) => {
              if (typeof entry === "string") add("source", entry, "Source");
              else if (entry && typeof entry === "object") add(entry.type || "source", entry.url, entry.label);
            });
          }
        } catch (_error) {
          toText(raw)
            .split(/[,\n]/)
            .map((item) => item.trim())
            .filter(Boolean)
            .forEach((url) => add("source", url, "Source"));
        }
      }
    }

    if (!isBlank(record.website)) add("official", record.website, "Website");
    if (!isBlank(record.admissions_page_link)) add("official", record.admissions_page_link, "Admissions");

    const unique = [];
    const seen = new Set();
    for (const entry of evidence) {
      const key = `${entry.type}:${entry.url}`;
      if (!seen.has(key) && isUrl(entry.url, false)) {
        unique.push(entry);
        seen.add(key);
      }
    }
    return unique;
  }

  function normalizeRecord(input, context) {
    const record = { ...input };
    for (const header of CSV_HEADERS) {
      if (record[header] === undefined || record[header] === null) record[header] = "";
      else record[header] = toText(record[header]);
    }

    const country = toText(record.country || record.country_name || context?.country);
    if (isBlank(record.location) && country && COUNTRY_CODES[country]) {
      record.location = String(COUNTRY_CODES[country]);
    }
    if (isBlank(record.slug)) record.slug = slugify(record.name);
    if (!isBlank(record.country) && !/,/.test(record.name)) record.name = `${record.name}, ${record.country}`;
    return record;
  }

  function issue(field, severity, ruleId, message, evidenceUrl) {
    return { field, severity, rule_id: ruleId, message, evidence_url: evidenceUrl || "" };
  }

  function scoreRecord(input, context = {}) {
    const record = normalizeRecord(input, context);
    const findings = [];
    const evidence = parseEvidence(record);
    const evidenceTypes = new Set(evidence.map((entry) => entry.type));
    const officialDomain = normalizeDomain(record.website);
    const admissionsDomain = normalizeDomain(record.admissions_page_link);
    const mailDomain = emailDomain(record.admissions_contact);

    let schemaErrors = 0;
    let schemaWarnings = 0;

    if (!isBlank(record.id)) {
      findings.push(issue("id", "minor", "csv.id.must_be_blank", "id must be empty for imports."));
      schemaWarnings += 1;
    }

    for (const field of CSV_HEADERS) {
      if (OPTIONAL_EXPORT_FIELDS.has(field)) continue;
      if (isBlank(record[field])) {
        const severity = ["name", "location", "description", "slug"].includes(field) ? "critical" : "major";
        findings.push(issue(field, severity, `csv.${field}.missing`, `${field} is missing.`));
        if (severity === "critical") schemaErrors += 1;
      }
    }

    for (const field of BINARY_FIELDS) {
      if (!isBinary(record[field])) {
        findings.push(issue(field, "critical", `csv.${field}.binary`, `${field} must be 0 or 1.`));
        schemaErrors += 1;
      }
    }

    for (const field of INTEGER_FIELDS) {
      const allowBlank = field === "global_rank";
      if (!isIntegerLike(record[field], allowBlank)) {
        findings.push(issue(field, "critical", `csv.${field}.integer`, `${field} must be a plain integer.`));
        schemaErrors += 1;
      }
    }

    if (!isUrl(record.website, true)) {
      findings.push(issue("website", "major", "csv.website.url", "website must be a full http(s) URL."));
      schemaWarnings += 1;
    }
    if (!isUrl(record.admissions_page_link, true)) {
      findings.push(issue("admissions_page_link", "major", "csv.admissions_page_link.url", "admissions page must be a full http(s) URL."));
      schemaWarnings += 1;
    }
    if (!isEmail(record.admissions_contact, true)) {
      findings.push(issue("admissions_contact", "major", "csv.admissions_contact.email", "admissions_contact must be a real email format."));
      schemaWarnings += 1;
    }
    if (!isPhone(record.admissions_phone, true)) {
      findings.push(issue("admissions_phone", "major", "csv.admissions_phone.phone", "admissions_phone must start with a country code."));
      schemaWarnings += 1;
    }

    const schemaScore = Math.max(0, 20 - schemaErrors * 5 - schemaWarnings * 2);

    const required = CSV_HEADERS.filter((field) => !OPTIONAL_EXPORT_FIELDS.has(field));
    const completeCount = required.filter((field) => !isBlank(record[field])).length;
    const completenessScore = Math.round((completeCount / required.length) * 20);

    let evidenceScore = 0;
    if (evidenceTypes.has("official")) evidenceScore += 11;
    if (evidenceTypes.has("wikidata")) evidenceScore += 7;
    if (evidenceTypes.has("wikipedia")) evidenceScore += 5;
    evidenceScore += Math.min(2, evidence.length);
    evidenceScore = Math.min(25, evidenceScore);
    if (evidenceScore < 8) {
      findings.push(issue("source_evidence", "major", "evidence.weak", "Source evidence is weak or absent."));
    }

    let contactScore = 0;
    if (isUrl(record.website, false)) contactScore += 4;
    if (isUrl(record.admissions_page_link, false)) contactScore += 4;
    if (isEmail(record.admissions_contact, false)) contactScore += 3;
    if (isPhone(record.admissions_phone, false)) contactScore += 2;
    if (
      (officialDomain && admissionsDomain && sameRootDomain(officialDomain, admissionsDomain)) ||
      (officialDomain && mailDomain && sameRootDomain(officialDomain, mailDomain))
    ) {
      contactScore += 2;
    }
    if (officialDomain && admissionsDomain && !sameRootDomain(officialDomain, admissionsDomain)) {
      findings.push(issue("admissions_page_link", "major", "contact.domain_mismatch", "Admissions page domain does not match official website.", record.admissions_page_link));
    }
    if (officialDomain && mailDomain && !sameRootDomain(officialDomain, mailDomain)) {
      findings.push(issue("admissions_contact", "minor", "contact.email_domain_mismatch", "Admissions email domain does not match official website."));
    }
    contactScore = Math.min(15, contactScore);

    let consistencyScore = 10;
    for (const [field, range] of Object.entries(NUMERIC_RANGES)) {
      if (isBlank(record[field]) || !isIntegerLike(record[field], false)) continue;
      const value = toInt(record[field], 0);
      if (value < range[0] || value > range[1]) {
        findings.push(issue(field, field === "international_student_ratio" ? "critical" : "major", `outlier.${field}`, `${field} is outside the expected range ${range[0]}-${range[1]}.`));
        consistencyScore -= field === "international_student_ratio" ? 4 : 2;
      }
    }
    consistencyScore = Math.max(0, consistencyScore);

    const slugCounts = context.slugCounts || {};
    const nameCounts = context.nameCounts || {};
    const duplicateSlug = record.slug && slugCounts[record.slug] > 1;
    const duplicateName = record.name && nameCounts[record.name.toLowerCase()] > 1;
    let duplicateScore = 10;
    if (duplicateSlug) {
      findings.push(issue("slug", "critical", "duplicate.slug", "Duplicate slug conflict."));
      duplicateScore = 0;
    } else if (duplicateName) {
      findings.push(issue("name", "major", "duplicate.name", "Duplicate institution name needs slug disambiguation."));
      duplicateScore = 6;
    }

    const components = {
      schema_type_validity: schemaScore,
      field_completeness: completenessScore,
      source_evidence_strength: evidenceScore,
      website_contact_verification: contactScore,
      consistency_outliers: consistencyScore,
      duplicate_slug_uniqueness: duplicateScore,
    };

    const score = Object.values(components).reduce((sum, value) => sum + value, 0);
    const hasCritical = findings.some((entry) => entry.severity === "critical");
    const importantMissing = findings.some((entry) => entry.rule_id.endsWith(".missing") && entry.severity !== "minor");
    let qualityStatus = "Risky";
    if (duplicateSlug || score < 45) qualityStatus = "Risky";
    else if (score >= 85 && (evidenceTypes.has("official") || evidenceTypes.has("wikidata"))) qualityStatus = "Verified";
    else if (score >= 70 && !hasCritical) qualityStatus = "Probable";
    else if (score >= 45 || importantMissing) qualityStatus = "Needs Review";

    return {
      ...record,
      quality_score: score,
      quality_status: qualityStatus,
      truth_status: qualityStatus,
      export_ready: (record.review_status === "Approved" || record.export_approved === "1" || record.export_approved === 1) && !hasCritical && score >= 70,
      score_components: components,
      evidence_links: evidence,
      finding_count: findings.length,
      critical_count: findings.filter((entry) => entry.severity === "critical").length,
      major_count: findings.filter((entry) => entry.severity === "major").length,
      risky_flags: findings.filter((entry) => entry.severity === "critical" || entry.severity === "major").map((entry) => entry.rule_id),
      findings,
    };
  }

  function makeCounts(records) {
    const slugCounts = {};
    const nameCounts = {};
    for (const row of records) {
      const slug = toText(row.slug);
      if (slug) slugCounts[slug] = (slugCounts[slug] || 0) + 1;
      const name = toText(row.name).toLowerCase();
      if (name) nameCounts[name] = (nameCounts[name] || 0) + 1;
    }
    return { slugCounts, nameCounts };
  }

  function scoreBatch(records, context = {}) {
    const normalized = (records || []).map((record) => normalizeRecord(record, context));
    const counts = makeCounts(normalized);
    return normalized.map((record) => scoreRecord(record, { ...context, ...counts }));
  }

  function aggregate(records, context = {}) {
    const scoredRecords = scoreBatch(records || [], context);
    const total = scoredRecords.length;
    const statusCounts = { Verified: 0, Probable: 0, "Needs Review": 0, Risky: 0 };
    const scoreBands = { "0-44": 0, "45-69": 0, "70-84": 0, "85-100": 0 };
    const sourceMix = { official: 0, wikidata: 0, wikipedia: 0, source: 0, none: 0 };
    const fieldCompleteness = {};
    const numericOutliers = {};
    const allFindings = [];
    const countries = new Set();
    let duplicateCount = 0;

    for (const field of CSV_HEADERS) fieldCompleteness[field] = { present: 0, missing: 0, pct: 0 };
    for (const field of Object.keys(NUMERIC_RANGES)) numericOutliers[field] = 0;

    for (const record of scoredRecords) {
      statusCounts[record.quality_status] = (statusCounts[record.quality_status] || 0) + 1;
      if (record.quality_score < 45) scoreBands["0-44"] += 1;
      else if (record.quality_score < 70) scoreBands["45-69"] += 1;
      else if (record.quality_score < 85) scoreBands["70-84"] += 1;
      else scoreBands["85-100"] += 1;

      if (!isBlank(record.location)) countries.add(toText(record.location));
      if (record.risky_flags.includes("duplicate.slug") || record.risky_flags.includes("duplicate.name")) duplicateCount += 1;

      for (const field of CSV_HEADERS) {
        if (isBlank(record[field])) fieldCompleteness[field].missing += 1;
        else fieldCompleteness[field].present += 1;
      }

      const sourceTypes = new Set(record.evidence_links.map((entry) => entry.type));
      if (!sourceTypes.size) sourceMix.none += 1;
      for (const type of sourceTypes) sourceMix[type] = (sourceMix[type] || 0) + 1;

      for (const finding of record.findings) {
        allFindings.push({ ...finding, slug: record.slug, name: record.name });
        if (finding.rule_id.startsWith("outlier.")) {
          numericOutliers[finding.field] = (numericOutliers[finding.field] || 0) + 1;
        }
      }
    }

    for (const field of CSV_HEADERS) {
      const present = fieldCompleteness[field].present;
      fieldCompleteness[field].pct = total ? Math.round((present / total) * 100) : 0;
    }

    const completenessAverage = total
      ? Math.round(Object.values(fieldCompleteness).reduce((sum, item) => sum + item.pct, 0) / CSV_HEADERS.length)
      : 0;
    const exportable = scoredRecords.filter((record) => record.export_ready).length;

    return {
      records: scoredRecords,
      findings: allFindings,
      summary: {
        total,
        countries: countries.size,
        verified: statusCounts.Verified || 0,
        probable: statusCounts.Probable || 0,
        needs_review: statusCounts["Needs Review"] || 0,
        risky: statusCounts.Risky || 0,
        completeness_score: completenessAverage,
        duplicate_count: duplicateCount,
        export_ready: exportable,
        export_blocked: Math.max(0, total - exportable),
      },
      charts: {
        status_counts: statusCounts,
        score_bands: scoreBands,
        source_mix: sourceMix,
        numeric_outliers: numericOutliers,
      },
      fieldCompleteness,
    };
  }

  function validateExport(records, context = {}) {
    const scored = scoreBatch(records || [], context);
    const exportable = scored.filter((record) => record.export_ready);
    const headerOk = CSV_HEADERS.join(",") === "id,name,location,description,slug,sponsored,website,global_rank,financials,student_loan_available,campus_student_life,number_of_students,student_to_faculty_ratio,international_student_ratio,housing_availability,admissions_contact,admissions_phone,contact_person,admissions_page_link,immigration_support,university_campuses";
    const blocked = scored.filter((record) => !record.export_ready).map((record) => ({
      slug: record.slug,
      name: record.name,
      quality_score: record.quality_score,
      quality_status: record.quality_status,
      critical_count: record.critical_count,
      review_status: record.review_status || "",
    }));
    return { headerOk, exportable, blocked };
  }

  function toCsv(records, context = {}) {
    const check = validateExport(records || [], context);
    if (!check.headerOk) throw new Error("CSV header order mismatch.");
    const lines = [CSV_HEADERS.join(",")];
    for (const record of check.exportable) {
      lines.push(CSV_HEADERS.map((header) => csvEscape(record[header])).join(","));
    }
    return { filename: "University_Import_Clean.csv", csv: `${lines.join("\r\n")}\r\n`, count: check.exportable.length, blocked: check.blocked };
  }

  return {
    CSV_HEADERS,
    COUNTRY_CODES,
    normalizeRecord,
    scoreRecord,
    scoreBatch,
    aggregate,
    validateExport,
    toCsv,
    slugify,
  };
})();

if (typeof module !== "undefined") {
  module.exports = UniversityQuality;
}
