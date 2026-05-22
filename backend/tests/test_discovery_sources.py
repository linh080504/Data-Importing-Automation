from types import SimpleNamespace

from app.services.discovery_sources import fetch_discovery_bundle_from_source
from app.services.supplemental_registry import resolve_supplemental_coverage_plan


def test_fetch_discovery_bundle_from_unirank_ranking_html(monkeypatch) -> None:
    html = '''
    <html><body>
      <a href="/vn/uni/example-university/">Example University</a>
      <a href="/vn/uni/another-university/">Another University</a>
    </body></html>
    '''

    monkeypatch.setattr("app.services.discovery_sources._request_text", lambda method, url: html)

    source = SimpleNamespace(
        id="src_unirank",
        source_name="uniRank Vietnam Rankings",
        config={
            "source_type": "official_catalog_html",
            "url": "https://www.unirank.org/vn/ranking/",
            "parser_variant": "ranking_html",
        },
    )

    bundle = fetch_discovery_bundle_from_source(source, country="Vietnam")

    assert len(bundle.rows) == 2
    assert bundle.rows[0].normalized["name"] == "Example University"
    assert bundle.rows[0].normalized.get("website") is None
    assert bundle.rows[0].normalized["source_url"] == "https://www.unirank.org/vn/uni/example-university/"
    assert bundle.rows[0].raw_payload["source_url"] == "https://www.unirank.org/vn/uni/example-university/"


def test_fetch_discovery_bundle_from_unirank_enriches_detail_and_official_site(monkeypatch) -> None:
    ranking_html = '''
    <html><body>
      <a href="/vn/uni/example-university/">Example University</a>
    </body></html>
    '''
    detail_html = '''
    <html><head>
      <meta name="description" content="Example University is a public university in Hanoi with engineering and science programs.">
    </head><body>
      <h1>Example University</h1>
      <a href="https://example.edu/">Official Website</a>
      <p>Location: Hanoi, Vietnam</p>
    </body></html>
    '''
    official_html = '''
    <html><body>
      <a href="/admissions">Admissions</a>
      <a href="/tuition">Tuition and fees</a>
      <a href="/housing">Housing</a>
      <p>Contact admissions@example.edu or +84 24 1234 5678 for admissions.</p>
      <p>Tuition fees are 18,000,000 VND per year for undergraduate programs.</p>
      <p>Student housing is available on campus.</p>
    </body></html>
    '''

    def fake_request_public_html(method, url, *, parser_variant, referer=None):
        if parser_variant == "ranking_html":
            return ranking_html
        if parser_variant == "ranking_detail_html":
            return detail_html
        raise AssertionError(f"Unexpected {parser_variant} {url}")

    monkeypatch.setattr("app.services.discovery_sources._request_public_html", fake_request_public_html)
    monkeypatch.setattr("app.services.discovery_sources._request_official_html", lambda url, referer=None: official_html)

    source = SimpleNamespace(
        id="src_unirank",
        source_name="uniRank Vietnam Rankings",
        config={
            "source_type": "official_catalog_html",
            "url": "https://www.unirank.org/vn/ranking/",
            "parser_variant": "ranking_html",
            "enrich_detail_pages": True,
            "enrich_official_site": True,
            "max_detail_pages": 1,
            "max_official_sites": 1,
        },
    )

    bundle = fetch_discovery_bundle_from_source(source, country="Vietnam", focus_fields=["financials", "housing_availability"])

    row = bundle.rows[0].normalized
    assert row["website"] == "https://example.edu/"
    assert row.get("location") is None
    assert row["description"].startswith("Example University is a public university")
    assert row["admissions_contact"] == "admissions@example.edu"
    assert row["admissions_phone"] == "+84 24 1234 5678"
    assert "18,000,000 VND per year" in row["financials"]
    assert row["housing_availability"] is True


def test_official_site_enrichment_rejects_generic_financials_and_placeholder_phone(monkeypatch) -> None:
    from app.services.discovery_sources import _enrich_with_official_site

    official_html = '''
    <html><body>
      <a href="/admissions">Admissions</a>
      <a href="/tuition">Tuition and fees</a>
      <p>Admissions phone: 123456</p>
      <p>Tuition fees vary by program and are published annually.</p>
    </body></html>
    '''

    monkeypatch.setattr("app.services.discovery_sources._request_official_html", lambda url, referer=None: official_html)

    row = {"website": "https://example.edu/"}
    _enrich_with_official_site(row)

    assert row.get("admissions_phone") is None
    assert row.get("financials") is None


