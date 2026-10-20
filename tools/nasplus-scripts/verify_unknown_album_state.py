
#!/usr/bin/env python3
"""Read-only check that a failed tag run did not persist a partial edit."""

from pathlib import Path
from mutagen.flac import FLAC


path = Path('/volume1/music/Rips-CD/Unknown Artist/Unknown Album_0610bd12/01 - Track 1.flac')
audio = FLAC(path)
for key in ('ALBUM', 'ALBUMARTIST', 'ARTIST', 'TITLE', 'TRACKNUMBER', 'CDDB'):
    print('{}={}'.format(key, '|'.join(audio.get(key, []))))

