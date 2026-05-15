from app.services.source_adapters.escaped_jsonld import load_escaped_jsonld_item_list


def test_load_escaped_jsonld_item_list_from_rendered_table(monkeypatch):
    html = """
    <html><body>
    <tr class="row clickableRow">
      <td></td>
      <td><div><div class="repoOwner">UEB</div><div class="repoName">Trường Đại học Kinh tế</div></div></td>
      <td><div class="descCellExpanded">Đại học công lập tại Hà Nội.</div></td>
      <td><span class="chip chipMuted">Công lập</span></td>
      <td><span class="chip">Kinh tế</span></td>
      <td><span class="chip chipMuted">Hà Nội</span></td>
    </tr>
    <script>self.__next_f.push([1,"\\\"position\\\":1,\\\"url\\\":\\\"https://example.test/truong/ueb\\\",\\\"name\\\":\\\"Trường Đại học Kinh tế\\\""])</script>
    </body></html>
    """

    class Response:
        text = html
        url = "https://example.test"

        def raise_for_status(self) -> None:
            return None

    def fake_get(*args, **kwargs):
        return Response()

    monkeypatch.setattr("app.services.source_adapters.escaped_jsonld.httpx.get", fake_get)

    rows = load_escaped_jsonld_item_list({"url": "https://example.test", "country": "Vietnam"})

    assert rows == [
        {
            "name": "Trường Đại học Kinh tế",
            "short_name": "UEB",
            "description": "Đại học công lập tại Hà Nội.",
            "type": "Công lập",
            "featured_major": "Kinh tế",
            "campuses": ["Hà Nội"],
            "website": "https://example.test/truong/ueb",
            "source_url": "https://example.test/truong/ueb",
            "country": "Vietnam",
            "position": 1,
            "evidence": {
                "source_page": "https://example.test",
                "parser": "rendered_table",
            },
        }
    ]
