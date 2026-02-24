"""
用 GPT-4V 看布布、一二等角色参考图，生成一段「外观+画风」描述，
供 DALL·E 每镜生成时注入 prompt，使角色一致、像布布一二。
支持每个角色多角度：正面、斜侧面、侧面、背面（见 VIEW_ORDER）。
"""
import os
import base64
from pathlib import Path
from typing import List, Tuple

# 每个角色目录下可放多角度图，按此顺序读取（文件名不含扩展名）
# 若没有任何角度图，则回退到 best.png / best.jpg
VIEW_ORDER = [
    ("front", "正面"),
    ("oblique", "斜侧面"),
    ("side", "侧面"),
    ("back", "背面"),
]


def _image_to_data_uri(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.standard_b64encode(f.read()).decode("utf-8")
    ext = Path(path).suffix.lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    return f"data:{mime};base64,{b64}"


def _collect_character_images(subdir: Path) -> List[Tuple[str, str]]:
    """返回 (角度名, data_uri) 列表。优先多角度，没有则用 best。"""
    out = []
    for key, _ in VIEW_ORDER:
        for ext in (".png", ".jpg", ".jpeg"):
            p = subdir / f"{key}{ext}"
            if p.exists():
                out.append((key, _image_to_data_uri(str(p))))
                break
    if out:
        return out
    for name in ("best.png", "best.jpg"):
        p = subdir / name
        if p.exists():
            return [("best", _image_to_data_uri(str(p)))]
    return []


def get_character_style_text(character_photo_path: str, cache_path: str = None) -> str:
    """
    从 character_photo_path 下各角色目录读取参考图（支持正面/斜侧面/侧面/背面，或单张 best），
    用 GPT-4V 生成一段「角色外观与画风」描述；若提供 cache_path 则写入并优先读缓存。
    返回描述字符串，无图或失败时返回空字符串。
    """
    root = Path(character_photo_path)
    if not root.is_dir():
        return ""
    if cache_path and Path(cache_path).exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    # 每个角色：多角度 (front, oblique, side, back) 或单张 best
    images = []
    view_names = {k: label for k, label in VIEW_ORDER}
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            continue
        pairs = _collect_character_images(sub)
        for key, uri in pairs:
            label = view_names.get(key, "参考") if key != "best" else "整体"
            images.append((sub.name, label, uri))
    if not images:
        return ""

    try:
        from openai import OpenAI
    except ImportError:
        return ""
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    prompt = (
        "以下图片按顺序提供：每个角色依次为其「正面、斜侧面、侧面、背面」（仅包含存在的角度），角色按目录名排序。"
        "请综合这些角度，用一段简洁的中文描述（可夹少量英文关键词）概括：1) 角色整体画风（如卡通、圆润、可爱）；"
        "2) 各角色从各角度可见的外观、发型、服装与造型；3) 便于文生图时每张图都保持同一画风、角色一致。"
        "禁止用动物种类（如熊猫、熊、狗、猫等）来概括角色，只描述外观与画风。"
        "只输出这段描述，不要标题或解释，控制在 200 字以内。"
    )
    content = [{"type": "text", "text": prompt}]
    for name, label, uri in images:
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
