from worker.digest.models import Paper
from worker.digest.scoring import dedupe_papers, rank_papers, score_paper


def make_paper(title: str, doi: str = "", abstract: str = "", venue: str = "", date: str = "2026-11-01") -> Paper:
    return Paper(title=title, doi=doi, abstract=abstract, venue=venue, date=date, source="crossref")


def test_diamond_neutron_paper_scores_higher_than_unrelated():
    relevant = make_paper(
        "Multi-channel sCVD diamond detector array for DT fusion neutron spectroscopy at a tokamak",
        doi="10.1/x",
        abstract="Radiation-hard diamond detectors for 14 MeV neutron time-of-flight diagnostics.",
        venue="Nuclear Fusion",
    )
    unrelated = make_paper("A study of lattice vibrations in perovskite oxides", doi="10.2/y", abstract="Phonon dispersion.")
    assert score_paper(relevant) > score_paper(unrelated)


def test_dedupe_by_doi_and_title():
    a = make_paper("Diamond Neutron Detector!", doi="10.1/ABC")
    b = make_paper("diamond neutron detector", doi="10.1/abc")
    c = make_paper("Diamond Neutron Detector", doi="")
    d = make_paper("Other paper", doi="10.9/z")
    assert len(dedupe_papers([a, b, c, d])) == 2


def test_rank_papers_respects_max_and_orders_by_score():
    papers = [
        make_paper("unrelated", doi="10.1/u", date="2026-11-05"),
        make_paper("diamond neutron detector fusion tokamak", doi="10.1/r", date="2026-10-30"),
    ]
    ranked = rank_papers(papers, max_papers=1)
    assert len(ranked) == 1
    assert ranked[0].doi == "10.1/r"
