# AnimeAPI SDK for Python

Official SDK for [AnimeAPI](https://animeapi.ai): anime image generation from **$0.003 per image**, one of the cheapest anime image APIs, plus anime video. New accounts get **3 free images, no card**.

Sync and async clients, fully typed, Python 3.9+. One dependency (`httpx`).

```bash
pip install animeapi-sdk
```

The package is `animeapi-sdk` on PyPI; you import it as `animeapi`.

## Quick start

```python
from animeapi import AnimeAPI

client = AnimeAPI(api_key="ank_...")
image = client.images.generate("a silver-haired girl reading under a cherry tree")
print(image.image_url)
```

Create a key (it starts with `ank_`) at <https://animeapi.ai/dashboard/api-keys>. If you leave `api_key` out, the SDK reads the `ANIMEAPI_API_KEY` environment variable.

## Prices

| Model | Price | Good for |
| --- | --- | --- |
| `anime` (default) | $0.003 per image | Characters and illustrations; plain-English prompts are rewritten into tags |
| `ultra` | $0.01 per image | Long, detailed sentences and legible text |
| `ultra-max` | $0.02 per image | Finest detail and real typography |
| Video, 480p | $0.016 per second | 5 to 15 second clips, 24 fps, with sound |
| Video, 768p | $0.04 per second | 5 to 15 second clips, 24 fps, with sound |

Any orientation costs the same. You pay from a prepaid balance (from $5) that never expires; there is no subscription. New accounts get 3 free images, no card.

## Images

```python
image = client.images.generate(
    "a knight in ornate armor on a cliff at sunrise",
    model="anime",            # "anime" | "ultra" | "ultra-max"
    orientation="landscape",  # "portrait" (default) | "square" | "landscape"
    enhance=True,             # anime model: rewrite the prompt into tags (default true)
)

image.image_url           # https://animeapi.ai/i/….webp
image.enhanced_prompt     # what the model actually received
image.balance_usd         # balance after this charge
image.generation_time_ms  # about 4 s on anime, about 11 s on ultra
```

`client.generate("a prompt")` is a shortcut with the defaults.

AnimeAPI does not generate adult content. Explicit prompts are refused and not charged.

### Keeping the image

Image URLs are not permanent storage. Download what you want to keep:

```python
file = client.images.download(image)   # DownloadedFile(content=bytes, content_type=...)
file.save("girl.webp")
```

`anime` returns WebP; `ultra` and `ultra-max` return PNG.

## Async

```python
import asyncio
from animeapi import AsyncAnimeAPI

async def main():
    async with AsyncAnimeAPI() as client:
        image = await client.images.generate("a fox spirit shrine maiden at dusk")
        print(image.image_url)

asyncio.run(main())
```

The async client has the same methods as the sync one.

## Video

Video jobs are asynchronous. The price is charged when the job starts and refunded if it fails.

```python
# Start and wait in one call (a 5 second 480p clip costs $0.08):
video = client.videos.create_and_wait(
    "a girl with a red umbrella waits at a rainy bus stop, then looks up as the bus pulls in",
    resolution="480p",   # "480p" | "768p" (default)
    duration=5,          # 5 to 15 seconds
    orientation="landscape",
)
print(video.video_url)

# Or control the steps yourself:
job = client.videos.create("...", resolution="480p")
current = client.videos.get(job.id)                # status: "processing" | "succeeded" | "failed"
done = client.videos.wait(job.id, interval=5, timeout=600)
client.videos.download(done).save("clip.mp4")
```

Pass `first_frame` and/or `last_frame` (an image URL or a base64 data URI, up to 10 MB) to animate from or to an image.

## Models

```python
for model in client.models.list():
    print(model.id, "-", model.description)
```

## Error handling

Every failure raises an `AnimeAPIError` with `status`, `code` and `retryable`.

```python
from animeapi import AnimeAPI, AnimeAPIError, InsufficientBalanceError, ModerationError

try:
    client.images.generate(prompt)
except InsufficientBalanceError:
    ...  # top up at https://animeapi.ai/dashboard/billing
except ModerationError:
    ...  # the prompt was blocked
except AnimeAPIError as err:
    print(err.status, err.code, err.retryable, err.message)
```

| Status | `code` | Class | Retried automatically |
| --- | --- | --- | --- |
| 400 | (validation), `PROVIDER_REJECTED`, `INVALID_FRAME` | `InvalidRequestError` | no |
| 400 | `MODERATION_BLOCKED` | `ModerationError` | no |
| 401 | `INVALID_KEY` | `AuthenticationError` | no |
| 402 | `INSUFFICIENT_BALANCE` | `InsufficientBalanceError` | no |
| 404 | `NOT_FOUND` | `NotFoundError` | no |
| 429 | `RATE_LIMITED` | `RateLimitError` | when the API says it is retryable |
| 500 | `GENERATION_FAILED` | `GenerationError` | yes |
| 503 | `PROVIDER_UNAVAILABLE` | `ServiceUnavailableError` | yes, after `Retry-After` |
| none | `CONNECTION_ERROR` | `ConnectionError` | yes |
| none | `TIMEOUT` | `TimeoutError` | no |

A video that finishes with status `failed` raises `VideoFailedError` from `wait` (the charge has been refunded).

### Retries and timeouts

Retryable failures are tried again up to 2 more times with exponential back-off, and the SDK waits for the `Retry-After` header when the API sends one.

```python
import httpx

client = AnimeAPI(
    api_key="ank_...",
    max_retries=2,       # 0 turns retries off
    timeout=120,         # seconds, per request
    base_url="https://animeapi.ai",
    http_client=httpx.Client(proxy="http://localhost:8080"),  # bring your own httpx client
)

client.images.generate(prompt, timeout=30, max_retries=0)  # per request
```

## Already using the OpenAI client?

The official `openai` library works too: point its base URL at `https://animeapi.ai/v1`.

```python
from openai import OpenAI

openai_client = OpenAI(api_key="ank_...", base_url="https://animeapi.ai/v1")
result = openai_client.images.generate(model="anime", prompt="a fox spirit shrine maiden at dusk", size="1024x1024")
print(result.data[0].url)
```

Only the shape of `size` is used (square, portrait or landscape). `n` can be 1 to 4, and `response_format` can be `url` or `b64_json`.

## Links

- Docs: <https://animeapi.ai/docs>
- API reference: <https://animeapi.ai/docs/api-reference>
- OpenAPI: <https://animeapi.ai/openapi.json>
- JavaScript/TypeScript SDK: <https://github.com/animeapi-ai/animeapi-js>

MIT licence.
