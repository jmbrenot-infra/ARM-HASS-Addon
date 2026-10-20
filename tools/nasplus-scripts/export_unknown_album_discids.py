
#!/usr/bin/env python3
"""Compute MusicBrainz-compatible disc IDs from local FLAC CD tables of contents."""

import base64
import hashlib
import json
from pathlib import Path

from mutagen.flac import FLAC


ROOT = Path('/volume1/music/Rips-CD/Unknown Artist')


def disc_id(track_offsets, leadout):
    values = [1, len(track_offsets), leadout] + track_offsets + [0] * (99 - len(track_offsets))
    encoded = '{:02X}{:02X}'.format(values[0], values[1])
    encoded += ''.join('{:08X}'.format(value) for value in values[2:])
    digest = hashlib.sha1(encoded.encode('ascii')).digest()
    return base64.b64encode(digest).decode('ascii').translate(str.maketrans('+/', '._')).replace('=', '-')


def main():
    albums = []
    for album_dir in sorted(ROOT.glob('Unknown Album_*')):
        tracks = sorted(album_dir.glob('*.flac'))
        if not tracks or len(tracks) > 99:
            continue
        offset = 150
        offsets = []
        for track in tracks:
            info = FLAC(track).info
            if info.sample_rate != 44100 or info.total_samples % 588:
                raise ValueError('Non-CD frame count for {}'.format(track))
            offsets.append(offset)
            offset += info.total_samples // 588
        albums.append({
            'album_id': album_dir.name.split('_', 1)[1],
            'disc_id': disc_id(offsets, offset),
            'toc': '1 {} {} {}'.format(len(offsets), offset, ' '.join(map(str, offsets))),
            'tracks': len(offsets),
        })
    print(json.dumps(albums, ensure_ascii=False))


if __name__ == '__main__':
    main()

