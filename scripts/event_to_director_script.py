"""
根据「event 标题 + 该 event 的图片描述」生成该 event 的编剧导演稿。
导演稿包含：叙事、角色做什么动作、怎么动、运镜建议等，用于后续作为整体剧本的一部分。
"""
import json
import sys
from pathlib import Path

DIRECTOR_SCRIPT_SYSTEM = """你是一位短片编剧兼导演。根据「事件标题」和「根据现场照片得到的描述」，写一段该事件的**编剧导演稿**。
要求：
1. **叙事**：用 2～4 句话概括这个事件在演什么（时间、地点、谁在做什么）。
2. **角色动作与动势**：明确写出角色（用占位名如 布布、一二）分别做什么动作、怎么动（例如：布布在展厅里走动看画；一二双手捧着饺子端上桌）。
3. **运镜与镜头建议**：写出 2～5 个镜头的建议，要具体到景别和主体（人物/道具/局部）。**格式必须统一**：用连贯段落写，例如「首先，…。接着，…。然后，…。最后，…。」或「镜头一：…。镜头二：…。」不要用 1. 2. 3. 或「镜头建议：1. …」这种分点列表。
4. 风格：可直接用于后续自动分镜，所以动作和运镜要写清楚、可执行。
5. 全部用中文，不要用 markdown 标题，整段是一气呵成的导演稿，不要出现分点列表。"""


def generate_director_script_for_event(
    event_title: str,
    image_descriptions: list,
    characters: list,
    llm: str = "gpt4-o",
) -> str:
    """
    根据事件标题 + 图片描述列表，用 LLM 生成该事件的编剧导演稿（一段文字）。
    """
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from movie_agent.base_agent import BaseAgent

    parts = [f"事件标题：{event_title}"]
    if image_descriptions:
        parts.append("根据现场照片得到的描述：")
        for i, d in enumerate(image_descriptions, 1):
            parts.append(f"  图{i}：{d}")
    else:
        parts.append("（无图片描述，仅根据标题发挥）")
    parts.append(f"出镜角色（用这些名字写动作与运镜）：{', '.join(characters)}")
    user_content = "\n".join(parts)

    agent = BaseAgent(llm, system_prompt=DIRECTOR_SCRIPT_SYSTEM, use_history=False, temp=0.6)
    out = agent(user_content, parse=False)
    return (out or "").strip()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--event-title", required=True)
    p.add_argument("--descriptions", nargs="*", default=[], help="图片描述，可多句")
    p.add_argument("--characters", default='["布布", "一二"]', help="JSON 数组")
    p.add_argument("--llm", default="gpt4-o")
    args = p.parse_args()
    chars = json.loads(args.characters)
    text = generate_director_script_for_event(
        args.event_title,
        args.descriptions,
        chars,
        llm=args.llm,
    )
    print(text)
    sys.exit(0)
