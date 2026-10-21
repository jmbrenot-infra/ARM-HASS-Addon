#!/usr/bin/env python3
"""Detect albums where multiple physical discs were ripped into the same
Artist/Album folder (abcde has no disc-aware OUTPUTFORMAT), and reorganize
them into CD1/CD2/.../CDN subfolders with DISCNUMBER/DISCTOTAL tags set.

Disc separation uses, in order: an explicit disc prefix in the filename
(e.g. "2-01 - Title.flac"), a concatenated 3-digit disc+track prefix
(e.g. "104 Title.flac" = disc 1 track 04 -- a real CD TOC never exceeds 99
tracks, so any 3-digit leading number must be disc*100+track), then the
`cddb` tag (each physical disc gets a distinct hash via abcde's TOC lookup),
falling back to a mtime-gap clustering heuristic only as a last resort
(logged loudly, since it is the least reliable signal).

Disc order within a detected group is: filename-encoded disc number if
present, otherwise earliest-mtime-first. This is a *default*, not
necessarily the disc order printed on the physical box set -- run
--dry-run first and sanity-check unusual results by hand.

After reorganizing an album, the top-level `<Artist>-<Album>.m3u` playlist
is (re)written to list the new per-disc paths -- otherwise it would keep
pointing at the old flat layout (or simply be missing) after the move.
"""

import argparse
import os
import re
import shutil
import sys
from collections import defaultdict

from mutagen.flac import FLAC

DEFAULT_ROOT = "/volume1/music/Rips-CD"
MTIME_GAP_SECONDS = 120


def sanitize(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "-", name)


def leading_number_token(filename: str):
    m = re.match(r"^(\d+(?:-\d+)?)", filename)
    return m.group(1) if m else None


def list_albums(root: str):
    for artist in sorted(os.listdir(root)):
        if artist == "@eaDir" or artist == "Unknown Artist":
            continue
        artist_path = os.path.join(root, artist)
        if not os.path.isdir(artist_path):
            continue
        for album in sorted(os.listdir(artist_path)):
            if album == "@eaDir":
                continue
            album_path = os.path.join(artist_path, album)
            if os.path.isdir(album_path):
                yield artist, album, album_path


def read_flacs(album_path: str):
    files = []
    for name in sorted(os.listdir(album_path)):
        if not name.lower().endswith(".flac"):
            continue
        p = os.path.join(album_path, name)
        if not os.path.isfile(p):
            continue  # Synology @eaDir can contain a directory named like a .flac file
        f = FLAC(p)
        files.append({
            "name": name, "path": p,
            "tracknumber": f.get("tracknumber", [None])[0],
            "title": f.get("title", [None])[0],
            "cddb": f.get("cddb", [None])[0],
            "mtime": os.path.getmtime(p),
            "flac": f,
        })
    return files


