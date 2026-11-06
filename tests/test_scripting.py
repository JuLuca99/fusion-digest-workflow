import json

from worker.digest.models import DigestInput, NewsItem, Paper
from worker.digest.scripting import build_user_prompt, parse_script_json


def sample_papers():
    return [Paper(title="Diamond neutron detector for JET", doi="10.1/a", abstract="abstract", source="crossref")]


def test_parse_script_json_plain():
    payload = {
        "episode_title": "Episode 1",
        "segments": [
            {"speaker": "host", "text": "Welcome!"},
            {"speaker": "expert", "text": "Today we discuss diamond detectors."},
        ],
        "transcript_md": "# Episode 1",
    }
    doc = parse_script_json(json.dumps(payload))
    assert doc.episode_title == "Episode 1"
    assert [s.speaker for s in doc.segments] == ["host", "expert"]


def test_parse_script_json_with_surrounding_text():
    payload = {"episode_title": "E", "segments": [{"speaker": "host", "text": "Hi"}], "transcript_md": "md"}
    doc = parse_script_json("Sure! Here is the JSON:\n" + json.dumps(payload) + "\nHope that helps.")
    assert doc.segments[0].text == "Hi"


def test_parse_script_json_builds_transcript_when_missing():
    payload = {"episode_title": "E", "segments": [{"speaker": "expert", "text": "Deep dive."}]}
    doc = parse_script_json(json.dumps(payload))
    assert "Deep dive." in doc.transcript_md


def test_parse_script_json_rejects_empty():
    import pytest

    with pytest.raises(ValueError):
        parse_script_json("no json at all")


def test_build_user_prompt_contains_papers_and_constraints():
    news = [NewsItem(title="ITER news", source="iter.org", url="https://iter.org", published="2026-11-05")]
    prompt = build_user_prompt(sample_papers(), news, DigestInput(days_back=7, target_minutes=18))
    assert "Diamond neutron detector for JET" in prompt
    assert "ITER news" in prompt
    assert "18 minutes" in prompt
