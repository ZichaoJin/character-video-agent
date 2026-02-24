"""
MovieAgent pipeline runner for a single job.
Called from main.py as a background task.

Environment variables required:
  OPENAI_API_KEY
  GOOGLE_API_KEY (or GEMINI_API_KEY)
  RUNWAYML_API_SECRET
  S3_BUCKET           e.g. my-movieagent-bucket
  CHARACTER_PHOTOS_PATH  absolute path to the baked-in character_list directory
                          e.g. /app/character_photos/character_list

Optional:
  LLM_MODEL           default gpt4-o
  AWS_DEFAULT_REGION  default ap-southeast-1
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

import boto3

from api import jobs

# 保证同一时刻只有一个 job 在进行 module reload + agent 初始化，避免并发时状态污染
_PIPELINE_LOCK = threading.Lock()

# ── paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.resolve()
MOVIE_AGENT_DIR = REPO_ROOT / "movie_agent"
SCRIPTS_DIR = REPO_ROOT / "scripts"

CHARACTER_PHOTOS_PATH = os.environ.get(
    "CHARACTER_PHOTOS_PATH",
    str(REPO_ROOT / "dataset" / "character_list"),
)
S3_BUCKET = os.environ.get("S3_BUCKET", "")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt4-o")

JOBS_BASE_DIR = Path(tempfile.gettempdir()) / "movieagent_jobs"


# ── helpers ───────────────────────────────────────────────────────────────────

def _job_dir(job_id: str) -> Path:
    d = JOBS_BASE_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _upload_to_s3(local_path: str, job_id: str) -> str:
    """Upload final video and return a 24h presigned URL."""
    if not S3_BUCKET:
        raise RuntimeError("S3_BUCKET env var is not set")
    s3 = boto3.client("s3", region_name=AWS_REGION)
    key = f"jobs/{job_id}/final.mp4"
    s3.upload_file(local_path, S3_BUCKET, key, ExtraArgs={"ContentType": "video/mp4"})
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=86400,  # 24h
    )
    return url


# ── main pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(
    job_id: str,
    story_title: str,
    event_titles: list[str],
    event_photo_paths: list[list[str]],  # [[path, ...], [path, ...], ...]
    characters: list[str] | None = None,
):
    """
    Full pipeline: story_config → script_synopsis → MovieAgent → S3.
    event_photo_paths[i] = list of saved file paths for events[i].
    Characters are taken from CHARACTER_PHOTOS_PATH directory names if not provided.
    """
    try:
        jdir = _job_dir(job_id)

        # ── 1. infer characters from character_list dirs ───────────────────
        jobs.update(job_id, status="running", progress=5, step="initializing")
        if not characters:
            char_root = Path(CHARACTER_PHOTOS_PATH)
            if char_root.is_dir():
                characters = sorted(
                    d.name for d in char_root.iterdir()
                    if d.is_dir() and not d.name.startswith(".")
                )
            else:
                characters = ["Character 1", "Character 2"]

        # ── 2. write story_config.json ─────────────────────────────────────
        jobs.update(job_id, progress=10, step="building story config")
        events = []
        for i, title in enumerate(event_titles):
            photos = event_photo_paths[i] if i < len(event_photo_paths) else []
            events.append({"title": title, "image_paths": photos})

        story_config = {
            "story_title": story_title,
            "characters": characters,
            "events": events,
        }
        config_path = jdir / "story_config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(story_config, f, ensure_ascii=False, indent=2)

        # ── 3. run story_to_script → script_synopsis.json + events detail ──
        jobs.update(job_id, progress=15, step="generating script synopsis")
        script_synopsis_path = jdir / "script_synopsis.json"
        events_detail_path = jdir / "events_detail.json"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "story_to_script.py"),
                str(config_path),
                "-o", str(script_synopsis_path),
                "--llm", LLM_MODEL,
                "--save-events", str(events_detail_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        if result.returncode != 0:
            raise RuntimeError(f"story_to_script failed:\n{result.stderr[-2000:]}")

        # ── 4. build ScriptBreakAgent args namespace ───────────────────────
        jobs.update(job_id, progress=25, step="planning scenes & shots")
        with _PIPELINE_LOCK:
            # module reload 必须在锁内执行，避免并发 reload 导致模块状态混乱
            if str(MOVIE_AGENT_DIR) not in sys.path:
                sys.path.insert(0, str(MOVIE_AGENT_DIR))
            import importlib
            run_mod = importlib.reload(importlib.import_module("run"))
            ScriptBreakAgent = run_mod.ScriptBreakAgent
            load_config = run_mod.load_config

        video_save_path = jdir / "video"
        video_save_path.mkdir(exist_ok=True)

        args = SimpleNamespace(
            LLM=LLM_MODEL,
            gen_model="Gemini",
            audio_model="NoAudio",
            talk_model=None,
            Image2Video="Runway",
            script_path=str(script_synopsis_path),
            character_photo_path=CHARACTER_PHOTOS_PATH,
            save_path=str(jdir / "results"),
            video_save_path=str(video_save_path),
            resume_from_shots=False,
            skip_existing_keyframes=False,
            only_first_scene=False,
            only_planning=False,
            crossfade=0.1,
            final_name="final",
            scene_style_text="",
        )
        # load model configs
        for model_name in ("Gemini", "Runway"):
            cfg = load_config(model_name)
            for k, v in cfg.items():
                if not getattr(args, k, None):
                    setattr(args, k, v)

        # ── 5. run pipeline ────────────────────────────────────────────────
        # chdir 已删除：load_config 改为用 __file__ 的绝对路径，不再依赖 CWD
        agent = ScriptBreakAgent(
            args,
            sample_model=args.gen_model,
            audio_model=args.audio_model,
            talk_model=args.talk_model,
            Image2Video=args.Image2Video,
            script_path=str(script_synopsis_path),
            character_photo_path=CHARACTER_PHOTOS_PATH,
            save_mode="video",
        )
        # override save paths to job dir
        agent.save_path = str(jdir / "results")
        agent.video_save_path = str(video_save_path)

        # ── 直接从 events_detail 构造 Step_1，跳过 ScriptBreak LLM ──────────
        jobs.update(job_id, progress=30, step="building sub-scripts")
        synopsis_data = json.loads(script_synopsis_path.read_text(encoding="utf-8"))
        all_chars = synopsis_data.get("Character", characters)
        sub_script_dict = {}
        if events_detail_path.exists():
            events_data = json.loads(events_detail_path.read_text(encoding="utf-8"))
            for i, ev in enumerate(events_data.get("events", []), 1):
                sub_script_dict[f"Sub-Script {i}"] = {
                    "Plot": ev.get("director_script") or ev.get("event_title", ""),
                    "Involving Characters": all_chars,
                    "Timeline": ev.get("event_title", f"Event {i}"),
                    "Reason for Division": f"Event {i}: {ev.get('event_title', '')}",
                }
        else:
            # fallback：整段剧本作为单一 Sub-Script
            sub_script_dict["Sub-Script 1"] = {
                "Plot": synopsis_data.get("MovieScript", ""),
                "Involving Characters": all_chars,
                "Timeline": "Full story",
                "Reason for Division": "Single event",
            }
        # 构造 Relationships
        rels = {}
        if len(all_chars) >= 2:
            rels[f"{all_chars[0]} - {all_chars[1]}"] = "Friends"
        step1 = {"Relationships": rels, "Sub-Script": sub_script_dict}
        Path(agent.sub_script_path).parent.mkdir(parents=True, exist_ok=True)
        Path(agent.sub_script_path).write_text(
            json.dumps(step1, ensure_ascii=False, indent=4), encoding="utf-8"
        )

        jobs.update(job_id, progress=45, step="ScenePlanning")
        agent.ScenePlanning()

        jobs.update(job_id, progress=55, step="ShotPlotCreate")
        agent.ShotPlotCreate()

        jobs.update(job_id, progress=65, step="generating keyframes & video")
        agent.VideoAudioGen()

        jobs.update(job_id, progress=90, step="concatenating clips")
        agent.Final(crossfade=args.crossfade, final_name=args.final_name)

        # ── 6. upload to S3 ────────────────────────────────────────────────
        jobs.update(job_id, progress=95, step="uploading to S3")
        final_video = str(video_save_path / "final.mp4")
        if not os.path.isfile(final_video):
            raise FileNotFoundError(f"Final video not found: {final_video}")

        video_url = _upload_to_s3(final_video, job_id)

        jobs.update(job_id, status="done", progress=100, step="done", video_url=video_url)

    except Exception as e:
        import traceback
        jobs.update(job_id, status="error", error=traceback.format_exc()[-3000:])
        raise

    finally:
        # clean up job workdir to save disk space (comment out to keep for debug)
        # shutil.rmtree(str(jdir), ignore_errors=True)
        pass
