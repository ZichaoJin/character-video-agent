import os
import re
import shutil
from datetime import datetime
import argparse

from base_agent import BaseAgent
from system_prompts import sys_prompts
from tools import ToolCalling, save_json
import json
from moviepy import VideoFileClip, concatenate_videoclips
from pathlib import Path
import yaml

def parse_args():
    
    # parser = argparse.ArgumentParser(description='MovieAgent', formatter_class=argparse.RawTextHelpFormatter)
    parser = argparse.ArgumentParser(description="MovieAgent")

    parser.add_argument(
        "--script_path",
        type=str,
        required=True,
        help="user query",
    )
    parser.add_argument(
        "--character_photo_path",
        type=str,
        required=True,
        help="user query",
    )
    parser.add_argument(
        "--LLM",
        type=str,
        required=False,
        default="gpt4-o",
        help="剧本/分镜用 LLM: gpt4-o | deepseek-r1 | deepseek-v3 (default: gpt4-o)",
    )
    parser.add_argument(
        "--gen_model",
        type=str,
        required=False,
        default="Replicate",
        help="关键帧模型: Replicate | Replicate_flux_kontext | Gemini | OpenAI | ROICtrl | StoryDiffusion (default: Replicate)。Gemini 用 Nano Banana 双图+文生图；Replicate_flux_kontext 用 FLUX Kontext。",
    )
    parser.add_argument(
        "--audio_model",
        type=str,
        required=False,
        default="NoAudio",
        help="model: NoAudio | VALL-E (default: NoAudio, no dialogue)",
    ) 
    parser.add_argument(
        "--talk_model",
        type=str,
        required=False,
        help="model",
    )
    parser.add_argument(
        "--Image2Video",
        type=str,
        required=False,
        default="Runway",
        help="图生视频模型: Runway | SVD | I2Vgen | CogVideoX (default: Runway)",
    )
    parser.add_argument(
        "--resume_from_shots",
        action="store_true",
        help="跳过剧本拆分与分镜，直接用已有的 Step_3 分镜结果只跑关键帧+图生视频（需之前跑过分镜并生成过 Step_3_shot_results.json）",
    )
    parser.add_argument(
        "--skip_existing_keyframes",
        action="store_true",
        help="与 resume_from_shots 合用：若某镜关键帧 .jpg 已存在则跳过该镜，只生成缺失的关键帧与视频",
    )
    parser.add_argument(
        "--only_first_scene",
        action="store_true",
        help="只跑第一个 Sub-Script 的第一个 Scene（例如只跑艺术馆这一场），跑完即停",
    )
    parser.add_argument(
        "--only_planning",
        action="store_true",
        help="只跑 Step 1-3（ScriptBreak / ScenePlanning / ShotPlotCreate），不生成关键帧与视频",
    )
    parser.add_argument(
        "--only_final",
        action="store_true",
        help="跳过所有生成步骤，只把已有 .mp4 拼接成最终视频",
    )
    parser.add_argument(
        "--skip_video",
        action="store_true",
        help="只生成关键帧，跳过图生视频（Runway）步骤",
    )
    parser.add_argument(
        "--crossfade",
        type=float,
        default=0.1,
        help="Final 拼接时的 crossfade 时长（秒），0 表示不叠化 (default: 0.1)",
    )
    parser.add_argument(
        "--final_name",
        type=str,
        default="final_video",
        help="最终视频文件名（不含扩展名）(default: final_video)",
    )

    args = parser.parse_args()

    if args.gen_model:
        config = load_config(args.gen_model)
        # print(config)
        for key, value in config.items():
            if not getattr(args, key, None):  
                setattr(args, key, value)
    
    if args.Image2Video:
        config = load_config(args.Image2Video)
        # print(config)
        for key, value in config.items():
            if not getattr(args, key, None):  
                setattr(args, key, value)

    return args


def load_config(model_name):
    """ with model_name, read config """
    # 用 __file__ 的绝对路径，不依赖当前工作目录（保证多线程安全）
    config_path = Path(__file__).resolve().parent / "configs" / f"{model_name}.json"

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            if config_path.suffix == ".json":
                return json.load(f)
            elif config_path.suffix in [".yaml", ".yml"]:
                return yaml.safe_load(f)
    return {}  


