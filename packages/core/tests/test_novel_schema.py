import pytest
from pydantic import ValidationError

from mangadock_core.schemas import Chapter, Novel


def test_novel_accepts_sequential_chapters() -> None:
    novel = Novel(
        title="旧港",
        chapters=[
            Chapter(index=1, title="第一章 归来", text="林夏回到旧港。"),
            Chapter(index=2, title="第二章 录音", text="她听见父亲的声音。"),
        ],
    )

    assert novel.title == "旧港"
    assert len(novel.chapters) == 2


@pytest.mark.parametrize(
    "value",
    [
        {"title": "", "chapters": [{"index": 1, "title": "正文", "text": "内容"}]},
        {"title": "旧港", "chapters": []},
        {"title": "旧港", "chapters": [{"index": 1, "title": "", "text": "内容"}]},
        {"title": "旧港", "chapters": [{"index": 1, "title": "正文", "text": " "}]},
        {
            "title": "旧港",
            "chapters": [
                {"index": 1, "title": "第一章", "text": "一"},
                {"index": 3, "title": "第三章", "text": "三"},
            ],
        },
    ],
)
def test_novel_rejects_invalid_content(value: dict) -> None:
    with pytest.raises(ValidationError):
        Novel.model_validate(value)


def test_chapter_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Chapter.model_validate(
            {"index": 1, "title": "正文", "text": "内容", "unexpected": True}
        )
