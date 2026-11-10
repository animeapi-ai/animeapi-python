from __future__ import annotations

import asyncio
import email.utils
import json
import os
import random
import time
from typing import Any, Callable, Dict, List, Optional, Union
from urllib.parse import quote

import httpx

from ._errors import (
    AnimeAPIError,
    AuthenticationError,
    ConnectionError,
    GenerationError,
    InvalidRequestError,
    TimeoutError,
    VideoFailedError,
    error_from_response,
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
)
from ._version import __version__

DEFAULT_BASE_URL = "https://animeapi.ai"
DEFAULT_TIMEOUT = 120.0
DEFAULT_MAX_RETRIES = 2
MAX_RETRY_AFTER = 60.0


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _resolve_key(api_key: Optional[str]) -> str:
    key = api_key or os.environ.get("ANIMEAPI_API_KEY")
    if not key:
        raise AuthenticationError(
            "Missing API key. Pass api_key=... or set ANIMEAPI_API_KEY. "
            "Create a key at https://animeapi.ai/dashboard/api-keys",
            code="INVALID_KEY",
        )
    return key


def _resolve_base_url(base_url: Optional[str]) -> str:
    return (base_url or os.environ.get("ANIMEAPI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _headers(api_key: str, has_body: bool) -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": f"animeapi-python/{__version__}",
    }
    if has_body:
        headers["Content-Type"] = "application/json"
    return headers


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, when.timestamp() - time.time())


def _backoff(attempt: int) -> float:
    base = min(8.0, 0.5 * (2**attempt))
    return base / 2 + random.random() * (base / 2)


def _retry_delay(error: AnimeAPIError, attempt: int) -> float:
    if error.retry_after is not None:
        return min(MAX_RETRY_AFTER, error.retry_after)
    return _backoff(attempt)


def _error_for(response: httpx.Response, authenticated: bool) -> AnimeAPIError:
    retry_after = _parse_retry_after(response.headers.get("retry-after"))
    body: Any
    try:
        body = response.json()
    except ValueError:
        body = response.text
    if authenticated:
        return error_from_response(response.status_code, body, retry_after)
    return AnimeAPIError(
        f"Download failed with status {response.status_code}",
        status=response.status_code,
        code="NOT_FOUND" if response.status_code == 404 else "GENERATION_FAILED",
        retryable=response.status_code >= 500,
        retry_after=retry_after,
        body=body,
    )


def _transport_error(exc: httpx.HTTPError, timeout: float) -> AnimeAPIError:
    if isinstance(exc, httpx.TimeoutException) and not isinstance(exc, httpx.ConnectTimeout):
        return TimeoutError(f"Request timed out after {timeout:g} s", code="TIMEOUT", retryable=False)
    return ConnectionError(f"Could not reach AnimeAPI: {exc}", code="CONNECTION_ERROR", retryable=True)


def _parse_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        raise GenerationError(
            "AnimeAPI returned a response that was not JSON.",
            status=response.status_code,
            code="GENERATION_FAILED",
            body=response.text,
        ) from None


def _image_body(
    prompt: str,
    model: Optional[ImageModel],
    orientation: Optional[Orientation],
    enhance: Optional[bool],
    allow_nsfw: Optional[bool],
) -> Dict[str, Any]:
    body: Dict[str, Any] = {"prompt": prompt}
    if model is not None:
        body["model"] = model
    if orientation is not None:
        body["orientation"] = orientation
    if enhance is not None:
        body["enhance"] = enhance
    # allow_nsfw is deprecated and ignored by the API (adult output is not available); it is not sent.
    del allow_nsfw
    return body


def _video_body(
    prompt: str,
    resolution: Optional[VideoResolution],
    duration: Optional[int],
    orientation: Optional[Orientation],
    enhance: Optional[bool],
    first_frame: Optional[str],
    last_frame: Optional[str],
) -> Dict[str, Any]:
    body: Dict[str, Any] = {"prompt": prompt}
    if resolution is not None:
        body["resolution"] = resolution
    if duration is not None:
        body["duration"] = duration
    if orientation is not None:
        body["orientation"] = orientation
    if enhance is not None:
        body["enhance"] = enhance
    if first_frame is not None:
        body["first_frame"] = first_frame
    if last_frame is not None:
        body["last_frame"] = last_frame
    return body


