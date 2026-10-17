from starlette.responses import JSONResponse

from app.services.import_parser import MAX_UPLOAD_BYTES


class UploadLimitMiddleware:
    """Bound the full request before multipart parsing or temporary file creation."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") not in {
            "/api/v1/imports/preview",
            "/api/v1/imports/confirm",
            "/api/v1/cash/statements/preview",
            "/api/v1/cash/statements/confirm",
        }:
            return await self.app(scope, receive, send)
        # Allow a small multipart envelope in addition to the 10 MB file.
        limit = MAX_UPLOAD_BYTES + 64 * 1024
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > limit:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "detail": {
                            "code": "file_too_large",
                            "message": "Файл превышает лимит 10 МБ.",
                        }
                    },
                )
                return await response(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
