"""Conservative, lossless-enough Aminet readme parsing."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import re


@dataclass(frozen=True)
class ReadmeParse:
    encoding: str
    replacements: int
    fields: dict[str, str]
    raw_text: str
    warnings: tuple[str, ...] = ()
    confidence: str = "low"
    parser_version: str = "amigalab-readme-1"


def decode_readme(path: Path, max_bytes: int = 1_048_576) -> ReadmeParse:
    raw = path.read_bytes()[:max_bytes]
    warnings = []
    if len(path.read_bytes()) > max_bytes:
        warnings.append("text truncated at configured limit")
    if b"\x00" in raw:
        return ReadmeParse("binary", 0, {}, "", ("binary-looking readme",), "unknown")
    for encoding in ("utf-8", "ascii", "cp1252", "iso-8859-1"):
        try:
            text = raw.decode(encoding, errors="strict")
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("iso-8859-1", errors="replace")
        warnings.append("decoding replacements used")
        encoding = "iso-8859-1"
    fields = {}
    patterns = {
        "short_description": r"(?im)^\s*(?:short\s+description|description)\s*:\s*(.+)$",
        "author": r"(?im)^\s*(?:author|written\s+by)\s*:\s*(.+)$",
        "uploader": r"(?im)^\s*uploader\s*:\s*(.+)$",
        "version": r"(?im)^\s*version\s*:\s*(.+)$",
        "requirements": r"(?im)^\s*(?:requires|requirements)\s*:\s*(.+)$",
        "license": r"(?im)^\s*(?:license|copyright|distribution)\s*:\s*(.+)$",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            fields[key] = match.group(1).strip()
    confidence = "medium" if fields else "low"
    return ReadmeParse(encoding, text.count("�"), fields, text, tuple(warnings), confidence)
