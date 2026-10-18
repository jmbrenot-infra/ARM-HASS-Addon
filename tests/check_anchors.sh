#!/bin/bash
# Checks, inside the built add-on image, that the upstream files and commands the fork relies on
# still exist (run by .github/workflows/addon-image-check.yml).
set -u

failures=0
ok() { echo "ok   $*"; }
ko() { echo "FAIL $*"; failures=$((failures + 1)); }
check() { local what=$1; shift; if "$@"; then ok "$what"; else ko "$what"; fi; }

DOCKER_DIR=/opt/arm/scripts/docker

check "original wrapper kept as docker_arm_wrapper.orig.sh" test -x "$DOCKER_DIR/docker_arm_wrapper.orig.sh"
check "docker_arm_wrapper.sh is the fork shim" grep -q "jmbrenot-infra fork" "$DOCKER_DIR/docker_arm_wrapper.sh"
check "/home/arm/logs links to /media/arm/logs" test "$(readlink /home/arm/logs)" = /media/arm/logs
for f in /run.sh /entry_jmb.sh /usr/local/bin/arm_disc_watcher.sh; do
    check "$f is executable" test -x "$f"
done
check "/run.sh still sets up /etc/arm/config" grep -q /etc/arm/config /run.sh
for cmd in udevadm python3 abcde setsid flac; do
    check "command $cmd" command -v "$cmd"
done
check "arm_ma_sync.py compiles" python3 -c 'import py_compile, sys; py_compile.compile(sys.argv[1], cfile="/tmp/arm_ma_sync.pyc", doraise=True)' /usr/local/bin/arm_ma_sync.py

if [ -r /opt/arm/VERSION ]; then
    echo "ARM version: $(cat /opt/arm/VERSION)"
else
    echo "warning: /opt/arm/VERSION not found"
fi

if [ "$failures" -eq 0 ]; then echo "anchors: all passed"; else echo "anchors: $failures failure(s)"; exit 1; fi
