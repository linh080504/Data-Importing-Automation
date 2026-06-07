import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("university_scrapling_crawler.py")
SPEC = importlib.util.spec_from_file_location("university_scrapling_crawler_tested", MODULE_PATH)
CRAWLER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CRAWLER
SPEC.loader.exec_module(CRAWLER)


class UniversityCrawlerTests(unittest.TestCase):
    def test_table_discovery_uses_name_column_only(self):
        html = """
        <div id="mw-content-text"><div>
          <table class="wikitable">
            <tr><th>No.</th><th>Name</th><th>Type of operation</th></tr>
            <tr>
              <td>1</td>
              <td><a href="/wiki/British_University_Vietnam" title="British University Vietnam">BUV</a></td>
              <td>
                Degrees awarded by
                <a href="/wiki/University_of_London" title="University of London">University of London</a>
                and <a href="/wiki/Staffordshire_University" title="Staffordshire University">Staffordshire University</a>
              </td>
            </tr>
          </table>
        </div></div>
        """
        links = CRAWLER.discover_links_from_html(
            html,
            "https://en.wikipedia.org/wiki/List_of_universities_in_Vietnam",
            20,
        )
        self.assertEqual(links, [("British University Vietnam", "https://en.wikipedia.org/wiki/British_University_Vietnam")])

    def test_country_validation_rejects_explicit_foreign_location(self):
        info = CRAWLER.Infobox(location_text="Stoke-on-Trent, United Kingdom")
        validation = CRAWLER.country_validation(
            info,
            {"name": "Vietnam"},
            "https://en.wikipedia.org/wiki/University_of_Staffordshire",
        )
        self.assertEqual(validation["status"], "rejected")

    def test_country_validation_accepts_vietnamese_city(self):
        info = CRAWLER.Infobox(location_text="Da Nang")
        validation = CRAWLER.country_validation(
            info,
            {"name": "Vietnam"},
            "https://en.wikipedia.org/wiki/University_of_Danang",
        )
        self.assertEqual(validation["status"], "verified")

    def test_same_official_site_accepts_redirect_scheme_and_subdomain(self):
        self.assertTrue(CRAWLER.same_official_site("http://dut.udn.vn", "https://en.dut.udn.vn/programs"))
        self.assertFalse(CRAWLER.same_official_site("https://dut.udn.vn", "https://stir.ac.uk/programs"))

    def test_vietnamese_academic_and_contact_links_are_discovered(self):
        body = """
        <html><body>
          <a href="/dao-tao/chuong-trinh">Chuong trinh dao tao</a>
          <a href="/tuyen-sinh">Tuyen sinh</a>
          <a href="https://partner.example/programs">Partner</a>
        </body></html>
        """
        links = CRAWLER.find_official_links(body, "https://example.edu.vn/", "https://example.edu.vn")
        self.assertIn("https://example.edu.vn/dao-tao/chuong-trinh", links)
        self.assertIn("https://example.edu.vn/tuyen-sinh", links)
        self.assertNotIn("https://partner.example/programs", links)


if __name__ == "__main__":
    unittest.main()
