"""Serves the SARCADE web client (installable PWA) from the server itself.

The client then shares the API origin: no CORS, and it works on a local
network without Internet. Mounted last so it never shadows an API route.
"""
from pathlib import Path

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

# Files the browser must re-check at every start so a new client version is
# picked up; the hashed assets (main.dart.js, canvaskit) may be cached.
_REVALIDATE = {"", "index.html", "manifest.json", "flutter_bootstrap.js", "flutter_service_worker.js", "version.json"}


class _WebClientFiles(StaticFiles):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Mounted at "/", so the request path is the file path.
        relative = scope.get("path", "").lstrip("/")

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if relative in _REVALIDATE:
                    headers.append((b"cache-control", b"no-cache"))
                headers.append((b"x-content-type-options", b"nosniff"))
                message = {**message, "headers": headers}
            await send(message)

        await super().__call__(scope, receive, send_with_headers)


def mount_web_client(app: FastAPI, root: str | Path | None) -> bool:
    """Mounts the built web client at "/" when [root] holds an index.html."""
    if not root:
        return False
    directory = Path(root)
    if not (directory / "index.html").is_file():
        return False
    app.mount("/", _WebClientFiles(directory=directory, html=True), name="web-client")
    return True
