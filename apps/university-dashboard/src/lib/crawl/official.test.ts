import { describe, expect, it } from "vitest";
import { firstOfficialUrl } from "@/lib/crawl/official";

describe("official site detection", () => {
  it("ignores GeoHack and map links when choosing official website", () => {
    expect(
      firstOfficialUrl([
        "https://geohack.toolforge.org/geohack.php?pagename=Vietnam_National_University",
        "https://www.openstreetmap.org/relation/123",
        "https://vnu.edu.vn",
      ]),
    ).toBe("https://vnu.edu.vn");
  });

  it("prefers Wikidata official website when present", () => {
    expect(firstOfficialUrl(["https://random-news.example/article"], "https://official.example.edu")).toBe("https://official.example.edu");
  });

  it("uses infobox official website before noisy external links", () => {
    expect(
      firstOfficialUrl(
        ["https://geohack.toolforge.org/geohack.php?pagename=HNUE"],
        "",
        "http://english.hnue.edu.vn/",
      ),
    ).toBe("http://english.hnue.edu.vn/");
  });
});