def test_fetch_discovery_bundle_from_wikipedia_list_html_filters_navigation(monkeypatch) -> None:
    html = '''
    <html><body>
      <div id="mw-content-text">
        <a href="/wiki/Main_Page">Main page</a>
        <a href="/wiki/List_of_universities_in_Vietnam">List of universities in Vietnam</a>
        <a href="/wiki/Example_University">Example University</a>
        <a href="/wiki/Another_University">Another University</a>
        <a href="/wiki/Category:Universities_in_Vietnam">Universities in Vietnam category</a>
        <a href="#cite_note-1">citation needed</a>
      </div>
    </body></html>
    '''

    monkeypatch.setattr("app.services.discovery_sources._request_text", lambda method, url: html)

    source = SimpleNamespace(
        id="src_wikipedia",
        source_name="Wikipedia Vietnam Universities",
        config={
            "source_type": "official_catalog_html",
            "url": "https://en.wikipedia.org/wiki/List_of_universities_in_Vietnam",
            "parser_variant": "wikipedia_list_html",
        },
    )

    bundle = fetch_discovery_bundle_from_source(source, country="Vietnam")

    assert [row.normalized["name"] for row in bundle.rows] == ["Example University", "Another University"]
    assert bundle.rows[0].normalized.get("website") is None
    assert bundle.rows[0].normalized["source_url"] == "https://en.wikipedia.org/wiki/Example_University"
    assert bundle.rows[0].unique_key == "https://en.wikipedia.org/wiki/Example_University"


def test_fetch_discovery_bundle_from_wikipedia_list_html_reads_table_rows_without_article_links(monkeypatch) -> None:
    html = '''
    <html><body>
      <div id="mw-content-text">
        <table class="wikitable">
          <tr><th>No.</th><th>Location</th><th>English name</th><th>Vietnamese name</th></tr>
          <tr>
            <td>1</td>
            <td>Hanoi</td>
            <td>Vietnam Aviation Academy</td>
            <td>Hoc vien Hang khong Viet Nam</td>
          </tr>
          <tr>
            <td>2</td>
            <td>Hanoi</td>
            <td><a href="./Hanoi_University_of_Science_and_Technology">Hanoi University of Science and Technology</a></td>
            <td>Dai hoc Bach khoa Ha Noi</td>
          </tr>
        </table>
      </div>
    </body></html>
    '''

    monkeypatch.setattr("app.services.discovery_sources._request_text", lambda method, url: html)

    source = SimpleNamespace(
        id="src_wikipedia",
        source_name="Wikipedia Vietnam Universities",
        config={
            "source_type": "official_catalog_html",
            "url": "https://en.wikipedia.org/wiki/List_of_universities_in_Vietnam",
            "parser_variant": "wikipedia_list_html",
        },
    )

    bundle = fetch_discovery_bundle_from_source(source, country="Vietnam")

    names = [row.normalized["name"] for row in bundle.rows]
    assert "Vietnam Aviation Academy" in names
    assert "Hanoi University of Science and Technology" in names
    aviation_row = next(row for row in bundle.rows if row.normalized["name"] == "Vietnam Aviation Academy")
    assert aviation_row.normalized.get("location") is None
    assert aviation_row.unique_key.endswith("#vietnam-aviation-academy")


def test_fetch_discovery_bundle_from_wikipedia_table_keeps_numeric_location_code(monkeypatch) -> None:
    html = '''
    <html><body>
      <div id="mw-content-text">
        <table class="wikitable">
          <tr><th>English name</th><th>Location</th></tr>
          <tr><td>Example University</td><td>356</td></tr>
        </table>
      </div>
    </body></html>
    '''

    monkeypatch.setattr("app.services.discovery_sources._request_text", lambda method, url: html)

    source = SimpleNamespace(
        id="src_wikipedia",
        source_name="Wikipedia Vietnam Universities",
        config={
            "source_type": "official_catalog_html",
            "url": "https://en.wikipedia.org/wiki/List_of_universities_in_Vietnam",
            "parser_variant": "wikipedia_list_html",
        },
    )

    bundle = fetch_discovery_bundle_from_source(source, country="Vietnam")

    assert bundle.rows[0].normalized["name"] == "Example University"
    assert bundle.rows[0].normalized["location"] == 356


