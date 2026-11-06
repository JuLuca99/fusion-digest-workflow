from datetime import datetime, timedelta, timezone

import mistralai.workflows as workflows
from mistralai.workflows import Depends
from mistralai.workflows.client import get_mistral_client

from worker.digest.models import (
    AudioArtifact,
    DigestInput,
    DigestOutput,
    NewsItem,
    Paper,
    ScriptDoc,
)


@workflows.activity(name="fetch-papers", start_to_close_timeout=timedelta(minutes=10))
async def fetch_papers_activity(input: DigestInput) -> tuple[list[Paper], list[str]]:
    from worker.digest import sources

    since = datetime.now(timezone.utc).date() - timedelta(days=input.days_back)
    return await sources.fetch_papers(since, input.max_papers)


@workflows.activity(name="fetch-news", start_to_close_timeout=timedelta(minutes=10))
async def fetch_news_activity(
    input: DigestInput,
    client=Depends(get_mistral_client),
) -> tuple[list[NewsItem], list[str]]:
    from worker.digest import sources

    since = datetime.now(timezone.utc).date() - timedelta(days=input.days_back)
    return await sources.fetch_news(client, since, input.days_back, input.max_news)


@workflows.activity(name="write-script", start_to_close_timeout=timedelta(minutes=15))
async def write_script_activity(
    papers: list[Paper],
    news: list[NewsItem],
    input: DigestInput,
    client=Depends(get_mistral_client),
) -> ScriptDoc:
    from worker.digest import scripting

    return await scripting.generate_script(client, papers, news, input)


@workflows.activity(
    name="synthesize-audio",
    start_to_close_timeout=timedelta(minutes=60),
    heartbeat_timeout=timedelta(minutes=2),
)
async def synthesize_audio_activity(
    script: ScriptDoc,
    episode_date: str,
    client=Depends(get_mistral_client),
) -> AudioArtifact:
    from worker.digest import tts

    return await tts.render_podcast(client, script, episode_date)


@workflows.workflow.define(
    name="fusion-digest-podcast",
    workflow_display_name="Fusion Digest Podcast",
    workflow_description=(
        "One-shot digest: latest nuclear fusion news (light intro) plus a PhD-level deep dive into the most "
        "relevant recent publications on neutron diagnostics with synthetic diamond detectors. Returns a podcast "
        "mp3 (signed URL) and full transcript. Trigger manually; no schedule."
    ),
    execution_timeout=timedelta(hours=3),
)
class FusionDigestPodcastWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: DigestInput | None = None) -> DigestOutput:
        from worker.digest.models import DigestInput as _DigestInput

        inp = input or _DigestInput()
        now = workflows.workflow.now()
        episode_date = now.date().isoformat()
        warnings: list[str] = []

        papers, paper_warnings = await fetch_papers_activity(inp)
        warnings.extend(paper_warnings)
        news, news_warnings = await fetch_news_activity(inp)
        warnings.extend(news_warnings)
        if not papers:
            warnings.append("no papers found in the selected window; deep dive will be based on news only")

        script = await write_script_activity(papers, news, inp)
        audio = await synthesize_audio_activity(script, episode_date)

        return DigestOutput(
            generated_at=now.isoformat(),
            window_days=inp.days_back,
            papers=papers,
            news=news,
            script=script,
            audio=audio,
            warnings=warnings,
        )
