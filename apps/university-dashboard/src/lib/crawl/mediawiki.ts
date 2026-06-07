import type { CountryOption } from "@/lib/types";
import { fetchJson } from "@/lib/crawl/http";

const WIKI_API = "https://en.wikipedia.org/w/api.php";

interface ParseResponse {
  parse?: {
    title: string;
    links?: Array<{ "*": string; ns: number }>;
    externallinks?: string[];
    pageprops?: { wikibase_item?: string };
    text?: { "*": string };
  };
  error?: { code: string; info: string };
}

interface SummaryResponse {
  title: string;
  extract?: string;
  content_urls?: { desktop?: { page?: string } };
}

export interface InfoboxFacts {
  caption: string;
  type: string;
  established: string;
  president: string;
  students: string;
  undergraduates: string;
  postgraduates: string;
  locationText: string;
  campus: string;
  website: string;
}

interface SearchResponse {
  query?: {
    search?: Array<{ title: string }>;
  };
}

interface CategoryMembersResponse {
  query?: {
    categorymembers?: Array<{ title: string; ns: number }>;
  };
}

function apiUrl(params: Record<string, string>) {
  const search = new URLSearchParams({ format: "json", origin: "*", ...params });
  return `${WIKI_API}?${search.toString()}`;
}

function decodeHtml(value: string) {
  return value
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&ndash;|&mdash;/gi, "-")
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<sup[\s\S]*?<\/sup>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function attrValue(tag: string, attr: string) {
  const match = tag.match(new RegExp(`${attr}=["']([^"']+)["']`, "i"));
  return match?.[1] ?? "";
}

