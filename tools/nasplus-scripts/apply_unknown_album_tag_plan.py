
#!/usr/bin/env python3
"""Apply a reviewed MusicBrainz tag-and-rename plan to Unknown Album FLAC folders."""

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from mutagen.flac import FLAC


MUSIC_ROOT = Path('/volume1/music/Rips-CD')
UNKNOWN_ROOT = MUSIC_ROOT / 'Unknown Artist'
BACKUP_ROOT = Path('/volume1/scripts')
INVALID_FILENAME = re.compile(r'[\x00-\x1f<>:"/\\|?*]+')


def filesystem_name(value):
    cleaned = INVALID_FILENAME.sub(' - ', value)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' .')
    if not cleaned:
        raise ValueError('An empty filesystem name was produced')
    return cleaned


def build_jobs(plan):
    jobs = []
    destinations = set()
    for album in plan:
        source = UNKNOWN_ROOT / 'Unknown Album_{}'.format(album['album_id'])
        target = MUSIC_ROOT / filesystem_name(album['album_artist']) / filesystem_name(album['album'])
        if not source.is_dir():
            raise ValueError('Missing source album: {}'.format(source))
        target_exists = target.exists()
        if target_exists and not target.is_dir():
            raise ValueError('Destination is not a directory: {}'.format(target))
        if target_exists and int(album['disc_number']) == 1:
            raise ValueError('Destination already exists: {}'.format(target))
        if str(target).casefold() in destinations:
            raise ValueError('Duplicate destination: {}'.format(target))
        destinations.add(str(target).casefold())
        files = sorted(source.glob('*.flac'))
        tracks = album['tracks']
        if len(files) != len(tracks):
            raise ValueError('{} has {} FLAC files, plan has {} tracks'.format(source, len(files), len(tracks)))
        file_jobs = []
        target_names = set()
        for index, (source_file, track) in enumerate(zip(files, tracks), start=1):
            number = int(track['number'])
            if number != index:
                raise ValueError('{} track order is not sequential at {}'.format(source, source_file.name))
            prefix = '{}-{:02d}'.format(album['disc_number'], number) if target_exists else '{:02d}'.format(number)
            target_name = '{} - {}.flac'.format(prefix, filesystem_name(track['title']))
            if target_name.casefold() in target_names or (target / target_name).exists():
                raise ValueError('Target file collision: {}'.format(target / target_name))
            target_names.add(target_name.casefold())
            file_jobs.append((source_file, target_name, track))
        remove_source_cache = False
        if target_exists:
            planned_sources = {path for path, _, _ in file_jobs}
            residual = [path.name for path in source.iterdir() if path not in planned_sources]
            if residual == ['@eaDir']:
                remove_source_cache = True
            elif residual:
                raise ValueError('Cannot merge {}; unplanned files remain: {}'.format(source, residual))
        jobs.append((album, source, target, file_jobs, target_exists, remove_source_cache))
    return jobs


def serializable_tags(audio):
    return {key: list(value) for key, value in (audio.tags or {}).items()}


def write_tags(path, album, track):
    audio = FLAC(path)
    tags = audio.tags
    tags['ALBUM'] = [album['album']]
    tags['ALBUMARTIST'] = [album['album_artist']]
    tags['ARTIST'] = [track['artist']]
    tags['TITLE'] = [track['title']]
    tags['TRACKNUMBER'] = [track['number']]
    tags['TRACKTOTAL'] = [str(len(album['tracks']))]
    tags['DISCNUMBER'] = [album['disc_number']]
    tags['DISCTOTAL'] = [album['disc_total']]
    if album.get('date'):
        tags['DATE'] = [album['date']]
    tags['MUSICBRAINZ_ALBUMID'] = [album['release_id']]
    tags['MUSICBRAINZ_RELEASEGROUPID'] = [album['release_group_id']]
    tags['MUSICBRAINZ_TRACKID'] = [track['recording_id']]
    if 'CDDB' in tags:
        del tags['CDDB']
    audio.save()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding='utf-8-sig'))
    jobs = build_jobs(plan)
    for album, source, target, file_jobs, target_exists, remove_source_cache in jobs:
        action = 'merge into' if target_exists else 'move to'
        print('{}: {} {} {} ({} tracks)'.format(album['album_id'], source, action, target, len(file_jobs)))
    if args.dry_run:
        print('DRY RUN: no file was changed')
        return

    backup = {
        'created_at': datetime.now().astimezone().isoformat(),
        'albums': [],
    }
    for album, source, _, file_jobs, _, _ in jobs:
        backup['albums'].append({
            'album_id': album['album_id'],
            'source': str(source),
            'files': [{'path': str(path), 'tags': serializable_tags(FLAC(path))} for path, _, _ in file_jobs],
        })
    backup_path = BACKUP_ROOT / 'unknown-album-tags-backup-{}.json'.format(datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding='utf-8')

    for album, source, target, file_jobs, target_exists, remove_source_cache in jobs:
        target.parent.mkdir(parents=True, exist_ok=True)
        for source_file, target_name, track in file_jobs:
            write_tags(source_file, album, track)
            renamed = source_file.with_name(target_name)
            source_file.rename(renamed)
            if target_exists:
                shutil.move(str(renamed), str(target / target_name))
        if target_exists:
            if remove_source_cache:
                shutil.rmtree(source / '@eaDir')
            source.rmdir()
        else:
            shutil.move(str(source), str(target))
        print('TAGGED {}'.format(album['album_id']))
    print('BACKUP {}'.format(backup_path))


if __name__ == '__main__':
    main()

