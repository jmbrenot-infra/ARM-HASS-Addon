
#!/usr/bin/env python3
"""Read-only inventory of Unknown Album FLAC metadata on NASPLUS."""

import json
from pathlib import Path

from mutagen.flac import FLAC


ROOT = Path("/volume1/music/Rips-CD/Unknown Artist")
FIELDS = (
    "ALBUM",
    "ALBUMARTIST",
    "ARTIST",
    "TITLE",
    "TRACKNUMBER",
    "DISCNUMBER",
    "DATE",
    "YEAR",
    "GENRE",
    "CDDB",
    "DISCID",
    "MUSICBRAINZ_ALBUMID",
    "MUSICBRAINZ_ARTISTID",
    "MUSICBRAINZ_TRACKID",
)


def tags_for(audio: FLAC) -> dict:
    tags = audio.tags or {}
    return {field: list(tags[field]) for field in FIELDS if field in tags}


def main() -> None:
    albums = []
    for album_dir in sorted(ROOT.glob("Unknown Album_*")):
        if not album_dir.is_dir():
            continue
        tracks = []
        for flac_path in sorted(album_dir.glob("*.flac")):
            audio = FLAC(flac_path)
            tracks.append(
                {
                    "file": flac_path.name,
                    "duration_seconds": round(audio.info.length, 3),
                    "tags": tags_for(audio),
                }
            )
        albums.append({"folder": album_dir.name, "tracks": tracks})
    print(json.dumps(albums, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

