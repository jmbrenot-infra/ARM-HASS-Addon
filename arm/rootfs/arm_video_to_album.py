#!/usr/bin/env python3
"""Move a finished DVD/Blu-ray rip into its matching music album folder (jmbrenot-infra fork).

abcde writes audio rips to /media/music/<Artist>/<Album>/ (OUTPUTFORMAT in abcde.conf), but
ARM has no equivalent for video: a ripped DVD/BD sits in /media/media/completed/... (if
HandBrake transcoded it) or /media/arm/raw/... (if it did not -- HandBrake needs working
hardware/software encoding, which a disc's raw rip never depends on), invisible next to the
audio rips of the same release (e.g. a bonus DVD bundled with a CD).

Called once per device after a rip finishes (same hook as arm_ma_sync.py in
docker_arm_wrapper_shim.sh); does nothing for an audio CD job. For a DVD/Blu-ray job: finds
the video file(s) (transcoded output if HandBrake succeeded, otherwise the raw rip -- always
move something, a failed transcode must not leave the file stranded), matches the disc's
label against existing <Artist>/<Album> folders under /media/music/ by keyword, and moves the
file there. When no single folder matches unambiguously, moves it to Unknown Artist/Unknown
Album_<job id> instead of guessing -- same convention already used for unidentified audio CDs,
so it surfaces for manual triage rather than getting lost in ARM's internal paths.
"""
import os
import re
import shutil
import sqlite3
import sys

DB_PATH = "/media/arm/db/arm.db"
MUSIC_ROOT = "/media/music"
RAW_ROOT = "/media/arm/raw"
COMPLETED_ROOT = "/media/media/completed"
STOPWORDS = {"the", "a", "an", "of", "and", "vol", "disc", "cd", "dvd"}


def log(msg: str) -> None:
    print(f"[ARM] video-to-album: {msg}", flush=True)


def latest_video_job(devname: str):
    devpath = f"/dev/{devname}"
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            "SELECT job_id, title, label, disctype FROM job "
            "WHERE devpath = ? AND disctype IN ('dvd', 'bluray') "
            "ORDER BY start_time DESC LIMIT 1",
            (devpath,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def find_source_dir(label: str, job_id: int):
    """Prefer the transcoded output; fall back to the raw rip. Either one may be named
    `<label>` or `<label>_<stage>` (ARM appends an arbitrary stage suffix when the plain
    name is already taken by a previous job on the same label)."""
    for root in (COMPLETED_ROOT, RAW_ROOT):
        if not os.path.isdir(root):
            continue
        for base, _dirs, _files in os.walk(root):
            name = os.path.basename(base)
            if name == label or name.startswith(f"{label}_"):
                video_files = [
                    os.path.join(base, f)
                    for f in os.listdir(base)
                    if f.lower().endswith((".mkv", ".mp4", ".m4v"))
                ]
                if video_files:
                    return video_files
    return []


def keywords(text: str):
    tokens = re.split(r"[^A-Za-z0-9]+", text.lower())
    return {t for t in tokens if len(t) > 2 and t not in STOPWORDS}


def find_album_match(label: str, music_root: str = MUSIC_ROOT):
    label_kw = keywords(label)
    if not label_kw:
        return None
    matches = []
    if not os.path.isdir(music_root):
        return None
    for artist in sorted(os.listdir(music_root)):
        artist_path = os.path.join(music_root, artist)
        if artist == "Unknown Artist" or not os.path.isdir(artist_path):
            continue
        artist_kw = keywords(artist)
        if not (artist_kw & label_kw):
            continue
        for album in sorted(os.listdir(artist_path)):
            album_path = os.path.join(artist_path, album)
            if not os.path.isdir(album_path):
                continue
            album_kw = keywords(album)
            if album_kw & label_kw:
                matches.append((artist, album, album_path))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        log(f"ambiguous match for label {label!r}: {[f'{a}/{b}' for a, b, _ in matches]}, not guessing")
    return None


def sanitize(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "-", name)


def main() -> int:
    if len(sys.argv) < 2:
        log("no device given")
        return 1
    devname = sys.argv[1]

    job = latest_video_job(devname)
    if not job:
        return 0  # not a DVD/Blu-ray job (or none found) -- nothing to do
    label = job["label"] or job["title"] or f"job{job['job_id']}"

    video_files = find_source_dir(label, job["job_id"])
    if not video_files:
        log(f"no video file found for {label!r} (job #{job['job_id']}), nothing to move")
        return 0

    match = find_album_match(label)
    if match:
        artist, album, album_path = match
        dest_dir = album_path
        log(f"{label!r} matched {artist}/{album}")
    else:
        dest_dir = os.path.join(MUSIC_ROOT, "Unknown Artist", f"Unknown Album_{job['job_id']}")
        log(f"{label!r} matched no album, moving to Unknown Album_{job['job_id']}")

    os.makedirs(dest_dir, exist_ok=True)
    for i, src in enumerate(video_files):
        ext = os.path.splitext(src)[1]
        if match:
            name = f"{sanitize(album)} - DVD bonus.mkv" if i == 0 else f"{sanitize(album)} - DVD bonus ({i + 1}){ext}"
        else:
            name = f"{sanitize(label)}{ext}" if i == 0 else f"{sanitize(label)} ({i + 1}){ext}"
        dest = os.path.join(dest_dir, name)
        shutil.move(src, dest)
        log(f"moved {src} -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
