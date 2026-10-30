import re

from mangadock_core.parsing.errors import NovelParseError
from mangadock_core.schemas import Chapter

CHAPTER_HEADING = re.compile(
    r"(?m)^(第[0-9零一二三四五六七八九十百千万两]+章[^\n]*)$"
)


def clean_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip()


def split_chapters(text: str) -> list[Chapter]:
    matches = list(CHAPTER_HEADING.finditer(text))
    if not matches:
        return [Chapter(index=1, title="正文", text=text)]

    chapters = []
    preamble = clean_text(text[: matches[0].start()])
    if preamble:
        chapters.append(Chapter(index=1, title="序幕", text=preamble))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = clean_text(text[match.end() : end])
        if not body:
            raise NovelParseError("empty", "章节标题后缺少正文")
        chapters.append(
            Chapter(
                index=len(chapters) + 1,
                title=match.group(1).strip(),
                text=body,
            )
        )
    return chapters
