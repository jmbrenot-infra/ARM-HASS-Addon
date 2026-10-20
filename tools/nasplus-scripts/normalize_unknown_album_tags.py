#!/usr/bin/env python3
"""Disambiguate legacy Unknown Album FLAC tags without touching other metadata,
then fix any multi-disc albums that got merged into a single Artist/Album folder
(see fix_multidisc_albums.py for why -- abcde has no disc-aware OUTPUTFORMAT)."""

import argparse
import subprocess
import sys
from pathlib import Path

from mutagen.flac import FLAC


DEFAULT_ROOT = Path("/volume1/music/Rips-CD/Unknown Artist")
PREFIX = "Unknown Album_"
UNSUFFIXED_ALBUM = "Unknown Album"
MULTIDISC_FIX_SCRIPT = "/volume1/scripts/fix_multidisc_albums.py"


def normalize(root: Path, dry_run: bool) -> int:
    scanned = candidates = changed = skipped = failures = 0

    if not root.is_dir():
        print(f"Target directory does not exist: {root}", file=sys.stderr)
        return 2

    for album_dir in sorted(root.iterdir()):
        if not album_dir.is_dir() or not album_dir.name.startswith(PREFIX):
            continue

        cddb_hash = album_dir.name[len(PREFIX):]
        if not cddb_hash:
            skipped += 1
            continue

        desired_album = f"Unknown Album ({cddb_hash})"
        for flac_path in sorted(album_dir.glob("*.flac")):
            scanned += 1
            try:
                audio = FLAC(flac_path)
                album_values = list(audio.tags.get("ALBUM", [])) if audio.tags else []
                if album_values != [UNSUFFIXED_ALBUM]:
                    skipped += 1
                    continue

                candidates += 1
                if not dry_run:
                    audio["ALBUM"] = [desired_album]
                    audio.save()
                    changed += 1
            except Exception as error:  # keep processing unrelated FLAC files
                failures += 1
                print(f"Failed to process {flac_path}: {error}", file=sys.stderr)

    action = "would change" if dry_run else "changed"
    print(
        f"scanned={scanned} {action}={candidates if dry_run else changed} "
        f"already-compliant-or-skipped={skipped} failures={failures}"
    )
    return 1 if failures else 0


def run_multidisc_fix(dry_run: bool) -> int:
    if not Path(MULTIDISC_FIX_SCRIPT).is_file():
        print(f"multi-disc fix script not found, skipping: {MULTIDISC_FIX_SCRIPT}", file=sys.stderr)
        return 0
    cmd = [sys.executable, MULTIDISC_FIX_SCRIPT]
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report eligible files without changing tags")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Unknown Artist directory to scan")
    args = parser.parse_args()
    rc1 = normalize(args.root, args.dry_run)
    rc2 = run_multidisc_fix(args.dry_run)
    return rc1 or rc2


if __name__ == "__main__":
    raise SystemExit(main())
