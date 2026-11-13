#!/usr/bin/env python3
"""Tests for arm_album_art.py. Run with: pytest test_arm_album_art.py"""

import os
import types

import arm_album_art as art

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


class FakeTools:
    """Stands in for convert and metaflac."""

    def __init__(self, convert_ok=True, with_picture=()):
        self.convert_ok = convert_ok
        self.with_picture = set(with_picture)
        self.embedded = []
        self.calls = []

    def __call__(self, cmd, **_kwargs):
        self.calls.append(cmd)
        if cmd[0] == "convert":
            if not self.convert_ok:
                return types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"boom")
            assert _kwargs["stdin"].read(4) in (PNG[:4], JPEG[:4])
            return types.SimpleNamespace(returncode=0, stdout=JPEG, stderr=b"")
        track = cmd[-1]
        if "--list" in cmd:
            out = "METADATA block #2" if os.path.basename(track) in self.with_picture else ""
            return types.SimpleNamespace(returncode=0, stdout=out, stderr="")
        self.embedded.append(os.path.basename(track))
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")


def make_album(tmp_path, cover=PNG, cover_in_backup=True, tracks=2):
    root = tmp_path / "Rips-CD"
    album = root / "Artist" / "Album"
    album.mkdir(parents=True)
    lines = []
    for n in range(1, tracks + 1):
        (album / f"{n:02} - Song.flac").write_bytes(b"fLaC")
        lines.append(f"Artist/Album/{n:02} - Song.flac")
    playlist = root / "Artist-Album.m3u"
    playlist.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if cover is not None:
        folder = album / "albumart_backup" if cover_in_backup else album
        folder.mkdir(exist_ok=True)
        (folder / "cover.jpg").write_bytes(cover)
    return root, album, playlist


def test_read_outputdir_takes_last_uncommented_value(tmp_path):
    conf = tmp_path / "abcde.conf"
    conf.write_text('# OUTPUTDIR="$home/music/"\nOUTPUTDIR="/media/musique/Rips-CD/"  # prod\n', encoding="utf-8")

    assert art.read_outputdir(str(conf)) == "/media/musique/Rips-CD"


def test_read_outputdir_defaults_when_file_missing(tmp_path):
    assert art.read_outputdir(str(tmp_path / "missing.conf")) == art.DEFAULT_OUTPUTDIR


def test_recent_playlists_ignores_old_ones(tmp_path):
    root, _album, playlist = make_album(tmp_path)
    old = root / "Old-Album.m3u"
    old.write_text("x\n", encoding="utf-8")
    now = os.path.getmtime(playlist)
    os.utime(old, (now - 86400, now - 86400))

    assert art.recent_playlists(str(root), now=now) == [str(playlist)]


def test_album_dir_of_follows_first_track(tmp_path):
    _root, album, playlist = make_album(tmp_path)

    assert art.album_dir_of(str(playlist)) == str(album)


def test_album_dir_of_returns_none_for_dangling_playlist(tmp_path):
    playlist = tmp_path / "Gone-Album.m3u"
    playlist.write_text("Gone/Album/01 - Song.flac\n", encoding="utf-8")

    assert art.album_dir_of(str(playlist)) is None


def test_find_cover_falls_back_to_albumart_backup(tmp_path):
    _root, album, _playlist = make_album(tmp_path)

    assert art.find_cover(str(album)) == str(album / "albumart_backup" / "cover.jpg")


def test_oversized_png_cover_gives_folder_playlist_image_and_embedded_art(tmp_path):
    # ARM-HASS-Addon#26: abcde saved a PNG as cover.jpg, metaflac refused it, no image anywhere.
    root, album, playlist = make_album(tmp_path, cover=PNG)
    tools = FakeTools()

    assert art.process_playlist(str(playlist), run=tools) is True

    assert (album / "folder.jpg").read_bytes() == JPEG
    assert (root / "Artist-Album.jpg").read_bytes() == JPEG
    assert tools.embedded == ["01 - Song.flac", "02 - Song.flac"]
    convert = next(c for c in tools.calls if c[0] == "convert")
    assert f"{art.MAX_SIDE}x{art.MAX_SIDE}>" in convert
    assert [f for f in os.listdir(album) if f.endswith(".jpg")] == ["folder.jpg"]  # no temp left


def test_tracks_that_already_have_art_are_left_alone(tmp_path):
    _root, _album, playlist = make_album(tmp_path)
    tools = FakeTools(with_picture=["01 - Song.flac", "02 - Song.flac"])

    art.process_playlist(str(playlist), run=tools)

    assert tools.embedded == []


def test_existing_images_are_never_overwritten(tmp_path):
    root, album, playlist = make_album(tmp_path)
    (album / "folder.jpg").write_bytes(b"\xff\xd8\xffKEEP")
    (root / "Artist-Album.png").write_bytes(b"KEEP")
    tools = FakeTools(with_picture=["01 - Song.flac", "02 - Song.flac"])

    assert art.process_playlist(str(playlist), run=tools) is False

    assert (album / "folder.jpg").read_bytes() == b"\xff\xd8\xffKEEP"
    assert not (root / "Artist-Album.jpg").exists()
    assert not any(c[0] == "convert" for c in tools.calls)


def test_no_cover_downloaded_changes_nothing(tmp_path):
    root, album, playlist = make_album(tmp_path, cover=None)
    tools = FakeTools()

    assert art.process_playlist(str(playlist), run=tools) is False

    assert not (album / "folder.jpg").exists()
    assert not (root / "Artist-Album.jpg").exists()
    assert tools.embedded == []


def test_convert_failure_falls_back_to_copy_of_a_jpeg_cover(tmp_path):
    _root, album, playlist = make_album(tmp_path, cover=JPEG)
    tools = FakeTools(convert_ok=False)

    assert art.process_playlist(str(playlist), run=tools) is True

    assert (album / "folder.jpg").read_bytes() == JPEG


def test_convert_failure_on_a_png_cover_writes_nothing(tmp_path):
    root, album, playlist = make_album(tmp_path, cover=PNG)
    tools = FakeTools(convert_ok=False)

    assert art.process_playlist(str(playlist), run=tools) is False

    assert not (album / "folder.jpg").exists()
    assert not (root / "Artist-Album.jpg").exists()
    assert tools.embedded == []
    assert os.listdir(album / "albumart_backup") == ["cover.jpg"]
