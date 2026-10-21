#!/usr/bin/env python3
"""Tests for fix_multidisc_albums.py. Run with: pytest test_fix_multidisc_albums.py"""

import os

from fix_multidisc_albums import write_m3u


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
