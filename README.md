# MovieAgent

<table align="center">
  <tr>
    <td><img src="./assets/logo.png" alt="MovieAgent Logo" width="180"></td>
    <td>
      <h3>MovieAgent: Automated Movie Generation via Multi-Agent CoT Planning</h3>
      <a href="https://weijiawu.github.io/MovieAgent/">
        <img src="https://img.shields.io/static/v1?label=Project%20Page&message=Github&color=blue&logo=github-pages">
      </a> &ensp;
      <a href="https://arxiv.org/abs/2503.07314">
        <img src="https://img.shields.io/static/v1?label=Paper&message=Arxiv&color=red&logo=arxiv">
      </a>
    </td>
  </tr>
</table>

---

## Pipeline Overview

### Step 0 — Story to Script

```
story_config.json
  story_title: "匹兹堡之旅"
  characters: ["布布", "一二"]
  events:
    event 1: title + events_photos/event_1/*.jpg
    event 2: title + events_photos/event_2/*.jpg

    -> image_to_description.py
       gpt-4o 视觉模型看每张照片 -> 图片描述

    -> event_to_director_script.py
       LLM 根据 title + 图片描述 -> 编剧导演稿（每个 event 独立）

    -> story_to_script.py --output-step1
       -> script_synopsis.json         (MovieScript 文本 + Character 列表)
       -> Step_1_script_results.json   (直接跳过 ScriptBreak，每个 event = 1 Sub-Script)
```

```bash
python scripts/story_to_script.py dataset/my_story/ \
  -o dataset/my_story/script_synopsis.json \
  --llm gpt4-o \
  --output-step1 movie_agent/Results/my_story/Step_1_script_results.json
```

---

### Step 1-5 — MovieAgent Pipeline

```
[ScriptBreak]  -- 如果 Step_1 已存在则自动跳过 --
  GPT-4o + screenwriterCoT-sys
  规则：1 event = 1 Sub-Script，2~8个，不在 event 内过度拆分
  -> Step_1_script_results.json

[ScenePlanning]
  GPT-4o + ScenePlanningCoT-sys
  每个 Sub-Script -> 严格 1 个 Scene
  输入：Sub-Script.Plot + Relationships
  输出：Plot / Scene Description / Emotional Tone / Key Props / Cinematography Notes
  -> Step_2_scene_results.json

[ShotPlotCreate]
  GPT-4o + ShotPlotCreateCoT-sys
  每个 Scene -> 固定 3 个 Shot（use_history=False，各 Scene 完全独立）
  输入：Scene Details（Plot / Description / Tone / Props / Cinematography）
  输出：Involving Characters + bbox / Plot / Visual Description /
        Camera Movement / Shot Type / Subtitles: {}
  镜类型：角色镜（有 bbox）或 道具特写镜（Involving Characters: {}）
  -> Step_3_shot_results.json

[VideoAudioGen]  逐镜循环
  |
  +-- 关键帧生成  Gemini 3 Pro Image (gemini-3-pro-image-preview)
  |   参考图（<=8 张，每镜重新读取）：
  |     同 scene 第 2/3 镜：prev_keyframe（上一镜成片）排第 1 张
  |     character_list 下角色 front/oblique/side/back x N 人
  |   scene 边界 reset（不跨 scene 传 prev_keyframe）
  |   道具镜 prompt：复刻画风，不画人物
  |   角色镜 prompt：严格按参考图画角色，不改样貌
  |   plot 前注入 [Camera: {camera_mv}]
  |
  +-- 图生视频  Runway gen4_turbo
  |   分辨率：1280x720，时长：2s
  |   prompt = [Camera: xxx] + Plot + Preserve face suffix
  |   指数退避重试 x3 (2/4/8s)
  |
  -> video/ 目录：Sub-Script_N|Scene_1|Shot_N.jpg + .mp4

[Final]
  按自然排序（Sub-Script 1 Shot 1 -> Sub-Script N Shot 3）
  crossfade 0.1s 拼接所有 .mp4 -> final_video.mp4
  同步更新 审阅/ 目录（剧本 + 分镜 JSON + 关键帧示例）
```

```bash
cd movie_agent
python run.py \
  --script_path ../dataset/my_story/script_synopsis.json \
  --character_photo_path ../dataset/my_story/character_list \
  --LLM gpt4-o \
  --gen_model Gemini \
  --Image2Video Runway
```

常用 flags：

| Flag | 说明 |
|------|------|
| `--only_planning` | 只跑 Step 0-3，不生图/视频 |
| `--only_final` | 只跑 Final 拼接 |
| `--crossfade 0.1` | 转场淡入淡出时长（秒），默认 0.1 |
| `--final_name final_video` | 输出文件名 |

---

## Dataset Structure

```
dataset/
  my_story/
    story_config.json
    script_synopsis.json
    character_list/
      布布/
        front.jpg  oblique.jpg  side.jpg  back.jpg
      一二/
        ...
    events_photos/
      event_1/  event_2/  ...

movie_agent/Results/my_story/gpt4-o_Gemini_Runway/
  Step_1_script_results.json
  Step_2_scene_results.json
  Step_3_shot_results.json
  video/
    Sub-Script_1|Scene_1|Shot_1.jpg
    Sub-Script_1|Scene_1|Shot_1.mp4
    ...
    final_video.mp4
  审阅/
```

---

## Installation

```bash
git clone https://github.com/ZichaoJin/MovieAgent-main.git
cd MovieAgent-main
git checkout copilot
pip install -r requirements.txt
```

Environment variables:

```bash
export OPENAI_API_KEY=sk-...
export GOOGLE_API_KEY=...
export RUNWAYML_API_SECRET=...
export S3_BUCKET=your-bucket-name
export AWS_DEFAULT_REGION=ap-southeast-1
export CHARACTER_PHOTOS_PATH=/path/to/character_list
```

---

## API (EC2)

Server: `http://18.142.186.126:8000`

### POST /generate

```
multipart/form-data:
  story_title  = "匹兹堡之旅"
  events_json  = '["在机场等待", "到达酒店"]'
  photos_0     = [image1.jpg, image2.jpg]   <- event 0 的照片（可选）
  photos_1     = [image3.jpg]               <- event 1 的照片（可选）
```

Response: `{ "job_id": "xxxx", "status": "queued" }`

### GET /status/{job_id}

```json
{
  "status": "running",
  "progress": 65,
  "step": "generating keyframes & video",
  "video_url": null,
  "error": null
}
```

`status`: `queued` -> `running` -> `done` / `error`

`video_url`: 完成后为 S3 presigned URL（24h 有效），可直接用 AVPlayer 播放。

### DELETE /jobs/{job_id}

清理临时文件。

### 进度阶段

| progress | step |
|----------|------|
| 5% | initializing |
| 15% | generating script synopsis |
| 25% | planning scenes & shots |
| 55% | ShotPlotCreate |
| 65% | generating keyframes & video |
| 90% | concatenating final video |
| 95% | uploading to S3 |
| 100% | done |

---

## Citation

```bibtex
@misc{wu2025movieagent,
  title={Automated Movie Generation via Multi-Agent CoT Planning},
  author={Weijia Wu, Zeyu Zhu, Mike Zheng Shou},
  year={2025},
  eprint={2503.07314},
  archivePrefix={arXiv},
  primaryClass={cs.CV}
}
```
