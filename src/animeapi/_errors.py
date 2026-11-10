from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

if TYPE_CHECKING:
    from ._types import Video


class AnimeAPIError(Exception):
    """Base class for every error this SDK raises.

    Attributes:
        status: HTTP status, or 0 when no response was received.
        code: Machine-readable code such as ``INSUFFICIENT_BALANCE``.
        retryable: True when sending the same request again can succeed.
        retry_after: Seconds the server asked you to wait (``Retry-After``), if any.
        body: The parsed response body, when there was one.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int = 0,
        code: str = "",
        retryable: bool = False,
        retry_after: Optional[float] = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after
        self.body = body

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}({self.message!r}, status={self.status}, "
            f"code={self.code!r}, retryable={self.retryable})"
        )


class InvalidRequestError(AnimeAPIError):
    """400: the request was invalid, or the model declined it (``PROVIDER_REJECTED``)."""


class ModerationError(InvalidRequestError):
    """400 ``MODERATION_BLOCKED``: the prompt was blocked."""


class AuthenticationError(AnimeAPIError):
    """401 ``INVALID_KEY``: missing, malformed, unknown or revoked key."""


class InsufficientBalanceError(AnimeAPIError):
    """402 ``INSUFFICIENT_BALANCE``: top up at https://animeapi.ai/dashboard/billing."""


class NotFoundError(AnimeAPIError):
    """404 ``NOT_FOUND``."""


class RateLimitError(AnimeAPIError):
    """429 ``RATE_LIMITED``."""


class GenerationError(AnimeAPIError):
    """500 ``GENERATION_FAILED``: retrying is fine."""


class ServiceUnavailableError(AnimeAPIError):
    """503 ``PROVIDER_UNAVAILABLE``: temporarily unavailable; see ``retry_after``."""


class ConnectionError(AnimeAPIError):  # noqa: A001 - mirrors the JavaScript SDK's name
    """The request never got a response (network failure)."""


class TimeoutError(AnimeAPIError):  # noqa: A001 - mirrors the JavaScript SDK's name
    """The request, or a video wait, ran out of time."""


class VideoFailedError(AnimeAPIError):
    """A video job finished with status ``failed`` (the charge was refunded)."""

    def __init__(self, video: "Video") -> None:
        super().__init__(
            video.error or "The video couldn't be generated.",
            status=200,
            code="VIDEO_FAILED",
            retryable=False,
        )
        self.video = video


def error_from_response(status: int, body: Any, retry_after: Optional[float]) -> AnimeAPIError:
    obj: Dict[str, Any] = cast(Dict[str, Any], body) if isinstance(body, dict) else {}
    raw_error = obj.get("error")
    # The OpenAI-compatible endpoints nest the message: {"error": {"message", "code"}}.
    nested: Dict[str, Any] = cast(Dict[str, Any], raw_error) if isinstance(raw_error, dict) else {}
    if isinstance(raw_error, str):
        message = raw_error
    elif isinstance(nested.get("message"), str):
        message = nested["message"]
    else:
        message = f"AnimeAPI request failed with status {status}"
    code = obj.get("code") if isinstance(obj.get("code"), str) else nested.get("code")
    if not isinstance(code, str):
        code = None
    retryable = obj["retryable"] if isinstance(obj.get("retryable"), bool) else status in (500, 503)

    def make(cls: "type[AnimeAPIError]", default_code: str) -> AnimeAPIError:
        return cls(
            message,
            status=status,
            code=code or default_code,
            retryable=retryable,
            retry_after=retry_after,
            body=body,
        )

    if status == 401:
        return make(AuthenticationError, "INVALID_KEY")
    if status == 402:
        return make(InsufficientBalanceError, "INSUFFICIENT_BALANCE")
    if status == 404:
        return make(NotFoundError, "NOT_FOUND")
    if status == 429:
        return make(RateLimitError, "RATE_LIMITED")
    if status == 503:
        return make(ServiceUnavailableError, "PROVIDER_UNAVAILABLE")
    if status >= 500:
        return make(GenerationError, "GENERATION_FAILED")
    if code == "MODERATION_BLOCKED":
        return make(ModerationError, "MODERATION_BLOCKED")
    return make(InvalidRequestError, "INVALID_REQUEST")
