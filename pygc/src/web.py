"""FastAPI transport and packaged SPA hosting."""

import json
import os
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .rpc import error, handle, repository_methods


def create_app(static_dir: Path | None = None, *, directory: Path | None = None) -> FastAPI:
    app = FastAPI(title="Git-centric", version="0.1.0")

    methods = repository_methods(
        (directory or Path(os.environ.get("PYGC_WEB_REPO", "."))).resolve()
    )

    @app.post("/api/rpc")
    async def rpc(request: Request) -> Response:
        try:
            payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JSONResponse(error(-32700, "Parse error"))
        requests = payload if isinstance(payload, list) else [payload]
        read_methods = {
            "repo.get",
            "code.browse",
            "greet",
            "issues.list",
            "issues.show",
            "pulls.list",
            "pulls.show",
            "pulls.patch",
        }
        if any(
            isinstance(item, dict)
            and isinstance(item.get("method"), str)
            and item["method"] in methods
            and item["method"] not in read_methods
            for item in requests
        ):
            # Verify the peer as well as Host to protect non-loopback launches and DNS rebinding.
            local = {"localhost", "127.0.0.1", "::1"}
            origin = request.headers.get("origin")
            if (
                request.client is None
                or request.client.host not in local
                or request.url.hostname not in local
                or (
                    origin
                    and origin
                    not in {
                        f"{request.url.scheme}://{request.url.netloc}",
                        "http://localhost:5173",
                        "http://127.0.0.1:5173",
                    }
                )
            ):
                return JSONResponse({"detail": "Local access required"}, status_code=403)
        result = await run_in_threadpool(handle, payload, methods)
        return Response(status_code=204) if result is None else JSONResponse(result)

    # Keep unknown API routes from falling through to frontend files.
    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def unknown_api(path: str) -> Response:
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    assets = static_dir if static_dir is not None else Path(__file__).parent / "static"
    if (assets / "index.html").is_file():
        app.mount("/", StaticFiles(directory=assets, html=True), name="frontend")
    else:

        @app.get("/", response_class=HTMLResponse)
        async def frontend_not_built() -> str:
            return (
                "<h1>Git-centric API is running</h1>"
                "<p>Build the frontend: <code>cd frontend &amp;&amp; npm ci "
                "&amp;&amp; npm run build</code>, then restart gc web.</p>"
                "<p>For development, run <code>npm run dev</code> in frontend "
                "and open <a href='http://localhost:5173'>localhost:5173</a>.</p>"
            )

    return app
