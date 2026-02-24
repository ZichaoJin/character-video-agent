#!/usr/bin/env python3
from __future__ import annotations

"""
将「故事标题 + 多个 events（每个含 title + 图片）」转为 MovieAgent 可用的 script_synopsis.json。

流程：
1. 对每个 event：用视觉模型看该 event 的每张图 + event title，生成图片描述。
2. 对每个 event：用 LLM 根据「event title + 图片描述」生成该 event 的**编剧导演稿**（角色动作、怎么动、运镜等）。
3. 把所有 event 的导演稿按顺序拼成整部剧本（MovieScript），并写入 script_synopsis.json。

输入 JSON 格式示例（如 story_input.json）：
{
  "story_title": "匹兹堡之旅",
  "characters": ["布布", "一二"],
  "events": [
    { "title": "我和宝宝一起去逛艺术馆啦", "image_paths": ["path/to/art1.jpg", "path/to/art2.jpg"] },
    { "title": "宝宝给我包饺子啦", "image_paths": ["path/to/dumpling1.jpg"], "caption": "可选：补充说明" }
  ]
}

若某 event 没有 image_paths，则仅用 title（和可选 caption）生成该 event 的导演稿。

用法：
  python scripts/story_to_script.py story_input.json -o dataset/布布一二_PittsburghTrip/script_synopsis.json --llm gpt4-o
  python scripts/story_to_script.py story_input.json --no-images   # 不使用图片，仅用 title/caption
"""

import argparse
import json
import sys
from pathlib import Path


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parent


def _describe_event_images(image_paths: list, event_title: str, vision_model: str):
    """对单个 event 的图片做视觉描述。"""
    if not image_paths:
        return []
    sd = _scripts_dir()
    if str(sd) not in sys.path:
        sys.path.insert(0, str(sd))
    from image_to_description import describe_images_batch
    return describe_images_batch(image_paths, event_title=event_title, model=vision_model)


def _director_script_for_event(event_title: str, image_descriptions: list, characters: list, llm: str):
    """生成单个 event 的编剧导演稿。"""
    repo = Path(__file__).resolve().parents[1]
    sd = _scripts_dir()
    for p in (sd, repo):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    from event_to_director_script import generate_director_script_for_event
    return generate_director_script_for_event(event_title, image_descriptions, characters, llm=llm)


def build_simple_synopsis(story_title: str, events: list, characters: list) -> str:
    """无 LLM/无图片时：用 event 的 title（和可选 caption）拼成一段梗概。"""
    parts = [f"{story_title}。由{''.join(characters)}两位角色演绎。"]
    for ev in events:
        title = ev.get("title", "").strip()
        caption = ev.get("caption", "").strip()
        if title:
            parts.append(title)
        if caption:
            parts.append(caption)
    return " ".join(parts)


def run_with_images_and_director_script(
    story_title: str,
    events: list,
    characters: list,
    llm: str,
    vision_model: str,
    no_images: bool,
) -> tuple[str, list[dict]]:
    """
    对每个 event：若有多图则先做图片描述，再生成导演稿；否则仅用 title/caption 生成导演稿。
    返回 (完整 MovieScript 文本, 每个 event 的详情列表)。
    """
    event_results = []
    director_parts = []

    for idx, ev in enumerate(events):
        title = ev.get("title", "").strip()
        caption = ev.get("caption", "").strip()
        image_paths = ev.get("image_paths") or []
        if no_images:
            image_paths = []

        # 1) 图片描述
        image_descriptions = []
        if image_paths:
            abs_paths = []
            cwd = Path.cwd()
            for p in image_paths:
                path = Path(p)
                if not path.is_absolute():
                    path = cwd / path
                if path.exists():
                    abs_paths.append(str(path))
            image_descriptions = _describe_event_images(abs_paths, title, vision_model)

        # 2) 该 event 的导演稿（含角色动作、运镜）
        if image_descriptions or title or caption:
            # 无图时把 caption 当“唯一描述”传给导演稿
            if not image_descriptions and caption:
                image_descriptions = [caption]
            script_text = _director_script_for_event(title, image_descriptions, characters, llm=llm)
        else:
            script_text = f"【{title}】无描述与图片，保留为占位。"
        director_parts.append(script_text)
        event_results.append({
            "event_index": idx + 1,
            "event_title": title,
            "image_descriptions": image_descriptions,
            "director_script": script_text,
        })

    # 3) 整部剧本：按顺序拼接各 event 的导演稿，并加故事标题
    full_script = f"{story_title}\n\n" + "\n\n".join(director_parts)
    return full_script, event_results


