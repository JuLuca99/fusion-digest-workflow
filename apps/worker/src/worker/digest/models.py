import pydantic


class DigestInput(pydantic.BaseModel):
    days_back: int = 7
    max_papers: int = 5
    max_news: int = 8
    language: str = "en"
    target_minutes: int = 18


class Paper(pydantic.BaseModel):
    title: str
    authors: list[str] = []
    venue: str = ""
    date: str = ""
    doi: str = ""
    url: str = ""
    abstract: str = ""
    source: str = ""
    score: float = 0.0


class NewsItem(pydantic.BaseModel):
    title: str
    source: str = ""
    url: str = ""
    published: str = ""
    summary: str = ""


class ScriptSegment(pydantic.BaseModel):
    speaker: str
    text: str


class ScriptDoc(pydantic.BaseModel):
    episode_title: str
    segments: list[ScriptSegment]
    transcript_md: str


class AudioArtifact(pydantic.BaseModel):
    file_id: str
    signed_url: str
    format: str = "mp3"
    size_bytes: int = 0
    segment_count: int = 0
    approx_duration_s: float = 0.0


class DigestOutput(pydantic.BaseModel):
    generated_at: str
    window_days: int
    papers: list[Paper]
    news: list[NewsItem]
    script: ScriptDoc
    audio: AudioArtifact
    warnings: list[str] = []
