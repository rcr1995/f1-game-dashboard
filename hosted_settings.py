"""Non-secret hosting settings, shared without granting any write capability."""

from collections.abc import Mapping
import os
from urllib.parse import urlsplit


DEFAULT_DASHBOARD_URL = "https://f1puskasleague.vercel.app/"


def dashboard_url(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    value = env.get("F1_PUBLIC_DASHBOARD_URL", DEFAULT_DASHBOARD_URL)
    if any(character.isspace() or ord(character) < 32 for character in value) or "\\" in value:
        return DEFAULT_DASHBOARD_URL
    try:
        parsed = urlsplit(value)
        _ = parsed.port  # Also validate nonnumeric/out-of-range ports.
    except ValueError:
        return DEFAULT_DASHBOARD_URL
    if (value != value.strip() or parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        return DEFAULT_DASHBOARD_URL
    return value.rstrip("/") + "/"


def validate_publisher_target(publisher: object, environ: Mapping[str, str] | None = None) -> None:
    """An enabled hosted reader and its Admin writer must use one workbook."""
    import public_workbook

    source = public_workbook.configuration(environ)
    if source is None:
        return
    for field in ("owner", "repository", "branch", "workbook_path"):
        expected, actual = getattr(source, field), getattr(publisher, field, None)
        if field in {"owner", "repository"} and isinstance(actual, str):
            actual, expected = actual.casefold(), expected.casefold()
        if actual != expected:
            raise ValueError("The Admin publisher and public dashboard must use the same GitHub workbook.")
