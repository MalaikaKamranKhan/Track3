"""Turn an uploaded file into plain text for battles: .txt, .md, .csv and .pdf."""
from __future__ import annotations

import io

MAX_BYTES = 8 * 1024 * 1024
TEXT_TYPES = (".txt", ".md", ".markdown", ".csv")


class NotesError(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if len(data) > MAX_BYTES:
        raise NotesError("That file is over 8 MB. Try a smaller PDF or paste the key slides as text.")
    if name.endswith(TEXT_TYPES):
        text = data.decode("utf-8", errors="ignore")
    elif name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:40])
        except Exception as exc:  # noqa: BLE001 - any PDF problem becomes one friendly line
            raise NotesError(f"Couldn't read that PDF ({type(exc).__name__}).") from None
    else:
        raise NotesError("I can read .pdf, .txt and .md files.")
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(text) < 40:
        raise NotesError("I couldn't find text in that file. Scanned slides? Try a text PDF or .txt notes.")
    return text
