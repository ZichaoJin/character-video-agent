"""
用视觉模型（Vision API）看一张或多张图，生成用于编剧/导演稿的文本描述。
支持 OpenAI GPT-4o 多图输入；单图时也可用。
"""
import base64
import json
import os
import sys
from pathlib import Path


def _image_to_base64_url(image_path: str) -> str:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    with open(path, "rb") as f:
        b64 = base64.standard_b64encode(f.read()).decode("utf-8")
    suffix = path.suffix.lower()
    mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png" if suffix == ".png" else "image/webp"
    return f"data:{mime};base64,{b64}"


def describe_images_with_vision(
    image_paths: list,
    prompt: str = "用一两句话描述这张图：场景、人物在做什么、重要物品或动作。用于后续写短片分镜。",
    model: str = "gpt-4o",
) -> list[str]:
    """
    对每张图调用 vision API，返回描述列表（与 image_paths 一一对应）。
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("需要 openai: pip install openai")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    descriptions = []
    for i, ip in enumerate(image_paths):
        url = _image_to_base64_url(ip)
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": url}},
        ]
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            max_tokens=300,
        )
        text = (resp.choices[0].message.content or "").strip()
        descriptions.append(text)
    return descriptions


def describe_images_batch(
    image_paths: list,
    event_title: str = "",
    prompt_template: str = "事件标题：{event_title}\n请针对下面这张图，用一两句话描述：场景、人物在做什么、重要物品或动作。用于后续写短片分镜。",
    model: str = "gpt-4o",
) -> list[str]:
    """对多张图逐张调用 vision，带 event 上下文。"""
    prompt = prompt_template.format(event_title=event_title or "（无标题）").strip()
    return describe_images_with_vision(image_paths, prompt=prompt, model=model)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("image_paths", nargs="+", help="图片路径")
    p.add_argument("--event-title", default="", help="事件标题，会放进 prompt")
    p.add_argument("--model", default="gpt-4o")
    args = p.parse_args()
    descs = describe_images_batch(args.image_paths, event_title=args.event_title, model=args.model)
    for path, d in zip(args.image_paths, descs):
        print(path, "->", d)
    sys.exit(0)
