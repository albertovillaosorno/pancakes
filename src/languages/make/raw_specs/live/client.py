# ruff: noqa: S310
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001041#repo.make-scraper.raw-specs.live-scraping-disabled-by-default
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Small documented Make API client for raw-spec retrieval.

Boundary contract:
- Owns: authenticated HTTPS JSON requests for explicit live scraper runs.
- Must not: write raw specs, parse catalog schema, decide sync targets, or
cache.
- Allows: injected transport, retry handling, and scraper-local error mapping.
- Split when: client needs new auth modes, pagination policies, or endpoints.
- Merge when: another live client performs the same Make API request contract.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Final, NamedTuple, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from languages.make.raw_specs.live.errors import (
    MakeApiConfigurationError,
    MakeApiError,
    MakeApiRateLimitError,
    MakeApiRemoteError,
)
from languages.make.raw_specs.live.http import (
    HttpResponseLike,
    JsonQuery,
    default_sleep,
)
from languages.make.raw_specs.live.payloads import ensure_json_object

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from languages.make.raw_specs.models import JsonObject

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_RETRIES = 3
DEFAULT_HTTP_429_BACKOFF_SECONDS = (30.0, 60.0, 150.0)
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Codex/1.0"
HTTPS_PREFIX = "https://"
HTTP_TOO_MANY_REQUESTS = 429
CURRENT_IMT_APP_VERSION = "current"
IMT_PATH_TOKEN_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")


class MakeApiClientConfig(NamedTuple):
    """Credential and transport configuration for Make API calls."""

    api_token: str | None
    zone: str | None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_rate_limit_retries: int = DEFAULT_RETRIES
    http_429_backoff_seconds: tuple[float, ...] = (
        DEFAULT_HTTP_429_BACKOFF_SECONDS
    )
    user_agent: str = DEFAULT_USER_AGENT


class MakeApiClient:
    """Authenticated Make API client used only by explicit live scraper runs."""

    def __init__(
        self,
        config: MakeApiClientConfig,
        *,
        opener: Callable[[Request, float], HttpResponseLike] | None = None,
        sleeper: Callable[[float], None] = default_sleep,
    ) -> None:
        """Store injected transport dependencies."""
        self._config = config
        self._opener = opener or _open_url
        self._sleeper = sleeper

    def get_json(
        self, path: str, *, query: JsonQuery | None = None
    ) -> JsonObject:
        """Execute one GET request and require a JSON object response.

        Returns:
            The JSON object returned by the GET request.
        """
        return self.request_json("GET", path, query=query)

    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: JsonQuery | None = None,
        body: JsonObject | None = None,
    ) -> JsonObject:
        """Execute one request and parse an object payload.

        Returns:
            The parsed object payload returned by the request.
        """
        payload_bytes = _body_bytes(body)
        request = _https_request(
            url=self._build_url(path=path, query=query),
            data=payload_bytes,
            headers=self._headers(
                include_json_content_type=payload_bytes is not None
            ),
            method=method.upper(),
        )
        return self._execute_with_retries(
            request=request, method=method.upper(), path=path
        )

    def list_imt_apps(
        self, *, organization_id: str, search: str | None = None
    ) -> JsonObject:
        """List IMT app summaries visible to one organization.

        Returns:
            The documented result.
        """
        query: JsonQuery = {"organizationId": organization_id}
        if search is not None and search.strip():
            query["search"] = search.strip()
        return self.get_json("/imt/apps", query=query)

    def get_imt_app(self, *, app_slug: str, app_version: str) -> JsonObject:
        """Fetch one IMT app raw specification.

        Returns:
            The documented result.
        """
        safe_slug = _imt_path_token(app_slug, label="app_slug")
        safe_version = _imt_path_token(app_version, label="app_version")
        if safe_version == CURRENT_IMT_APP_VERSION:
            return self.get_json(f"/imt/apps/{safe_slug}")
        return self.get_json(f"/imt/apps/{safe_slug}/{safe_version}")

    def get_imt_app_explicit_version(
        self, *, app_slug: str, app_version: str
    ) -> JsonObject:
        """Fetch one IMT app through the explicit versioned endpoint.

        Returns:
            The documented result.
        """
        safe_slug = _imt_path_token(app_slug, label="app_slug")
        safe_version = _imt_path_token(app_version, label="app_version")
        return self.get_json(f"/imt/apps/{safe_slug}/{safe_version}")

    def _execute_with_retries(
        self,
        *,
        request: Request,
        method: str,
        path: str,
    ) -> JsonObject:
        attempts = max(0, self._config.max_rate_limit_retries) + 1
        for attempt in range(1, attempts + 1):
            try:
                with self._opener(
                    request, self._config.timeout_seconds
                ) as response:
                    return ensure_json_object(
                        response.read(), label=f"{method} {path}"
                    )
            except HTTPError as exc:
                if exc.code != HTTP_TOO_MANY_REQUESTS or attempt >= attempts:
                    raise _remote_error(exc, method=method, path=path) from exc
                retry_delay = _retry_delay(
                    exc, attempt, self._config.http_429_backoff_seconds
                )
                _close_http_error(exc)
                self._sleeper(retry_delay)
            except URLError as exc:
                message = (
                    f"Make API transport failure for {method} {path}:"
                    f"{exc.reason}"
                )
                raise MakeApiRemoteError(message) from exc
        message = "Make API rate limit reached after retry exhaustion."
        raise MakeApiRateLimitError(message)

    def _headers(self, *, include_json_content_type: bool) -> dict[str, str]:
        token = str(self._config.api_token or "").strip()
        if not token:
            message = "Make API token is required for live scraping."
            raise MakeApiConfigurationError(message)
        headers = {
            "Accept": "application/json ",
            "Authorization": f"Token {token}",
            "User-Agent": self._config.user_agent,
        }
        if include_json_content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def _build_url(
        self, *, path: str, query: Mapping[str, object] | None
    ) -> str:
        normalized_path = path if path.startswith("/") else f"/{path}"
        url = f"{self._base_url()}{normalized_path}"
        if not query:
            return url
        encoded = urlencode(
            {key: _query_value(value) for key, value in query.items()},
        )
        return f"{url}?{encoded}"

    def _base_url(self) -> str:
        zone = str(self._config.zone or "").strip().lower()
        if not zone:
            message = "Make API zone is required for live scraping."
            raise MakeApiConfigurationError(message)
        host = zone if zone.endswith(".make.com") else f"{zone}.make.com"
        return f"https://{host}/api/v2"


