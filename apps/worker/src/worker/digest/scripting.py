import json
import re

from worker.digest.models import DigestInput, NewsItem, Paper, ScriptDoc, ScriptSegment

SCRIPT_MODEL = "mistral-large-latest"

SYSTEM_PROMPT = """You are the writer of a science podcast aimed at a PhD researcher in fusion plasma physics whose thesis is on neutron diagnostic measurements using synthetic (CVD) diamond detectors.

The episode has two parts:
1. A LIGHT introduction (about 3-4 minutes when spoken) covering the most important general nuclear fusion news of the period. Conversational, accessible, no jargon dumps.
2. A DEEP DIVE (the rest of the episode) into each scientific paper provided, at PhD level. For every paper cover: (a) motivation and context within fusion neutron diagnostics; (b) the detector physics - e.g. CVD diamond properties (5.5 eV bandgap, high carrier mobility, radiation hardness), charge collection, the 12C(n,alpha)9Be reaction at ~5.7 MeV threshold for fast-neutron spectroscopy, proton recoil, time-of-flight, pulse-height analysis; (c) experimental or simulation methodology; (d) key quantitative results; (e) limitations and systematic uncertainties; (f) why it matters for the listener's PhD work and what to follow up on.

Format: a dialogue between two speakers. "host" asks questions and keeps the light intro; "expert" gives the deep technical answers. Alternate naturally. Target the requested total length. Write for the ear: no bullet points, no markdown, no citations brackets in the spoken text - speak URLs only if essential, otherwise say "the link is in the show notes".

Respond with ONLY a JSON object of the form:
{
  "episode_title": "...",
  "segments": [{"speaker": "host"|"expert", "text": "..."}, ...],
  "transcript_md": "full markdown transcript with headings, paper list with DOIs/URLs, and news list with links"
}
"""


def build_user_prompt(papers: list[Paper], news: list[NewsItem], inp: DigestInput) -> str:
    papers_payload = [
        {
            "title": p.title,
            "authors": p.authors[:8],
            "venue": p.venue,
            "date": p.date,
            "doi": p.doi,
            "url": p.url,
            "source": p.source,
            "abstract": p.abstract[:2000],
        }
        for p in papers
    ]
    news_payload = [
        {
            "title": n.title,
            "source": n.source,
            "url": n.url,
            "published": n.published,
            "summary": n.summary,
        }
        for n in news
    ]
    return (
        f"Produce this week's episode in {inp.language}. Target total length: about {inp.target_minutes} minutes. "
        f"Cover up to {len(news)} news items in the light intro (pick the most important 3-5) and deep-dive into ALL "
        f"{len(papers)} papers below, roughly {max(2, inp.target_minutes - 4)}/{len(papers) if papers else 1} minutes per paper.\n\n"
        f"NEWS (last {inp.days_back} days):\n{json.dumps(news_payload, indent=2, ensure_ascii=False)}\n\n"
        f"PAPERS (most relevant first):\n{json.dumps(papers_payload, indent=2, ensure_ascii=False)}\n\n"
        "Return ONLY the JSON object."
    )


def parse_script_json(content: str) -> ScriptDoc:
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found in script response")
    data = json.loads(match.group(0))
    segments = []
    for seg in data.get("segments", []):
        speaker = str(seg.get("speaker", "host")).lower()
        if speaker not in ("host", "expert"):
            speaker = "expert" if speaker not in ("host",) else "host"
        text = str(seg.get("text", "")).strip()
        if text:
            segments.append(ScriptSegment(speaker=speaker, text=text))
    if not segments:
        raise ValueError("script response contained no segments")
    transcript = str(data.get("transcript_md") or "").strip()
    if not transcript:
        lines = [f"# {data.get('episode_title', 'Fusion Digest Episode')}", ""]
        for seg in segments:
            lines.append(f"**{seg.speaker.title()}:** {seg.text}")
            lines.append("")
        transcript = "\n".join(lines)
    return ScriptDoc(
        episode_title=str(data.get("episode_title") or "Fusion Digest Episode"),
        segments=segments,
        transcript_md=transcript,
    )


async def generate_script(client, papers: list[Paper], news: list[NewsItem], inp: DigestInput) -> ScriptDoc:
    response = await client.chat.complete_async(
        model=SCRIPT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(papers, news, inp)},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
        max_tokens=16000,
    )
    content = response.choices[0].message.content or ""
    if isinstance(content, list):
        content = " ".join(str(c.get("text", "")) if isinstance(c, dict) else str(c) for c in content)
    return parse_script_json(content)
