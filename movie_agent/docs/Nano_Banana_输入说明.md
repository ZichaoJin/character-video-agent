# 目前给 Nano Banana 的输入都是啥

当 `--gen_model Gemini` 时，每镜关键帧会调用 Gemini（Nano Banana）图+文生图，下面就是**实际送进 API 的全部输入**。  
**画风描述（scene_style_text）已去掉**，只靠角色参考图 + 固定风格句 + 本镜镜头描述。

---

## 1. 输入一：参考图（1 或 2 张）

- **来源**：`run.py` 里按「本镜出现的角色」从 `character_list` 取图。
  - 单人镜：`character_phot_list = [该角色的一张图]`
  - 双人镜：`character_phot_list = [角色1的一张图, 角色2的一张图]`
- **选图顺序**（每个角色目录下）：  
  `best.png` → `best.jpg` → `front.png` → `front.jpg` → `oblique.png` → `oblique.jpg` → `side.png` → `side.jpg` → `back.png` → `back.jpg`，**取第一个存在的文件**。
- **角色名**：分镜里若是 "Character 1" / "Character 2"，会通过 `character_list/character_mapping.json` 映射成文件夹名（如 布布、一二），再在 `character_list/布布/`、`character_list/一二/` 下找上面这些文件名。
- **送给 Nano Banana 的方式**：按顺序作为多模态 **contents** 的前几段——先图 1（若双人再图 2），再文本。**最多 2 张图**，双人镜就是「图1 + 图2 + 一段文本」。

总结：**输入图 = 本镜角色在 character_list 下选出的 1～2 张参考图（你上传的两个参考角色的图）。**

---

## 2. 输入二：文本 prompt（一段）

送进 API 的是一整段文本，由下面三部分**按顺序拼接**而成：

### 2.1 固定前缀（style_rule）

每镜都会先加这段英文（在 `models/Gemini_Image/gemini_image.py` 里写死）：

```text
Use these reference images for the two characters. Complete all scene details in the same art style as the references — not realistic, but exactly like the style in the photos. Do not change the appearance or body shape of either character; only their poses and actions may change.
```

含义：用参考图里的两个角色、按参考图的画风完成场景、不写实、两个角色样貌身形不改、只改动作。

### 2.2 本镜镜头描述（plot）——从哪来的？

- **字段**：分镜里该镜的 **`Plot/Visual Description`**（非 ROICtrl 时），或 **`Coarse Plot`**（当 `gen_model` 为 ROICtrl 时）。即「这一镜在画什么」的那段英文。
- **出处**：
  1. **生成阶段**：跑完整流程（不设 `--resume_from_shots`）时，**ShotPlotCreate** 步骤会调 LLM（system prompt 在 `system_prompts.py` 的 **ShotPlotCreateCoT-sys**），根据当前**场景**的信息（Plot、Involving Characters、Scene Description、Emotional Tone、Key Props、Cinematography Notes）为每个镜头生成一坨结构化结果，其中就包含每个 shot 的 **Plot/Visual Description** 和 **Coarse Plot**。
  2. **存哪儿**：这份结果被写入 **Step_3_shot_results.json**（路径形如 `Results/项目名/gpt4-o_Replicate_Runway/Step_3_shot_results.json`），结构是：  
     `Sub-Script → [子剧本名] → Scene Annotation → Scene → [场景名] → Shot Annotation → Shot → [镜头名]`  
     每个镜头名下面有 `"Plot/Visual Description"`、`"Coarse Plot"`、`"Involving Characters"` 等字段。
  3. **用的时候**：关键帧生成时（`run.py` 的 `VideoAudioGen`）会 `read_json(self.shot_path)` 读到 Step_3 的 JSON，再取 `shot_info["Plot/Visual Description"]`（或 ROICtrl 时 `shot_info["Coarse Plot"]`）当作本镜的 plot，拼进 Nano Banana 的 prompt。
- 若用 **`--resume_from_shots`**，不会重新跑 ShotPlotCreate，用的就是**之前跑出来的** Step_3_shot_results.json 里已有的 Plot/Visual Description。

最终送给 Nano Banana 的**整段文本**就是（**不再包含画风描述**）：

```text
[style_rule]

[本镜的 Plot/Visual Description]
```

（中间换行，总长截到 4000 字符以内。）

---

## 3. 其他（不直接作为「内容」的输入）

- **character_box**：本镜角色 bbox，当前 Gemini 管道**没有用**，只接接口兼容。
- **save_path**：结果要保存的路径（如 `.../Sub-Script_1|Scene_1|Shot_1.jpg`），只影响存盘，不参与 API 请求内容。
- **size**：当前也**没有**传给 Gemini（Nano Banana 输出尺寸由模型决定），只接接口兼容。

---

## 4. 汇总表

| 输入项 | 来源 | 是否传给 Nano Banana | 说明 |
|--------|------|----------------------|------|
| 参考图 1 | character_list/角色1/ 下 best→front→… 第一张存在 | ✅ 是 | 多模态 part：图 |
| 参考图 2 | character_list/角色2/ 下同上（仅双人镜） | ✅ 是 | 多模态 part：图 |
| 文本 prompt | style_rule + Plot/Visual Description（**不含**画风描述） | ✅ 是 | 多模态 part：文本 |
| character_box | 分镜 bbox | ❌ 否 | 未使用 |
| save_path / size | 运行参数 | ❌ 否 | 仅本地保存用 |

所以你问的「目前给 Nano Banana 的输入都是啥」就是：**1～2 张参考图 + 固定风格句 + 本镜 Plot/Visual Description**；没有画风描述，没有别的隐藏输入。