def _https_request(
    *,
    url: str,
    data: bytes | None,
    headers: dict[str, str],
    method: str,
) -> Request:
    """Build a request only after enforcing the HTTPS scheme.

    Returns:
        The built request only after enforcing the HTTPS scheme.

    Raises:
        MakeApiConfigurationError: If the Make API client configuration is
        invalid.
    """
    if not url.startswith(HTTPS_PREFIX):
        message = f"Make API URL must use HTTPS: {url}"
        raise MakeApiConfigurationError(message)
    return Request(url, data=data, headers=headers, method=method)


def _open_url(request: Request, timeout_seconds: float) -> HttpResponseLike:
    """Open one URL through the standard library transport.

    Returns:
        The opened URL through the standard library transport.
    """
    return cast("HttpResponseLike", urlopen(request, timeout=timeout_seconds))


def _body_bytes(body: JsonObject | None) -> bytes | None:
    """Return canonical request bytes when a body is present."""
    if body is None:
        return None
    return json.dumps(body, ensure_ascii=True, sort_keys=True).encode("utf-8")


def _query_value(value: object) -> str:
    """Return one query value as Make-compatible text."""
    return str(value).lower() if isinstance(value, bool) else str(value)


def _imt_path_token(value: str, *, label: str) -> str:
    """Return a safe IMT endpoint path segment.

    Raises:
        MakeApiConfigurationError: If the token would alter the endpoint path.
    """
    token = value.strip()
    if not IMT_PATH_TOKEN_PATTERN.fullmatch(token) or set(token) <= {"."}:
        message = (
            f"Make API IMT {label} must be a plain path token using letters, "
            "numbers, dash, underscore, or dot."
        )
        raise MakeApiConfigurationError(message)
    return token


def _retry_delay(
    exc: HTTPError, attempt: int, fallback_seconds: tuple[float, ...]
) -> float:
    """Resolve retry delay from Retry-After or fallback backoff.

    Returns:
        The resolved retry delay from Retry-After or fallback backoff.
    """
    header = exc.headers.get("Retry-After")
    if header is not None:
        try:
            parsed = float(header)
        except ValueError:
            parsed = 0.0
        if parsed > 0:
            return parsed
    if not fallback_seconds:
        return 1.0
    index = min(max(0, attempt - 1), len(fallback_seconds) - 1)
    return max(1.0, fallback_seconds[index])


def _close_http_error(exc: HTTPError) -> None:
    """Drain and close one retryable HTTP error response."""
    _ = exc.read()
    exc.close()


def _remote_error(exc: HTTPError, *, method: str, path: str) -> MakeApiError:
    """Map one HTTP error into a scraper-local exception.

    Returns:
        The scraper-local exception for the HTTP error.
    """
    try:
        response_body = (
            exc.read().decode("utf-8", errors="replace")[:400].strip()
        )
    finally:
        exc.close()
    message = f"Make API failed for {method} {path} with status {exc.code}."
    if response_body:
        message = f"{message} Response: {response_body}"
    if exc.code == HTTP_TOO_MANY_REQUESTS:
        return MakeApiRateLimitError(message)
    return MakeApiRemoteError(message)