def _load_character_mapping_and_dirs(character_photo_path):
    """加载 character_list 下的 character_mapping.json（可选）和子目录列表，用于把 Character 1/2 映射到 布布、一二。"""
    mapping = None
    mapping_path = os.path.join(character_photo_path, "character_mapping.json")
    if os.path.isfile(mapping_path):
        try:
            with open(mapping_path, "r", encoding="utf-8") as f:
                mapping = json.load(f)
        except Exception:
            pass
    dirs = []
    if os.path.isdir(character_photo_path):
        dirs = sorted(
            d for d in os.listdir(character_photo_path)
            if os.path.isdir(os.path.join(character_photo_path, d)) and not d.startswith(".")
        )
    return {"mapping": mapping, "dirs": dirs}


def _resolve_character_names(character_names, character_photo_path, mapping, dirs):
    """把分镜里的角色名（如 Character 1, Character 2）解析为 character_list 下的文件夹名（如 布布、一二）。"""
    if not character_names:
        return character_names
    out = []
    for name in character_names:
        if mapping and name in mapping:
            out.append(mapping[name])
        elif mapping:
            out.append(name)
        else:
            # 无映射文件时：Character 1 -> 第1目录，Character A -> 第1目录
            m_num = re.match(r"Character\s*(\d+)", name, re.IGNORECASE)
            m_letter = re.match(r"Character\s*([A-D])", name, re.IGNORECASE)
            if m_num and dirs:
                idx = int(m_num.group(1))
                if 1 <= idx <= len(dirs):
                    out.append(dirs[idx - 1])
                else:
                    out.append(name)
            elif m_letter and dirs:
                idx = ord(m_letter.group(1).upper()) - ord('A')  # A=0, B=1...
                if 0 <= idx < len(dirs):
                    out.append(dirs[idx])
                else:
                    out.append(name)
            else:
                out.append(name)
    return out


