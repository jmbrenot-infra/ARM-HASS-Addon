#!/usr/bin/env python3
"""Finish the album art of a freshly ripped audio CD (jmbrenot-infra fork).

abcde downloads the cover (`getalbumart`), embeds it in the tracks (`embedalbumart`) and then
moves it to `<album>/albumart_backup/`. Two things go wrong for Music Assistant:

- a huge cover (seen: a 55 MB PNG saved as `cover.jpg`) is refused by metaflac ("file is too
  large": a FLAC picture block holds 16 MiB at most). abcde still reports success, so the
  tracks silently end up without art (jmbrenot-infra/ARM-HASS-Addon#26);
- nothing writes `<album>/folder.jpg`, nor the `<Artist>-<Album>.jpg` next to the playlist,
  which is the image Music Assistant shows for a `.m3u` playlist.

Called after each rip, before arm_ma_sync.py (docker_arm_wrapper_shim.sh). For every playlist
written recently under abcde's OUTPUTDIR: builds a bounded JPEG from the downloaded cover,
writes it as `folder.jpg` and as the playlist image, and embeds it in the FLAC tracks that
have no picture. Never overwrites an existing image, never touches a track that already has
art; a DVD/Blu-ray job writes no playlist, so it is a no-op there.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ABCDE_CONF = "/etc/arm/config/abcde.conf"
DEFAULT_OUTPUTDIR = "/media/music"
RECENT_SECONDS = 6 * 3600
MAX_SIDE = 1400
JPEG_QUALITY = "90"
# A FLAC metadata block length is 24 bits; keep a margin for the picture block header.
FLAC_PICTURE_LIMIT = (1 << 24) - 1024
IMAGE_EXTS = (".jpg", ".jpeg", ".png")
COVER_STEMS = ("folder", "cover", "front")
BACKUP_DIR = "albumart_backup"


def log(msg: str) -> None:
    print(f"[ARM] album-art: {msg}", flush=True)


def read_outputdir(conf_path: str = ABCDE_CONF) -> str:
    """OUTPUTDIR of abcde.conf (last uncommented assignment), without quotes."""
    value = None
    try:
        with open(conf_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"\s*OUTPUTDIR\s*=\s*(.*?)\s*(?:#.*)?$", line)
                if m:
                    value = m.group(1).strip().strip("\"'")
    except OSError:
        pass
    return (value or DEFAULT_OUTPUTDIR).rstrip("/") or "/"


def recent_playlists(root: str, now: float = None, max_age: float = RECENT_SECONDS):
    """Playlists at the root of `root` modified during the last `max_age` seconds."""
    now = time.time() if now is None else now
    found = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return found
    for name in names:
        path = os.path.join(root, name)
        if name.lower().endswith(".m3u") and os.path.isfile(path):
            if now - os.path.getmtime(path) <= max_age:
                found.append(path)
    return found


def album_dir_of(playlist: str):
    """Folder of the first track listed in the playlist, or None."""
    root = os.path.dirname(playlist)
    try:
        with open(playlist, encoding="utf-8", errors="replace") as f:
            for line in f:
                entry = line.strip().lstrip(chr(0xFEFF))
                if not entry or entry.startswith("#"):
                    continue
                track = os.path.normpath(os.path.join(root, entry.replace("\\", "/")))
                folder = os.path.dirname(track)
                return folder if os.path.isdir(folder) else None
    except OSError:
        pass
    return None


def has_image_beside(playlist: str) -> bool:
    stem = os.path.splitext(playlist)[0]
    return any(os.path.isfile(stem + ext) for ext in IMAGE_EXTS)


def find_cover(album_dir: str):
    """Best cover file of an album: folder.* / cover.* / front.* in the album folder, then the
    copy abcde leaves in albumart_backup/. Returns None when there is none."""
    for folder in (album_dir, os.path.join(album_dir, BACKUP_DIR)):
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for stem in COVER_STEMS:
            for name in names:
                base, ext = os.path.splitext(name.lower())
                if base == stem and ext in IMAGE_EXTS and os.path.isfile(os.path.join(folder, name)):
                    return os.path.join(folder, name)
    return None


def is_jpeg(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(3) == b"\xff\xd8\xff"
    except OSError:
        return False


def make_jpeg(src: str, dest: str, run=subprocess.run) -> bool:
    """Write a JPEG of at most MAX_SIDE pixels to `dest` with ImageMagick. Falls back to a plain
    copy when convert is unavailable or fails and the source is already a JPEG small enough to
    be embedded. Returns False when no usable image could be produced."""
    folder = os.path.dirname(dest)
    fd, tmp = tempfile.mkstemp(suffix=".jpg", dir=folder)
    os.close(fd)
    try:
        ok = False
        try:
            # The image goes through stdin/stdout: ImageMagick gives a meaning to "[", "%" and
            # ":" in file names, which album folders may contain, and guesses the type from the
            # content (abcde names a PNG "cover.jpg"). "[0]": first frame only.
            with open(src, "rb") as image:
                result = run(
                    ["convert", "-[0]", "-auto-orient", "-resize", f"{MAX_SIDE}x{MAX_SIDE}>",
                     "-strip", "-quality", JPEG_QUALITY, "jpg:-"],
                    stdin=image, capture_output=True, timeout=300,
                )
            ok = result.returncode == 0 and result.stdout[:3] == bytes((0xFF, 0xD8, 0xFF))
            if ok:
                with open(tmp, "wb") as out:
                    out.write(result.stdout)
            else:
                stderr = (result.stderr or b"").decode("utf-8", "replace").strip()[:200]
                log(f"convert failed on {src}: {stderr}")
        except (OSError, subprocess.SubprocessError) as err:
            log(f"convert unavailable ({err})")
        if not ok and is_jpeg(src) and os.path.getsize(src) <= FLAC_PICTURE_LIMIT:
            shutil.copyfile(src, tmp)
            ok = True
        if not ok:
            return False
        os.chmod(tmp, 0o644)
        os.replace(tmp, dest)
        return True
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def flac_has_picture(track: str, run=subprocess.run) -> bool:
    result = run(["metaflac", "--list", "--block-type=PICTURE", track],
                 capture_output=True, text=True, timeout=120)
    return result.returncode == 0 and "METADATA block" in (result.stdout or "")


def embed_missing(album_dir: str, image: str, run=subprocess.run) -> int:
    """Embed `image` in every FLAC of the album that has no picture. Returns how many."""
    if os.path.getsize(image) > FLAC_PICTURE_LIMIT:
        log(f"{image} is too large for a FLAC picture block, not embedding")
        return 0
    done = 0
    for name in sorted(os.listdir(album_dir)):
        track = os.path.join(album_dir, name)
        if not name.lower().endswith(".flac") or not os.path.isfile(track):
            continue
        try:
            if flac_has_picture(track, run):
                continue
            result = run(["metaflac", f"--import-picture-from={image}", track],
                         capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as err:
            log(f"metaflac unavailable ({err})")
            return done
        if result.returncode == 0:
            done += 1
        else:
            log(f"cannot embed art in {name}: {(result.stderr or '').strip()[:200]}")
    return done


def process_playlist(playlist: str, run=subprocess.run) -> bool:
    """Complete the art of the album a playlist points to. Returns True when something was
    written."""
    album_dir = album_dir_of(playlist)
    if not album_dir:
        log(f"{os.path.basename(playlist)}: album folder not found, skipping")
        return False
    name = os.path.basename(album_dir)
    changed = False

    folder_jpg = next(
        (os.path.join(album_dir, f) for f in sorted(os.listdir(album_dir))
         if os.path.splitext(f.lower())[0] == "folder" and f.lower().endswith(IMAGE_EXTS)),
        None,
    )
    if not folder_jpg:
        cover = find_cover(album_dir)
        if not cover:
            log(f"{name}: no cover art downloaded by abcde, nothing to do")
            return False
        folder_jpg = os.path.join(album_dir, "folder.jpg")
        if not make_jpeg(cover, folder_jpg, run):
            log(f"{name}: WARNING could not build folder.jpg from {cover}")
            return False
        log(f"{name}: wrote folder.jpg ({os.path.getsize(folder_jpg)} bytes) from {os.path.basename(cover)}")
        changed = True

    if not has_image_beside(playlist):
        ext = os.path.splitext(folder_jpg)[1].lower()
        dest = os.path.splitext(playlist)[0] + ext
        shutil.copyfile(folder_jpg, dest)
        os.chmod(dest, 0o644)
        log(f"{name}: wrote playlist image {os.path.basename(dest)}")
        changed = True

    embedded = embed_missing(album_dir, folder_jpg, run)
    if embedded:
        log(f"{name}: WARNING abcde left {embedded} track(s) without art, embedded folder image")
        changed = True
    return changed


def main() -> int:
    root = read_outputdir()
    playlists = recent_playlists(root)
    if not playlists:
        return 0  # not an audio CD rip (or nothing written): nothing to do
    for playlist in playlists:
        try:
            process_playlist(playlist)
        except Exception as err:  # never break the post-rip chain (Music Assistant sync)
            log(f"{os.path.basename(playlist)}: unexpected error ({err})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
