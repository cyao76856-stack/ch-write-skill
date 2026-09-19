from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile


_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_WORD_TAG = f"{{{_WORD_NAMESPACE}}}t"
_DOCUMENT_TAG = f"{{{_WORD_NAMESPACE}}}document"
_BODY_TAG = f"{{{_WORD_NAMESPACE}}}body"
_PARAGRAPH_TAG = f"{{{_WORD_NAMESPACE}}}p"


def extract_docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(Path(path)) as archive:
            document_xml = archive.read("word/document.xml")
        document = ET.fromstring(document_xml)
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, ET.ParseError):
        raise ValueError("invalid DOCX file") from None

    if document.tag != _DOCUMENT_TAG:
        raise ValueError("invalid DOCX file")
    body = document.find(_BODY_TAG)
    if body is None:
        raise ValueError("invalid DOCX file")

    paragraphs = []
    for paragraph in body.iter(_PARAGRAPH_TAG):
        paragraphs.append("".join(node.text or "" for node in paragraph.iter(_WORD_TAG)))
    return "\n".join(paragraphs)