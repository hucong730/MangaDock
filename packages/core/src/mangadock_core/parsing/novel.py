from io import BytesIO
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from mangadock_core.parsing.chapters import clean_text, split_chapters
from mangadock_core.parsing.errors import NovelParseError
from mangadock_core.schemas import Novel


def parse_novel(filename: str, content: bytes) -> Novel:
    if not content:
        raise NovelParseError("empty", "文件为空，未包含可用文本")

    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".txt":
            text = content.decode("utf-8-sig")
        elif suffix == ".pdf":
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise NovelParseError("encrypted", "PDF 已加密，无法读取")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif suffix == ".docx":
            document = Document(BytesIO(content))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        else:
            raise NovelParseError("unsupported", "仅支持 PDF、DOCX 和 TXT 文件")
    except UnicodeDecodeError as error:
        raise NovelParseError("encoding", "TXT 文件必须使用 UTF-8 编码") from error
    except NovelParseError:
        raise
    except Exception as error:
        raise NovelParseError("corrupted", "文件损坏或无法解析") from error

    text = clean_text(text)
    if not text:
        raise NovelParseError("empty", "文件为空，未包含可用文本")
    title = Path(filename).stem or "未命名小说"
    return Novel(title=title, chapters=split_chapters(text))
