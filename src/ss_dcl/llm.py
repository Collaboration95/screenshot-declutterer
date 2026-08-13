"""LiteRT-LM client: health probing, retry classification, name suggestion, PNG normalization.

All LiteRT network interaction lives here. The server process lifecycle
(start/stop/pidfile ownership) is managed by :mod:`src.ss_dcl.server`.
"""

import base64
import errno
import io
import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

LITERT_BASE_URL = os.environ.get("LITERT_BASE_URL", "http://localhost:9379")
LITERT_HEALTH_TIMEOUT = 3  # seconds
_LITERT_HEALTH_TTL = 5.0  # seconds
_litert_health_cache: tuple[float, bool] | None = None


def reset_health_cache() -> None:
    """Force the next :func:`_litert_healthy` call to probe the server."""
    global _litert_health_cache
    _litert_health_cache = None


def _is_retryable_llm_error(exc: BaseException) -> bool:
    """Return True if *exc* is transient and worth retrying.

    Unwraps ``urllib.error.URLError`` (whose ``.reason`` may itself be an
    exception) and classifies the underlying cause.  Connection refused and
    DNS lookup failures mean the server is down — retrying is futile — while
    timeouts, resets, broken pipes, HTTP 429 and HTTP 5xx are transient.
    Unrecognized errors default to retryable to stay conservative.
    """
    if isinstance(exc, urllib.error.HTTPError):
        # HTTPError is a URLError subclass carrying an HTTP status code.
        return exc.code == 429 or exc.code >= 500

    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, BaseException):
            return _is_retryable_llm_error(reason)
        # Non-exception reason (e.g. plain string) — unknown, stay conservative.
        return True

    # socket.timeout is an alias of TimeoutError since Python 3.10.
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, (ConnectionResetError | BrokenPipeError)):
        return True
    if isinstance(exc, socket.gaierror):
        return False
    if isinstance(exc, ConnectionRefusedError):
        return False
    if isinstance(exc, OSError):
        if exc.errno == errno.ECONNREFUSED:
            return False
        if exc.errno in (errno.EPIPE, errno.ECONNRESET):
            return True
        # Unknown OSError (possibly no errno) — conservative default.
        return True
    return True


def _sanitize_suggestion(raw: str, extension: str = ".png") -> str | None:
    """Turn a raw LLM reply into a safe kebab-case filename.

    Lowercases, replaces spaces with hyphens, strips punctuation, collapses
    repeated hyphens, truncates to 120 chars, and appends *extension*
    (leading dot included, e.g. ".jpg").
    """
    sanitized = raw.lower().replace(" ", "-")
    sanitized = "".join(c for c in sanitized if c.isalnum() or c in "-_")
    # Collapse repeated hyphens (from multi-space / punctuation gaps)
    while "--" in sanitized:
        sanitized = sanitized.replace("--", "-")
    # Truncate then strip so trailing hyphen after slice is removed
    sanitized = sanitized[:120].strip("-_")
    if not sanitized:
        return None
    return sanitized + extension


def _image_to_png_data_uri(image_path: Path) -> str:
    """Normalize any supported image to a PNG base64 data URI.

    PNG/JPG pass through a Pillow re-encode; BMP/TIFF (whose raw base64 can be
    tens of MB) collapse to a few KB. Also strips alpha (convert("RGB")), which
    some vision encoders reject.
    """
    with Image.open(image_path) as im:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _call_litert_suggest(image_path: Path, model: str, extension: str = ".png") -> str | None:
    """Call the LiteRT-LM OpenAI-compatible server with an image.

    Returns a sanitized suggested filename (extension included), or None on
    failure. Retries up to 2 times on transient errors with 1s/2s backoff,
    fails fast on permanent ones.
    """
    max_retries = 2
    data_uri = _image_to_png_data_uri(image_path)

    prompt = (
        "Describe this screenshot in 3-5 words as a filename. "
        "Return only the filename, no explanation, no quotes."
    )

    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
            "max_tokens": 40,
            "stream": False,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{LITERT_BASE_URL}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    raw = ""
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                choices = result.get("choices") or []
                raw = choices[0].get("message", {}).get("content", "").strip() if choices else ""
                break
        except json.JSONDecodeError as exc:
            logger.warning("LiteRT returned malformed JSON for %s: %s", image_path.name, exc)
            return None
        except (urllib.error.URLError, OSError) as exc:
            if not _is_retryable_llm_error(exc):
                logger.warning(
                    "LiteRT unreachable for %s, not retrying: %s",
                    image_path.name,
                    exc,
                )
                return None
            if attempt < max_retries:
                wait = 2**attempt
                logger.warning(
                    "LiteRT attempt %d/%d failed for %s, retrying in %ds: %s",
                    attempt + 1,
                    max_retries + 1,
                    image_path.name,
                    wait,
                    exc,
                )
                time.sleep(wait)
            else:
                logger.warning(
                    "LiteRT suggest failed after %d attempts for %s: %s",
                    max_retries + 1,
                    image_path.name,
                    exc,
                )
                return None

    if not raw:
        return None
    return _sanitize_suggestion(raw, extension)


def _litert_healthy() -> bool:
    """Cheap reachability probe for the LiteRT-LM server (GET /v1/models).

    Negative AND positive verdicts are cached for ``_LITERT_HEALTH_TTL``
    seconds so a down server is probed at most once per batch instead of
    once per file.
    """
    global _litert_health_cache
    now = time.monotonic()
    if _litert_health_cache is not None and now - _litert_health_cache[0] < _LITERT_HEALTH_TTL:
        return _litert_health_cache[1]

    ok = False
    try:
        with urllib.request.urlopen(
            f"{LITERT_BASE_URL}/v1/models", timeout=LITERT_HEALTH_TIMEOUT
        ) as resp:
            ok = resp.status == 200
    except (urllib.error.URLError, OSError):
        ok = False

    _litert_health_cache = (time.monotonic(), ok)
    return ok
