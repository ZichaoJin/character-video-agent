"""
画风图 → GPT-4V 描述 → 缓存。
用户把「画风参考图」放在 dataset/xxx/style_reference/ 下，本模块用 GPT-4V 看图生成
「场景与事物的画风」描述，写入 scene_style.txt，供 Replicate 每镜 prompt 前注入。
"""
import os
from pathlib import Path


def _image_to_data_uri(path: str) -> str:
    with open(path, "rb") as f:
        b64 = __import__("base64").standard_b64encode(f.read()).decode("utf-8")
    ext = Path(path).suffix.lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    return f"data:{mime};base64,{b64}"


def get_scene_style_text(style_reference_dir: str, cache_path: str = None) -> str:
    """
    从 style_reference_dir 读取所有图片（.png/.jpg/.jpeg），用 GPT-4V 生成一段
    「场景与事物的画风」描述；若提供 cache_path 则写入并优先读缓存。
    返回描述字符串，无图或失败时返回空字符串。
    """
    root = Path(style_reference_dir)
    if not root.is_dir():
        return ""
    if cache_path and Path(cache_path).exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    images = []
    for ext in (".png", ".jpg", ".jpeg"):
        for p in sorted(root.glob(f"*{ext}")):
            if p.is_file():
                images.append(_image_to_data_uri(str(p)))
    if not images:
        return ""

    try:
        from openai import OpenAI
    except ImportError:
        return ""
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    prompt = (
        "以下图片仅用于提取「画面风格」描述。\n\n"
        "【必须只描述画面风格，不要描述角色或人物】"
        "不要描述图中任何人/角色/形象的长相、服装、动作、是谁。"
        "禁止在描述中出现任何动物名（如熊猫、熊、狗、猫等），不要用动物类型概括画风。"
        "只描述：画风类型（如 2D 卡通、扁平、厚涂、简笔）、线条风格（圆润/硬朗/粗细）、"
        "颜色与饱和度（高饱和/低饱和/冷暖色调）、明暗与光影、整体氛围、画面质感。"
        "用一段简洁的中文（可夹少量英文关键词）概括上述风格，便于文生图时场景与事物统一。"
        "只输出这段风格描述，不要标题或解释，控制在 200 字以内。"
    )
    content = [{"type": "text", "text": prompt}]
    for uri in images[:10]:  # 最多 10 张，避免超长
        content.append({"type": "image_url", "image_url": {"url": uri}})

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": content}],
        max_tokens=400,
    )
    text = (resp.choices[0].message.content or "").strip()
    if cache_path and text:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(text)
    return text
