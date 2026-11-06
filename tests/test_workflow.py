import uuid

from mistralai.workflows import testing

from worker.digest import scripting, sources, tts
from worker.digest.models import (
    AudioArtifact,
    DigestInput,
    NewsItem,
    Paper,
    ScriptDoc,
    ScriptSegment,
)
from worker.workflows.fusion_digest import (
    FusionDigestPodcastWorkflow,
    fetch_news_activity,
    fetch_papers_activity,
    synthesize_audio_activity,
    write_script_activity,
)

FAKE_PAPERS = [
    Paper(title="Diamond detector neutron spectroscopy at JET", doi="10.1/a", date="2026-11-04", source="crossref", score=9.0)
]
FAKE_NEWS = [NewsItem(title="ITER milestone", source="iter.org", url="https://iter.org", published="2026-11-05")]
FAKE_SCRIPT = ScriptDoc(
    episode_title="Episode",
    segments=[ScriptSegment(speaker="host", text="Welcome"), ScriptSegment(speaker="expert", text="Deep dive.")],
    transcript_md="# Episode",
)
FAKE_AUDIO = AudioArtifact(
    file_id="file-123",
    signed_url="https://example.com/fusion-digest.mp3",
    size_bytes=1024,
    segment_count=2,
    approx_duration_s=30.0,
)


async def test_fusion_digest_workflow_end_to_end(temporal_env, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")

    async def fake_fetch_papers(since, max_papers):
        return FAKE_PAPERS[:max_papers], []

    async def fake_fetch_news(client, since, days_back, max_news):
        return FAKE_NEWS[:max_news], []

    async def fake_generate_script(client, papers, news, inp):
        return FAKE_SCRIPT

    async def fake_render_podcast(client, script, episode_date):
        return FAKE_AUDIO

    monkeypatch.setattr(sources, "fetch_papers", fake_fetch_papers)
    monkeypatch.setattr(sources, "fetch_news", fake_fetch_news)
    monkeypatch.setattr(scripting, "generate_script", fake_generate_script)
    monkeypatch.setattr(tts, "render_podcast", fake_render_podcast)

    async with testing.create_test_worker(
        temporal_env,
        workflows=[FusionDigestPodcastWorkflow],
        activities=[
            fetch_papers_activity,
            fetch_news_activity,
            write_script_activity,
            synthesize_audio_activity,
        ],
    ):
        handle = await temporal_env.client.start_workflow(
            "fusion-digest-podcast",
            DigestInput().model_dump(mode="json"),
            id=f"test-{uuid.uuid4()}",
            task_queue="test-task-queue",
        )
        result = await handle.result()

    assert result["window_days"] == 7
    assert result["papers"][0]["doi"] == "10.1/a"
    assert result["news"][0]["title"] == "ITER milestone"
    assert result["script"]["episode_title"] == "Episode"
    assert result["audio"]["signed_url"] == "https://example.com/fusion-digest.mp3"
    assert result["warnings"] == []