function wikiTitleFromHref(href: string) {
  if (!href.startsWith("/wiki/")) return "";
  if (href.includes(":")) return "";
  return decodeURIComponent(href.replace(/^\/wiki\//, "").split("#")[0].replace(/_/g, " "));
}

function extractAnchors(html: string) {
  const anchors: Array<{ title: string; href: string; text: string }> = [];
  for (const match of html.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/gi)) {
    const attrs = match[1];
    const href = attrValue(attrs, "href");
    const title = attrValue(attrs, "title") || wikiTitleFromHref(href);
    const text = decodeHtml(match[2]);
    if (title || href || text) anchors.push({ title, href, text });
  }
  return anchors;
}

function tableBlocks(html: string, classNeedle: string) {
  const blocks: string[] = [];
  const tableRe = /<table\b[^>]*>[\s\S]*?<\/table>/gi;
  for (const match of html.matchAll(tableRe)) {
    const table = match[0];
    if (new RegExp(`class=["'][^"']*${classNeedle}`, "i").test(table)) blocks.push(table);
  }
  return blocks;
}

function firstExternalHref(html: string) {
  return extractAnchors(html).find((anchor) => /^https?:\/\//i.test(anchor.href))?.href ?? "";
}

function parseNumberText(value: string) {
  return value.match(/[\d,]{3,}/)?.[0]?.replace(/,/g, "") ?? "";
}

export function parseInfoboxFacts(html: string): InfoboxFacts {
  const empty: InfoboxFacts = {
    caption: "",
    type: "",
    established: "",
    president: "",
    students: "",
    undergraduates: "",
    postgraduates: "",
    locationText: "",
    campus: "",
    website: "",
  };
  const infobox = tableBlocks(html, "infobox")[0] ?? "";
  if (!infobox) return empty;
  const caption = infobox.match(/<caption\b[^>]*>([\s\S]*?)<\/caption>/i)?.[1] ?? "";
  const facts = { ...empty, caption: decodeHtml(caption) };

  for (const row of infobox.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)) {
    const rowHtml = row[1];
    const labelHtml = rowHtml.match(/<th\b[^>]*>([\s\S]*?)<\/th>/i)?.[1] ?? "";
    const valueHtml = rowHtml.match(/<td\b[^>]*>([\s\S]*?)<\/td>/i)?.[1] ?? "";
    const label = decodeHtml(labelHtml).toLowerCase();
    const value = decodeHtml(valueHtml);
    if (!label || !value) continue;

    if (label === "type") facts.type = value;
    else if (label.includes("established") || label.includes("founded")) facts.established = value;
    else if (label.includes("president") || label.includes("rector") || label.includes("chancellor")) facts.president = value;
    else if (label.includes("students") || label.includes("enrol") || label.includes("enroll")) facts.students = parseNumberText(value);
    else if (label.includes("undergraduate")) facts.undergraduates = parseNumberText(value);
    else if (label.includes("postgraduate")) facts.postgraduates = parseNumberText(value);
    else if (label === "location") facts.locationText = value;
    else if (label.includes("campus")) facts.campus = value;
    else if (label.includes("website")) facts.website = firstExternalHref(valueHtml) || value;
  }
  return facts;
}

function extractInstitutionTitlesFromTables(html: string) {
  const tables = tableBlocks(html, "wikitable");
  const titles: string[] = [];
  const seen = new Set<string>();
  for (const table of tables) {
    for (const anchor of extractAnchors(table)) {
      const title = anchor.title || anchor.text;
      if (!title || seen.has(title)) continue;
      seen.add(title);
      titles.push(title);
    }
  }
  return titles;
}

export async function parsePage(page: string, prop: string): Promise<ParseResponse> {
  return fetchJson<ParseResponse>(apiUrl({ action: "parse", page, prop }));
}

export async function pageSummary(title: string) {
  const encoded = encodeURIComponent(title.replace(/ /g, "_"));
  return fetchJson<SummaryResponse>(`https://en.wikipedia.org/api/rest_v1/page/summary/${encoded}`);
}

async function searchPages(query: string, limit: number) {
  const data = await fetchJson<SearchResponse>(
    apiUrl({
      action: "query",
      list: "search",
      srsearch: query,
      srlimit: String(limit),
      srnamespace: "0",
    }),
  );
  return data.query?.search?.map((entry) => entry.title) ?? [];
}

async function categoryMembers(categoryTitle: string, limit: number) {
  const data = await fetchJson<CategoryMembersResponse>(
    apiUrl({
      action: "query",
      list: "categorymembers",
      cmtitle: categoryTitle,
      cmlimit: String(limit),
      cmnamespace: "0|14",
    }),
  );
  return data.query?.categorymembers ?? [];
}

function likelyListPageTitle(title: string, country: CountryOption) {
  const lowered = title.toLowerCase();
  const countryName = country.name.toLowerCase();
  return (
    lowered.includes(countryName) &&
    (/list of .*universit/.test(lowered) ||
      /list of .*college/.test(lowered) ||
      /institutions of higher education/.test(lowered) ||
      /universities and colleges/.test(lowered))
  );
}

function cleanCountryTitle(title: string) {
  return title
    .replace(/^List of universities and colleges in /i, "")
    .replace(/^List of colleges and universities in /i, "")
    .replace(/^List of universities in /i, "")
    .replace(/^List of colleges in /i, "")
    .replace(/^List of institutions of higher education in /i, "")
    .trim();
}

export async function discoverCountryListPage(country: CountryOption) {
  const index = await parsePage("Lists_of_universities_and_colleges_by_country", "links");
  const indexLinks = index.parse?.links ?? [];
  const fromIndex = indexLinks
    .map((link) => link["*"])
    .find((title) => likelyListPageTitle(title, country) || cleanCountryTitle(title).toLowerCase() === country.name.toLowerCase());
  const candidates = [...country.listPageCandidates, ...(fromIndex ? [fromIndex] : [])];
  const seen = new Set<string>();
  for (const candidate of candidates) {
    if (seen.has(candidate)) continue;
    seen.add(candidate);
    const parsed = await parsePage(candidate, "links");
    if (!parsed.error && parsed.parse?.links?.length) return candidate;
  }
  throw new Error(`No Wikipedia list page found for ${country.name}.`);
}

function isLikelyInstitutionTitle(title: string) {
  if (!title) return false;
  if (/^(List of|Category:|Template:|Help:|File:|Portal:|Wikipedia:)/i.test(title)) return false;
  if (/Education in|Higher education|Universities in|Colleges in|Rankings of/i.test(title)) return false;
  return /(University|College|Institute|School|Academy|Polytechnic|Conservatoire|Seminary)/i.test(title);
}

function isLikelyInstitutionListTitle(title: string, country: CountryOption) {
  if (!title || /^Category:/i.test(title)) return false;
  const lowered = title.toLowerCase();
  const countryName = country.name.toLowerCase();
  return (
    lowered.includes(countryName) &&
    (/^list of .*universit/.test(lowered) ||
      /^list of .*college/.test(lowered) ||
      /institutions of higher education/.test(lowered) ||
      /universities and colleges/.test(lowered))
  );
}

function countryCategoryCandidates(country: CountryOption) {
  return [
    `Category:Universities in ${country.name}`,
    `Category:Colleges in ${country.name}`,
    `Category:Universities and colleges in ${country.name}`,
    `Category:Higher education in ${country.name}`,
  ];
}

function searchQueries(country: CountryOption) {
  return [
    `intitle:University "${country.name}"`,
    `intitle:College "${country.name}"`,
    `intitle:Institute "${country.name}"`,
    `"universities in ${country.name}"`,
    `"colleges in ${country.name}"`,
  ];
}

export async function discoverInstitutionTitles(country: CountryOption, limit: number) {
  const listPage = await discoverCountryListPage(country);
  const seen = new Set<string>();
  const titles: string[] = [];

  function addTitle(title: string) {
    if (!isLikelyInstitutionTitle(title) || seen.has(title) || titles.length >= limit) return;
    seen.add(title);
    titles.push(title);
  }

  async function collectFromListPage(pageTitle: string) {
    const parsed = await parsePage(pageTitle, "links|text");
    const sublists: string[] = [];
    const categories: string[] = [];
    for (const title of extractInstitutionTitlesFromTables(parsed.parse?.text?.["*"] ?? "")) {
      addTitle(title);
      if (titles.length >= limit) break;
    }
    for (const link of parsed.parse?.links ?? []) {
      const title = link["*"];
      if (isLikelyInstitutionTitle(title)) addTitle(title);
      else if (isLikelyInstitutionListTitle(title, country)) sublists.push(title);
      else if (/^Category:/i.test(title) && /universit|college|higher education|school/i.test(title)) categories.push(title);
      if (titles.length >= limit) break;
    }
    return { sublists, categories };
  }

  const relatedLists = new Set<string>();
  const relatedCategories = new Set<string>(countryCategoryCandidates(country));
  const root = await collectFromListPage(listPage);
  root.sublists.slice(0, 10).forEach((title) => relatedLists.add(title));
  root.categories.slice(0, 12).forEach((title) => relatedCategories.add(title));

  for (const pageTitle of relatedLists) {
    if (titles.length >= limit) break;
    const result = await collectFromListPage(pageTitle).catch(() => ({ sublists: [], categories: [] }));
    result.categories.slice(0, 8).forEach((title) => relatedCategories.add(title));
  }

  for (const categoryTitle of relatedCategories) {
    if (titles.length >= limit) break;
    const members = await categoryMembers(categoryTitle, Math.min(100, limit * 2)).catch(() => []);
    for (const member of members) {
      if (member.ns === 0) addTitle(member.title);
      if (member.ns === 14 && /universit|college|institute|school/i.test(member.title)) {
        const nested = await categoryMembers(member.title, Math.min(60, limit)).catch(() => []);
        nested.filter((entry) => entry.ns === 0).forEach((entry) => addTitle(entry.title));
      }
      if (titles.length >= limit) break;
    }
  }

  for (const query of searchQueries(country)) {
    if (titles.length >= limit) break;
    const results = await searchPages(query, Math.min(50, limit)).catch(() => []);
    results.forEach(addTitle);
  }

  return { listPage, titles, discoveredCount: titles.length };
}

export async function fetchInstitutionEvidence(title: string) {
  const [summary, parsed] = await Promise.all([
    pageSummary(title).catch((): SummaryResponse => ({ title, extract: "", content_urls: { desktop: { page: "" } } })),
    parsePage(title, "text|externallinks|pageprops"),
  ]);
  return {
    title: parsed.parse?.title || summary.title || title,
    extract: summary.extract || "",
    wikipediaUrl: summary.content_urls?.desktop?.page || `https://en.wikipedia.org/wiki/${encodeURIComponent(title.replace(/ /g, "_"))}`,
    externalLinks: parsed.parse?.externallinks ?? [],
    wikidataId: parsed.parse?.pageprops?.wikibase_item,
    html: parsed.parse?.text?.["*"] ?? "",
    infobox: parseInfoboxFacts(parsed.parse?.text?.["*"] ?? ""),
  };
}
