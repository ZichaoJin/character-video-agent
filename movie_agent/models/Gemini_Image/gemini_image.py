"""
用 Google Gemini（Nano Banana）图+文生图 API 生成每镜关键帧，支持 1～2 张参考图，双人/画风表现较好。
接口与 GenModel.predict 一致：prompt 为镜头描述，refer_image 为参考图路径列表（1 或 2 张），结果保存到 save_path。
需安装: pip install google-genai，环境变量: GOOGLE_API_KEY 或 GEMINI_API_KEY。
"""
import os
from pathlib import Path


def _build_contents(refer_image, prompt_text):
    """构建 Gemini 多模态 contents：参考图最多 8 张（多方向）+ 文本 prompt。"""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise ImportError("请安装 google-genai: pip install google-genai") from None

    parts = []
    ref_list = [p for p in (refer_image if isinstance(refer_image, (list, tuple)) else [refer_image]) if p and os.path.isfile(p)]
    for path in ref_list[:8]:  # 最多 8 张参考图（多方向）
        with open(path, "rb") as f:
            data = f.read()
        ext = Path(path).suffix.lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))
    parts.append(prompt_text)
    return parts


def _save_response_image(response, save_path):
    """从 generate_content 的 response 里取出图片并保存。"""
    if not response or not response.candidates:
        raise RuntimeError("Gemini 未返回有效内容")
    for part in response.candidates[0].content.parts:
        if getattr(part, "inline_data", None) and getattr(part.inline_data, "data", None):
            with open(save_path, "wb") as f:
                f.write(part.inline_data.data)
            return
    raise RuntimeError("Gemini 返回中未找到生成的图片（可能被安全策略拦截）")


