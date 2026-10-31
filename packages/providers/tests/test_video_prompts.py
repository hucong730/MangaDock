from mangadock_providers.video_prompts import (
    build_minimax_h3_prompt,
    build_seedance_prompt,
    build_wan_prompt,
)


def segment() -> dict:
    return {
        "index": 1,
        "duration_s": 7,
        "cuts": [
            {
                "index": 1,
                "duration_s": 3,
                "characters": ["林夏", "周衡"],
                "prompt": "<image1>林夏</image1><image2>周衡</image2>；林夏，辫梢红绳、藏青学生装；周衡，深灰西装、银框眼镜；旧港仓库夜景，双人中景",
                "camera": "缓慢推近",
            },
            {
                "index": 2,
                "duration_s": 4,
                "characters": ["周衡"],
                "prompt": "<image1>周衡</image1>；周衡，深灰西装、银框眼镜；仓库门口，冷色侧光，中近景",
                "camera": "固定机位后拉",
            },
        ],
    }


def test_wan_prompt_describes_only_current_cut() -> None:
    prompt = build_wan_prompt(segment(), 1)

    assert "以输入图片为首帧" in prompt
    assert "林夏，辫梢红绳、藏青学生装" in prompt
    assert "缓慢推近" in prompt
    assert "3 秒" in prompt
    assert "仓库门口" not in prompt
    assert "<image1>" not in prompt


def test_seedance_prompt_uses_four_sections() -> None:
    prompt = build_seedance_prompt(segment(), 1)

    assert prompt.index("[首帧参考]") < prompt.index("[角色与场景]")
    assert prompt.index("[角色与场景]") < prompt.index("[动作与运镜]")
    assert prompt.index("[动作与运镜]") < prompt.index("[输出]")
    assert "单镜头，3 秒" in prompt
    assert "仓库门口" not in prompt


def test_minimax_h3_prompt_uses_official_fields_and_segment_timeline() -> None:
    prompt = build_minimax_h3_prompt(segment(), 1)

    assert "integrated_multimodal_description:" in prompt
    assert "overall_soundscape: No additional dialogue" in prompt
    assert "non_diegetic_music: None" in prompt
    assert "[Shot 1] At 00:00.000" in prompt
    assert "[Shot 2] At 00:03.000" in prompt
    assert "current shot" in prompt
    assert "仓库门口" in prompt
    assert "只生成" in prompt
