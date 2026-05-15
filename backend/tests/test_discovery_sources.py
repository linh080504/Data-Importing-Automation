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
    assert bundle.rows[0].normalized["website"] == "https://www.unirank.org/vn/uni/example-university/"


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
    assert bundle.rows[0].normalized["website"] == "https://en.wikipedia.org/wiki/Example_University"
    assert bundle.rows[0].unique_key == "https://en.wikipedia.org/wiki/Example_University"


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