class ScriptBreakAgent:
    def __init__(self, args, sample_model="sdxl-1", audio_model="VALL-E", talk_model = "Hallo2", Image2Video = "CogVideoX",
                 script_path = "", character_photo_path="", save_mode="img"):
        self.args = args
        self.sample_model = sample_model
        self.audio_model = audio_model
        self.talk_model = talk_model
        self.Image2Video = Image2Video
        self.script_path = script_path
        self.character_photo_path = character_photo_path
        self.characters_list = []
        self.movie_name = script_path.split("/")[-1].replace(".json","")
        self.save_mode = save_mode

        self.update_info()
        self.init_agent()
        self.init_videogen()
    
    def init_videogen(self):
        movie_script, characters_list = self.extract_characters_from_json(self.script_path, 40)

        self.tools = ToolCalling(self.args, sample_model=self.sample_model, audio_model = self.audio_model, \
                                 talk_model = self.talk_model, Image2Video = self.Image2Video, \
                                    photo_audio_path = self.character_photo_path, \
                                    characters_list=characters_list, save_mode=self.save_mode)
    
    def init_agent(self):
        # initialize agent
        self.screenwriter_agent = BaseAgent(self.args.LLM, system_prompt=sys_prompts["screenwriterCoT-sys"], use_history=False, temp=0.7)
        # self.supervisor_agent = BaseAgent(system_prompt=sys_prompts["scriptsupervisor-sys"], temp=0.7)

        self.sceneplanning_agent = BaseAgent(self.args.LLM, system_prompt=sys_prompts["ScenePlanningCoT-sys"], use_history=False, temp=0.7)

        self.shotplotcreate_agent = BaseAgent(self.args.LLM, system_prompt=sys_prompts["ShotPlotCreateCoT-sys"], use_history=False, temp=0.7)
        
        
        
    def format_results(self, results):
        formatted_text = "Observation:\n\n"
        for item in results:
            formatted_text += f"Prompt: {item['Prompt']}\n"
            for question, answer in zip(item["Questions"], item["Answers"]):
                formatted_text += f"Question: {question} -- Answer: {answer}\n"
            formatted_text += "\n"
        return formatted_text

    
    def update_info(self):
        folder_name = self.script_path.split("/")[-2]
        self.save_path = f"./Results/{folder_name}"
        
        model_config = self.args.LLM + "_" + self.sample_model + "_" + self.args.Image2Video 
        self.video_save_path = os.path.join(self.save_path, model_config, "video")

        self.sub_script_path = os.path.join(self.save_path, model_config, f"Step_1_script_results.json")
        self.scene_path = os.path.join(self.save_path, model_config, f"Step_2_scene_results.json")
        self.shot_path = os.path.join(self.save_path, model_config, f"Step_3_shot_results.json")

        os.makedirs(self.save_path, exist_ok=True)
        os.makedirs(self.video_save_path, exist_ok=True)

    def read_json(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        return data

    def extract_characters_from_json(self,file_path, n):
        data = self.read_json(file_path)
        movie_script = data['MovieScript']
        characters = data['Character']
        selected_characters = characters[:n]
        self.characters_list = selected_characters
        return movie_script,selected_characters

    def ScriptBreak(self, all_chat=[]):
        

        movie_script, characters_list = self.extract_characters_from_json(self.script_path, 40)
        first_sentence = movie_script.split(".")[0]
        # all_chat.append(query)
        previous_sub_script = None
        n = 0
        index = 1
        result = {}
        characters_list = str(characters_list)
        while True:
            if previous_sub_script: 
                query = f"""
                    Script Synopsis: {movie_script}
                    Character: {characters_list}
                    Previous Sub-Script: {previous_sub_script}
                    """
            else:
                query = f"""
                    Script Synopsis: {movie_script}
                    Character: {characters_list}
                    There is no Previous Sub-Script. 
                    The current sub-script is the first one. Please start summarizing the first sub-script based on the following content: {first_sentence}.
                    """
                
            query = f"""
                    Script Synopsis: {movie_script}
                    Character: {characters_list}
                    """
            
            task_response = self.screenwriter_agent(query, parse=True)
            # task_response = task_response.replace("'",'"')
            result = task_response

            break
        
        # all_chat.append(self.task_agent.messages)
        save_json(result, self.sub_script_path)
        # return 

    def ScenePlanning(self):
        data = self.read_json(self.sub_script_path)
        data_scene = data
        
        character_relationships = data['Relationships']
        sub_script_list = data['Sub-Script']

        for sub_script_name in sub_script_list:
            sub_script = sub_script_list[sub_script_name]["Plot"]
            query = f"""
                        Given the following inputs:
                        - Script Synopsis: "{sub_script}"
                        - Character Relationships: {character_relationships}
                        """
            task_response = self.sceneplanning_agent(query, parse=True)
            # if "Scene Annotation" not in data_scene[sub_script_name]:
            #     data_scene[sub_script_name]["Scene Annotation"] = []
            
            data_scene['Sub-Script'][sub_script_name]["Scene Annotation"]=task_response

            save_json(data_scene, self.scene_path)
            # break
    
    def ShotPlotCreate(self):
        data = self.read_json(self.scene_path)
        data_scene = data
        
        character_relationships = data['Relationships']
        sub_script_list = data['Sub-Script']

        for sub_script_name in sub_script_list:
            scene_list = sub_script_list[sub_script_name]["Scene Annotation"]["Scene"]
            for scene_name in scene_list:
                scene_details = scene_list[scene_name]
                query = f"""
                            Given the following Scene Details:
                            - Involving Characters: "{scene_details['Involving Characters']}" 
                            - Plot: "{scene_details['Plot']}"
                            - Scene Description: "{scene_details['Scene Description']}"
                            - Emotional Tone: "{scene_details['Emotional Tone']}"
                            - Key Props: {scene_details['Key Props']}
                            - Cinematography Notes: "{scene_details['Cinematography Notes']}"
                            """
                            
                task_response = self.shotplotcreate_agent(query, parse=True)
                # if "Shot Annotation" not in data_scene[sub_script_name]:
                #     data_scene[sub_script_name]["Shot Annotation"] = []
                
                data_scene['Sub-Script'][sub_script_name]["Scene Annotation"]["Scene"][scene_name]["Shot Annotation"] = task_response

                save_json(data_scene, self.shot_path)
            #     break
        
    def VideoAudioGen(self):
        data = self.read_json(self.shot_path)
        character_relationships = data['Relationships']
        sub_script_list = data['Sub-Script']

        prev_keyframe_path = None  # 上一镜关键帧路径，用于本镜参考服装一致
        for idx_1,sub_script_name in enumerate(sub_script_list):
            scene_list = sub_script_list[sub_script_name]["Scene Annotation"]["Scene"]
            # scene_path = os.path.join(self.video_save_path,shot_name+".jpg")
            # if idx_1!=len(sub_script_list)-1:
            #     continue

            for scene_name in scene_list:
                shot_lists = scene_list[scene_name]["Shot Annotation"]["Shot"]
                prev_keyframe_path = None  # scene 边界 reset，不把上一 scene 的服装带入下一 scene

                # scene_path = os.path.join(self.video_save_path,shot_name+".jpg")
                # if idx_1!=len(sub_script_list)-1:
            #     continue

                for shot_name in shot_lists:
                    shot_info = shot_lists[shot_name]
                    involving = shot_info["Involving Characters"]
                    character_box = involving if isinstance(involving, dict) else {}
                    character_names = list(character_box.keys())
                    # 先加载「角色名 -> 文件夹名」映射（分镜里常为 Character 1/2，文件夹为 布布、一二）
                    if not getattr(self, "_character_mapping_loaded", False):
                        _cache = _load_character_mapping_and_dirs(self.character_photo_path)
                        self._character_mapping = _cache["mapping"]
                        self._character_photo_dirs = _cache["dirs"]
                        self._character_mapping_loaded = True
                    character_names = _resolve_character_names(
                        character_names,
                        self.character_photo_path,
                        getattr(self, "_character_mapping", None),
                        getattr(self, "_character_photo_dirs", None),
                    )
                    # Prop/detail shots (no characters): use Plot/Visual Description for full prompt
                    if not character_names:
                        plot = shot_info.get("Plot/Visual Description", shot_info.get("Coarse Plot", ""))
                    elif self.sample_model == "ROICtrl":
                        plot = shot_info["Coarse Plot"]
                    else:
                        plot = shot_info["Plot/Visual Description"]
                    # 画面内容里不写具体角色名，用占位词替换（按本镜实际角色数）
                    _char_label = "这个角色" if len(character_names) == 1 else "两个角色"
                    def _replace_character_names_in_plot(text, dirs, mapping, label):
                        if not text:
                            return text
                        names = set(dirs)
                        if mapping:
                            names |= set(mapping.values())
                        for name in names:
                            text = text.replace(name, label)
                        for i in range(1, 6):
                            text = text.replace(f"Character {i}", label).replace(f"Character{i}", label)
                        return text
                    if len(character_names) <= 1:
                        # 单角色 / 道具镜：统一替换为"这个角色"
                        plot = _replace_character_names_in_plot(
                            plot,
                            getattr(self, "_character_photo_dirs", []),
                            getattr(self, "_character_mapping", None),
                            _char_label,
                        )
                    else:
                        # 多角色镜：把 plot 里所有角色名变体替换为有序占位标签（角色A/B/C/D），
                        # 与 gemini_image.py 里参考图分组 hint 的标签严格对应。
                        # 不管 GPT-4o 输出中文名还是 Character N，都统一清除，避免 Gemini 认错人。
                        _ordered_labels = ["Character A", "Character B", "Character C", "Character D"]
                        _char_mapping = getattr(self, "_character_mapping", {}) or {}
                        for _ci, _cname in enumerate(character_names):
                            _clabel = _ordered_labels[_ci] if _ci < len(_ordered_labels) else f"Character {chr(65+_ci)}"
                            # 替换中文真实名字
                            plot = plot.replace(_cname, _clabel)
                            # 替换 mapping 里的 key（如 "Character 1"）和 value
                            for _orig_key, _mapped_val in _char_mapping.items():
                                if _mapped_val == _cname:
                                    plot = plot.replace(_orig_key, _clabel)
                            # 替换 Character N 通用占位（数字，如 Character 1）
                            plot = plot.replace(f"Character {_ci+1}", _clabel).replace(f"Character{_ci+1}", _clabel)
                            # 替换 Character A/B/C/D（GPT-4o 把角色A直接英译的变体）
                            _letter = chr(65 + _ci)  # A, B, C, D
                            plot = plot.replace(f"Character {_letter}", _clabel).replace(f"Character{_letter}", _clabel)

                    subtitle = shot_info.get("Subtitles") or {}
                    # [Camera: ...] 注入：把分镜里的 Camera Movement 前置到 plot
                    camera_mv = shot_info.get("Camera Movement", "").strip()
                    if camera_mv:
                        plot = f"[Camera: {camera_mv}] " + plot
                    # 参考图：Replicate 用 1～2 张；Gemini 用四方向（front/oblique/side/back）最多 8 张，没有 best
                    def _first_ref_image(char_name):
                        base = os.path.join(self.character_photo_path, char_name.replace(" ", "_"))
                        for direc in ("front", "oblique", "side", "back"):
                            for ext in (".png", ".jpg", ".PNG", ".JPG"):
                                p = os.path.join(base, direc + ext)
                                if os.path.isfile(p):
                                    return p
                        return None
                    def _ref_images_up_to_8(char_names):
                        """按角色顺序收四方向（front→oblique→side→back），每角色最多 4 张，共最多 8 张。支持 .jpg/.JPG/.png/.PNG。"""
                        # 每个方向试小写+大写扩展名，兼容 front.JPG 等
                        directions = ("front", "oblique", "side", "back")
                        exts = (".png", ".jpg", ".PNG", ".JPG")
                        out, seen = [], set()
                        for name in char_names:
                            base = os.path.join(self.character_photo_path, name.replace(" ", "_"))
                            for direc in directions:
                                if len(out) >= 8:
                                    return out
                                for ext in exts:
                                    p = os.path.join(base, direc + ext)
                                    if os.path.isfile(p) and p not in seen:
                                        out.append(p)
                                        seen.add(p)
                                        break
                        return out
                    if getattr(self.args, "gen_model", None) == "Gemini":
                        gemini_char_dirs = getattr(self, "_character_photo_dirs", [])
                        if not character_names:
                            # 道具镜：传所有角色参考图仅用于画风参考，Gemini 内部识别为 prop shot
                            character_phot_list = _ref_images_up_to_8(gemini_char_dirs)
                        else:
                            # 角色镜：只传本镜实际出现的角色的参考图
                            character_phot_list = _ref_images_up_to_8(character_names)
                        # 不注入 prev_keyframe：前一帧可能是特写/单人镜，注入后 Gemini 会被误导（如双人镜只画出两只手）
                    elif character_names:
                        path0 = _first_ref_image(character_names[0])
                        character_phot_list = [path0] if os.path.isfile(path0) else []
                        if len(character_names) > 1:
                            path1 = _first_ref_image(character_names[1])
                            if os.path.isfile(path1):
                                character_phot_list.append(path1)
                            else:
                                print(f"[提示] 本镜有两人但第二角色「{character_names[1]}」参考图不存在 ({path1})，将只使用首角色参考图。请在 character_list 下为该角色放置四方向图（front/oblique/side/back）。")
                    else:
                        character_phot_list = []
                    if character_names and character_phot_list:
                        _ordered_labels = ["Character A", "Character B", "Character C", "Character D"]
                        labels = [
                            _ordered_labels[i] if i < len(_ordered_labels) else f"Character {chr(65+i)}"
                            for i in range(len(character_names))
                        ]
                        print(f"[本镜角色] {labels}，参考图数: {len(character_phot_list)}")
                    save_path = os.path.join(self.video_save_path, sub_script_name + "|" + scene_name + "|" + shot_name + ".jpg")
                    save_path = save_path.replace(" ", "_")

                    video_save_path = save_path.replace(".jpg", ".mp4")
                    # 若已存在关键帧且指定了跳过
                    if getattr(self.args, "skip_existing_keyframes", False) and os.path.isfile(save_path):
                        if os.path.isfile(video_save_path):
                            print(f"跳过（关键帧+视频已有）: {save_path}")
                            prev_keyframe_path = save_path
                            continue
                        # 关键帧已有但视频缺失：只补图生视频
                        print(f"关键帧已有，补生成视频: {video_save_path}")
                        try:
                            self.tools.image2video.predict(plot, save_path, video_save_path, (1024, 512))
                        except Exception as e:
                            print(f"[图生视频失败] 本镜跳过: {save_path}，错误: {e}")
                        prev_keyframe_path = save_path
                        continue
                    print("Save the video to path:", save_path)
                    self.tools.sample(plot, character_phot_list, character_box, subtitle, save_path, (1024, 512))
                    prev_keyframe_path = save_path  # 本镜成片作为下一镜的服装参考


                    # break
                if getattr(self.args, "only_first_scene", False):
                    print("[only_first_scene] 已跑完第一个 Scene，停止。")
                    break
            if getattr(self.args, "only_first_scene", False):
                break

    def Final(self, crossfade: float = 0.1, final_name: str = "final_video"):
        import natsort
        directory = self.video_save_path
        mp4_files = [
            f for f in os.listdir(directory)
            if f.endswith('.mp4') and not f.startswith("final_")
        ]
        mp4_files = natsort.natsorted(mp4_files)

        clips = []
        for file in mp4_files:
            file_path = os.path.join(directory, file)
            clip = VideoFileClip(file_path)
            clips.append(clip)

        if crossfade > 0 and len(clips) > 1:
            from moviepy.video.fx.CrossFadeIn import CrossFadeIn
            clips_with_fx = [clips[0]]
            for clip in clips[1:]:
                clips_with_fx.append(clip.with_effects([CrossFadeIn(crossfade)]))
            final_video = concatenate_videoclips(clips_with_fx, padding=-crossfade, method="compose")
        else:
            final_video = concatenate_videoclips(clips)

        final_video_path = os.path.join(directory, f"{final_name}.mp4")
        final_video.write_videofile(final_video_path, codec="libx264")
        return final_video_path


def update_review_folder(dataset_dir, script_path, character_photo_path, scene_style_path=None,
                         save_path=None, video_save_path=None, max_keyframe_samples=8):
    """
    把剧本、画风描述、角色参考图、分镜结果及关键帧示例汇总到 dataset_dir/审阅/ 供你查看。
    """
    review_dir = os.path.join(dataset_dir, "审阅")
    os.makedirs(review_dir, exist_ok=True)

    # 剧本：输入剧本
    if script_path and os.path.isfile(script_path):
        dest = os.path.join(review_dir, "剧本_script_synopsis.json")
        shutil.copy2(script_path, dest)

    # 画风描述
    if scene_style_path and os.path.isfile(scene_style_path):
        dest = os.path.join(review_dir, "画风描述_scene_style.txt")
        shutil.copy2(scene_style_path, dest)

    # 角色参考图（布布、一二等）
    if character_photo_path and os.path.isdir(character_photo_path):
        char_review = os.path.join(review_dir, "角色参考图")
        os.makedirs(char_review, exist_ok=True)
        for name in os.listdir(character_photo_path):
            src_sub = os.path.join(character_photo_path, name)
            if os.path.isdir(src_sub):
                dest_sub = os.path.join(char_review, name)
                if os.path.exists(dest_sub):
                    shutil.rmtree(dest_sub, ignore_errors=True)
                shutil.copytree(src_sub, dest_sub)

    # 分镜结果（Step_1/2/3）
    if save_path and os.path.isdir(save_path):
        subdirs = [d for d in os.listdir(save_path) if os.path.isdir(os.path.join(save_path, d))]
        for fname in ["Step_1_script_results.json", "Step_2_scene_results.json", "Step_3_shot_results.json"]:
            for sub in subdirs:
                src = os.path.join(save_path, sub, fname)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(review_dir, fname))
                    break

    # 关键帧示例（生成好的布布一二等，前 N 张）
    if video_save_path and os.path.isdir(video_save_path):
        jpgs = sorted([f for f in os.listdir(video_save_path) if f.endswith(".jpg")])
        sample_dir = os.path.join(review_dir, "关键帧示例")
        os.makedirs(sample_dir, exist_ok=True)
        for f in jpgs[:max_keyframe_samples]:
            shutil.copy2(os.path.join(video_save_path, f), os.path.join(sample_dir, f))

    print("审阅文件夹已更新:", review_dir)


