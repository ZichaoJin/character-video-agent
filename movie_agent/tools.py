import sys
import os
import json

from tqdm import tqdm




class GenModel:
    def __init__(self,args, model_name, save_mode="video") -> None:
        self.save_mode = save_mode
        if model_name == "vc2":
            from models.VC2.vc2_predict import VideoCrafter
            self.predictor = VideoCrafter("vc2")
        elif model_name == "vc09":
            from models.VC09.vc09_predict import VideoCrafter09
            self.predictor = VideoCrafter09()
        elif model_name == "modelscope":
            from models.modelscope.modelscope_predict import ModelScope
            self.predictor = ModelScope()
        elif model_name == "latte1":
            from models.latte.latte_1_predict import Latte1
            self.predictor = Latte1()
            
        elif model_name == "SDXL-1":
            from models.SD.sd_predict import SDXL
            self.predictor = SDXL()
        elif model_name == "SD-21":
            from models.SD.sd_predict import SD21
            self.predictor = SD21()
        elif model_name == "SD-14":
            from models.SD.sd_predict import SD14
            self.predictor = SD14()
        elif model_name == "SD-3":
            from models.SD.sd_predict import SD3
            self.predictor = SD3() 
        elif model_name == "ConsisID":
            from models.ConsisID.consisid_predict import ConsisID
            self.predictor = ConsisID(model_path="/storage/wuweijia/MovieGen/MovieDirector/MovieDirector/movie_agent/ckpts") 
        elif model_name == "StoryDiffusion":
            from models.StoryDiffusion.storydiffusion import StoryDiffusion
            # self.predictor = StoryDiffusion()
        elif model_name == "OmniGen":
            from models.OmniGen.OmniGen import OminiGen_pipe
            self.predictor = OminiGen_pipe()
        elif model_name == "ROICtrl":
            from models.ROICtrl.ROICtrl import ROICtrl_pipe
            self.predictor = ROICtrl_pipe(args.pretrained_roictrl , args.roictrl_path)
        elif model_name in ("OpenAI", "DALLE"):
            from models.OpenAI_DALLE.openai_dalle import OpenAI_DALLE_pipe
            self.predictor = OpenAI_DALLE_pipe(
                model=getattr(args, "dalle_model", "dall-e-3"),
                size=getattr(args, "dalle_size", "1792x1024"),
                quality=getattr(args, "dalle_quality", "standard"),
                character_style_text=getattr(args, "character_style_text", None),
            )
        elif model_name in ("Replicate", "Replicate_flux_kontext"):
            from models.Replicate_Consistent.replicate_consistent import Replicate_Consistent_pipe
            self.predictor = Replicate_Consistent_pipe(
                model=getattr(args, "replicate_model", "ideogram-ai/ideogram-character"),
                character_photo_path=getattr(args, "character_photo_path", "") or "",
                scene_style_text=getattr(args, "scene_style_text", None) or "",
                number_of_outputs=getattr(args, "replicate_number_of_outputs", 1),
                output_format=getattr(args, "replicate_output_format", "png"),
                output_quality=getattr(args, "replicate_output_quality", 90),
            )
        elif model_name == "Gemini":
            from models.Gemini_Image.gemini_image import Gemini_Image_pipe
            self.predictor = Gemini_Image_pipe(
                model=getattr(args, "gemini_model", "gemini-3-pro-image-preview"),
                character_photo_path=getattr(args, "character_photo_path", "") or "",
                scene_style_text=getattr(args, "scene_style_text", None) or "",
                api_key=os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"),
            )
        else:
            raise ValueError(f"This {model_name} has not been implemented yet")
    
    
    def predict(self, prompt, refer_image, character_box, save_path, size):
        # os.makedirs(save_path, exist_ok=True)
        # name = prompt.strip().replace(" ", "_")
        # if self.save_mode == "video":
        #     save_name = os.path.join(save_path, f"{name}.mp4")
        # elif self.save_mode == "img":
        #     save_name = os.path.join(save_path, f"{name}.png")
        # else:
        #     raise NotImplementedError(f"Wrong mode -- {self.save_mode}")
        
        self.predictor.predict(prompt, refer_image, character_box, save_path, size)
        return prompt, save_path