def detect_disc_groups(files):
    for d in files:
        d["_leading"] = leading_number_token(d["name"])

    has_prefix = any(d["_leading"] and re.match(r"^\d+-\d+$", d["_leading"]) for d in files)
    if has_prefix:
        groups = defaultdict(list)
        for d in files:
            m = re.match(r"^(\d+)-(\d+)$", d["_leading"] or "")
            if m:
                disc = int(m.group(1))
                d["local_track"] = m.group(2)
            else:
                disc = 1
                d["local_track"] = d["_leading"] or d["tracknumber"]
            groups[disc].append(d)
        return [groups[k] for k in sorted(groups.keys())] if len(groups) > 1 else None

    all_3digit = all(d["_leading"] and re.match(r"^[1-9]\d{2}$", d["_leading"]) for d in files)
    if all_3digit:
        groups = defaultdict(list)
        for d in files:
            disc = int(d["_leading"][0])
            d["local_track"] = d["_leading"][1:]
            groups[disc].append(d)
        return [groups[k] for k in sorted(groups.keys())] if len(groups) > 1 else None

    by_cddb = defaultdict(list)
    for d in files:
        by_cddb[d["cddb"]].append(d)
    real_cddbs = [k for k in by_cddb if k is not None]
    if len(real_cddbs) > 1:
        ordered = sorted(real_cddbs, key=lambda k: min(x["mtime"] for x in by_cddb[k]))
        groups = []
        for k in ordered:
            for d in by_cddb[k]:
                d["local_track"] = d["tracknumber"]
            groups.append(by_cddb[k])
        return groups

    by_tn = defaultdict(list)
    for d in files:
        by_tn[d["tracknumber"]].append(d)
    if not any(len(v) > 1 for v in by_tn.values()):
        return None

    ordered_files = sorted(files, key=lambda d: d["mtime"])
    groups = [[ordered_files[0]]]
    for prev, cur in zip(ordered_files, ordered_files[1:]):
        if cur["mtime"] - prev["mtime"] > MTIME_GAP_SECONDS:
            groups.append([])
        groups[-1].append(cur)
    for g in groups:
        for d in g:
            d["local_track"] = d["tracknumber"]
    if len(groups) > 1:
        print(f"  AVERTISSEMENT: separation par ecart temporel (signal le moins fiable) "
              f"pour ce dossier -- a verifier manuellement.", file=sys.stderr)
        return groups
    return None


def write_m3u(root: str, artist: str, album: str, plan: list) -> str:
    """(Re)write the top-level `<Artist>-<Album>.m3u` playlist after an album has been
    reorganized into CD1/CD2/.../CDN, so it reflects the new per-disc paths instead of
    the stale flat ones. Returns the path written."""
    lines = [os.path.join(artist, album, it["new_rel"]) for it in plan]
    m3u_path = os.path.join(root, f"{sanitize(artist)}-{sanitize(album)}.m3u")
    with open(m3u_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return m3u_path


def plan_album(album_path: str):
    files = read_flacs(album_path)
    if not files:
        return None
    groups = detect_disc_groups(files)
    if not groups:
        return None
    total = len(groups)
    plan = []
    for disc_num, group in enumerate(groups, start=1):
        for d in group:
            local_track = d.get("local_track") or d["tracknumber"] or "00"
            try:
                local_track_fmt = f"{int(local_track):02d}"
            except (TypeError, ValueError):
                local_track_fmt = local_track
            new_name = f"{local_track_fmt} - {sanitize(d['title'] or 'Unknown')}.flac"
            plan.append({
                "old_path": d["path"], "old_name": d["name"],
                "new_rel": os.path.join(f"CD{disc_num}", new_name),
                "disc_num": disc_num, "disc_total": total, "flac": d["flac"],
            })
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report planned changes without writing")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="Rips-CD directory to scan")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        print(f"Target directory does not exist: {args.root}", file=sys.stderr)
        return 2

    albums_found = albums_fixed = failures = 0
    for artist, album, album_path in list_albums(args.root):
        try:
            plan = plan_album(album_path)
        except Exception as error:
            failures += 1
            print(f"Failed to inspect {album_path}: {error}", file=sys.stderr)
            continue
        if not plan:
            continue
        albums_found += 1
        discs = sorted(set(p["disc_num"] for p in plan))
        print(f"{artist} / {album}: {len(discs)} discs, {len(plan)} files"
              f"{' (dry-run)' if args.dry_run else ''}")
        if args.dry_run:
            continue
        try:
            for it in plan:
                new_path = os.path.join(album_path, it["new_rel"])
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                f = it["flac"]
                f["discnumber"] = [str(it["disc_num"])]
                f["disctotal"] = [str(it["disc_total"])]
                f.save()
                shutil.move(it["old_path"], new_path)
            write_m3u(args.root, artist, album, plan)
            albums_fixed += 1
        except Exception as error:
            failures += 1
            print(f"Failed to reorganize {album_path}: {error}", file=sys.stderr)

    action = "found" if args.dry_run else "fixed"
    print(f"albums-with-multiple-discs-{action}={albums_fixed if not args.dry_run else albums_found} "
          f"failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
