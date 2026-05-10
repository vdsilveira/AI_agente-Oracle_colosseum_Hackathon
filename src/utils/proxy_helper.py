"""HTTP proxy configuration helper for YouTube-facing services."""

from ..config import config


def get_proxy_dict() -> dict[str, str]:
    """Return dict suitable for `requests`/`httpx` `proxies` parameter."""
    proxies = {}
    if config.HTTP_PROXY:
        proxies["http://"] = config.HTTP_PROXY
    if config.HTTPS_PROXY:
        proxies["https://"] = config.HTTPS_PROXY
    return proxies or None


def get_httpx_proxy() -> str | None:
    """Return proxy URL for httpx `proxy` parameter."""
    return config.HTTPS_PROXY or config.HTTP_PROXY or None


def get_ytdlp_proxy() -> str | None:
    """Return proxy URL for yt-dlp `proxy` option."""
    return config.HTTPS_PROXY or config.HTTP_PROXY or None


def is_proxy_configured() -> bool:
    """Check if any proxy is configured."""
    return bool(config.HTTP_PROXY or config.HTTPS_PROXY)
