#!/usr/bin/env python3
"""Tests for fix_multidisc_albums.py. Run with: pytest test_fix_multidisc_albums.py"""

import os
import sys

from mutagen.flac import FLAC

from fix_multidisc_albums import main, plan_album, write_m3u


def write_test_flac(path, title, tracknumber, cddb=None, discnumber=None, disctotal=None):
    """Write a metadata-only, but valid enough for mutagen, local FLAC file."""
    streaminfo = (
        (4096).to_bytes(2, "big") + (4096).to_bytes(2, "big") + b"\0" * 6
        + ((8000 << 44) | (15 << 36)).to_bytes(8, "big") + b"\0" * 16
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fLaC" + bytes([128, 0, 0, 34]) + streaminfo)
    audio = FLAC(path)
    audio["title"] = [title]
    audio["tracknumber"] = [str(tracknumber)]
    if cddb is not None:
        audio["cddb"] = [cddb]
    if discnumber is not None:
        audio["discnumber"] = [str(discnumber)]
    if disctotal is not None:
        audio["disctotal"] = [str(disctotal)]
    audio.save()


def run_fix(root, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["fix_multidisc_albums.py", "--root", str(root)])
    assert main() == 0


def flac_tags(path):
    audio = FLAC(path)
    return audio["discnumber"], audio["disctotal"]


def test_write_m3u_lists_both_discs_in_order(tmp_path):
    root = str(tmp_path)
    plan = [
        {"new_rel": os.path.join("CD1", "01 - First.flac"), "disc_num": 1, "disc_total": 2},
        {"new_rel": os.path.join("CD1", "02 - Second.flac"), "disc_num": 1, "disc_total": 2},
        {"new_rel": os.path.join("CD2", "01 - Third.flac"), "disc_num": 2, "disc_total": 2},
    ]

    m3u_path = write_m3u(root, "Some Artist", "Some Album", plan)

    assert m3u_path == os.path.join(root, "Some Artist-Some Album.m3u")
    with open(m3u_path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    assert lines == [
        os.path.join("Some Artist", "Some Album", "CD1", "01 - First.flac"),
        os.path.join("Some Artist", "Some Album", "CD1", "02 - Second.flac"),
        os.path.join("Some Artist", "Some Album", "CD2", "01 - Third.flac"),
    ]


def test_write_m3u_overwrites_a_stale_existing_playlist(tmp_path):
    root = str(tmp_path)
    stale_path = os.path.join(root, "Some Artist-Some Album.m3u")
    with open(stale_path, "w", encoding="utf-8") as fh:
        fh.write("Some Artist/Some Album/01 - Old Flat Layout.flac\n")

    plan = [{"new_rel": os.path.join("CD1", "01 - First.flac"), "disc_num": 1, "disc_total": 1}]
    write_m3u(root, "Some Artist", "Some Album", plan)

    with open(stale_path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    assert lines == [os.path.join("Some Artist", "Some Album", "CD1", "01 - First.flac")]


def test_write_m3u_sanitizes_a_slash_in_the_album_name():
    import tempfile
    with tempfile.TemporaryDirectory() as root:
        plan = [{"new_rel": os.path.join("CD1", "01 - First.flac"), "disc_num": 1, "disc_total": 2}]
        m3u_path = write_m3u(root, "Peter Gabriel", "Scratch My Back / And I'll Scratch Yours", plan)
        assert m3u_path == os.path.join(root, "Peter Gabriel-Scratch My Back - And I'll Scratch Yours.m3u")
        assert os.path.isfile(m3u_path)


def test_later_cd2_tracks_are_caught_after_cd1_was_already_sorted(tmp_path, monkeypatch):
    root = tmp_path / "Rips-CD"
    album = root / "Artist" / "Album"
    write_test_flac(album / "CD1" / "01 - First.flac", "First", 1, "disc-one", 1, 2)
    write_test_flac(album / "CD1" / "02 - Second.flac", "Second", 2, "disc-one", 1, 2)
    write_test_flac(album / "01 - Third.flac", "Third", 1, "disc-two")
    write_test_flac(album / "02 - Fourth.flac", "Fourth", 2, "disc-two")

    run_fix(root, monkeypatch)

    assert not list(album.glob("*.flac"))
    assert flac_tags(album / "CD2" / "01 - Third.flac") == (["2"], ["2"])
    assert flac_tags(album / "CD2" / "02 - Fourth.flac") == (["2"], ["2"])
    assert (root / "Artist-Album.m3u").read_text(encoding="utf-8").splitlines() == [
        os.path.join("Artist", "Album", "CD1", "01 - First.flac"),
        os.path.join("Artist", "Album", "CD1", "02 - Second.flac"),
        os.path.join("Artist", "Album", "CD2", "01 - Third.flac"),
        os.path.join("Artist", "Album", "CD2", "02 - Fourth.flac"),
    ]


def test_existing_cddb_directories_keep_their_disc_number_when_flat_tracks_arrive(tmp_path, monkeypatch):
    root = tmp_path / "Rips-CD"
    album = root / "Artist" / "Album"
    cd1 = album / "CD1" / "01 - Alpha old.flac"
    cd2 = album / "CD2" / "01 - Beta old.flac"
    write_test_flac(cd1, "Alpha old", 1, "alpha", 1, 2)
    write_test_flac(cd2, "Beta old", 1, "beta", 2, 2)
    write_test_flac(album / "02 - Alpha new.flac", "Alpha new", 2, "alpha")
    write_test_flac(album / "02 - Beta new.flac", "Beta new", 2, "beta")
    # The beta group sorts first by mtime, which would expose a fresh 1/2
    # enumeration instead of preserving the cddb-to-CDn association.
    os.utime(cd1, (200, 200))
    os.utime(cd2, (100, 100))
    os.utime(album / "02 - Alpha new.flac", (300, 300))
    os.utime(album / "02 - Beta new.flac", (300, 300))

    plan = plan_album(str(album))
    by_old_name = {item["old_name"]: item for item in plan}
    assert by_old_name["02 - Alpha new.flac"]["disc_num"] == 1
    assert by_old_name["02 - Beta new.flac"]["disc_num"] == 2
    assert not by_old_name["01 - Alpha old.flac"]["needs_move"]
    assert not by_old_name["01 - Alpha old.flac"]["needs_retag"]

    run_fix(root, monkeypatch)

    assert (album / "CD1" / "02 - Alpha new.flac").is_file()
    assert (album / "CD2" / "02 - Beta new.flac").is_file()
    assert flac_tags(album / "CD1" / "02 - Alpha new.flac") == (["1"], ["2"])
    assert flac_tags(album / "CD2" / "02 - Beta new.flac") == (["2"], ["2"])


def test_filename_prefix_detection_still_works_without_existing_cd_directories(tmp_path):
    album = tmp_path / "Album"
    write_test_flac(album / "2-01 - Second disc.flac", "Second disc", 1)
    write_test_flac(album / "1-01 - First disc.flac", "First disc", 1)

    plan = plan_album(str(album))

    assert [(item["old_name"], item["disc_num"]) for item in plan] == [
        ("1-01 - First disc.flac", 1),
        ("2-01 - Second disc.flac", 2),
    ]


def test_three_digit_prefix_detection_still_works_without_existing_cd_directories(tmp_path):
    album = tmp_path / "Album"
    write_test_flac(album / "201 Second disc.flac", "Second disc", 1)
    write_test_flac(album / "101 First disc.flac", "First disc", 1)

    plan = plan_album(str(album))

    assert [(item["old_name"], item["disc_num"]) for item in plan] == [
        ("101 First disc.flac", 1),
        ("201 Second disc.flac", 2),
    ]


def test_cddb_detection_still_works_without_existing_cd_directories(tmp_path):
    album = tmp_path / "Album"
    first = album / "01 - First disc.flac"
    second = album / "01 - Second disc.flac"
    write_test_flac(first, "First disc", 1, "first-cddb")
    write_test_flac(second, "Second disc", 1, "second-cddb")
    os.utime(first, (100, 100))
    os.utime(second, (200, 200))

    plan = plan_album(str(album))

    assert [(item["old_name"], item["disc_num"]) for item in plan] == [
        ("01 - First disc.flac", 1),
        ("01 - Second disc.flac", 2),
    ]


def test_mtime_gap_detection_still_works_without_existing_cd_directories(tmp_path):
    album = tmp_path / "Album"
    first = album / "01 - First disc.flac"
    second = album / "01 - Second disc.flac"
    write_test_flac(first, "First disc", 1)
    write_test_flac(second, "Second disc", 1)
    os.utime(first, (100, 100))
    os.utime(second, (300, 300))

    plan = plan_album(str(album))

    assert [(item["old_name"], item["disc_num"]) for item in plan] == [
        ("01 - First disc.flac", 1),
        ("01 - Second disc.flac", 2),
    ]
