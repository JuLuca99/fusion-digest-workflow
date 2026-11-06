from datetime import date

from worker.digest import sources
from worker.digest.models import NewsItem

ARXIV_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2611.00001v1</id>
    <title>  Diamond detector neutron spectroscopy at JET </title>
    <summary>We present a single crystal diamond detector for 14 MeV neutron measurements.</summary>
    <published>2026-11-02T10:00:00Z</published>
    <author><name>Jane Doe</name></author>
    <author><name>John Roe</name></author>
    <doi>10.48550/arxiv.2611.00001</doi>
  </entry>
</feed>
"""

RSS_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>t</title>
  <item>
    <title>ITER completes vacuum vessel sector assembly</title>
    <link>https://www.iter.org/news/123</link>
    <pubDate>Mon, 03 Nov 2026 09:00:00 EST</pubDate>
    <description>ITER &amp; tokamak milestone.</description>
  </item>
  <item>
    <title>Unrelated quantum computing story</title>
    <link>https://phys.org/news/999</link>
    <pubDate>Mon, 03 Nov 2026 08:00:00 EST</pubDate>
    <description>Qubits.</description>
  </item>
</channel></rss>
"""


def test_parse_arxiv_extracts_fields():
    papers = sources.parse_arxiv(ARXIV_SAMPLE)
    assert len(papers) == 1
    p = papers[0]
    assert p.title == "Diamond detector neutron spectroscopy at JET"
    assert p.date == "2026-11-02"
    assert p.authors == ["Jane Doe", "John Roe"]
    assert p.url == "https://arxiv.org/abs/2611.00001v1"
    assert p.source == "arxiv"


def test_parse_rss_extracts_items():
    items = sources.parse_rss(RSS_SAMPLE, "phys.org")
    assert len(items) == 2
    assert items[0].title.startswith("ITER completes")
    assert items[0].published == "2026-11-03"


def test_fusion_keyword_filter():
    assert sources.is_fusion_related("ITER tokamak reaches new plasma record")
    assert not sources.is_fusion_related("Unrelated quantum computing story about qubits")


def test_parse_agent_news_json():
    content = 'Here you go: [{"title": "W7-X record plasma", "source": "IPP", "url": "https://ipp.mpg.de/x", "published": "2026-11-05", "summary": "Long pulse."}] done'
    items = sources.parse_agent_news(content)
    assert len(items) == 1
    assert items[0].title == "W7-X record plasma"
    assert items[0].published == "2026-11-05"


def test_parse_agent_news_empty_on_garbage():
    assert sources.parse_agent_news("no json here") == []


async def test_fetch_papers_filters_old_entries(monkeypatch):
    async def fake_crossref(since, rows=30):
        from worker.digest.models import Paper

        return [
            Paper(title="diamond neutron detector tokamak fusion", doi="10.1/new", date="2026-11-04", source="crossref"),
            Paper(title="old diamond neutron paper", doi="10.2/old", date="2020-01-01", source="crossref"),
        ]

    async def fake_arxiv(since, max_results=50):
        return []

    monkeypatch.setattr(sources, "fetch_crossref", fake_crossref)
    monkeypatch.setattr(sources, "fetch_arxiv", fake_arxiv)
    papers, warnings = await sources.fetch_papers(date(2026, 10, 30), max_papers=5)
    assert warnings == []
    assert [p.doi for p in papers] == ["10.1/new"]


def test_news_item_model():
    item = NewsItem(title="t")
    assert item.source == ""
