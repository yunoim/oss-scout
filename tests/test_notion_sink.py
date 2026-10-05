from __future__ import annotations

from scout.sinks.notion import NotionSink


class _DS:
    def __init__(self, pages):
        self.pages = pages

    def query(self, _id, **_kw):
        return {"results": self.pages, "has_more": False}


class _Client:
    def __init__(self, pages):
        self.data_sources = _DS(pages)


def _page(name, status):
    return {"id": name, "properties": {"Name": {"title": [{"plain_text": name}]}, "Status": {"select": {"name": status}}}}


def test_fetch_statuses_keeps_github_case():
    # W41: lowercased keys let a Rejected mixed-case repo (vas3k/TaxHacker) back into the Top 15
    sink = object.__new__(NotionSink)
    sink.client = _Client([_page("vas3k/TaxHacker", "Rejected"), _page("bagisto/bagisto", "Rejected")])
    sink.data_source_id = "ds"
    statuses = sink.fetch_statuses()
    assert statuses == {"vas3k/TaxHacker": "Rejected", "bagisto/bagisto": "Rejected"}
    assert sink._pages["vas3k/taxhacker"]["id"] == "vas3k/TaxHacker"  # lookup stays case-insensitive
