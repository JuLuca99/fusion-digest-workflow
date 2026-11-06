# Fusion Digest Podcast (Mistral Workflow)

A one-shot Mistral Workflow that produces a podcast-style digest for a PhD in neutron diagnostic
measurements based on synthetic (CVD) diamond detectors:

1. **Light intro** — the most important general nuclear fusion news of the selected window
   (web search via a Mistral agent with the built-in `web_search` tool + RSS feeds).
2. **Deep dive** — PhD-level discussion of the most relevant recent publications on neutron
   diagnostics with synthetic diamond detectors, gathered from Crossref and arXiv.
3. **Audio** — the script is synthesized with Voxtral TTS (`voxtral-mini-tts-3-0`, two voices:
   `host` and `expert`), concatenated into one mp3, uploaded to the Mistral Files API, and returned
   as a signed download URL together with the full transcript.

## Trigger (one-shot, no schedule)

```bash
curl -X POST https://api.mistral.ai/v1/workflows/fusion-digest-podcast/execute \
  -H "Authorization: Bearer $MISTRAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": {"days_back": 7, "max_papers": 5, "max_news": 8, "language": "en", "target_minutes": 18}, "wait_for_result": true}'
```

All input fields are optional (defaults shown). The execution result contains `audio.signed_url`
(mp3), `script.transcript_md`, the selected `papers` and `news`, and any `warnings`.

## Layout

- `apps/worker/src/worker/workflows/fusion_digest.py` — workflow + activities
- `apps/worker/src/worker/digest/` — sources (Crossref/arXiv/RSS/web-search), scoring, scripting, TTS
- `deploy/docker/Dockerfile.worker` — image built by the managed deployment

## Tests

```bash
uv sync --group dev
uv run pytest
```