class ToolBox:
    def __init__(self) -> None:
        pass
    

    def call(self, tool_name, video_pairs):
        method = getattr(self, tool_name, None)
        
        
        if callable(method):
            return method(video_pairs)
        else:
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{tool_name}'")
    
    def color_binding(self, image_pairs):
        sys.path.insert(0, "eval_tools/t2i_comp/BLIPvqa_eval")
        from eval_tools.t2i_comp.BLIPvqa_eval.BLIP_vqa_eval_agent import calculate_attribute_binding
        results = calculate_attribute_binding(image_pairs)
        return results
    
    def shape_binding(self, image_pairs):
        sys.path.insert(0, "eval_tools/t2i_comp/BLIPvqa_eval")
        from eval_tools.t2i_comp.BLIPvqa_eval.BLIP_vqa_eval_agent import calculate_attribute_binding
        results = calculate_attribute_binding(image_pairs)
        return results

    def texture_binding(self, image_pairs):
        sys.path.insert(0, "eval_tools/t2i_comp/BLIPvqa_eval")
        from eval_tools.t2i_comp.BLIPvqa_eval.BLIP_vqa_eval_agent import calculate_attribute_binding
        results = calculate_attribute_binding(image_pairs)
        return results
    

    def non_spatial(self, image_pairs):
        sys.path.insert(0, "eval_tools/t2i_comp/CLIPScore_eval")
        from eval_tools.t2i_comp.CLIPScore_eval.CLIP_similarity_eval_agent import calculate_clip_score
        results = calculate_clip_score(image_pairs)
        return results
    
    
    def overall_consistency(self, video_pairs):
        from eval_tools.vbench.overall_consistency import compute_overall_consistency
        results = compute_overall_consistency(video_pairs)
        return results
    
    
    def aesthetic_quality(self, video_pairs):
        from eval_tools.vbench.aesthetic_quality import compute_aesthetic_quality
        results = compute_aesthetic_quality(video_pairs)
        return results

    def appearance_style(self, video_pairs):
        from eval_tools.vbench.appearance_style import compute_appearance_style
        results = compute_appearance_style(video_pairs)
        return results
    
    
    def background_consistency(self, video_pairs):
        from eval_tools.vbench.background_consistency import compute_background_consistency
        results = compute_background_consistency(video_pairs)
        return results

    def color(self, video_pairs):
        from eval_tools.vbench.color import compute_color
        results = compute_color(video_pairs)
        return results
    
    def dynamic_degree(self, video_pairs):
        from eval_tools.vbench.dynamic_degree import compute_dynamic_degree
        results = compute_dynamic_degree(video_pairs)
        return results

    def human_action(self, video_pairs):
        from eval_tools.vbench.human_action import compute_human_action
        results = compute_human_action(video_pairs)
        return results

    def imaging_quality(self, video_pairs):
        from eval_tools.vbench.imaging_quality import compute_imaging_quality
        results = compute_imaging_quality(video_pairs)
        return results

    def motion_smoothness(self, video_pairs):
        from eval_tools.vbench.motion_smoothness import compute_motion_smoothness
        results = compute_motion_smoothness(video_pairs)
        return results

    def multiple_objects(self, video_pairs):
        from eval_tools.vbench.multiple_objects import compute_multiple_objects
        results = compute_multiple_objects(video_pairs)
        return results

    def object_class(self, video_pairs):
        from eval_tools.vbench.object_class import compute_object_class
        results = compute_object_class(video_pairs)
        return results
    
    def scene(self, video_pairs):
        from eval_tools.vbench.scene import compute_scene
        results = compute_scene(video_pairs)
        return results
    
    def spatial_relationship(self, video_pairs):
        from eval_tools.vbench.spatial_relationship import compute_spatial_relationship
        results = compute_spatial_relationship(video_pairs)
        return results

    def subject_consistency(self, video_pairs):
        from eval_tools.vbench.subject_consistency import compute_subject_consistency
        results = compute_subject_consistency(video_pairs)
        return results

    def temporal_style(self, video_pairs):
        from eval_tools.vbench.temporal_style import compute_temporal_style
        results = compute_temporal_style(video_pairs)
        return results



