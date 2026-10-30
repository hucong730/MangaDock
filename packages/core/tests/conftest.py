from io import BytesIO

import pytest
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)


def make_pdf(encrypted: bool = False, with_text: bool = True) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    if with_text:
        font = DictionaryObject()
        font.update(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        resources = DictionaryObject()
        fonts = DictionaryObject()
        fonts[NameObject("/F1")] = font
        resources[NameObject("/Font")] = fonts
        page[NameObject("/Resources")] = resources
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 20 150 Td (First page text) Tj ET")
        page[NameObject("/Contents")] = stream
    if encrypted:
        writer.encrypt("secret")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def pdf_bytes() -> bytes:
    return make_pdf()


@pytest.fixture
def encrypted_pdf_bytes() -> bytes:
    return make_pdf(encrypted=True)


@pytest.fixture
def blank_pdf_bytes() -> bytes:
    return make_pdf(with_text=False)


@pytest.fixture
def docx_bytes() -> bytes:
    document = Document()
    document.add_paragraph("第一章 归来")
    document.add_paragraph("林夏回到旧港。")
    document.add_paragraph("第二章 录音")
    document.add_paragraph("她听见父亲的声音。")
    output = BytesIO()
    document.save(output)
    return output.getvalue()


@pytest.fixture
def empty_docx_bytes() -> bytes:
    output = BytesIO()
    Document().save(output)
    return output.getvalue()
