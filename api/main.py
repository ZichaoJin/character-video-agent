"""
FastAPI backend for MovieAgent.

Input (POST /generate):
  - story_title       : str  (Form)
  - events_json       : str  (Form) — JSON array of event titles, e.g. '["机场等待","到达酒店"]'
  - photos_0, photos_1, … : List[UploadFile]  (File) — photos for each event in order

Character reference photos are baked in on the server (CHARACTER_PHOTOS_PATH env var).

Run locally:
  cd MovieAgent-main
  pip install fastapi uvicorn python-multipart boto3
  uvicorn api.main:app --reload --port 8000
"""

import json
import os
import uuid
from pathlib import Path
from typing import List

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Security, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import JSONResponse

from api import jobs
from api.pipeline import JOBS_BASE_DIR, run_pipeline

app = FastAPI(title="MovieAgent API", version="1.0")

# ── auth ──────────────────────────────────────────────────────────────────────

_BEARER = HTTPBearer(auto_error=False)
# Require API_TOKEN to be provided via environment variable. Do NOT keep a
# hard-coded default here to avoid accidental public exposure.
_API_TOKEN: str = os.environ.get("API_TOKEN", "")


def verify_token(credentials: HTTPAuthorizationCredentials = Security(_BEARER)):
    if not _API_TOKEN:
        raise HTTPException(status_code=500, detail="Server misconfiguration: API_TOKEN not set")
    if credentials is None or credentials.credentials != _API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing token")


# ── helpers ───────────────────────────────────────────────────────────────────

def _save_upload(file: UploadFile, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = file.file.read()
    with open(dest, "wb") as f:
        f.write(content)
    return str(dest)


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate", dependencies=[Depends(verify_token)])
async def generate(
    background_tasks: BackgroundTasks,
    story_title: str = Form(..., description="故事标题"),
    events_json: str = Form(..., description='事件标题 JSON 数组，如 ["机场等待", "到达酒店"]'),
    # iOS sends photos_0, photos_1, ... as separate multipart fields
    photos_0: List[UploadFile] = File(default=[]),
    photos_1: List[UploadFile] = File(default=[]),
    photos_2: List[UploadFile] = File(default=[]),
    photos_3: List[UploadFile] = File(default=[]),
    photos_4: List[UploadFile] = File(default=[]),
    photos_5: List[UploadFile] = File(default=[]),
    photos_6: List[UploadFile] = File(default=[]),
    photos_7: List[UploadFile] = File(default=[]),
    photos_8: List[UploadFile] = File(default=[]),
    photos_9: List[UploadFile] = File(default=[]),
):
    # ── parse events ──────────────────────────────────────────────────────
    try:
        event_titles: list[str] = json.loads(events_json)
        if not isinstance(event_titles, list) or not event_titles:
            raise ValueError
    except Exception:
        raise HTTPException(status_code=400, detail="events_json must be a non-empty JSON array of strings")

    all_photo_fields = [
        photos_0, photos_1, photos_2, photos_3, photos_4,
        photos_5, photos_6, photos_7, photos_8, photos_9,
    ]

    # ── create job & save uploaded files ─────────────────────────────────
    job_id = str(uuid.uuid4())
    jobs.create(job_id)

    jdir = JOBS_BASE_DIR / job_id
    event_photo_paths: list[list[str]] = []

    for i, title in enumerate(event_titles):
        uploaded = all_photo_fields[i] if i < len(all_photo_fields) else []
        saved = []
        for j, f in enumerate(uploaded):
            if not f.filename:
                continue
            ext = Path(f.filename).suffix or ".jpg"
            dest = jdir / "events" / str(i) / f"{j:04d}{ext}"
            saved.append(_save_upload(f, dest))
        event_photo_paths.append(saved)

    # ── launch background pipeline ────────────────────────────────────────
    background_tasks.add_task(
        run_pipeline,
        job_id=job_id,
        story_title=story_title,
        event_titles=event_titles,
        event_photo_paths=event_photo_paths,
    )

    return {"job_id": job_id, "status": "queued"}


@app.get("/status/{job_id}", dependencies=[Depends(verify_token)])
def status(job_id: str):
    if not jobs.exists(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return jobs.get(job_id)


@app.delete("/jobs/{job_id}", dependencies=[Depends(verify_token)])
def delete_job(job_id: str):
    """Manually clean up a job's temp files."""
    import shutil
    jdir = JOBS_BASE_DIR / job_id
    if jdir.exists():
        shutil.rmtree(str(jdir), ignore_errors=True)
    return {"deleted": job_id}
