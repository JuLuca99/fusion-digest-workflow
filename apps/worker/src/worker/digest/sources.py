import asyncio
import json
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

from worker.digest.models import NewsItem, Paper
from worker.digest.scoring import dedupe_papers, rank_papers

USER_AGENT = "fusion-digest-workflow/0.1 (one-shot research digest; contact: workspace owner)"
HTTP_TIMEOUT = 45.0

ARXIV_API = "https://export.arxiv.org/api/query"
CROSSREF_API = "https://api.crossref.org/works"

ARXIV_QUERIES = [
    'cat:nucl-ex AND all:"diamond detector" AND all:neutron',
    'all:"diamond detector" AND all:neutron AND all:fusion',
    'all:"diamond" AND all:"neutron spectrometer"',
    'all:"single crystal diamond" AND all:neutron AND all:tokamak',
]

CROSSREF_QUERIES = [
    "diamond detector neutron diagnostics fusion plasma",
    "single crystal diamond detector neutron tokamak",
    "sCVD diamond neutron spectrometer fusion",
    "diamond detector array deuterium tritium neutron diagnostics",
    "CVD diamond neutron detector calibration fusion facility",
]

RSS_FEEDS = [
    ("phys.org", "https://phys.org/rss-feed/physics-news/"),
]

NEWS_KEYWORDS = (
    "fusion",
    "tokamak",
    "stellarator",
    "iter",
    "jet",
    "w7-x",
    "wendelstein",
    "plasma",
    "tritium",
    "deuterium",
    "q>1",
    "fusion energy",
    "fusion reactor",
    "fusion startup",
    "national ignition facility",
    "nif",
)

ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def _parse_date(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        dt = parsedate_to_datetime(raw)
        return dt.date().isoformat()
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return ""


def _crossref_date(item: dict) -> str:
    for key in ("published", "published-print", "published-online", "issued", "created"):
        parts = (item.get(key) or {}).get("date-parts")
        if parts and parts[0]:
            year, month, day = (parts[0] + [1, 1])[:3]
            return date(int(year), int(month), int(day)).isoformat()
    return ""


def _authors_from_crossref(item: dict) -> list[str]:
    authors = []
    for a in item.get("author", [])[:12]:
        name = " ".join(p for p in [a.get("given", ""), a.get("family", "")] if p).strip()
        if name:
            authors.append(name)
    return authors


async def fetch_crossref(since: date, rows: int = 30) -> list[Paper]:
    papers: list[Paper] = []
    async with _http_client() as client:
        for query in CROSSREF_QUERIES:
            params = {
                "query.bibliographic": query,
                "filter": f"from-pub-date:{since.isoformat()}",
                "rows": str(rows),
                "select": "DOI,title,author,published,published-print,published-online,issued,container-title,URL,abstract,type",
            }
            resp = await client.get(CROSSREF_API, params=params)
            resp.raise_for_status()
            items = resp.json().get("message", {}).get("items", [])
            for item in items:
                if item.get("type") not in ("journal-article", "proceedings-article", "book-chapter"):
                    continue
                titles = item.get("title") or []
                if not titles:
                    continue
                venue_list = item.get("container-title") or []
                abstract = re.sub(r"<[^>]+>", " ", item.get("abstract") or "")
                papers.append(
                    Paper(
                        title=titles[0].strip(),
                        authors=_authors_from_crossref(item),
                        venue=venue_list[0] if venue_list else "",
                        date=_crossref_date(item),
                        doi=(item.get("DOI") or "").lower(),
                        url=item.get("URL") or (f"https://doi.org/{item.get('DOI')}" if item.get("DOI") else ""),
                        abstract=" ".join(abstract.split())[:4000],
                        source="crossref",
                    )
                )
    return papers


def parse_arxiv(xml_text: str) -> list[Paper]:
    papers: list[Paper] = []
    root = ET.fromstring(xml_text)
    for entry in root.findall(f"{ATOM_NS}entry"):
        title = " ".join((entry.findtext(f"{ATOM_NS}title") or "").split())
        if not title:
            continue
        arxiv_id = (entry.findtext(f"{ATOM_NS}id") or "").rstrip("/").split("/abs/")[-1]
        summary = " ".join((entry.findtext(f"{ATOM_NS}summary") or "").split())
        published = _parse_date(entry.findtext(f"{ATOM_NS}published") or "")
        authors = [a.findtext(f"{ATOM_NS}name") or "" for a in entry.findall(f"{ATOM_NS}author")]
        doi = ""
        doi_el = entry.find(f"{ATOM_NS}doi")
        if doi_el is not None and doi_el.text:
            doi = doi_el.text.strip().lower()
        papers.append(
            Paper(
                title=title,
                authors=[a for a in authors if a][:12],
                venue="arXiv",
                date=published,
                doi=doi,
                url=f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
                abstract=summary[:4000],
                source="arxiv",
            )
        )
    return papers


async def fetch_arxiv(since: date, max_results: int = 50) -> list[Paper]:
    papers: list[Paper] = []
    async with _http_client() as client:
        for query in ARXIV_QUERIES:
            params = {
                "search_query": query,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": str(max_results),
            }
            resp = await client.get(ARXIV_API, params=params)
            resp.raise_for_status()
            papers.extend(parse_arxiv(resp.text))
    return papers


def parse_rss(xml_text: str, source: str) -> list[NewsItem]:
    items: list[NewsItem] = []
    root = ET.fromstring(xml_text)
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = _parse_date(item.findtext("pubDate") or "")
        description = " ".join((item.findtext("description") or "").split())
        description = re.sub(r"<[^>]+>", " ", description)
        if title:
            items.append(
                NewsItem(
                    title=title,
                    source=source,
                    url=link,
                    published=published,
                    summary=" ".join(description.split())[:800],
                )
            )
    for entry in root.findall(f".//{ATOM_NS}entry"):
        title = (entry.findtext(f"{ATOM_NS}title") or "").strip()
        link_el = entry.find(f"{ATOM_NS}link")
        link = link_el.get("href", "") if link_el is not None else ""
        published = _parse_date(entry.findtext(f"{ATOM_NS}published") or entry.findtext(f"{ATOM_NS}updated") or "")
        summary = " ".join((entry.findtext(f"{ATOM_NS}summary") or "").split())
        if title:
            items.append(NewsItem(title=title, source=source, url=link, published=published, summary=summary[:800]))
    return items


def is_fusion_related(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in NEWS_KEYWORDS)


async def fetch_rss_news(since: date) -> list[NewsItem]:
    items: list[NewsItem] = []
    async with _http_client() as client:
        for source, feed_url in RSS_FEEDS:
            try:
                resp = await client.get(feed_url)
                resp.raise_for_status()
                for item in parse_rss(resp.text, source):
                    if item.published and item.published < since.isoformat():
                        continue
                    if not is_fusion_related(f"{item.title} {item.summary}"):
                        continue
                    items.append(item)
            except Exception:
                continue
    return items


def parse_agent_news(content: str) -> list[NewsItem]:
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    items: list[NewsItem] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        if not title:
            continue
        items.append(
            NewsItem(
                title=title,
                source=str(entry.get("source") or "web search"),
                url=str(entry.get("url") or ""),
                published=_parse_date(str(entry.get("published") or "")),
                summary=str(entry.get("summary") or "")[:800],
            )
        )
    return items


async def fetch_web_news(client, since: date, days_back: int, max_news: int) -> list[NewsItem]:
    agent = await client.beta.agents.create_async(
        model="mistral-large-latest",
        name="fusion-news-scout",
        description="Finds the latest nuclear fusion news stories.",
        instructions=(
            "You search the web for the most important nuclear fusion news. "
            "Always use the web_search tool; do not rely on your own knowledge. "
            "Return ONLY a JSON array of objects with keys: title, source, url, published (ISO date), summary (max 3 sentences)."
        ),
        tools=[{"type": "web_search"}],
    )
    try:
        prompt = (
            f"Today is {datetime.now(timezone.utc).date().isoformat()}. Using web search, list the {max_news} most "
            f"important and recent nuclear fusion news stories from the last {days_back} days (since {since.isoformat()}). "
            "Cover major experiments and facilities (ITER, JET, W7-X, JT-60SA, EAST, KSTAR, NIF, SPARC, etc.), "
            "private fusion companies, policy/funding, and notable scientific results. "
            "Prefer primary sources and reputable outlets. Return ONLY the JSON array."
        )
        response = await client.agents.complete_async(
            agent_id=agent.id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
        )
        content = response.choices[0].message.content or ""
        if isinstance(content, list):
            content = " ".join(str(c.get("text", "")) if isinstance(c, dict) else str(c) for c in content)
        return parse_agent_news(content)
    finally:
        try:
            await client.beta.agents.delete_async(agent.id)
        except Exception:
            pass


async def fetch_papers(since: date, max_papers: int) -> tuple[list[Paper], list[str]]:
    warnings: list[str] = []
    results = await asyncio.gather(
        fetch_crossref(since), fetch_arxiv(since), return_exceptions=True
    )
    papers: list[Paper] = []
    for label, result in zip(("crossref", "arxiv"), results):
        if isinstance(result, Exception):
            warnings.append(f"{label} fetch failed: {type(result).__name__}")
        else:
            papers.extend(result)
    today = datetime.now(timezone.utc).date()
    recent = [p for p in papers if not p.date or since.isoformat() <= p.date <= (today + timedelta(days=1)).isoformat()]
    deduped = dedupe_papers(recent)
    ranked = rank_papers(deduped, max_papers)
    return ranked, warnings


async def fetch_news(client, since: date, days_back: int, max_news: int) -> tuple[list[NewsItem], list[str]]:
    warnings: list[str] = []
    rss_items = await fetch_rss_news(since)
    try:
        agent_items = await fetch_web_news(client, since, days_back, max_news)
    except Exception as exc:
        agent_items = []
        warnings.append(f"web-search news failed: {type(exc).__name__}")
    seen: set[str] = set()
    merged: list[NewsItem] = []
    for item in sorted(agent_items + rss_items, key=lambda i: i.published, reverse=True):
        key = re.sub(r"[^a-z0-9]+", " ", item.title.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        if item.published and item.published < since.isoformat():
            continue
        merged.append(item)
    return merged[:max_news], warnings