def load_story_input(input_path: str) -> tuple[Path, dict]:
    """
    支持两种输入：
    1) 单个 JSON 文件：直接读取，events 里用 image_paths 或 caption。
    2) 目录（如 我的故事）：读取该目录下 story_config.json；每个 event 若有 image_folder，
       则从 目录/events_photos/{image_folder}/ 下收集所有 .jpg/.png/.jpeg 作为 image_paths（绝对路径）。
    返回 (config_dir_or_json_parent, data_dict)。
    """
    path = Path(input_path).resolve()
    if path.is_dir():
        config_file = path / "story_config.json"
        if not config_file.exists():
            raise FileNotFoundError(f"目录模式下需要存在 {config_file}")
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        events_photos_root = path / "events_photos"
        events = []
        for ev in data.get("events", []):
            ev = dict(ev)
            folder_name = ev.pop("image_folder", None)
            if folder_name and events_photos_root.is_dir():
                folder = events_photos_root / folder_name
                if folder.is_dir():
                    image_paths = []
                    for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
                        image_paths.extend(folder.glob(ext))
                    ev["image_paths"] = [str(p.resolve()) for p in sorted(set(image_paths))]
                    ev["_scan_dir"] = str(folder.resolve())
                else:
                    ev["image_paths"] = []
                    ev["_scan_dir"] = str(folder.resolve())
            else:
                if "image_paths" not in ev:
                    ev["image_paths"] = []
                ev["_scan_dir"] = ""
            events.append(ev)
        data["events"] = events
        return path, data
    else:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return path.parent, data


def main():
    parser = argparse.ArgumentParser(description="Story + Events（含图片）-> 编剧导演稿 -> script_synopsis.json")
    parser.add_argument("input_json", type=str, help="输入：story_config.json 路径，或「我的故事」目录（内含 story_config.json 和 events_photos/）")
    parser.add_argument("-o", "--output", type=str, default=None, help="输出 script_synopsis.json 路径")
    parser.add_argument("--llm", type=str, default="gpt4-o", help="用于生成导演稿的 LLM，如 gpt4-o / deepseek-v3")
    parser.add_argument("--vision-model", type=str, default="gpt-4o", help="用于看图的视觉模型，如 gpt-4o")
    parser.add_argument("--no-images", action="store_true", help="不使用图片，仅用每个 event 的 title 和 caption 生成导演稿")
    parser.add_argument("--save-events", type=str, default=None, help="可选：把每个 event 的导演稿与图片描述保存到此 JSON 文件")
    args = parser.parse_args()

    config_dir, data = load_story_input(args.input_json)

    story_title = data.get("story_title", "未命名故事")
    characters = data.get("characters", ["布布", "一二"])
    events = data.get("events", [])

    for i, ev in enumerate(events):
        paths = ev.get("image_paths") or []
        n = len(paths)
        if n:
            print(f"Event {i+1}「{ev.get('title', '')[:20]}…」: 使用 {n} 张图片生成描述并参与导演稿。")
        else:
            print(f"Event {i+1}「{ev.get('title', '')[:20]}…」: 未找到图片，仅用标题/caption 生成。")
            if ev.get("_scan_dir"):
                print(f"  （已扫描目录: {ev['_scan_dir']}）")

    if not events:
        synopsis = build_simple_synopsis(story_title, [], characters)
        event_results = []
    else:
        synopsis, event_results = run_with_images_and_director_script(
            story_title, events, characters,
            llm=args.llm,
            vision_model=args.vision_model,
            no_images=args.no_images,
        )

    result = {
        "MovieScript": synopsis,
        "Character": characters,
    }

    out_path = args.output or (config_dir.parent / "script_synopsis.json")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("Wrote:", out_path)

    if args.save_events and event_results:
        events_path = Path(args.save_events)
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with open(events_path, "w", encoding="utf-8") as f:
            json.dump({"story_title": story_title, "events": event_results}, f, ensure_ascii=False, indent=2)
        print("Wrote events:", events_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
