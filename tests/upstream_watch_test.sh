#!/bin/bash
# Unit tests for .github/scripts/upstream_watch.sh (pure functions only, no network).
set -u
cd "$(dirname "$0")/.." || exit 1
# shellcheck source=../.github/scripts/upstream_watch.sh
source .github/scripts/upstream_watch.sh

failures=0
fail() { echo "FAIL: $*"; failures=$((failures + 1)); }

# semver filter: non-semver and pre-release tags are ignored, v prefix removed
got=$(printf 'v0.2.8\nv0.2.10\nlatest\nv0.3.0-beta\nv0.2.9\n' | latest_semver)
[ "$got" = "0.2.10" ] || fail "latest_semver: got '$got', want 0.2.10"

got=$(printf 'latest\nnightly\n' | latest_semver)
[ -z "$got" ] || fail "latest_semver without semver tags: got '$got', want empty"

version_gt 2.24.4 2.20.5 || fail "version_gt 2.24.4 2.20.5 should be true"
version_gt 2.20.5 2.20.5 && fail "version_gt 2.20.5 2.20.5 should be false"
version_gt 0.2.10 0.2.9 || fail "version_gt 0.2.10 0.2.9 should be true"
version_gt 0.2.8 0.2.9 && fail "version_gt 0.2.8 0.2.9 should be false"

tmp=$(mktemp)
printf 'FROM x:1\nLABEL io.jmbrenot.upstream.addon="0.2.8" \\\n      io.jmbrenot.upstream.arm="2.20.5"\n' > "$tmp"
got=$(DOCKERFILE="$tmp" read_label io.jmbrenot.upstream.arm)
[ "$got" = "2.20.5" ] || fail "read_label arm: got '$got', want 2.20.5"
got=$(DOCKERFILE="$tmp" read_label io.jmbrenot.upstream.addon)
[ "$got" = "0.2.8" ] || fail "read_label addon: got '$got', want 0.2.8"
rm -f "$tmp"

if [ "$failures" -eq 0 ]; then echo "upstream_watch tests: all passed"; else echo "upstream_watch tests: $failures failure(s)"; exit 1; fi