def _video_url(video: Union[Video, str]) -> str:
    url = video if isinstance(video, str) else video.video_url
    if not url:
        raise InvalidRequestError(
            "This video has no URL yet. Wait until its status is succeeded.", code="INVALID_REQUEST"
        )
    return url


def _wait_timeout(video_id: str, timeout: float) -> TimeoutError:
    return TimeoutError(
        f"Video {video_id} was still processing after {timeout:g} s", code="TIMEOUT", retryable=False
    )


# ---------------------------------------------------------------------------
# Sync client
# ---------------------------------------------------------------------------


class AnimeAPI:
    """Synchronous AnimeAPI client.

    Args:
        api_key: Your key (starts with ``ank_``). Defaults to the ``ANIMEAPI_API_KEY`` environment variable.
        base_url: Defaults to ``https://animeapi.ai``.
        timeout: Per-request timeout in seconds. Default 120.
        max_retries: How many times a retryable failure is tried again. Default 2; 0 turns retries off.
        http_client: Bring your own ``httpx.Client`` (proxies, custom transports).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self._api_key = _resolve_key(api_key)
        self.base_url = _resolve_base_url(base_url)
        self.timeout = timeout
        self.max_retries = max_retries
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(follow_redirects=True)
        self.images = Images(self)
        self.videos = Videos(self)
        self.models = Models(self)

    def __enter__(self) -> "AnimeAPI":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client (only if this client created it)."""
        if self._owns_client:
            self._client.close()

    def generate(
        self,
        prompt: str,
        *,
        model: Optional[ImageModel] = None,
        orientation: Optional[Orientation] = None,
        enhance: Optional[bool] = None,
        allow_nsfw: Optional[bool] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> GeneratedImage:
        """Shortcut for ``client.images.generate(...)``."""
        return self.images.generate(
            prompt,
            model=model,
            orientation=orientation,
            enhance=enhance,
            allow_nsfw=allow_nsfw,
            timeout=timeout,
            max_retries=max_retries,
        )

    def request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> Any:
        """Low-level request with authentication, timeout and retries. Returns the parsed JSON body."""
        response = self._send(
            method,
            self.base_url + path,
            headers=_headers(self._api_key, body is not None),
            content=None if body is None else json.dumps(body).encode(),
            timeout=timeout,
            max_retries=max_retries,
            authenticated=True,
        )
        return _parse_json(response)

    def download(
        self, url: str, *, timeout: Optional[float] = None, max_retries: Optional[int] = None
    ) -> DownloadedFile:
        """Download a file (an image or video URL returned by the API) as bytes."""
        response = self._send(
            "GET",
            url,
            headers={"User-Agent": f"animeapi-python/{__version__}"},
            content=None,
            timeout=timeout,
            max_retries=max_retries,
            authenticated=False,
        )
        return DownloadedFile(
            content=response.content,
            content_type=response.headers.get("content-type", "application/octet-stream"),
        )

    def _send(
        self,
        method: str,
        url: str,
        *,
        headers: Dict[str, str],
        content: Optional[bytes],
        timeout: Optional[float],
        max_retries: Optional[int],
        authenticated: bool,
    ) -> httpx.Response:
        retries = max(0, self.max_retries if max_retries is None else max_retries)
        limit = self.timeout if timeout is None else timeout
        attempt = 0
        while True:
            try:
                response = self._client.request(method, url, headers=headers, content=content, timeout=limit)
                if response.is_success:
                    return response
                error = _error_for(response, authenticated)
            except httpx.HTTPError as exc:
                error = _transport_error(exc, limit)
                error.__cause__ = exc
            if not error.retryable or attempt >= retries:
                raise error
            time.sleep(_retry_delay(error, attempt))
            attempt += 1


class Images:
    def __init__(self, client: AnimeAPI) -> None:
        self._client = client

    def generate(
        self,
        prompt: str,
        *,
        model: Optional[ImageModel] = None,
        orientation: Optional[Orientation] = None,
        enhance: Optional[bool] = None,
        allow_nsfw: Optional[bool] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> GeneratedImage:
        """Generate one anime image.

        Synchronous: returns in about 4 seconds on ``anime``, about 11 seconds on ``ultra``.

        Args:
            prompt: What to draw, in plain English. Up to 1000 characters.
            model: ``anime`` (default, $0.003 per image), ``ultra`` ($0.01) or ``ultra-max`` ($0.02).
            orientation: ``portrait`` (default), ``square`` or ``landscape``.
            enhance: ``anime`` model only: rewrite the prompt into tags first. Default true.
            allow_nsfw: Deprecated. Ignored by the API; adult output is not available.
                Kept so existing code keeps working.
        """
        raw = self._client.request(
            "POST",
            "/api/generate",
            _image_body(prompt, model, orientation, enhance, allow_nsfw),
            timeout=timeout,
            max_retries=max_retries,
        )
        return GeneratedImage._from(raw)  # pyright: ignore[reportPrivateUsage]

    def download(
        self, image: Union[GeneratedImage, str], *, timeout: Optional[float] = None
    ) -> DownloadedFile:
        """Download the image bytes. Image URLs are not permanent storage, so save what you want to keep."""
        url = image if isinstance(image, str) else image.image_url
        return self._client.download(url, timeout=timeout)


class Videos:
    def __init__(self, client: AnimeAPI) -> None:
        self._client = client

    def create(
        self,
        prompt: str,
        *,
        resolution: Optional[VideoResolution] = None,
        duration: Optional[int] = None,
        orientation: Optional[Orientation] = None,
        enhance: Optional[bool] = None,
        first_frame: Optional[str] = None,
        last_frame: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> VideoJob:
        """Start a video job. Returns at once with a job id.

        The price is charged up front (480p $0.016 per second, 768p $0.04 per second) and
        refunded if the job fails.

        Args:
            prompt: What happens in the clip, in plain English. Up to 1000 characters.
            resolution: ``768p`` (default) or ``480p``.
            duration: Whole seconds, 5 to 15. Default 5.
            orientation: ``landscape`` (default), ``portrait`` or ``square``.
            enhance: Let the video model expand the prompt first. Default true.
            first_frame: Image the clip starts on: an http(s) URL or a base64 data URI, up to 10 MB.
            last_frame: Image the clip ends on. Same format as ``first_frame``.
        """
        raw = self._client.request(
            "POST",
            "/api/videos",
            _video_body(prompt, resolution, duration, orientation, enhance, first_frame, last_frame),
            timeout=timeout,
        )
        return VideoJob._from(raw)  # pyright: ignore[reportPrivateUsage]

    def get(self, video_id: str, *, timeout: Optional[float] = None) -> Video:
        """Get a video job by id."""
        raw = self._client.request("GET", f"/api/videos/{quote(video_id, safe='')}", timeout=timeout)
        return Video._from(raw)  # pyright: ignore[reportPrivateUsage]

    def wait(
        self,
        job: Union[VideoJob, Video, str],
        *,
        interval: float = 5.0,
        timeout: float = 600.0,
        on_poll: Optional[Callable[[Video], None]] = None,
    ) -> Video:
        """Poll until the video has finished.

        Returns the finished video. Raises ``VideoFailedError`` if the job failed and
        ``TimeoutError`` if it is still processing after ``timeout`` seconds.
        """
        video_id = job if isinstance(job, str) else job.id
        deadline = time.monotonic() + timeout
        while True:
            video = self.get(video_id)
            if on_poll is not None:
                on_poll(video)
            if video.status == "succeeded":
                return video
            if video.status == "failed":
                raise VideoFailedError(video)
            if time.monotonic() + interval > deadline:
                raise _wait_timeout(video_id, timeout)
            time.sleep(interval)

    def create_and_wait(
        self,
        prompt: str,
        *,
        resolution: Optional[VideoResolution] = None,
        duration: Optional[int] = None,
        orientation: Optional[Orientation] = None,
        enhance: Optional[bool] = None,
        first_frame: Optional[str] = None,
        last_frame: Optional[str] = None,
        interval: float = 5.0,
        timeout: float = 600.0,
        on_poll: Optional[Callable[[Video], None]] = None,
    ) -> Video:
        """Start a video and wait for it to finish."""
        job = self.create(
            prompt,
            resolution=resolution,
            duration=duration,
            orientation=orientation,
            enhance=enhance,
            first_frame=first_frame,
            last_frame=last_frame,
        )
        return self.wait(job.id, interval=interval, timeout=timeout, on_poll=on_poll)

    def download(self, video: Union[Video, str], *, timeout: Optional[float] = None) -> DownloadedFile:
        """Download the finished MP4 as bytes."""
        return self._client.download(_video_url(video), timeout=timeout)


class Models:
    def __init__(self, client: AnimeAPI) -> None:
        self._client = client

    def list(self, *, timeout: Optional[float] = None) -> List[Model]:
        """List the available image models with their prices."""
        raw = self._client.request("GET", "/v1/models", timeout=timeout)
        return [Model._from(item) for item in raw.get("data", [])]  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------


class AsyncAnimeAPI:
    """Asynchronous AnimeAPI client. Same surface as :class:`AnimeAPI`, with ``await``.

    Args:
        api_key: Your key (starts with ``ank_``). Defaults to the ``ANIMEAPI_API_KEY`` environment variable.
        base_url: Defaults to ``https://animeapi.ai``.
        timeout: Per-request timeout in seconds. Default 120.
        max_retries: How many times a retryable failure is tried again. Default 2; 0 turns retries off.
        http_client: Bring your own ``httpx.AsyncClient``.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._api_key = _resolve_key(api_key)
        self.base_url = _resolve_base_url(base_url)
        self.timeout = timeout
        self.max_retries = max_retries
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(follow_redirects=True)
        self.images = AsyncImages(self)
        self.videos = AsyncVideos(self)
        self.models = AsyncModels(self)

    async def __aenter__(self) -> "AsyncAnimeAPI":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client (only if this client created it)."""
        if self._owns_client:
            await self._client.aclose()

    async def generate(
        self,
        prompt: str,
        *,
        model: Optional[ImageModel] = None,
        orientation: Optional[Orientation] = None,
        enhance: Optional[bool] = None,
        allow_nsfw: Optional[bool] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> GeneratedImage:
        """Shortcut for ``client.images.generate(...)``."""
        return await self.images.generate(
            prompt,
            model=model,
            orientation=orientation,
            enhance=enhance,
            allow_nsfw=allow_nsfw,
            timeout=timeout,
            max_retries=max_retries,
        )

    async def request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> Any:
        """Low-level request with authentication, timeout and retries. Returns the parsed JSON body."""
        response = await self._send(
            method,
            self.base_url + path,
            headers=_headers(self._api_key, body is not None),
            content=None if body is None else json.dumps(body).encode(),
            timeout=timeout,
            max_retries=max_retries,
            authenticated=True,
        )
        return _parse_json(response)

    async def download(
        self, url: str, *, timeout: Optional[float] = None, max_retries: Optional[int] = None
    ) -> DownloadedFile:
        """Download a file (an image or video URL returned by the API) as bytes."""
        response = await self._send(
            "GET",
            url,
            headers={"User-Agent": f"animeapi-python/{__version__}"},
            content=None,
            timeout=timeout,
            max_retries=max_retries,
            authenticated=False,
        )
        return DownloadedFile(
            content=response.content,
            content_type=response.headers.get("content-type", "application/octet-stream"),
        )

    async def _send(
        self,
        method: str,
        url: str,
        *,
        headers: Dict[str, str],
        content: Optional[bytes],
        timeout: Optional[float],
        max_retries: Optional[int],
        authenticated: bool,
    ) -> httpx.Response:
        retries = max(0, self.max_retries if max_retries is None else max_retries)
        limit = self.timeout if timeout is None else timeout
        attempt = 0
        while True:
            try:
                response = await self._client.request(
                    method, url, headers=headers, content=content, timeout=limit
                )
                if response.is_success:
                    return response
                error = _error_for(response, authenticated)
            except httpx.HTTPError as exc:
                error = _transport_error(exc, limit)
                error.__cause__ = exc
            if not error.retryable or attempt >= retries:
                raise error
            await asyncio.sleep(_retry_delay(error, attempt))
            attempt += 1


class AsyncImages:
    def __init__(self, client: AsyncAnimeAPI) -> None:
        self._client = client

    async def generate(
        self,
        prompt: str,
        *,
        model: Optional[ImageModel] = None,
        orientation: Optional[Orientation] = None,
        enhance: Optional[bool] = None,
        allow_nsfw: Optional[bool] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> GeneratedImage:
        """Generate one anime image. See :meth:`Images.generate`."""
        raw = await self._client.request(
            "POST",
            "/api/generate",
            _image_body(prompt, model, orientation, enhance, allow_nsfw),
            timeout=timeout,
            max_retries=max_retries,
        )
        return GeneratedImage._from(raw)  # pyright: ignore[reportPrivateUsage]

    async def download(
        self, image: Union[GeneratedImage, str], *, timeout: Optional[float] = None
    ) -> DownloadedFile:
        """Download the image bytes. Image URLs are not permanent storage, so save what you want to keep."""
        url = image if isinstance(image, str) else image.image_url
        return await self._client.download(url, timeout=timeout)


class AsyncVideos:
    def __init__(self, client: AsyncAnimeAPI) -> None:
        self._client = client

    async def create(
        self,
        prompt: str,
        *,
        resolution: Optional[VideoResolution] = None,
        duration: Optional[int] = None,
        orientation: Optional[Orientation] = None,
        enhance: Optional[bool] = None,
        first_frame: Optional[str] = None,
        last_frame: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> VideoJob:
        """Start a video job. See :meth:`Videos.create`."""
        raw = await self._client.request(
            "POST",
            "/api/videos",
            _video_body(prompt, resolution, duration, orientation, enhance, first_frame, last_frame),
            timeout=timeout,
        )
        return VideoJob._from(raw)  # pyright: ignore[reportPrivateUsage]

    async def get(self, video_id: str, *, timeout: Optional[float] = None) -> Video:
        """Get a video job by id."""
        raw = await self._client.request("GET", f"/api/videos/{quote(video_id, safe='')}", timeout=timeout)
        return Video._from(raw)  # pyright: ignore[reportPrivateUsage]

    async def wait(
        self,
        job: Union[VideoJob, Video, str],
        *,
        interval: float = 5.0,
        timeout: float = 600.0,
        on_poll: Optional[Callable[[Video], None]] = None,
    ) -> Video:
        """Poll until the video has finished. See :meth:`Videos.wait`."""
        video_id = job if isinstance(job, str) else job.id
        deadline = time.monotonic() + timeout
        while True:
            video = await self.get(video_id)
            if on_poll is not None:
                on_poll(video)
            if video.status == "succeeded":
                return video
            if video.status == "failed":
                raise VideoFailedError(video)
            if time.monotonic() + interval > deadline:
                raise _wait_timeout(video_id, timeout)
            await asyncio.sleep(interval)

    async def create_and_wait(
        self,
        prompt: str,
        *,
        resolution: Optional[VideoResolution] = None,
        duration: Optional[int] = None,
        orientation: Optional[Orientation] = None,
        enhance: Optional[bool] = None,
        first_frame: Optional[str] = None,
        last_frame: Optional[str] = None,
        interval: float = 5.0,
        timeout: float = 600.0,
        on_poll: Optional[Callable[[Video], None]] = None,
    ) -> Video:
        """Start a video and wait for it to finish."""
        job = await self.create(
            prompt,
            resolution=resolution,
            duration=duration,
            orientation=orientation,
            enhance=enhance,
            first_frame=first_frame,
            last_frame=last_frame,
        )
        return await self.wait(job.id, interval=interval, timeout=timeout, on_poll=on_poll)

    async def download(self, video: Union[Video, str], *, timeout: Optional[float] = None) -> DownloadedFile:
        """Download the finished MP4 as bytes."""
        return await self._client.download(_video_url(video), timeout=timeout)


class AsyncModels:
    def __init__(self, client: AsyncAnimeAPI) -> None:
        self._client = client

    async def list(self, *, timeout: Optional[float] = None) -> List[Model]:
        """List the available image models with their prices."""
        raw = await self._client.request("GET", "/v1/models", timeout=timeout)
        return [Model._from(item) for item in raw.get("data", [])]  # pyright: ignore[reportPrivateUsage]
