from pathlib import Path

import requests
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response


ROOT = Path(__file__).resolve().parent.parent
RENDER_BASE = "https://everly-clinic.onrender.com"

app = FastAPI(title="Everly Clinic Vercel Fallback")


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_api(path: str, request: Request):
    url = f"{RENDER_BASE}/api/{path}"
    body = await request.body()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length", "connection"}
    }
    try:
        upstream = requests.request(
            request.method,
            url,
            params=dict(request.query_params),
            data=body or None,
            headers=headers,
            timeout=60,
        )
    except requests.RequestException as exc:
        return Response(
            f'{{"ok":false,"detail":"Render API proxy failed: {exc}"}}',
            status_code=502,
            media_type="application/json",
        )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


@app.get("/assets/{path:path}")
def assets(path: str):
    target = (ROOT / "assets" / path).resolve()
    if not str(target).startswith(str((ROOT / "assets").resolve())) or not target.exists():
        return Response("Not found", status_code=404)
    return FileResponse(target)


@app.get("/{path:path}")
def dashboard(path: str = ""):
    return FileResponse(ROOT / "dashboard.html")
