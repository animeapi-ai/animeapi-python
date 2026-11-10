"""Official AnimeAPI SDK (https://animeapi.ai).

Anime image generation from $0.003 per image, plus anime video.

    from animeapi import AnimeAPI

    client = AnimeAPI()  # reads ANIMEAPI_API_KEY
    image = client.images.generate("a silver-haired girl reading under a cherry tree")
    print(image.image_url)
"""

from ._client import (
    AnimeAPI,
    AsyncAnimeAPI,
    AsyncImages,
    AsyncModels,
    AsyncVideos,
    Images,
    Models,
    Videos,
)
from ._errors import (
    AnimeAPIError,
    AuthenticationError,
    ConnectionError,
    GenerationError,
    InsufficientBalanceError,
    InvalidRequestError,
    ModerationError,
    NotFoundError,
    RateLimitError,
    ServiceUnavailableError,
    TimeoutError,
    VideoFailedError,
)
from ._types import (
    DownloadedFile,
    GeneratedImage,
    ImageModel,
    Model,
    Orientation,
    Video,
    VideoJob,
    VideoResolution,
    VideoStatus,
)
from ._version import __version__

__all__ = [
    "AnimeAPI",
    "AsyncAnimeAPI",
    "Images",
    "Videos",
    "Models",
    "AsyncImages",
    "AsyncVideos",
    "AsyncModels",
    "AnimeAPIError",
    "AuthenticationError",
    "ConnectionError",
    "GenerationError",
    "InsufficientBalanceError",
    "InvalidRequestError",
    "ModerationError",
    "NotFoundError",
    "RateLimitError",
    "ServiceUnavailableError",
    "TimeoutError",
    "VideoFailedError",
    "DownloadedFile",
    "GeneratedImage",
    "ImageModel",
    "Model",
    "Orientation",
    "Video",
    "VideoJob",
    "VideoResolution",
    "VideoStatus",
    "__version__",
]
