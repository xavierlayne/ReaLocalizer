"""
patch.py — In-place string patcher for BOCW localization files.

Strategy:
  1. We only patch string VALUES, never touch keys, offsets, or binary structure.
  2. For structured formats (XPAK): replace bytes at known offsets recorded
     during parsing. The replacement must fit in the same byte-length slot;
     if the Turkish string is longer, we truncate with a warning.
  3. For .str plain-text files: rewrite the whole file with new LANG_ENGLISH values.
  4. Always create a .bak backup before patching.

Encoding: BOCW uses UTF-8 throughout. Turkish chars (ş, ç, ö, ü, ğ, ı, İ …)
are valid UTF-8 and patch cleanly as long as the byte-length fits.
"""

from __future__ import annotations

import shutil
import struct
from pathlib import Path
from typing import Dict, List

from .xpak import LocalizeEntry, ParseResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode_value(value: str, encoding: str = "utf-8") -> bytes:
    return value.encode(encoding, errors="replace") + b"\x00"


def _backup(path: Path) -> Path:
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        shutil.copy2(path, bak)
    return bak


# ---------------------------------------------------------------------------
# Structured binary patcher (XPAK / FF)
# ---------------------------------------------------------------------------

class PatchError(Exception):
    pass


def patch_binary(
    path: Path,
    translations: Dict[str, str],   # key → Turkish value
    original_entries: List[LocalizeEntry],
    dry_run: bool = False,
) -> List[str]:
    """
    Patch *path* in-place using byte offsets recorded in *original_entries*.

    Returns a list of warning/error messages (empty = all good).
    """
    messages: List[str] = []
    data = bytearray(path.read_bytes())

    for entry in original_entries:
        if entry.key not in translations:
            continue
        new_value = translations[entry.key]
        new_bytes = _encode_value(new_value, entry.encoding)
        old_bytes = _encode_value(entry.value, entry.encoding)

        if entry.offset == 0:
            messages.append(
                f"SKIP {entry.key!r}: no offset recorded (brute-force entry)"
            )
            continue

        # Verify old bytes are still at expected offset
        actual = data[entry.offset : entry.offset + len(old_bytes)]
        if actual != old_bytes:
            # Try scanning a ±16 byte window for the old value
            found = False
            for delta in range(-16, 17):
                off = entry.offset + delta
                if off < 0:
                    continue
                if data[off : off + len(old_bytes)] == old_bytes:
                    entry.offset = off
                    found = True
                    break
            if not found:
                messages.append(
                    f"WARN {entry.key!r}: original bytes not found at offset "
                    f"{entry.offset:#x} — skipped"
                )
                continue

        if len(new_bytes) > len(old_bytes):
            # Truncate Turkish string to fit original slot
            max_chars = len(old_bytes) - 1  # reserve null terminator
            new_value_truncated = new_value.encode(entry.encoding)[:max_chars].decode(
                entry.encoding, errors="ignore"
            )
            new_bytes = _encode_value(new_value_truncated, entry.encoding)
            messages.append(
                f"TRUNC {entry.key!r}: Turkish value truncated from "
                f"{len(new_value)} to {len(new_value_truncated)} chars"
            )

        # Pad with nulls if shorter (safe — extra nulls before next string OK)
        patch_bytes = new_bytes + b"\x00" * (len(old_bytes) - len(new_bytes))
        data[entry.offset : entry.offset + len(old_bytes)] = patch_bytes

    if not dry_run:
        _backup(path)
        path.write_bytes(bytes(data))

    return messages


# ---------------------------------------------------------------------------
# Plain-text .str patcher
# ---------------------------------------------------------------------------

def patch_str_file(
    path: Path,
    translations: Dict[str, str],   # reference_key → Turkish value
    dry_run: bool = False,
) -> List[str]:
    """Rewrite a .str file replacing LANG_ENGLISH lines with Turkish values."""
    messages: List[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    output: List[str] = []
    current_key: str | None = None

    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("REFERENCE"):
            parts = stripped.split(None, 1)
            current_key = parts[1].strip() if len(parts) > 1 else ""
            output.append(line)
        elif stripped.upper().startswith("LANG_ENGLISH") and current_key in translations:
            indent = line[: len(line) - len(line.lstrip())]
            new_line = f'{indent}LANG_ENGLISH\t"{translations[current_key]}"\n'
            output.append(new_line)
        else:
            output.append(line)

    if not dry_run:
        _backup(path)
        path.write_text("".join(output), encoding="utf-8")

    return messages


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------

def apply_translations(
    result: ParseResult,
    translations: Dict[str, str],
    dry_run: bool = False,
) -> List[str]:
    """
    Apply *translations* to the file described by *result*.
    Returns a combined list of warnings/errors.
    """
    path = result.source_path
    suffix = path.suffix.lower()

    if suffix == ".str":
        return patch_str_file(path, translations, dry_run=dry_run)
    else:
        return patch_binary(path, translations, result.entries, dry_run=dry_run)
