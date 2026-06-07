import { describe, expect, it } from "vitest";
import { parseInfoboxFacts } from "@/lib/crawl/mediawiki";

describe("MediaWiki HTML parsing", () => {
  it("extracts useful CSV facts from university infobox HTML", () => {
    const html = `
      <table class="infobox vcard">
        <caption class="infobox-title fn org">Hanoi National University of Education</caption>
        <tbody>
          <tr><th class="infobox-label">Type</th><td class="infobox-data">Public University</td></tr>
          <tr><th class="infobox-label">Established</th><td class="infobox-data">1951</td></tr>
          <tr><th class="infobox-label">President</th><td class="infobox-data">Nguyen Van Minh</td></tr>
          <tr><th class="infobox-label">Undergraduates</th><td class="infobox-data">3,000<sup>[1]</sup></td></tr>
          <tr><th class="infobox-label">Postgraduates</th><td class="infobox-data">1,500<sup>[1]</sup></td></tr>
          <tr><th class="infobox-label">Location</th><td class="infobox-data adr">Hanoi, Vietnam</td></tr>
          <tr><th class="infobox-label">Campus</th><td class="infobox-data">Urban<br>150&nbsp;ha</td></tr>
          <tr><th class="infobox-label">Website</th><td class="infobox-data"><a rel="nofollow" class="external text" href="http://english.hnue.edu.vn/">english.hnue.edu.vn</a></td></tr>
        </tbody>
      </table>
    `;
    const facts = parseInfoboxFacts(html);
    expect(facts.caption).toBe("Hanoi National University of Education");
    expect(facts.type).toBe("Public University");
    expect(facts.established).toBe("1951");
    expect(facts.president).toBe("Nguyen Van Minh");
    expect(facts.undergraduates).toBe("3000");
    expect(facts.postgraduates).toBe("1500");
    expect(facts.locationText).toBe("Hanoi, Vietnam");
    expect(facts.campus).toBe("Urban 150 ha");
    expect(facts.website).toBe("http://english.hnue.edu.vn/");
  });
});
