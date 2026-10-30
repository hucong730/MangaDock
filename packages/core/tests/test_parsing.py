from pathlib import Path

import pytest

from mangadock_core.parsing import NovelParseError, parse_novel


def test_parse_txt_into_chapters() -> None:
    content = Path("tests/fixtures/tiny.txt").read_bytes()

    novel = parse_novel("tiny.TXT", content)

    assert novel.title == "tiny"
    assert [chapter.title for chapter in novel.chapters] == [
        "第一章 归来",
        "第二章 录音",
    ]
    assert "林夏回到旧港。" in novel.chapters[0].text


def test_parse_pdf(pdf_bytes: bytes) -> None:
    novel = parse_novel("sample.pdf", pdf_bytes)

    assert novel.title == "sample"
    assert len(novel.chapters) == 1
    assert "First page text" in novel.chapters[0].text


def test_parse_docx_into_chapters(docx_bytes: bytes) -> None:
    novel = parse_novel("sample.docx", docx_bytes)

    assert novel.title == "sample"
    assert len(novel.chapters) == 2
    assert novel.chapters[1].title == "第二章 录音"
    assert "父亲" in novel.chapters[1].text


def test_text_without_chapter_heading_becomes_single_chapter() -> None:
    novel = parse_novel("plain.txt", "没有章节标记的内容。".encode())

    assert len(novel.chapters) == 1
    assert novel.chapters[0].title == "正文"


@pytest.mark.parametrize("suffix", ["txt", "pdf", "docx"])
def test_empty_file_has_specific_error(suffix: str) -> None:
    with pytest.raises(NovelParseError, match="空") as error:
        parse_novel(f"empty.{suffix}", b"")

    assert error.value.code == "empty"


def test_blank_pdf_has_empty_error(blank_pdf_bytes: bytes) -> None:
    with pytest.raises(NovelParseError) as error:
        parse_novel("blank.pdf", blank_pdf_bytes)
    assert error.value.code == "empty"


def test_empty_docx_has_empty_error(empty_docx_bytes: bytes) -> None:
    with pytest.raises(NovelParseError) as error:
        parse_novel("empty.docx", empty_docx_bytes)
    assert error.value.code == "empty"


def test_corrupted_pdf_has_specific_error() -> None:
    with pytest.raises(NovelParseError) as error:
        parse_novel("broken.pdf", b"not a pdf")
    assert error.value.code == "corrupted"


def test_encrypted_pdf_has_specific_error(encrypted_pdf_bytes: bytes) -> None:
    with pytest.raises(NovelParseError) as error:
        parse_novel("encrypted.pdf", encrypted_pdf_bytes)
    assert error.value.code == "encrypted"


def test_invalid_utf8_has_specific_error() -> None:
    with pytest.raises(NovelParseError) as error:
        parse_novel("invalid.txt", b"\xff\xfe\x00")
    assert error.value.code == "encoding"


def test_unsupported_extension_has_specific_error() -> None:
    with pytest.raises(NovelParseError) as error:
        parse_novel("novel.epub", b"content")
    assert error.value.code == "unsupported"


def test_whitespace_only_text_has_empty_error() -> None:
    with pytest.raises(NovelParseError) as error:
        parse_novel("blank.txt", " \n\t ".encode())
    assert error.value.code == "empty"


@pytest.mark.parametrize("text", ["第一章\n第二章\n正文", "第一章\n"])
def test_empty_chapter_body_has_specific_error(text: str) -> None:
    with pytest.raises(NovelParseError) as error:
        parse_novel("empty-chapter.txt", text.encode())
    assert error.value.code == "empty"


def test_preamble_is_preserved_as_prologue() -> None:
    novel = parse_novel(
        "prologue.txt",
        "序幕内容。\n第一章 归来\n林夏回到旧港。".encode(),
    )

    assert [chapter.title for chapter in novel.chapters] == ["序幕", "第一章 归来"]
    assert novel.chapters[0].text == "序幕内容。"
