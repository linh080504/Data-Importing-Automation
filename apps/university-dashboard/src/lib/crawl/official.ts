import type { CountryOption } from "@/lib/types";
import { fetchText, isPublicHttpUrl } from "@/lib/crawl/http";

const DENY_EXTERNAL =
  /(wikipedia|wikimedia|wikidata|creativecommons|doi\.org|facebook|twitter|x\.com|linkedin|youtube|instagram|google|archive\.org|toolforge|geohack|openstreetmap|osm\.org|maps?|coordinates?|geonames|worldcat|viaf)/i;
const EMAIL_RE = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi;
const PHONE_RE = /(?:\+\d{1,3}[\s().-]?)?(?:\(?\d{2,5}\)?[\s().-]?){2,5}\d{3,5}/g;

function absoluteUrl(base: string, href: string) {
  try {
    return new URL(href, base).toString();
  } catch {
    return "";
  }
}

export function firstOfficialUrl(externalLinks: string[], wikidataOfficial = "", infoboxOfficial = "") {
  if (wikidataOfficial && isPublicHttpUrl(wikidataOfficial)) return wikidataOfficial;
  if (infoboxOfficial && isPublicHttpUrl(infoboxOfficial) && !DENY_EXTERNAL.test(infoboxOfficial)) return infoboxOfficial;
  const candidates = externalLinks.filter((url) => isPublicHttpUrl(url) && !DENY_EXTERNAL.test(url));
  return (
    candidates
      .map((url) => {
        const lowered = url.toLowerCase();
        let score = 0;
        if (/\.(edu|ac)\b/.test(lowered)) score += 5;
        if (/university|college|institute|academy|school/.test(lowered)) score += 4;
        if (/admission|contact|about/.test(lowered)) score += 1;
        if (/news|article|press|pdf/.test(lowered)) score -= 2;
        return { url, score };
      })
      .sort((left, right) => right.score - left.score)[0]?.url ?? ""
  );
}

function normalizePhone(raw: string, country: CountryOption) {
  const cleaned = raw.replace(/[^\d+]/g, "");
  if (cleaned.startsWith("+") && cleaned.length >= 8) return cleaned;
  if (cleaned.length >= 8 && cleaned.length <= 14) return `${country.phonePrefix}${cleaned.replace(/^0+/, "")}`;
  return "";
}

function unique<T>(items: T[]) {
  return Array.from(new Set(items.filter(Boolean)));
}

function extractAdmissionLinks(baseUrl: string, html: string) {
  const links = Array.from(html.matchAll(/href=["']([^"']+)["']/gi)).map((match) => absoluteUrl(baseUrl, match[1]));
  return links.filter((url) => /admission|apply|enrol|enroll/i.test(url));
}

export async function inspectOfficialSite(officialUrl: string, country: CountryOption) {
  if (!officialUrl || !isPublicHttpUrl(officialUrl)) {
    return { emails: [] as string[], phones: [] as string[], admissionsUrl: "", checkedPages: [] as string[], hasHousing: false };
  }

  const origin = new URL(officialUrl).origin;
  const pageCandidates = unique([
    officialUrl,
    `${origin}/admissions`,
    `${origin}/admission`,
    `${origin}/contact`,
    `${origin}/contact-us`,
  ]).slice(0, 4);

  const checkedPages: string[] = [];
  const emails: string[] = [];
  const phones: string[] = [];
  const admissionsLinks: string[] = [];
  let hasHousing = false;

  for (const page of pageCandidates) {
    try {
      const html = await fetchText(page, 4500, 240000);
      checkedPages.push(page);
      emails.push(...(html.match(EMAIL_RE) ?? []).map((email) => email.toLowerCase()));
      phones.push(...(html.match(PHONE_RE) ?? []).map((phone) => normalizePhone(phone, country)).filter(Boolean));
      admissionsLinks.push(...extractAdmissionLinks(page, html));
      if (/hostel|housing|residence|dormitory|accommodation/i.test(html)) hasHousing = true;
    } catch {
      // Official sites often block bots. The row keeps weaker evidence instead of failing the crawl.
    }
  }

  return {
    emails: unique(emails).slice(0, 5),
    phones: unique(phones).slice(0, 5),
    admissionsUrl: unique(admissionsLinks)[0] ?? pageCandidates.find((page) => /admission/i.test(page)) ?? "",
    checkedPages,
    hasHousing,
  };
}

export function stripHtml(html: string) {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}