def test_fetch_discovery_bundle_from_wikipedia_country_index_resolves_country_page(monkeypatch) -> None:
    index_html = '''
    <html><body>
      <div id="mw-content-text">
        <a href="./List_of_universities_in_Canada">Canada</a>
        <a href="./List_of_universities_in_Vietnam">Vietnam</a>
      </div>
    </body></html>
    '''
    list_html = '''
    <html><body>
      <div id="mw-content-text">
        <a href="./List_of_universities_and_colleges_in_Macau">Macau</a>
        <a href="./List_of_universities_in_Hong_Kong">Hong Kong</a>
        <a href="./Vietnam_National_University,_Hanoi">Vietnam National University, Hanoi</a>
        <a href="./Can_Tho_University">Can Tho University</a>
      </div>
    </body></html>
    '''
    requested_urls: list[str] = []

    def fake_request_text(method, url):
        requested_urls.append(url)
        if url.endswith("Lists_of_universities_and_colleges_by_country"):
            return index_html
        if url.endswith("List_of_universities_in_Vietnam"):
            return list_html
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("app.services.discovery_sources._request_text", fake_request_text)

    source = SimpleNamespace(
        id="src_wikipedia_index",
        source_name="Wikipedia universities by country index",
        config={
            "source_type": "official_catalog_html",
            "url": "https://en.wikipedia.org/wiki/Lists_of_universities_and_colleges_by_country",
            "parser_variant": "wikipedia_country_index_html",
        },
    )

    bundle = fetch_discovery_bundle_from_source(source, country="Vietnam")

    assert requested_urls == [
        "https://en.wikipedia.org/wiki/Lists_of_universities_and_colleges_by_country",
        "https://en.wikipedia.org/wiki/List_of_universities_in_Vietnam",
    ]
    assert [row.normalized["name"] for row in bundle.rows] == ["Vietnam National University, Hanoi", "Can Tho University"]
    assert bundle.rows[0].normalized["source_url"] == "https://en.wikipedia.org/wiki/Vietnam_National_University,_Hanoi"
    assert bundle.rows[0].normalized.get("website") is None


def test_fetch_discovery_bundle_from_wikipedia_country_index_enriches_article_and_official_site(monkeypatch) -> None:
    index_html = '''
    <html><body>
      <div id="mw-content-text">
        <a href="./List_of_universities_in_Vietnam">Vietnam</a>
      </div>
    </body></html>
    '''
    list_html = '''
    <html><body>
      <div id="mw-content-text">
        <a href="./Hanoi_University_of_Science_and_Technology">Hanoi University of Science and Technology</a>
      </div>
    </body></html>
    '''
    article_html = '''
    <html><body>
      <h1>Hanoi University of Science and Technology</h1>
      <table class="infobox vcard">
        <tr><th>Location</th><td>Hanoi, Vietnam</td></tr>
        <tr><th>Website</th><td><a href="https://hust.edu.vn/">hust.edu.vn</a></td></tr>
        <tr><th>Students</th><td>35,000</td></tr>
        <tr><th>Campus</th><td>Urban</td></tr>
      </table>
      <div id="mw-content-text">
        <p>Hanoi University of Science and Technology is a public technical university in Hanoi, Vietnam.</p>
      </div>
    </body></html>
    '''
    official_html = '''
    <html><body>
      <a href="/admissions">Admissions</a>
      <a href="/tuition-and-fees">Tuition and fees</a>
      <p>Contact admissions@hust.edu.vn or +84 24 3869 4242 for admissions.</p>
      <p>Tuition fees range from 22,000,000 to 28,000,000 VND per year.</p>
    </body></html>
    '''

    def fake_request_public_html(method, url, *, parser_variant, referer=None):
        if url.endswith("Lists_of_universities_and_colleges_by_country"):
            return index_html
        if url.endswith("List_of_universities_in_Vietnam"):
            return list_html
        if url.endswith("Hanoi_University_of_Science_and_Technology"):
            return article_html
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("app.services.discovery_sources._request_public_html", fake_request_public_html)
    monkeypatch.setattr("app.services.discovery_sources._request_official_html", lambda url, referer=None: official_html)

    source = SimpleNamespace(
        id="src_wikipedia_index",
        source_name="Wikipedia universities by country index",
        config={
            "source_type": "official_catalog_html",
            "url": "https://en.wikipedia.org/wiki/Lists_of_universities_and_colleges_by_country",
            "parser_variant": "wikipedia_country_index_html",
            "enrich_detail_pages": True,
            "enrich_official_site": True,
            "max_official_sites": 1,
        },
    )

    bundle = fetch_discovery_bundle_from_source(source, country="Vietnam")

    row = bundle.rows[0]
    assert row.normalized["name"] == "Hanoi University of Science and Technology"
    assert row.normalized.get("location") is None
    assert row.normalized["website"] == "https://hust.edu.vn/"
    assert row.normalized["number_of_students"] == "35,000"
    assert row.normalized["university_campuses"] == "Urban"
    assert row.normalized["admissions_page_link"] == "https://hust.edu.vn/admissions"
    assert row.normalized["admissions_contact"] == "admissions@hust.edu.vn"
    assert row.normalized["admissions_phone"] == "+84 24 3869 4242"
    assert "22,000,000 to 28,000,000 VND per year" in row.normalized["financials"]
    assert row.normalized["wikipedia_article_url"] == "https://en.wikipedia.org/wiki/Hanoi_University_of_Science_and_Technology"


