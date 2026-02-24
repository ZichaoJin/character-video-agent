# Gemini Nano Banana 关键帧 + Veo 视频

## 1. 用 Nano Banana 生成关键帧（已接入）

**Nano Banana** 是 Google Gemini 的「图+文生图」能力，支持**多张参考图**（你用的那种：两张角色照 + 一段“按画风、样貌身形不改只改动作”的 prompt），成图质量对你这种双人、固定画风很合适。

### 用法

```bash
cd movie_agent
# 设置 Google API Key（Gemini）
export GOOGLE_API_KEY="你的key"   # 或 GEMINI_API_KEY

../.venv/bin/python run.py \
  --script_path ../dataset/布布一二_PittsburghTrip/script_synopsis.json \
  --character_photo_path ../dataset/布布一二_PittsburghTrip/character_list \
  --gen_model Gemini \
  --resume_from_shots
```

- 需要先安装：`pip install google-genai`
- 双人镜会**直接传两张参考图**（布布、一二各一张），不再拼成一张，Nano Banana 原生支持多图输入。
- Prompt 会自动加上你那种要求：按参考图画风完成场景、两个角色样貌身形不改、只改动作。

### 配置

- `configs/Gemini.json` 里可改 `gemini_model`，例如 `gemini-2.5-flash-preview-05-20` 或你账号里可用的图像生成模型。
- 画风描述与 Replicate 一样：有 `style_reference/` 或 `scene_style.txt` 时会拼进每镜 prompt。

---

## 2. Nano 可以做视频吗？

**Nano Banana 只做「图」**，不做视频。

做视频的是同一套 Gemini 生态里的 **Veo**（如 Veo 3.1）：

- **Veo**：文生视频、图生视频，支持多张参考图（最多约 3 张）做角色/画风一致，可生成带音频的短片。
- 通过 **Gemini API** 可调 Veo（例如 Veo 3.1），但和 Nano Banana 是**不同接口、不同模型**。

当前项目里的「图生视频」用的是 **Runway** 等（见 `--Image2Video Runway`）。若要把「关键帧 → 视频」改成用 **Veo**，需要单独接 Veo 的 API（Google 已开放），并在本仓库里加一个 Veo 的图生视频后端（类似 `Runway_I2V`），再在配置里把图生视频指向 Veo。这一步可以后续再做。

---

## 3. 小结

| 能力           | 用的谁     | 本项目是否已支持 |
|----------------|------------|------------------|
| 关键帧（图+文） | Nano Banana | ✅ 已支持，`--gen_model Gemini` |
| 视频           | Veo        | ❌ 未接；当前图生视频是 Runway 等 |

你可以先用 **`--gen_model Gemini`** 做关键帧，再用现有的 Runway 图生视频；若以后要改成 Veo 出片，再接 Veo API 即可。
