#!/usr/bin/env python3
"""Tests for arm_video_to_album.py. Run with: pytest test_arm_video_to_album.py"""

import os

from arm_video_to_album import find_album_match, keywords, sanitize


def test_keywords_lowercases_and_splits_on_punctuation():
    assert keywords("MUSE_DRONES") == {"muse", "drones"}


def test_keywords_drops_stopwords_and_short_tokens():
    assert keywords("The Best Of CD 1") == {"best"}


def test_find_album_match_matches_unique_artist_and_album(tmp_path):
    root = tmp_path / "music"
    (root / "Muse" / "Drones").mkdir(parents=True)
    (root / "Muse" / "The Resistance").mkdir(parents=True)

    match = find_album_match("MUSE_DRONES", music_root=str(root))

    assert match is not None
    artist, album, path = match
    assert artist == "Muse"
    assert album == "Drones"
    assert path == str(root / "Muse" / "Drones")


def test_find_album_match_returns_none_when_ambiguous(tmp_path):
    root = tmp_path / "music"
    (root / "Muse" / "Drones").mkdir(parents=True)
    (root / "Muse Allstars" / "Drones Live").mkdir(parents=True)

    # Both albums contain "drones" -- two artists share the "muse" keyword too,
    # so this must not silently pick one.
    match = find_album_match("MUSE DRONES", music_root=str(root))

    assert match is None


def test_find_album_match_returns_none_when_no_candidate(tmp_path):
    root = tmp_path / "music"
    (root / "Duffy" / "Rockferry").mkdir(parents=True)

    match = find_album_match("MUSE_DRONES", music_root=str(root))

    assert match is None


def test_find_album_match_ignores_unknown_artist_folder(tmp_path):
    root = tmp_path / "music"
    (root / "Unknown Artist" / "Unknown Album_abc123").mkdir(parents=True)

    match = find_album_match("MUSE_DRONES", music_root=str(root))

    assert match is None


def test_sanitize_replaces_path_unsafe_characters():
    assert sanitize('Scratch My Back / And I’ll Scratch Yours') == "Scratch My Back - And I’ll Scratch Yours"
