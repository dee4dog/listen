from dataclasses import dataclass, field
from typing import Optional


def fmt_ts(seconds: float) -> str:
    seconds = max(0, int(seconds or 0))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


@dataclass
class Segment:
    start: float
    end: float
    speaker: str
    text: str


@dataclass
class IssueItem:
    kind: str                     # action | decision | issue | key_point
    text: str
    speaker: str
    normalized: str = ""
    recurring: bool = False
    prior_date: Optional[str] = None


@dataclass
class Session:
    title: str
    dtype: str                    # discussion type key
    started_at: str               # ISO string
    audio_path: str
    duration: float
    segments: list = field(default_factory=list)   # list[Segment]
    issues: list = field(default_factory=list)     # list[IssueItem]
    id: Optional[int] = None
    # transient: voice-embedding centroid per speaker label (not persisted)
    centroids: dict = field(default_factory=dict)
    # transient: filtered-export views list only these summary sections
    sections_override: Optional[list] = None

    def speaker_names(self) -> list:
        seen = []
        for seg in self.segments:
            if seg.speaker and seg.speaker not in seen:
                seen.append(seg.speaker)
        return seen
