import base64
import binascii
import io

import mistralai.workflows as workflows

from worker.digest.models import AudioArtifact, ScriptDoc

TTS_MODEL = "voxtral-mini-tts-3-0"
DEFAULT_VOICES = {"host": "gb_jane_neutral", "expert": "gb_daniel_neutral"}
WORDS_PER_MINUTE = 150.0
SIGNED_URL_EXPIRY_HOURS = 24 * 30


async def pick_voices(client) -> dict[str, str]:
    try:
        voices = await client.audio.voices.list_async()
        items = getattr(voices, "data", None) or voices
        english = [
            v for v in items
            if str(getattr(v, "language", "") or "").lower().startswith(("en", "gb"))
        ]
        ids = [str(getattr(v, "id", "") or getattr(v, "voice_id", "")) for v in english]
        ids = [i for i in ids if i]
        if len(ids) >= 2:
            return {"host": ids[0], "expert": ids[1]}
    except Exception:
        pass
    return dict(DEFAULT_VOICES)


def _decode_audio(audio_data: str) -> bytes:
    try:
        return base64.b64decode(audio_data, validate=True)
    except (binascii.Error, ValueError):
        return audio_data.encode("utf-8")


async def render_podcast(client, script: ScriptDoc, episode_date: str) -> AudioArtifact:
    voices = await pick_voices(client)
    chunks: list[bytes] = []
    for index, segment in enumerate(script.segments):
        voice_id = voices.get(segment.speaker, voices["host"])
        response = await client.audio.speech.complete_async(
            model=TTS_MODEL,
            input=segment.text,
            voice_id=voice_id,
            response_format="mp3",
        )
        chunks.append(_decode_audio(response.audio_data))
        workflows.activity_heartbeat(index + 1)
    audio_bytes = b"".join(chunks)
    uploaded = await client.files.upload_async(
        file={"content": io.BytesIO(audio_bytes), "file_name": f"fusion-digest-{episode_date}.mp3"},
        purpose="audio",
    )
    signed = await client.files.get_signed_url_async(file_id=uploaded.id, expiry=SIGNED_URL_EXPIRY_HOURS)
    total_words = sum(len(seg.text.split()) for seg in script.segments)
    return AudioArtifact(
        file_id=uploaded.id,
        signed_url=signed.url,
        format="mp3",
        size_bytes=len(audio_bytes),
        segment_count=len(script.segments),
        approx_duration_s=round(total_words / WORDS_PER_MINUTE * 60.0, 1),
    )
