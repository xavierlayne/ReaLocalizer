"""
translator.py — Translation layer.

Priority order:
  1. Manual override dictionary (user-edited JSON)
  2. Deep-L API (if DEEPL_API_KEY env var is set)
  3. Google Cloud Translate v2 (if GOOGLE_TRANSLATE_KEY env var is set)
  4. No-op fallback (returns original English text unchanged)

The translation cache is written to  translations_cache.json  next to the
running script so re-runs are free and offline-safe.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

_CACHE_FILE = Path("translations_cache.json")


def _load_cache() -> Dict[str, str]:
    if _CACHE_FILE.exists():
        try:
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache: Dict[str, str]) -> None:
    _CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Translation backends
# ---------------------------------------------------------------------------

def _translate_deepl(texts: List[str], api_key: str) -> List[str]:
    """Translate a batch of texts using DeepL Free/Pro REST API."""
    import urllib.request
    import urllib.parse

    endpoint = (
        "https://api-free.deepl.com/v2/translate"
        if api_key.endswith(":fx")
        else "https://api.deepl.com/v2/translate"
    )
    payload = urllib.parse.urlencode(
        [("auth_key", api_key), ("target_lang", "TR")]
        + [("text", t) for t in texts]
    ).encode()
    req = urllib.request.Request(endpoint, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
    return [t["text"] for t in body["translations"]]


def _translate_google(texts: List[str], api_key: str) -> List[str]:
    """Translate a batch of texts using Google Cloud Translate v2."""
    import urllib.request
    import urllib.parse

    endpoint = "https://translation.googleapis.com/language/translate/v2"
    payload = json.dumps(
        {"q": texts, "target": "tr", "source": "en", "format": "text"}
    ).encode()
    url = f"{endpoint}?key={urllib.parse.quote(api_key)}"
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
    return [t["translatedText"] for t in body["data"]["translations"]]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def translate_entries(
    entries: List[str],                    # English source strings
    overrides: Optional[Dict[str, str]] = None,   # manual overrides {en: tr}
    batch_size: int = 50,
    verbose: bool = False,
) -> Dict[str, str]:
    """
    Translate *entries* from English to Turkish.

    Returns a dict mapping each English source string to its Turkish
    translation.  Already-cached strings are never re-sent to the API.
    """
    overrides = overrides or {}
    cache = _load_cache()
    result: Dict[str, str] = {}
    to_translate: List[str] = []

    deepl_key  = os.environ.get("DEEPL_API_KEY", "")
    google_key = os.environ.get("GOOGLE_TRANSLATE_KEY", "")

    for text in entries:
        if not text.strip():
            result[text] = text
            continue
        if text in overrides:
            result[text] = overrides[text]
            continue
        if text in cache:
            result[text] = cache[text]
            continue
        to_translate.append(text)

    if to_translate:
        if deepl_key:
            backend = "DeepL"
            _fn = lambda batch: _translate_deepl(batch, deepl_key)
        elif google_key:
            backend = "Google Translate"
            _fn = lambda batch: _translate_google(batch, google_key)
        else:
            backend = "none (no API key set)"
            _fn = None

        if _fn:
            if verbose:
                print(f"[translator] Using {backend} for {len(to_translate)} strings.")
            for i in range(0, len(to_translate), batch_size):
                batch = to_translate[i : i + batch_size]
                try:
                    translated = _fn(batch)
                    for src, tr in zip(batch, translated):
                        result[src] = tr
                        cache[src] = tr
                except Exception as exc:
                    if verbose:
                        print(f"[translator] API error: {exc} — falling back to originals")
                    for src in batch:
                        result[src] = src
            _save_cache(cache)
        else:
            if verbose:
                print(
                    "[translator] No translation API key found.  "
                    "Set DEEPL_API_KEY or GOOGLE_TRANSLATE_KEY, "
                    "or edit translations_cache.json manually."
                )
            for text in to_translate:
                result[text] = text   # passthrough

    return result


def load_override_file(path: Path) -> Dict[str, str]:
    """Load a user-edited JSON file mapping English → Turkish."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[translator] Could not load override file {path}: {exc}")
        return {}


def export_for_editing(
    strings: List[str],
    output_path: Path,
    existing_cache: Optional[Dict[str, str]] = None,
) -> None:
    """
    Write a JSON file ready for manual translation editing.
    Format: { "English string": "Turkish translation or empty" }
    """
    existing = existing_cache or _load_cache()
    doc = {s: existing.get(s, "") for s in strings}
    output_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[translator] Exported {len(doc)} strings to {output_path}")
