"""Start the existing Streamlit app with private, runtime-only cloud secrets.

The deployment supplies ``F1_STREAMLIT_SECRETS_TOML`` as a sensitive, server-side
environment variable. This module never logs its value or writes it into the
source tree. Authentication and workbook authorization remain in admin_auth.py
and race_github.py; loading settings does not itself grant access.

Streamlit 1.59.2 declares ``secrets.files`` as a repeated CLI option in
lib/streamlit/config.py and lib/streamlit/web/cli.py. Passing one explicit path
replaces its default search locations. The file lives for the container's
lifetime because a successful exec replaces this process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import tomllib
from collections.abc import MutableMapping


SECRETS_ENV = "F1_STREAMLIT_SECRETS_TOML"
FEATURE_FLAG = "F1_ENABLE_RACE_IMPORT"
MAX_SECRET_BYTES = 32 * 1024
MAX_VALUE_BYTES = 16 * 1024
MAX_ITEMS = 256
MAX_DEPTH = 6
SOURCE_ROOT = Path(__file__).resolve().parent
CONFIGURATION_ERROR = "Server configuration is invalid. Admin access remains closed."
STARTUP_ERROR = "The server could not start securely. Check the deployment configuration."
_ALLOWED_SECTIONS = frozenset({"auth", "admin_auth", "github"})
_KEY_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,95}\Z")


class ConfigurationError(ValueError):
    """A deliberately generic error that must never contain secret content."""


@dataclass(frozen=True)
class LaunchPlan:
    command: tuple[str, ...]
    environment: dict[str, str] = field(repr=False)
    secret_file: Path | None = None


def _validate_secret_text(raw: str) -> bytes:
    """Accept bounded TOML settings, not arbitrary exported environment keys.

    Provider/identity/permission semantics are validated by the existing gates.
    This boundary checks syntax and shape before Streamlit can parse or log a
    malformed file. Root scalars other than the feature flag are prohibited;
    the legacy root feature flag is accepted but removed from the runtime file.
    Streamlit exports root scalars into the process environment, so keeping it
    would override the explicit deployment flag (including a disabled default).
    """
    try:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError
        # Check characters before allocating the encoded copy as well.
        if len(raw) > MAX_SECRET_BYTES or "\x00" in raw:
            raise ValueError
        encoded = raw.encode("utf-8", errors="strict")
        if len(encoded) > MAX_SECRET_BYTES:
            raise ValueError
        parsed = tomllib.loads(raw)
        if not parsed or not set(parsed) <= _ALLOWED_SECTIONS | {FEATURE_FLAG}:
            raise ValueError
        for name in _ALLOWED_SECTIONS & parsed.keys():
            if not isinstance(parsed[name], dict) or not parsed[name]:
                raise ValueError
        if FEATURE_FLAG in parsed and type(parsed[FEATURE_FLAG]) not in (str, int, bool):
            raise ValueError

        pending = [(parsed, 0)]
        count = 0
        while pending:
            value, depth = pending.pop()
            count += 1
            if depth > MAX_DEPTH or count > MAX_ITEMS:
                raise ValueError
            if isinstance(value, dict):
                for name, child in value.items():
                    if not _KEY_PATTERN.fullmatch(name):
                        raise ValueError
                    pending.append((child, depth + 1))
            elif isinstance(value, list):
                if len(value) > MAX_ITEMS:
                    raise ValueError
                pending.extend((child, depth + 1) for child in value)
            elif isinstance(value, str):
                if "\x00" in value or len(value.encode("utf-8")) > MAX_VALUE_BYTES:
                    raise ValueError
            elif type(value) is float:
                if not math.isfinite(value):
                    raise ValueError
            elif type(value) not in (bool, int):
                # Dates/times and other TOML types are not needed by our config.
                raise ValueError
        # Streamlit 1.59.2 uses the legacy ``toml`` package for secrets. Check
        # that parser too: otherwise a TOML-1.0-only construct accepted above
        # could fail later and cause Streamlit to print an error with its value.
        import toml

        if toml.loads(raw) != parsed:
            raise ValueError
        if FEATURE_FLAG in parsed:
            del parsed[FEATURE_FLAG]
            if not parsed:
                raise ValueError
            canonical = toml.dumps(parsed)
            if tomllib.loads(canonical) != parsed or toml.loads(canonical) != parsed:
                raise ValueError
            encoded = canonical.encode("utf-8")
            if len(encoded) > MAX_SECRET_BYTES:
                raise ValueError
        return encoded
    except Exception:
        # TOML parser errors can quote the source value. Never propagate them.
        raise ConfigurationError(CONFIGURATION_ERROR) from None


def cleanup_secret_file(secret_file: Path | None) -> None:
    """Remove only the exact private file/directory created by this launcher."""
    if secret_file is None:
        return
    try:
        secret_file.unlink(missing_ok=True)
        secret_file.parent.rmdir()
    except OSError:
        # Never expose a deployment path or secret through cleanup diagnostics.
        pass


def _write_runtime_secret(payload: bytes) -> Path:
    temp_root = Path(tempfile.gettempdir()).resolve()
    # A deployment override of TMPDIR must not put secrets into copied sources.
    if temp_root.is_relative_to(SOURCE_ROOT):
        raise ConfigurationError(CONFIGURATION_ERROR)
    secret_file: Path | None = None
    descriptor: int | None = None
    try:
        directory = Path(tempfile.mkdtemp(prefix="f1-runtime-", dir=temp_root))
        secret_file = directory / "secrets.toml"
        if os.name == "posix":
            directory.chmod(0o700)
        descriptor = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        if os.name == "posix":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None  # the context manager now owns this descriptor
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return secret_file
    except Exception:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        cleanup_secret_file(secret_file)
        raise ConfigurationError(CONFIGURATION_ERROR) from None


def prepare_launch(environ: MutableMapping[str, str] | None = None) -> LaunchPlan:
    """Remove the raw secret first, then build a non-shell Streamlit command."""
    environment = os.environ if environ is None else environ
    raw = environment.pop(SECRETS_ENV, None)
    # Explicitly closed when no feature flag was supplied, including local runs.
    environment.setdefault(FEATURE_FLAG, "0")
    port = environment.get("PORT", "80") or "80"
    if not re.fullmatch(r"[0-9]{1,5}", port) or not 1 <= int(port) <= 65535:
        raise ConfigurationError(CONFIGURATION_ERROR)
    secret_file = None
    if raw is not None:
        payload = _validate_secret_text(raw)
        # Drop local references as soon as the private runtime file exists.
        secret_file = _write_runtime_secret(payload)
        del payload
    del raw
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(SOURCE_ROOT / "app.py"),
        "--server.address=0.0.0.0",
        f"--server.port={port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    if secret_file is not None:
        command.append(f"--secrets.files={secret_file}")
    return LaunchPlan(tuple(command), dict(environment), secret_file)


def main() -> int:
    plan = None
    try:
        plan = prepare_launch()
        os.execve(sys.executable, plan.command, plan.environment)
        return 0  # execve does not return on success; useful for mocked tests.
    except ConfigurationError:
        print(CONFIGURATION_ERROR, file=sys.stderr)
    except Exception:
        print(STARTUP_ERROR, file=sys.stderr)
    if plan is not None:
        cleanup_secret_file(plan.secret_file)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
