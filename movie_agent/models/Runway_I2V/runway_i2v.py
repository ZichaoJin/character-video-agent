"""
用 Runway API 图生视频，不依赖本地 GPU。
优先使用官方 SDK (pip install runwayml)，否则用 requests。
需环境变量 RUNWAYML_API_SECRET 或 RUNWAY_API_KEY。
"""
import os
import time
import base64
import requests
from pathlib import Path
from typing import Optional

RUNWAY_API_BASE = os.environ.get("RUNWAY_API_BASE", "https://api.dev.runwayml.com/v1")
RUNWAY_VERSION = "2024-11-06"

_MAX_DATA_URI_BYTES = 3_500_000  # data URI 约 5MB 限制，预留余量
RUNWAY_W, RUNWAY_H = 1280, 720  # Runway 固定 16:9，关键帧是 1024x512 会被裁掉下边，需先垫黑


def _pad_to_16_9(image_path: str) -> bytes:
    """把关键帧 pad 成 1280x720（16:9），保留完整画面不裁切，上下或左右黑边。"""
    from PIL import Image
    import io
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    img = Image.open(path).convert("RGB")
    w, h = img.size
    target_w, target_h = RUNWAY_W, RUNWAY_H
    scale = min(target_w / w, target_h / h)
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    out = Image.new("RGB", (target_w, target_h), (0, 0, 0))
    paste_x = (target_w - new_w) // 2
    paste_y = (target_h - new_h) // 2
    out.paste(img, (paste_x, paste_y))
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _image_to_data_uri(image_path: str, size_hint: Optional[tuple] = None) -> str:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    # 关键帧常为 1024x512 (2:1)，Runway 输出 1280x720 会裁掉上下；先 pad 成 16:9 再发
    use_pad = size_hint is not None and (size_hint == (1024, 512) or size_hint[0] / max(size_hint[1], 1) > 1.5)
    if use_pad:
        data = _pad_to_16_9(image_path)
        mime = "image/jpeg"
    else:
        with open(path, "rb") as f:
            data = f.read()
        ext = path.suffix.lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        if len(data) > _MAX_DATA_URI_BYTES:
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(data)).convert("RGB")
                img.thumbnail((RUNWAY_W, RUNWAY_H), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                data = buf.getvalue()
                mime = "image/jpeg"
            except Exception:
                pass
    b64 = base64.standard_b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _get_api_key() -> str:
    # 官方文档用 RUNWAYML_API_SECRET，兼容 RUNWAY_API_KEY
    key = (os.environ.get("RUNWAYML_API_SECRET") or os.environ.get("RUNWAY_API_KEY") or "").strip()
    if not key:
        raise ValueError("请设置环境变量 RUNWAYML_API_SECRET（或 RUNWAY_API_KEY）")
    return key


class Runway_I2V_pipe:
    def __init__(self, model: str = "gen4_turbo", duration: int = 2, ratio: str = "1280:720"):
        self.model = model
        self.duration = max(2, min(10, duration))
        self.ratio = ratio
        self._api_key = _get_api_key()

    def predict(self, prompt, image_path, video_save_path, size=(1024, 512)):
        """
        调用 Runway image_to_video：上传关键帧 + prompt，轮询任务结果，下载视频到 video_save_path。
        优先用官方 SDK (runwayml)，否则用 requests。
        """
        prompt_image_uri = _image_to_data_uri(image_path, size_hint=size)
        # 显式指定关键帧为视频第一帧（避免被当作尾帧或参考）
        prompt_image_payload = [{"position": "first", "uri": prompt_image_uri}]
        # 把 plot 传给 Runway，同时保留面部特征 / 注入运镜 / 禁止字幕
        safe_plot = (prompt or "").strip()[:300]
        prompt_text = (
            (safe_plot + ". ") if safe_plot else ""
        ) + (
            "CRITICAL: Maintain the exact same visual style, color palette, line style, and overall aesthetic as the input keyframe image. "
            "Do not change the rendering style. Do not switch to photorealistic. Every visual element must look identical in style to the input frame. "
            "Preserve the characters' facial features exactly as shown in the input image. "
            "Keep all facial details faithful to the reference frame at all times. "
            "Do not generate any facial movement, mouth opening, or expression not present in the input image. "
            "Only apply the camera movement specified in the prompt; do not add any unspecified motion. "
            "No text. No subtitles. No captions. No watermarks."
        )
        duration_int = max(2, min(10, int(self.duration) if self.duration is not None else 2))

        task_id = None
        try:
            from runwayml import RunwayML
            client = RunwayML(api_key=self._api_key)
            task = client.image_to_video.create(
                model=str(self.model),
                prompt_image=prompt_image_payload,
                prompt_text=prompt_text,
                ratio=str(self.ratio),
                duration=duration_int,
            )
            task_id = getattr(task, "id", None) or (task if isinstance(task, str) else None)
        except ImportError:
            pass
        except Exception as e:
            if "400" in str(e) or "Bad Request" in str(e):
                raise RuntimeError(f"Runway 400 (SDK): {e}") from e
            raise

        if not task_id:
            # 使用 requests
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "X-Runway-Version": RUNWAY_VERSION,
                "Content-Type": "application/json",
            }
            body = {
                "model": str(self.model),
                "promptImage": prompt_image_payload,
                "promptText": prompt_text,
                "ratio": str(self.ratio),
                "duration": duration_int,
            }
            r = requests.post(
                f"{RUNWAY_API_BASE}/image_to_video",
                headers=headers,
                json=body,
                timeout=30,
            )
            if r.status_code == 401:
                raise RuntimeError(
                    "Runway 401 Unauthorized。请设置 RUNWAYML_API_SECRET，并在同一终端 export 后再运行。"
                ) from None
            if r.status_code == 400:
                raw = (r.text or "")[:1200]
                raise RuntimeError(f"Runway 400 Bad Request。完整响应: {raw}") from None
            r.raise_for_status()
            task_id = r.json().get("id")

        if not task_id:
            raise RuntimeError("Runway API did not return task id")

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "X-Runway-Version": RUNWAY_VERSION,
        }
        # 轮询任务
        while True:
            tr = requests.get(f"{RUNWAY_API_BASE}/tasks/{task_id}", headers=headers, timeout=30)
            tr.raise_for_status()
            data = tr.json()
            status = data.get("status", "").upper()
            if status == "SUCCEEDED":
                outputs = data.get("output") or []
                if not outputs:
                    raise RuntimeError("Runway task succeeded but no output")
                out_url = outputs[0] if isinstance(outputs[0], str) else outputs[0].get("url")
                break
            if status in ("FAILED", "CANCELLED", "ABORTED"):
                raise RuntimeError(f"Runway task {status}: {data.get('failure', data)}")
            time.sleep(6)

        # 下载视频
        Path(video_save_path).parent.mkdir(parents=True, exist_ok=True)
        vr = requests.get(out_url, timeout=120)
        vr.raise_for_status()
        with open(video_save_path, "wb") as f:
            f.write(vr.content)
        return image_path
