"""
xpak.py — BOCW T8 engine XPAK / FastFile localization extractor.

Supports:
  - .xpak   : Treyarch XPAK archive (magic 0x4950414B = b'IPAK')
  - .ff      : IW/Treyarch FastFile (magic 0x49570000 / 'IWff')
  - .str     : Legacy plain-text localizedstrings (CoD4-WaW compat shim)

String asset type IDs (T8 engine, community-researched):
  0x2E  = localize (string table)
  0x41  = localized string pool

All offsets and sizes are little-endian unless noted.
"""

from __future__ import annotations

import io
import os
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

XPAK_MAGIC        = b"IPAK"           # 4-byte magic for .xpak
FF_MAGIC_PREFIX   = b"IWff"           # first 4 bytes of .ff FastFile
STR_REFERENCE_KEY = b"REFERENCE"      # .str file key prefix

# T8 asset type for localize entries
T8_ASSET_LOCALIZE = 0x2E

# Minimum printable-ASCII run to count as a candidate string during bruteforce
MIN_STR_LEN = 4

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LocalizeEntry:
    """A single (key, value) localization pair extracted from a game file."""
    key: str          # string reference name / hash hex
    value: str        # display text
    offset: int = 0   # byte offset inside the source file (for patching)
    encoding: str = "utf-8"


@dataclass
class ParseResult:
    """Result returned by every parser function."""
    source_path: Path
    entries: List[LocalizeEntry] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    format_detected: str = "unknown"

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _read_cstring(buf: bytes, offset: int) -> Tuple[str, int]:
    """Read a null-terminated C string from *buf* starting at *offset*.
    Returns (string, new_offset_after_null)."""
    end = buf.index(b"\x00", offset)
    raw = buf[offset:end]
    text = raw.decode("utf-8", errors="replace")
    return text, end + 1


def _scan_strings(data: bytes) -> Iterator[Tuple[int, str]]:
    """
    Brute-force scan: yield (offset, string) for every printable ASCII run
    longer than MIN_STR_LEN that is null-terminated.
    Used as fallback when the structured parser fails.
    """
    i = 0
    length = len(data)
    while i < length:
        if 0x20 <= data[i] <= 0x7E:
            start = i
            while i < length and 0x20 <= data[i] <= 0x7E:
                i += 1
            if i < length and data[i] == 0x00:
                run = data[start:i].decode("ascii", errors="replace")
                if len(run) >= MIN_STR_LEN:
                    yield start, run
                i += 1  # skip null
        else:
            i += 1


# ---------------------------------------------------------------------------
# Plain-text .str parser  (CoD3, CoD4, WaW)
# ---------------------------------------------------------------------------

def _parse_str_file(path: Path) -> ParseResult:
    result = ParseResult(source_path=path, format_detected="str")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result.errors.append(str(exc))
        return result

    current_key: Optional[str] = None
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("REFERENCE"):
            parts = line.split(None, 1)
            current_key = parts[1].strip() if len(parts) > 1 else ""
        elif line.upper().startswith("LANG_ENGLISH") and current_key is not None:
            parts = line.split(None, 1)
            value = parts[1].strip().strip('"') if len(parts) > 1 else ""
            result.entries.append(LocalizeEntry(key=current_key, value=value))
            current_key = None
    return result


# ---------------------------------------------------------------------------
# XPAK parser  (.xpak — IPAK magic)
# ---------------------------------------------------------------------------

_XPAK_HEADER_FMT = "<4sIIII"   # magic, version, asset_count, unk1, unk2
_XPAK_HEADER_SZ  = struct.calcsize(_XPAK_HEADER_FMT)

_XPAK_ENTRY_FMT  = "<QQIQ"     # name_hash, data_offset, data_size, asset_type
_XPAK_ENTRY_SZ   = struct.calcsize(_XPAK_ENTRY_FMT)


def _parse_xpak(path: Path) -> ParseResult:
    result = ParseResult(source_path=path, format_detected="xpak")
    try:
        data = path.read_bytes()
    except OSError as exc:
        result.errors.append(str(exc))
        return result

    if len(data) < _XPAK_HEADER_SZ or data[:4] != XPAK_MAGIC:
        # Fallback to brute-force scan
        result.format_detected = "xpak-bruteforce"
        return _bruteforce_scan(path, data, result)

    try:
        magic, version, asset_count, unk1, unk2 = struct.unpack_from(
            _XPAK_HEADER_FMT, data, 0
        )
    except struct.error as exc:
        result.errors.append(f"Header parse error: {exc}")
        return _bruteforce_scan(path, data, result)

    entry_table_offset = _XPAK_HEADER_SZ
    for i in range(asset_count):
        off = entry_table_offset + i * _XPAK_ENTRY_SZ
        if off + _XPAK_ENTRY_SZ > len(data):
            result.errors.append(f"Entry {i}: offset out of bounds")
            break
        try:
            name_hash, data_off, data_sz, asset_type = struct.unpack_from(
                _XPAK_ENTRY_FMT, data, off
            )
        except struct.error as exc:
            result.errors.append(f"Entry {i} unpack error: {exc}")
            continue

        if asset_type != T8_ASSET_LOCALIZE:
            continue

        # Extract and parse the localize blob
        blob = data[data_off : data_off + data_sz]
        _parse_localize_blob(blob, data_off, name_hash, result)

    if not result.entries:
        # Nothing found structurally — try brute force
        return _bruteforce_scan(path, data, result)

    return result


