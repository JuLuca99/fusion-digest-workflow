import re

from worker.digest.models import Paper

KEYWORD_WEIGHTS: dict[str, float] = {
    "diamond": 3.0,
    "scvd": 2.5,
    "pcvd": 2.0,
    "single-crystal diamond": 2.5,
    "single crystal diamond": 2.5,
    "cvd": 1.5,
    "neutron": 3.0,
    "14 mev": 1.5,
    "time-of-flight": 1.5,
    "time of flight": 1.5,
    "proton recoil": 1.5,
    "charged particle": 1.0,
    "detector": 2.0,
    "diagnostic": 2.0,
    "spectrometer": 1.5,
    "spectroscopy": 1.5,
    "spectrometric": 1.5,
    "fusion": 2.0,
    "tokamak": 2.0,
    "stellarator": 2.0,
    "iter": 1.5,
    "jet": 1.0,
    "w7-x": 1.5,
    "west": 1.0,
    "kstar": 1.0,
    "demo": 1.0,
    "plasma": 1.0,
    "calibration": 1.0,
    "radiation hardness": 1.5,
    "radiation-hard": 1.5,
    "charge collection": 1.5,
    "pulse height": 1.0,
}

FUSION_VENUES = {
    "nuclear fusion",
    "plasma physics and controlled fusion",
    "fusion engineering and design",
    "review of scientific instruments",
    "ieee transactions on nuclear science",
    "journal of instrumentation",
    "nuclear instruments and methods",
}


def score_text(text: str) -> float:
    lowered = text.lower()
    return sum(weight for kw, weight in KEYWORD_WEIGHTS.items() if kw in lowered)


def score_paper(paper: Paper) -> float:
    score = 3.0 * score_text(paper.title) + score_text(paper.abstract)
    if paper.venue.strip().lower() in FUSION_VENUES:
        score += 2.0
    return score


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def dedupe_papers(papers: list[Paper]) -> list[Paper]:
    seen_dois: set[str] = set()
    seen_titles: set[str] = set()
    result: list[Paper] = []
    for paper in papers:
        doi = paper.doi.strip().lower()
        title = normalize_title(paper.title)
        if doi and doi in seen_dois:
            continue
        if not doi and title in seen_titles:
            continue
        if doi:
            seen_dois.add(doi)
        seen_titles.add(title)
        result.append(paper)
    return result


def rank_papers(papers: list[Paper], max_papers: int) -> list[Paper]:
    for paper in papers:
        paper.score = score_paper(paper)
    ranked = sorted(papers, key=lambda p: (p.score, p.date), reverse=True)
    return ranked[:max_papers]
