from starlette.responses import JSONResponse

from app.core.config import get_settings


class OriginMiddleware:
    """Reject unsafe browser requests sent from a different, untrusted origin."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        original_send = send

        async def private_response(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (key, value)
                    for key, value in message["headers"]
                    if key.lower() != b"cache-control"
                ] + [(b"cache-control", b"no-store")]
            await original_send(message)

        if (
            scope["type"] == "http"
            and scope["path"].startswith("/api/v1/")
            and scope["path"] != "/api/v1/health"
        ):
            send = private_response
        if (
            scope["type"] == "http"
            and scope["path"].startswith("/api/v1/")
            and scope["method"] not in {"GET", "HEAD", "OPTIONS"}
        ):
            headers = dict(scope["headers"])
            origin = headers.get(b"origin", b"").decode("latin-1")
            host = headers.get(b"host", b"").decode("latin-1")
            same_origin = f"{scope.get('scheme', 'http')}://{host}"
            valid_origin = origin in get_settings().cors_origins or origin == same_origin
            # Command-line clients omit Origin. Browser fetch metadata must still be
            # checked when present, including opaque origins and absent Origin headers.
            cross_site = headers.get(b"sec-fetch-site") == b"cross-site"
            if (origin and not valid_origin) or (not origin and cross_site):
                response = JSONResponse(
                    status_code=403,
                    content={
                        "detail": {
                            "code": "csrf_origin",
                            "message": "Запрос с этого сайта запрещён.",
                        }
                    },
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
