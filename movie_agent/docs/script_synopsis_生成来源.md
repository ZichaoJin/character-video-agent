# script_synopsis.json 是根据什么生成的？

**script_synopsis.json**（里头有 **MovieScript** 和 **Character**）是由 **`scripts/story_to_script.py`** 生成的。它「根据什么」可以分两层说：**输入素材** 和 **中间怎么变成剧本**。

---

## 1. 输入素材（你给 script 的东西）

`story_to_script.py` 支持两种输入方式：

### 方式 A：目录（例如「我的故事」）

- 你传一个**目录路径**（如 `dataset/布布一二_PittsburghTrip/我的故事`）。
- 脚本会在这个目录里找：
  - **story_config.json**（必选）：里头的 `story_title`、`characters`、`events`。
  - **events_photos/**（可选）：按每个 event 的 `image_folder` 去下面子文件夹里扫照片。

**story_config.json 大致长这样：**

```json
{
  "story_title": "匹兹堡之旅",
  "characters": ["布布", "一二"],
  "events": [
    { "title": "我和宝宝一起去逛艺术馆啦", "image_folder": "art_gallery" },
    { "title": "宝宝给我包饺子啦", "image_folder": "dumpling", "caption": "可选补充" }
  ]
}
```

- **image_folder**：表示该 event 的照片在 `events_photos/{image_folder}/` 下（会扫 `.jpg` / `.jpeg` / `.png`，含大写后缀）。
- 若某 event 没有 **image_folder**，就不会用图，只用 **title**（和可选的 **caption**）。

所以：**「根据什么」= 你目录里的 story_config.json + events_photos 里对应文件夹的照片。**

### 方式 B：单个 JSON 文件

- 你传一个 **JSON 文件路径**（例如手写的 `story_input.json`）。
- 文件里直接写 **story_title**、**characters**、**events**；每个 event 用 **image_paths**（图片路径列表）或 **caption**，不用 image_folder。

所以：**「根据什么」= 这个 JSON 里的标题、角色、事件文案和（若有）图片路径。**

---

## 2. 脚本内部是怎么生成 MovieScript 的？

对**每一个 event**，脚本会：

1. **看图（若该 event 有图）**  
   用**视觉模型**（默认 `gpt-4o`）对该 event 的每张图做描述（`image_to_description.describe_images_batch`）。
2. **生成该 event 的「导演稿」**  
   用 **LLM**（默认 `gpt4-o`）根据这三样生成一段导演稿（角色动作、运镜等）：
   - 该 event 的 **title**（和可选 **caption**）
   - 上一步得到的**图片描述**（若无图则只用 title/caption）
   - **characters** 列表（如 布布、一二）
   - 具体实现在 `event_to_director_script.generate_director_script_for_event`。
3. **拼成整部剧本**  
   把所有 event 的导演稿按顺序拼成一大段文本，前面加上 **story_title**，得到 **MovieScript**。  
   **Character** 直接来自 story_config（或输入 JSON）里的 **characters**。

最后写入 **script_synopsis.json** 的就是：

- **MovieScript**：上面这一大段剧本文本。
- **Character**：角色名列表。

---

## 3. 一句话对应你的问题

- **「这个是根据什么生成呢」**  
  - **输入**：你提供的「我的故事」目录（里的 **story_config.json** + **events_photos/** 下各 event 的照片），或者你手写的一个带 story_title / characters / events 的 JSON。  
  - **过程**：用**视觉模型**看图得到描述，用 **LLM** 根据「每个 event 的 title + 图片描述 + 角色列表」生成每个 event 的导演稿，再拼成整部 **MovieScript**，和 **Character** 一起写出 **script_synopsis.json**。

也就是说：**script_synopsis.json 是根据「故事配置 + 每个事件的标题和照片（若有）」通过「看图 + LLM 写导演稿」生成的。**
