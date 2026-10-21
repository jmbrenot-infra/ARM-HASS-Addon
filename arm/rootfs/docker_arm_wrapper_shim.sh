#!/bin/bash
# Shim installed over /opt/arm/scripts/docker/docker_arm_wrapper.sh (jmbrenot-infra fork).
#
# The upstream wrapper only detects the disc type from udev environment variables
# (ID_CDROM_MEDIA_CD / _DVD / _BD, ID_FS_TYPE), which exist only when it is called by a
# udev rule. On Home Assistant OS no udev rule calls it, and the web UI "Manual" start
# calls it without those variables: the disc is then reported as "Not CD, Blu-ray, DVD
# or Data" and ejected. This shim reads the missing properties from the udev database
# (mapped into the container by `udev: true`) and runs the original wrapper in the
# background, so the web request returns immediately and the rip logs to the add-on log.

DEVNAME="${1#/dev/}"
ORIG=/opt/arm/scripts/docker/docker_arm_wrapper.orig.sh
ADDON_LOG=/proc/1/fd/1

if [ -z "$DEVNAME" ]; then
    echo "[ARM] shim: no device given" >> "$ADDON_LOG"
    exit 1
fi

if [ -z "${ID_CDROM_MEDIA_CD}${ID_CDROM_MEDIA_CD_R}${ID_CDROM_MEDIA_CD_RW}${ID_CDROM_MEDIA_DVD}${ID_CDROM_MEDIA_BD}${ID_FS_TYPE}" ]; then
    while IFS='=' read -r key value; do
        case "$key" in
            ID_CDROM_MEDIA_CD|ID_CDROM_MEDIA_CD_R|ID_CDROM_MEDIA_CD_RW|ID_CDROM_MEDIA_DVD|ID_CDROM_MEDIA_BD|ID_FS_TYPE|ID_FS_LABEL)
                export "$key=$value"
                ;;
        esac
    done < <(udevadm info --query=property --name="/dev/${DEVNAME}" 2>/dev/null)
    echo "[ARM] shim: /dev/${DEVNAME} CD=${ID_CDROM_MEDIA_CD:-} DVD=${ID_CDROM_MEDIA_DVD:-} BD=${ID_CDROM_MEDIA_BD:-} FS=${ID_FS_TYPE:-}" >> "$ADDON_LOG"
fi

# ARM lists LOGPATH/progress when cleaning old logs (LOGLIFE >= 1) and crashes if it is missing.
LOGPATH=$(grep -m 1 '^LOGPATH:' /etc/arm/config/arm.yaml 2>/dev/null | sed -e 's/^LOGPATH:[[:space:]]*//' -e 's/[[:space:]]*#.*$//' -e 's/"//g')
mkdir -p "${LOGPATH:-/media/arm/logs}/progress"

# Run the original wrapper (it waits for the end of the rip), then ask Music Assistant to
# sync and move a finished DVD/Blu-ray rip next to its matching album (arm_video_to_album.py
# is a no-op for an audio CD job -- ARM-HASS-Addon#21).
# shellcheck disable=SC2016 # $0 and $1 are expanded by the child bash, on purpose
setsid bash -c '"$0" "$1"; python3 /usr/local/bin/arm_ma_sync.py; python3 /usr/local/bin/arm_video_to_album.py "$1"' "$ORIG" "$DEVNAME" >> "$ADDON_LOG" 2>&1 < /dev/null &
exit 0
