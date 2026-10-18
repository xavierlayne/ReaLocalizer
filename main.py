#!/usr/bin/env python3
"""
main.py — CLI + GUI launcher for the BOCW Turkish Localization Patcher.

Usage examples
--------------
# Open the GUI (default)
  python main.py

# CLI: scan a game dir and export strings to JSON for manual editing
  python main.py scan "C:\\Games\\BOCW" --export strings.json

# CLI: translate using API and apply patch immediately
  python main.py patch "C:\\Games\\BOCW" --override my_translations.json

# CLI: dry-run (no files changed)
  python main.py patch "C:\\Games\\BOCW" --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _cli_scan(args: argparse.Namespace) -> None:
    from bocw_tr_patch.xpak import scan_directory
    from bocw_tr_patch.translator import export_for_editing

    game_dir = Path(args.game_dir)
    print(f"[scan] Taranıyor: {game_dir}")
    results = scan_directory(game_dir)
    all_strings = []
    for r in results:
        for e in r.entries:
            all_strings.append(e.value)
        if r.errors:
            for err in r.errors:
                print(f"  WARN [{r.source_path.name}]: {err}")

    print(f"[scan] {len(all_strings)} string bulundu, {len(results)} dosya.")

    if args.export:
        out = Path(args.export)
        export_for_editing(all_strings, out)
        print(f"[scan] Dışa aktarıldı → {out}")


def _cli_patch(args: argparse.Namespace) -> None:
    from bocw_tr_patch.xpak import scan_directory
    from bocw_tr_patch.translator import (
        load_override_file,
        translate_entries,
    )
    from bocw_tr_patch.patch import apply_translations

    game_dir = Path(args.game_dir)
    print(f"[patch] Taranıyor: {game_dir}")
    results = scan_directory(game_dir)
    all_entries = [e for r in results for e in r.entries]
    print(f"[patch] {len(all_entries)} string bulundu.")

    overrides: dict = {}
    if args.override:
        overrides = load_override_file(Path(args.override))
        print(f"[patch] {len(overrides)} manuel çeviri yüklendi.")

    all_values = list({e.value for e in all_entries})
    print(f"[patch] Çeviriliyor…")
    translations = translate_entries(all_values, overrides=overrides, verbose=True)

    dry_run = args.dry_run
    total_msgs = []
    for r in results:
        tr_map = {
            e.key: translations.get(e.value, e.value)
            for e in r.entries
            if e.value in translations
        }
        msgs = apply_translations(r, tr_map, dry_run=dry_run)
        total_msgs.extend(msgs)

    if dry_run:
        print("[patch] KUR ÇALIŞMA — hiçbir dosya değiştirilmedi.")
    else:
        print("[patch] Yama uygulandı.")

    if total_msgs:
        print(f"[patch] {len(total_msgs)} uyarı:")
        for m in total_msgs:
            print(f"  {m}")
    else:
        print("[patch] Uyarı yok.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="bocw_tr_patch",
        description="BOCW Türkçe Yama Aracı",
    )
    sub = parser.add_subparsers(dest="command")

    # GUI (default)
    sub.add_parser("gui", help="Grafik arayüzü aç (varsayılan)")

    # scan
    sp = sub.add_parser("scan", help="Oyun klasörünü tara ve stringleri listele")
    sp.add_argument("game_dir", help="Oyun ana klasörü")
    sp.add_argument("--export", metavar="FILE",
                    help="Stringleri düzenleme için JSON dosyasına aktar")

    # patch
    pp = sub.add_parser("patch", help="Çeviri uygula")
    pp.add_argument("game_dir", help="Oyun ana klasörü")
    pp.add_argument("--override", metavar="FILE",
                    help="Manuel çeviri JSON dosyası")
    pp.add_argument("--dry-run", action="store_true",
                    help="Dosyaları değiştirmeden simüle et")

    args = parser.parse_args()

    if args.command == "scan":
        _cli_scan(args)
    elif args.command == "patch":
        _cli_patch(args)
    else:
        # Default: open GUI
        from bocw_tr_patch.gui import run
        run()


if __name__ == "__main__":
    main()
