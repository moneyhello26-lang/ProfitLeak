"""Serve a built SPA without hiding missing API routes or assets behind HTML."""

from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class FrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        normalized = path.replace("\\", "/")
        if normalized.split("/", 1)[0] == "api":
            raise HTTPException(status_code=404)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            # React routes are extensionless. Missing JS, CSV and images must
            # remain 404, including assets left in a browser after a new build.
            if (
                error.status_code != 404
                or "." in normalized
                or normalized.startswith(("assets/", "templates/"))
            ):
                raise
            response = await super().get_response("index.html", scope)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        return response


def mount_frontend(app: FastAPI, directory: Path | None) -> None:
    if directory is None:
        return
    directory = directory.resolve()
    if not (directory / "index.html").is_file():
        raise RuntimeError("FRONTEND_DIST must contain a built index.html; run the frontend build")
    app.mount("/", FrontendFiles(directory=directory, html=True), name="frontend")