def _parse_localize_blob(
    blob: bytes,
    base_offset: int,
    name_hash: int,
    result: ParseResult,
) -> None:
    """
    Parse a raw localize asset blob.

    T8 localize blob layout (approximated from community RE):
      4 bytes  : entry count (uint32 LE)
      For each entry:
        8 bytes  : string hash (uint64 LE)
        4 bytes  : string data offset relative to blob start (uint32 LE)
      String pool follows the entry table.
    """
    if len(blob) < 4:
        return
    try:
        entry_count = struct.unpack_from("<I", blob, 0)[0]
    except struct.error:
        return

    ENTRY_SZ = 12   # 8 (hash) + 4 (offset)
    table_end = 4 + entry_count * ENTRY_SZ

    for i in range(entry_count):
        off = 4 + i * ENTRY_SZ
        if off + ENTRY_SZ > len(blob):
            result.errors.append(
                f"Localize blob: entry {i} out of bounds (hash={name_hash:#x})"
            )
            break
        str_hash, str_data_off = struct.unpack_from("<QI", blob, off)
        abs_str_off = table_end + str_data_off
        if abs_str_off >= len(blob):
            continue
        try:
            value, _ = _read_cstring(blob, abs_str_off)
        except (ValueError, UnicodeDecodeError):
            continue
        if value:
            result.entries.append(
                LocalizeEntry(
                    key=f"{str_hash:#018x}",
                    value=value,
                    offset=base_offset + abs_str_off,
                )
            )


# ---------------------------------------------------------------------------
# FastFile parser  (.ff)
# ---------------------------------------------------------------------------

_FF_HEADER_FMT = "<4sHHII"    # magic4, version, unk, asset_count, string_count
_FF_HEADER_SZ  = struct.calcsize(_FF_HEADER_FMT)


def _parse_fastfile(path: Path) -> ParseResult:
    result = ParseResult(source_path=path, format_detected="fastfile")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        result.errors.append(str(exc))
        return result

    # FastFiles may be zlib-compressed after header
    if raw[:4] == FF_MAGIC_PREFIX:
        try:
            payload = zlib.decompress(raw[_FF_HEADER_SZ:], wbits=-15)
            data = raw[:_FF_HEADER_SZ] + payload
        except zlib.error:
            data = raw   # not compressed, or different algo
    else:
        data = raw

    # Brute-force scan the decompressed data for localize strings
    return _bruteforce_scan(path, data, result)


# ---------------------------------------------------------------------------
# Brute-force fallback
# ---------------------------------------------------------------------------

def _bruteforce_scan(
    path: Path,
    data: bytes,
    result: Optional[ParseResult] = None,
) -> ParseResult:
    if result is None:
        result = ParseResult(source_path=path, format_detected="bruteforce")
    else:
        result.format_detected += "+bruteforce"

    seen: set = set()
    for offset, s in _scan_strings(data):
        if s in seen:
            continue
        seen.add(s)
        result.entries.append(
            LocalizeEntry(key=f"0x{offset:08x}", value=s, offset=offset)
        )
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_file(path: Path) -> ParseResult:
    """Detect file type and extract localization entries."""
    suffix = path.suffix.lower()
    if suffix == ".str":
        return _parse_str_file(path)
    elif suffix == ".xpak":
        return _parse_xpak(path)
    elif suffix == ".ff":
        return _parse_fastfile(path)
    else:
        # Unknown extension — try brute-force
        try:
            data = path.read_bytes()
        except OSError as exc:
            r = ParseResult(source_path=path)
            r.errors.append(str(exc))
            return r
        return _bruteforce_scan(path, data)


def scan_directory(game_dir: Path) -> List[ParseResult]:
    """
    Walk *game_dir* and parse every localization-candidate file.
    Candidate files: *.xpak, *.ff, *.str  that contain "local" in name.
    """
    results: List[ParseResult] = []
    patterns = ("*.xpak", "*.ff", "*.str")
    for pattern in patterns:
        for p in sorted(game_dir.rglob(pattern)):
            name_lower = p.name.lower()
            # Only process files likely to contain localization data
            if any(
                keyword in name_lower
                for keyword in ("local", "string", "lang", "text", "ui", "menu")
            ):
                results.append(parse_file(p))
    return results
