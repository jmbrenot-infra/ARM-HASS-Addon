#!/bin/bash
# Disc insertion watcher (jmbrenot-infra fork).
#
# Home Assistant OS runs no udev rule for ARM, so inserting a disc never starts a rip.
# This loop polls the udev database (mapped into the container by `udev: true`) and
# starts the ARM wrapper when a drive goes from "no media" to "media present".
# Discs already present when the add-on starts are ignored (no rip on restart).

POLL_SECONDS=5
WRAPPER=/opt/arm/scripts/docker/docker_arm_wrapper.sh
declare -A had_media

media_present() {
    udevadm info --query=property --name="$1" 2>/dev/null | grep -q '^ID_CDROM_MEDIA=1$'
}

for dev in /dev/sr*; do
    [ -b "$dev" ] || continue
    if media_present "$dev"; then had_media[$dev]=1; else had_media[$dev]=0; fi
    echo "[ARM] watcher: ${dev} initial media=${had_media[$dev]}"
done

while true; do
    for dev in /dev/sr*; do
        [ -b "$dev" ] || continue
        if media_present "$dev"; then
            if [ "${had_media[$dev]:-0}" != "1" ]; then
                echo "[ARM] watcher: disc inserted in ${dev}, starting ARM"
                "$WRAPPER" "${dev#/dev/}"
            fi
            had_media[$dev]=1
        else
            had_media[$dev]=0
        fi
    done
    sleep "$POLL_SECONDS"
done
