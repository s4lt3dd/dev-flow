"""GET /health — Jira connectivity check."""

import requests as _requests
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    pipeline = request.app.state.pipeline
    jira_ok = False
    jira_detail = "not configured"

    if pipeline.jira_exporter:
        try:
            url = f"{pipeline.jira_exporter.base_url}/rest/api/3/myself"
            resp = _requests.get(
                url,
                auth=pipeline.jira_exporter._auth,
                headers=pipeline.jira_exporter._headers,
                timeout=5,
            )
            jira_ok = resp.ok
            jira_detail = "connected" if resp.ok else f"HTTP {resp.status_code}: {resp.text[:120]}"
        except Exception as exc:
            jira_detail = str(exc)

    return {
        "status": "ok",
        "jira": {"connected": jira_ok, "detail": jira_detail},
        "transcriber": pipeline.transcriber is not None,
    }