class Gemini_Image_pipe:
    """Gemini Nano Banana（图+文生图）关键帧管道，支持双图参考。"""

    DEFAULT_MODEL = "gemini-3-pro-image-preview"  # Nano Banana Pro（Gemini 3 Pro Image）

    def __init__(
        self,
        model: str = None,
        character_photo_path: str = None,
        scene_style_text: str = None,
        api_key: str = None,
    ):
        self.model = model or self.DEFAULT_MODEL
        self.character_photo_path = character_photo_path or ""
        self.scene_style_text = (scene_style_text or "").strip()
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
            except ImportError:
                raise ImportError("请安装 google-genai: pip install google-genai") from None
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def predict(self, prompt, refer_image, character_box, save_path, size=(1024, 512)):
        """
        用 Gemini 以 1～2 张参考图 + 文本生成一张图，保存到 save_path。
        双人镜时 refer_image 为 [角色1图, 角色2图]，直接传两张，无需拼图。
        """
        client = self._get_client()
        if not self._api_key:
            raise RuntimeError("请设置环境变量 GOOGLE_API_KEY 或 GEMINI_API_KEY")

        raw_list = refer_image if isinstance(refer_image, (list, tuple)) else [refer_image]
        ref_list = [p for p in raw_list if p and os.path.isfile(p)]
        if not ref_list and self.character_photo_path:
            # 从 character_list 取四方向（无 best），每角色 front/oblique/side/back
            root = Path(self.character_photo_path)
            if root.is_dir():
                dirs = sorted(d for d in root.iterdir() if d.is_dir() and not d.name.startswith("."))[:2]
                for sub in dirs:
                    for direc in ("front", "oblique", "side", "back"):
                        for ext in (".png", ".jpg", ".PNG", ".JPG"):
                            p = sub / (direc + ext)
                            if p.exists():
                                ref_list.append(str(p))
                                break
                    if len(ref_list) >= 8:
                        break
        if not ref_list:
            raise FileNotFoundError("Gemini 需要至少一张参考图，请提供 refer_image 或 character_photo_path 下角色图。")

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        scene_desc = (prompt or "").strip()[:1500] or "两个角色在一起的场景"
        if len(ref_list) > 1:
            print(f"[Gemini] 本镜参考图: {len(ref_list)} 张（多方向）")
        else:
            print(f"[Gemini] 本镜参考图: {ref_list[0]}")

        # 推断本镜角色数：统计 ref_list 中属于 character_photo_path 子目录的不同目录数
        char_count = 1
        char_photo_groups = []  # [(dir_name, count), ...] 按 ref_list 顺序，用于多角色分组标注
        if self.character_photo_path:
            root = Path(self.character_photo_path).resolve()
            from collections import OrderedDict
            _dir_groups: "OrderedDict[str, int]" = OrderedDict()
            for p in ref_list:
                parent = Path(p).parent.resolve()
                if parent.parent.resolve() == root:
                    _dir_groups[parent.name] = _dir_groups.get(parent.name, 0) + 1
            if _dir_groups:
                char_count = len(_dir_groups)
                char_photo_groups = list(_dir_groups.items())  # [(name, count), ...]

        # 道具/特写镜（无角色）：只复刻画风，不画人物；角色镜：按实际角色数动态生成 prompt
        no_text_rule = "不要在图片上添加任何文字、字幕、标签或水印。\n"
        closeup_style_rule = (
            "特别注意：即使是表情特写或大头构图，面部细节（线条、眼睛画法、阴影、色彩）"
            "也必须与参考图的绘画美术风格完全一致，不要因为是特写就切换到写实照片风格。\n"
        )
        is_prop_shot = not character_box
        if is_prop_shot:
            prompt = (
                "我上传的参考图定义了本片所有画面的美术风格——包括线条、色彩、笔触、整体画面质感。\n"
                "请严格按照参考图的美术风格画一张特写构图，画风必须与参考图完全一致，不能写实，不能换风格，"
                "要让人看出这张图和参考图属于同一部影片的同一画风。\n"
                "【重要】若画面内容涉及衣物、配件或物品穿戴/附着在角色身上，"
                "必须参照参考图中角色的插画体型和外形风格来画该角色的身体，"
                "绝对禁止出现写实比例的人体轮廓、照片质感的皮肤或面部——"
                "人物的身形、四肢、皮肤质感必须与参考图的插画/动画美术风格完全一致。\n"
                "若画面内容不涉及任何人物身体，则只画物品本身，不要凭空添加人体。\n"
                "此外，关于道具本身的绘制，必须严格匹配参考图的美术细节：线条粗细与笔触风格、上色方式（例如平涂或渐变）、"
                "高光与阴影的处理方式、以及材质表现（例如布料、皮革、金属）的插画化处理，"
                "都要与参考图保持一致，而非摄影写实的质感。请遵循参考图的主色调与配色方案，避免引入新的写实材质或照片级纹理。\n"
                "道具的比例、缝线、折痕、缀饰与边缘处理应使用与参考图相同的绘画语言；若道具在角色身上，"
                "其附着方式、位置与尺度需遵循参考图中角色的插画体型和风格，避免为表现道具而添加写实人体或改变角色的插画比例。\n"
                "在构图与光照上，若参考图中有明确的光源方向或高光处理，请尽量保持一致，避免引入照片级景深、噪点或真实相机反射。\n"
                "Do not switch to photorealistic style. Keep the exact same illustration aesthetic as the reference image; props must look like they were painted by the same artist.\n"
                + no_text_rule
            ) + scene_desc
        else:
            if char_count == 1:
                char_req = (
                    "要求：整张画里只能有这一个角色，不能多画其他人。"
                    "按参考图的画风完成场景，不要写实。"
                    "角色的样貌和身形不要改，只可以改动作和姿势。"
                )
                no_mirror = (
                    "不要画镜子、玻璃反射、镜中倒影等难以表现的内容；"
                    "若画面描述涉及镜子或反射，改为角色不照镜子的构图。\n"
                )
                char_photo_hint = ""
            else:
                n_str = "两" if char_count == 2 else str(char_count)
                char_req = (
                    f"要求：整张画里只能有这{n_str}个角色，不能多画额外的人。"
                    f"按参考图的画风完成场景，不要写实。"
                    f"{n_str}个角色的样貌和身形都不要改，只可以改动作和姿势。"
                )
                no_mirror = (
                    f"不要画镜子、玻璃反射、镜中倒影等难以表现的内容；"
                    f"若画面描述涉及镜子或反射，改为同场景下{n_str}个角色不照镜子的构图。\n"
                )
                # 生成参考图分组说明：告诉 Gemini 哪几张图对应哪个有序占位标签
                # 与 run.py 里 _ordered_labels = ["Character A","Character B",...] 严格对应
                _ordered_labels_hint = ["Character A", "Character B", "Character C", "Character D"]
                _idx = 1
                _hint_parts = []
                for _gi, (_gname, _gcount) in enumerate(char_photo_groups):
                    _hlabel = _ordered_labels_hint[_gi] if _gi < len(_ordered_labels_hint) else f"Character {chr(65+_gi)}"
                    _end = _idx + _gcount - 1
                    if _gcount == 1:
                        _hint_parts.append(f"第{_idx}张是【{_hlabel}】的外貌")
                    else:
                        _hint_parts.append(f"第{_idx}至{_end}张是【{_hlabel}】的多角度外貌照")
                    _idx += _gcount
                if _hint_parts:
                    _labels_str = "、".join(
                        f"【{_ordered_labels_hint[i]}】"
                        for i, (g, _) in enumerate(char_photo_groups)
                        if i < len(_ordered_labels_hint)
                    )
                    char_photo_hint = (
                        "【角色参考图对应关系——必须严格遵守】\n"
                        + "，".join(_hint_parts) + "。\n"
                        f"画面描述文字里的{_labels_str}与上面的参考图一一对应，请严格按照参考图还原每位角色的外貌。\n"
                        "绝对禁止将两位角色的脸型、发型、体型互换或混用。\n"
                    )
                else:
                    char_photo_hint = ""
            prompt = (
                "根据我上传的参考图，画一张图。风格必须和参考图完全一致，不要因为镜头内容不同就改变画风或角色长相。\n"
                + char_photo_hint
                + char_req + "\n"
                + no_mirror
                + closeup_style_rule
                + no_text_rule
                + "画面内容："
            ) + scene_desc

        contents = _build_contents(ref_list, prompt)
        try:
            from google.genai.types import GenerateContentConfig, Modality
            config = GenerateContentConfig(response_modalities=[Modality.TEXT, Modality.IMAGE])
        except (ImportError, AttributeError):
            config = None
        if config is not None:
            print("[Gemini PROMPT]", prompt)
            response = client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
        else:
            print("[Gemini PROMPT]", prompt)
            response = client.models.generate_content(
                model=self.model,
                contents=contents,
            )

        _save_response_image(response, save_path)
        return prompt, save_path
