from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

#: ``anime`` $0.003 per image, ``ultra`` $0.01, ``ultra-max`` $0.02.
ImageModel = Literal["anime", "ultra", "ultra-max"]
Orientation = Literal["portrait", "square", "landscape"]
#: 480p is $0.016 per second, 768p is $0.04 per second.
VideoResolution = Literal["480p", "768p"]
VideoStatus = Literal["processing", "succeeded", "failed"]


@dataclass(frozen=True)
class GeneratedImage:
    #: Temporary URL on animeapi.ai/cdn. Download the image if you need to keep it.
    image_url: str
    #: What the model actually received.
    enhanced_prompt: str
    #: Balance in US dollars after this charge.
    balance_usd: float
    generation_time_ms: float

    @classmethod
    def _from(cls, raw: "dict[str, Any]") -> "GeneratedImage":
        return cls(
            image_url=raw["image_url"],
            enhanced_prompt=raw.get("enhanced_prompt", ""),
            balance_usd=raw.get("balance_usd", 0.0),
            generation_time_ms=raw.get("generation_time_ms", 0.0),
        )


@dataclass(frozen=True)
class DownloadedFile:
    content: bytes
    #: For example ``image/webp``, ``image/png`` or ``video/mp4``.
    content_type: str

    def save(self, path: str) -> str:
        """Write the bytes to ``path`` and return the path."""
        with open(path, "wb") as handle:
            handle.write(self.content)
        return path


@dataclass(frozen=True)
class VideoJob:
    id: str
    status: VideoStatus
    poll_url: str
    enhanced_prompt: str
    resolution: VideoResolution
    duration: int
    orientation: Orientation
    #: Charged now; refunded if the job fails.
    cost_usd: float
    balance_usd: float

    @classmethod
    def _from(cls, raw: "dict[str, Any]") -> "VideoJob":
        return cls(
            id=raw["id"],
            status=raw.get("status", "processing"),
            poll_url=raw.get("poll_url", ""),
            enhanced_prompt=raw.get("enhanced_prompt", ""),
            resolution=raw.get("resolution", "768p"),
            duration=raw.get("duration", 0),
            orientation=raw.get("orientation", "landscape"),
            cost_usd=raw.get("cost_usd", 0.0),
            balance_usd=raw.get("balance_usd", 0.0),
        )


@dataclass(frozen=True)
class Video:
    id: str
    status: VideoStatus
    #: MP4 URL once ``status`` is ``succeeded``.
    video_url: Optional[str]
    prompt: str
    enhanced_prompt: str
    resolution: VideoResolution
    duration: int
    orientation: Orientation
    first_frame: bool
    last_frame: bool
    cost_usd: float
    #: True when the job failed and the charge was returned.
    refunded: bool
    generation_time_ms: Optional[float]
    #: Why the job failed.
    error: Optional[str]
    created_at: str

    @classmethod
    def _from(cls, raw: "dict[str, Any]") -> "Video":
        return cls(
            id=raw["id"],
            status=raw["status"],
            video_url=raw.get("video_url"),
            prompt=raw.get("prompt", ""),
            enhanced_prompt=raw.get("enhanced_prompt", ""),
            resolution=raw.get("resolution", "768p"),
            duration=raw.get("duration", 0),
            orientation=raw.get("orientation", "landscape"),
            first_frame=bool(raw.get("first_frame")),
            last_frame=bool(raw.get("last_frame")),
            cost_usd=raw.get("cost_usd", 0.0),
            refunded=bool(raw.get("refunded")),
            generation_time_ms=raw.get("generation_time_ms"),
            error=raw.get("error"),
            created_at=raw.get("created_at", ""),
        )


@dataclass(frozen=True)
class Model:
    id: str
    created: int
    owned_by: str
    description: Optional[str] = None

    @classmethod
    def _from(cls, raw: "dict[str, Any]") -> "Model":
        return cls(
            id=raw["id"],
            created=raw.get("created", 0),
            owned_by=raw.get("owned_by", ""),
            description=raw.get("description"),
        )
