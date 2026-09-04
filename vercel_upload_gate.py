"""Vercel-only HTTP upload authorization for pinned Streamlit 1.59.2.

Native Streamlit upload routes check XSRF and an active session, but not the
application's Admin identity. This narrowly wraps PUT/DELETE before the native
handler reads a request body. Both the server's live AppSession identity and
Streamlit's cryptographically verified request cookie must pass the existing
Google Admin gate. Public sessions and password mode cannot upload here.

This intentionally depends on private, version-pinned Streamlit APIs. A version
or factory-shape change stops server startup; re-audit this module before any
Streamlit upgrade. It does not solve multi-instance upload/session affinity.
Normal ``streamlit run app.py`` and the manual Excel workflow are unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import wraps
import inspect
import json
import sys
import time
from urllib.parse import urlsplit

import admin_auth


SUPPORTED_STREAMLIT_VERSION = "1.59.2"
STARTUP_ERROR = "Secure screenshot upload handling is unavailable. Server startup stopped."
DENIED_MESSAGE = "Admin sign-in is required to upload or remove screenshots."
_installed = False


def upload_is_authorized(request, runtime) -> bool:
    """Only trust server-owned identity and signed, origin-bound native cookies."""
    try:
        from streamlit.auth_util import get_origin_from_redirect_uri
        from streamlit.runtime.secrets import secrets_singleton
        from streamlit.web.server.starlette.starlette_server_config import USER_COOKIE_NAME
        from streamlit.web.server.starlette.starlette_websocket import (
            _get_signed_cookie_with_chunks,
        )

        if not admin_auth.race_import_enabled(secrets=secrets_singleton):
            return False
        config = admin_auth.load_admin_config(secrets_singleton)
        if config is None or not admin_auth.oidc_is_configured(secrets_singleton):
            return False

        session_id = request.path_params.get("session_id")
        if not isinstance(session_id, str) or not 1 <= len(session_id) <= 128:
            return False
        # This is the live server-side session created from verified WebSocket
        # authentication, never session_state or claims supplied in a request.
        info = runtime._session_mgr.get_active_session_info(session_id)
        if info is None or info.client is None:
            return False
        session_claims = info.session._user_info
        if not isinstance(session_claims, Mapping):
            return False
        now = time.time()
        if admin_auth.evaluate_admin_state(
            enabled=True, config=config, claims=dict(session_claims), now=now
        ) is not admin_auth.AdminState.AUTHORIZED:
            return False

        origin = get_origin_from_redirect_uri()
        if not isinstance(origin, str):
            return False
        parsed = urlsplit(origin)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            return False
        if request.headers.get("host", "").casefold() != parsed.netloc.casefold():
            return False
        if request.headers.get("origin", origin) != origin:
            return False
        if len(request.headers.get("cookie", "")) > 32768:
            return False

        # The helper validates every cookie chunk using the configured signing
        # secret and native age policy. A session id alone grants no upload.
        decoded = _get_signed_cookie_with_chunks(dict(request.cookies), USER_COOKIE_NAME)
        if not isinstance(decoded, bytes) or len(decoded) > 32768:
            return False
        claims = json.loads(decoded)
        if not isinstance(claims, dict) or claims.get("origin") != origin:
            return False
        return admin_auth.evaluate_admin_state(
            enabled=True, config=config, claims=claims, now=now
        ) is admin_auth.AdminState.AUTHORIZED
    except Exception:
        # Malformed cookies, unavailable config, incompatible APIs: fail closed
        # without logging request data, signatures, or credential values.
        return False


def _guard_handler(handler, runtime):
    @wraps(handler)
    async def guarded(request):
        from starlette.exceptions import HTTPException

        if not upload_is_authorized(request, runtime):
            raise HTTPException(status_code=403, detail=DENIED_MESSAGE)
        # Do not read/parse the body here. Preserve native size/XSRF/CORS checks.
        return await handler(request)

    return guarded


def install_upload_gate() -> None:
    """Replace only the factory reference used by the pinned Starlette app."""
    global _installed
    import streamlit
    from starlette.routing import Route
    from streamlit.web.server.starlette import starlette_app, starlette_routes

    if streamlit.__version__ != SUPPORTED_STREAMLIT_VERSION:
        raise RuntimeError(STARTUP_ERROR)
    if _installed:
        if not getattr(starlette_app.create_upload_routes, "_f1_admin_upload_gate", False):
            raise RuntimeError(STARTUP_ERROR)
        return
    original = starlette_routes.create_upload_routes
    if (
        starlette_app.create_upload_routes is not original
        or tuple(inspect.signature(original).parameters) != ("runtime", "upload_mgr", "base_url")
    ):
        raise RuntimeError(STARTUP_ERROR)

    @wraps(original)
    def create_guarded_upload_routes(runtime, upload_mgr, base_url):
        routes = original(runtime, upload_mgr, base_url)
        expected = {frozenset({"PUT"}), frozenset({"DELETE"}), frozenset({"OPTIONS"})}
        if len(routes) != 3 or {frozenset(route.methods or ()) for route in routes} != expected:
            raise RuntimeError(STARTUP_ERROR)
        protected = []
        for route in routes:
            if not isinstance(route, Route) or not route.path.endswith("/_stcore/upload_file/{session_id}/{file_id}"):
                raise RuntimeError(STARTUP_ERROR)
            if route.methods == {"OPTIONS"}:
                protected.append(route)
            else:
                protected.append(Route(
                    route.path, _guard_handler(route.endpoint, runtime),
                    methods=list(route.methods), name=route.name,
                ))
        return protected

    create_guarded_upload_routes._f1_admin_upload_gate = True
    starlette_app.create_upload_routes = create_guarded_upload_routes
    _installed = True


def main() -> None:
    try:
        install_upload_gate()
    except Exception:
        print(STARTUP_ERROR, file=sys.stderr)
        raise SystemExit(1) from None
    from streamlit.web import cli

    cli.main(prog_name="streamlit")


if __name__ == "__main__":
    main()
