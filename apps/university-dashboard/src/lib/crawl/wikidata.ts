import { fetchJson } from "@/lib/crawl/http";

interface WikidataEntityResponse {
  entities: Record<
    string,
    {
      claims?: Record<
        string,
        Array<{
          mainsnak?: {
            datavalue?: {
              value?: unknown;
            };
          };
        }>
      >;
    }
  >;
}

function claimValues(entity: WikidataEntityResponse["entities"][string] | undefined, property: string) {
  return entity?.claims?.[property]?.map((claim) => claim.mainsnak?.datavalue?.value).filter(Boolean) ?? [];
}

export async function fetchWikidataFacts(wikidataId?: string) {
  if (!wikidataId) return { officialWebsite: "", inceptionYear: "", studentCount: "" };
  const data = await fetchJson<WikidataEntityResponse>(`https://www.wikidata.org/wiki/Special:EntityData/${wikidataId}.json`);
  const entity = data.entities[wikidataId];
  const officialWebsite = String(claimValues(entity, "P856")[0] ?? "");
  const inceptionRaw = claimValues(entity, "P571")[0] as { time?: string } | undefined;
  const inceptionYear = inceptionRaw?.time?.match(/\d{4}/)?.[0] ?? "";
  const studentCount = String(claimValues(entity, "P2196")[0] ?? "");
  return { officialWebsite, inceptionYear, studentCount };
}