def test_fetch_discovery_bundle_from_qs_rankings_json_filters_country_and_keeps_evidence_url(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.discovery_sources._request_json",
        lambda method, url, **kwargs: {
            "data": [
                {
                    "country": "Vietnam",
                    "city": "Hanoi",
                    "region": "Asia",
                    "rank_display": "801-1000",
                    "score": "",
                    "title": '<div><a href="/universities/vietnam-national-university-hanoi">Vietnam National University, Hanoi</a></div>',
                },
                {
                    "country": "Singapore",
                    "city": "Singapore",
                    "region": "Asia",
                    "rank_display": "8",
                    "score": "95.9",
                    "title": '<div><a href="/universities/national-university-singapore-nus">National University of Singapore (NUS)</a></div>',
                },
            ]
        },
    )

    source = SimpleNamespace(
        id="src_qs",
        source_name="QS World University Rankings",
        config={
            "source_type": "qs_rankings_json",
            "url": "https://www.topuniversities.com/world-university-rankings",
            "reference_url": "https://www.topuniversities.com/world-university-rankings",
            "data_url": "https://www.topuniversities.com/sites/default/files/qs-rankings-data/en/3740566.txt",
        },
    )

    bundle = fetch_discovery_bundle_from_source(source, country="Vietnam")

    assert len(bundle.rows) == 1
    row = bundle.rows[0]
    assert row.normalized["name"] == "Vietnam National University, Hanoi"
    assert row.normalized["city"] == "Hanoi"
    assert row.normalized["global_rank"] == "801-1000"
    assert row.normalized["rank_display"] == "801-1000"
    assert row.normalized["source_url"] == "https://www.topuniversities.com/universities/vietnam-national-university-hanoi"
    assert row.normalized["reference_url"] == "https://www.topuniversities.com/world-university-rankings"
    assert row.normalized.get("website") is None


def test_fetch_discovery_bundle_from_hemis_public_directory(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.discovery_sources._request_json",
        lambda method, url, **kwargs: {
            "success": True,
            "data": [
                {
                    "id": "hemis_1",
                    "teN_DON_VI": "ĐẠI HỌC BÁCH KHOA HÀ NỘI",
                    "teN_TIENG_ANH": "Ha Noi University of Science and Technology",
                    "website": "https://hust.edu.vn/",
                    "tinH_THANH_ID": "01",
                }
            ],
        },
    )

    source = resolve_supplemental_coverage_plan("Vietnam")[0]
    bundle = fetch_discovery_bundle_from_source(SimpleNamespace(id=source["id"], source_name=source["name"], config=source["config"]), country="Vietnam")

    assert source["config"]["method"] == "POST"
    assert source["config"]["body"] == {}
    assert isinstance(source["config"].get("headers"), dict)
    assert len(bundle.rows) == 1
    assert bundle.rows[0].unique_key == "hemis_1"
    assert bundle.rows[0].normalized["name"] == "ĐẠI HỌC BÁCH KHOA HÀ NỘI"
    assert bundle.rows[0].normalized["website"] == "https://hust.edu.vn/"
    assert bundle.rows[0].raw_text == "ĐẠI HỌC BÁCH KHOA HÀ NỘI"