class AudioGenModel:
    def __init__(self, model_name, photo_audio_path, characters_list) -> None:
        self.predictor = None
        if model_name and model_name != "NoAudio":
            if model_name == "VALL-E":
                from models.VALLE.VALL_E import VALLE_pipe
                self.predictor = VALLE_pipe(photo_audio_path, characters_list)
            else:
                raise ValueError(f"This {model_name} has not been implemented yet")

    def predict(self, subtitle, save_path):
        if self.predictor is not None:
            self.predictor.predict(subtitle, save_path)
        return subtitle, save_path
    

class TalkingModel:
    def __init__(self, model_name) -> None:
        pass
        # if model_name == "Hallo2":
        #     from models.VALLE.VALL_E import VALLE_pipe
        #     self.predictor = VALLE_pipe()
        # else:
        #     raise ValueError(f"This {model_name} has not been implemented yet")
    
    
    def predict(self, subtitle, save_path):
        pass
        
        # self.predictor.predict(subtitle, save_path)
        # return subtitle, save_path

class Image2VideoModel:
    def __init__(self, args,model_name) -> None:
        # pass
        if model_name == "CogVideoX":
            from models.CogVideoX.CogVideoX import CogVideoX_pipe
            self.predictor = CogVideoX_pipe()
        elif model_name == "SVD":
            from models.SVD.svd import SVD_pipe
            self.predictor = SVD_pipe()
        elif model_name == "I2Vgen":
            from models.I2Vgen.I2Vgen import I2Vgen_pipe
            self.predictor = I2Vgen_pipe()
        elif model_name == "HunyuanVideo_I2V":
            from models.HunyuanVideo_I2V.HunyuanVideo_I2V import HunyuanVideo_I2V_pipe
            self.predictor = HunyuanVideo_I2V_pipe(args)
        elif model_name == "Runway":
            from models.Runway_I2V.runway_i2v import Runway_I2V_pipe
            self.predictor = Runway_I2V_pipe(
                model=getattr(args, "runway_model", "gen4_turbo"),
                duration=getattr(args, "runway_duration", 2),
                ratio=getattr(args, "runway_ratio", "1280:720"),
            )
        else:
            raise ValueError(f"This {model_name} has not been implemented yet")
    
    
    def predict(self, prompt, image_path,video_save_path, size):

        self.predictor.predict(prompt, image_path,video_save_path, size)
        return image_path

class ToolCalling:
    def __init__(self, args, sample_model, audio_model, talk_model, Image2Video, photo_audio_path, characters_list, save_mode):
        self.args = args
        self.gen = GenModel(args, sample_model, save_mode)
        self.audio_gen = AudioGenModel(audio_model,photo_audio_path,characters_list)
        self.talk_gen = TalkingModel(talk_model)
        # --skip_video 时不初始化 Image2VideoModel，避免强制检查 Runway key
        self.image2video = None if getattr(args, "skip_video", False) else Image2VideoModel(args,Image2Video)
        self.eval_tools = ToolBox()


    def sample(self, prompt, refer_path, character_box, subtitle, save_path, size = (1024, 512)):
        original_plot = prompt  # 保留原始分镜 plot，Runway 需要用这个而不是 Gemini 改写后的指令
        _unused, content = self.gen.predict(prompt, refer_path, character_box, save_path, size)
        video_save_path = save_path.replace(".jpg", ".mp4")
        # --skip_video 时只生成关键帧，跳过图生视频
        if getattr(self.args, "skip_video", False):
            return save_path
        # Runway 指数退避重试 ×3（间隔 30s / 60s / 120s，对 Runway 分钟级子限额有效）
        import time as _time
        last_err = None
        for attempt in range(3):
            try:
                save_path = self.image2video.predict(original_plot, save_path, video_save_path, size)
                last_err = None
                break
            except Exception as e:
                last_err = e
                wait = 30 * (attempt + 1)  # 30s / 60s / 120s
                print(f"[Runway重试 {attempt+1}/3] {e}，{wait}s 后重试…")
                _time.sleep(wait)
        if last_err is not None:
            print(f"[Runway全部失败] 本镜跳过，关键帧已保存: {save_path}，错误: {last_err}")
        return save_path

    def eval(self, tool_name, video_pairs):
        results = self.eval_tools.call(tool_name, video_pairs)
        return results





def save_json(content, file_path):
    with open(file_path, 'w') as json_file:
        json.dump(content, json_file, indent=4)
        
