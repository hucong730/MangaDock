import re
from collections.abc import Mapping
from typing import Any

REFERENCE_PATTERN = re.compile(r"<image\d+>([^<]+)</image\d+>")


def current_cut(segment: Mapping[str, Any], cut_index: int) -> Mapping[str, Any]:
    return next(cut for cut in segment["cuts"] if cut["index"] == cut_index)


def clean_prompt(prompt: str) -> str:
    return REFERENCE_PATTERN.sub(r"\1", prompt).strip()


def build_wan_prompt(segment: Mapping[str, Any], cut_index: int) -> str:
    cut = current_cut(segment, cut_index)
    return (
        "以输入图片为首帧，保持角色的身份、服装和外观一致。\n"
        f"{clean_prompt(cut['prompt'])}，人物动作自然连续。\n"
        f"运镜：{cut['camera']}。\n"
        f"生成当前镜头，时长 {cut['duration_s']} 秒，无字幕，无水印。"
    )


def build_seedance_prompt(segment: Mapping[str, Any], cut_index: int) -> str:
    cut = current_cut(segment, cut_index)
    return (
        "[首帧参考]\n使用输入首帧，保持角色身份、服装、配色和画面风格一致。\n\n"
        f"[角色与场景]\n{clean_prompt(cut['prompt'])}。\n\n"
        f"[动作与运镜]\n人物动作自然连续，镜头{cut['camera']}。\n\n"
        f"[输出]\n单镜头，{cut['duration_s']} 秒，不生成字幕或水印。"
    )


def build_minimax_h3_prompt(segment: Mapping[str, Any], cut_index: int) -> str:
    shots = []
    elapsed = 0
    for cut in segment["cuts"]:
        marker = "current shot" if cut["index"] == cut_index else "context only"
        shots.append(
            f"[Shot {cut['index']}] At 00:{elapsed:02d}.000, {marker}: "
            f"{clean_prompt(cut['prompt'])}；运镜：{cut['camera']}；"
            f"时长 {cut['duration_s']} 秒。"
        )
        elapsed += cut["duration_s"]
    return (
        "integrated_multimodal_description: "
        + "\n".join(shots)
        + f"\n本次只生成镜头 {cut_index}，不得合并或生成其他镜头。"
        "\noverall_soundscape: No additional dialogue; only necessary ambient sound."
        "\nnon_diegetic_music: None."
    )
