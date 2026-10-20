
#!/usr/bin/env python3
"""Read-only GnuDB/CDDB lookup from FLAC-derived CD tables of contents."""

from pathlib import Path
from typing import List
from urllib.parse import urlencode
from urllib.request import urlopen

from mutagen.flac import FLAC


ROOT = Path("/volume1/music/Rips-CD/Unknown Artist")
BASE_URL = "https://gnudb.gnudb.org/~cddb/cddb.cgi"
# CDDB protocol contact form: mailbox local-part + domain + application + version.
HELLO = "bruce31520+gmail.com+codex-unknown-album+1.0"


def request(command: str) -> List[str]:
    query = urlencode({"cmd": command, "hello": HELLO, "proto": "6"})
    with urlopen(f"{BASE_URL}?{query}", timeout=20) as response:
        return response.read().decode("latin-1", errors="replace").splitlines()


def main() -> None:
    for album_dir in sorted(ROOT.glob("Unknown Album_*")):
        flacs = sorted(album_dir.glob("*.flac"))
        if not flacs:
            continue
        cddb_id = album_dir.name[len("Unknown Album_"):]
        frame_offset = 150
        offsets = []
        for flac_path in flacs:
            offsets.append(frame_offset)
            frame_offset += round(FLAC(flac_path).info.length * 75)
        total_seconds = int(cddb_id[2:6], 16)
        command = "cddb query {} {} {} {}".format(
            cddb_id, len(flacs), " ".join(map(str, offsets)), total_seconds
        )
        print(f"=== {album_dir.name} ({len(flacs)} tracks, {total_seconds}s) ===")
        try:
            response = request(command)
        except Exception as error:
            print(f"ERROR {error}")
            continue
        for line in response:
            print(line)
        if response and response[0].startswith("200 "):
            _, category, disc_id, _ = response[0].split(" ", 3)
            try:
                for line in request(f"cddb read {category} {disc_id}"):
                    print(line)
            except Exception as error:
                print(f"READ_ERROR {error}")


if __name__ == "__main__":
    main()

