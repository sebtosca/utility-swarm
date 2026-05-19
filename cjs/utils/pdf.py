from pathlib import Path

import pymupdf


def extract_text_from_pdf(pdf_path: Path, max_pages: int = 20) -> str:
    """
    Extract text from a PDF file up to max_pages.

    Raises:
        FileNotFoundError: If pdf_path does not exist.
        ValueError: If input is not a PDF path or max_pages is invalid.
        RuntimeError: If PDF parsing fails.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {pdf_path}")
    if max_pages < 1:
        raise ValueError("max_pages must be >= 1")

    try:
        with pymupdf.open(pdf_path) as document:
            pages_to_read = min(len(document), max_pages)
            text_chunks: list[str] = []
            for page_index in range(pages_to_read):
                page = document[page_index]
                text_chunks.append(page.get_text("text"))
    except Exception as exc:
        raise RuntimeError(f"Failed to extract text from PDF {pdf_path}: {exc}") from exc

    return "\n".join(text_chunks).strip()