def main():
    args = parse_args()
    script_path = args.script_path
    character_photo_path = args.character_photo_path

    # 用 OpenAI 生成关键帧时：从布布一二参考图提取「角色+画风」描述并注入每镜 prompt，使成片像布布一二
    if getattr(args, "gen_model", None) in ("OpenAI", "DALLE") and character_photo_path:
        style_path = os.path.join(os.path.dirname(character_photo_path), "character_style.txt")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                args.character_style_text = f.read()
        else:
            from utils.character_style import get_character_style_text
            args.character_style_text = get_character_style_text(character_photo_path, cache_path=style_path) or ""

    # 用 Replicate 或 Gemini 生成关键帧时：画风图 → GPT-4V 描述 → 每镜 prompt 前注入（可选）
    if getattr(args, "gen_model", None) in ("Replicate", "Gemini") and character_photo_path:
        dataset_dir = os.path.dirname(character_photo_path)
        scene_style_path = os.path.join(dataset_dir, "scene_style.txt")
        style_ref_dir = os.path.join(dataset_dir, "style_reference")
        if os.path.isdir(style_ref_dir):
            from utils.scene_style import get_scene_style_text
            args.scene_style_text = get_scene_style_text(style_ref_dir, cache_path=scene_style_path) or ""
        elif os.path.exists(scene_style_path):
            with open(scene_style_path, "r", encoding="utf-8") as f:
                args.scene_style_text = f.read().strip()
        else:
            args.scene_style_text = ""

    dataset_dir = os.path.dirname(character_photo_path)
    scene_style_path = os.path.join(dataset_dir, "scene_style.txt")
    update_review_folder(dataset_dir, script_path, character_photo_path, scene_style_path=scene_style_path)

    movie_director = ScriptBreakAgent(args,sample_model=args.gen_model, audio_model=args.audio_model, \
                                      talk_model=args.talk_model, Image2Video=args.Image2Video, script_path = script_path, \
                                    character_photo_path=character_photo_path, \
                                    save_mode="video")

    if getattr(args, "only_final", False):
        print("[only_final] 跳过所有生成步骤，直接拼接最终视频。")
    elif getattr(args, "resume_from_shots", False) and os.path.isfile(movie_director.shot_path):
        print("使用已有分镜结果，跳过 ScriptBreak / ScenePlanning / ShotPlotCreate，只跑关键帧与图生视频。")
        movie_director.VideoAudioGen()
    else:
        movie_director.ScriptBreak()
        movie_director.ScenePlanning()
        movie_director.ShotPlotCreate()
        if getattr(args, "only_planning", False):
            print("[only_planning] 分镜规划完成，不生成视频。")
            return
        movie_director.VideoAudioGen()

    if getattr(args, "skip_video", False):
        print("[skip_video] 关键帧已生成，跳过视频拼接。")
        print(f"关键帧位置: {movie_director.video_save_path}")
        return
    update_review_folder(
        dataset_dir, script_path, character_photo_path,
        scene_style_path=os.path.join(dataset_dir, "scene_style.txt"),
        save_path=movie_director.save_path,
        video_save_path=movie_director.video_save_path,
    )
    # movie_director.AudioGen(script_path)
    movie_director.Final(crossfade=args.crossfade, final_name=args.final_name)


if __name__ == "__main__":
    main()











