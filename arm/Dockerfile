# Built locally by the Supervisor (no prebuilt image for this fork).
# Base pinned to a validated upstream image; versions in the io.jmbrenot.upstream.* labels below.
FROM ghcr.io/mliradelc/arm-hass-addon:0.2.8

# Upstream versions this image is based on (read by the upstream watch and tools/Update-ArmAddon.ps1).
LABEL io.jmbrenot.upstream.addon="0.2.8" \
      io.jmbrenot.upstream.arm="2.20.5"

# Fill the udev properties missing outside udev, so the web UI "Manual" start can rip.
RUN mv /opt/arm/scripts/docker/docker_arm_wrapper.sh /opt/arm/scripts/docker/docker_arm_wrapper.orig.sh
COPY rootfs/docker_arm_wrapper_shim.sh /opt/arm/scripts/docker/docker_arm_wrapper.sh
RUN chmod +x /opt/arm/scripts/docker/docker_arm_wrapper.sh /opt/arm/scripts/docker/docker_arm_wrapper.orig.sh

# Upstream crashes the whole rip job over a debug *log message*: put_track() does int(t_no)
# just to zero-pad the track number for logging.debug(), with no fallback for a release whose
# tracks are numbered non-numerically (e.g. "A1"/"B2" for a vinyl-only MusicBrainz match). The
# grep before and after makes the build fail loudly if upstream ever changes this line, instead
# of silently shipping the bug again. (jmbrenot-infra/ARM-HASS-Addon#9)
RUN grep -q 'Track #{int(t_no):02}' /opt/arm/arm/ripper/utils.py \
    && sed -i 's/Track #{int(t_no):02}/Track #{t_no}/' /opt/arm/arm/ripper/utils.py \
    && grep -q 'Track #{t_no}' /opt/arm/arm/ripper/utils.py

# ARM writes its main log to /home/arm/logs/arm.log, which does not exist in this image (upstream
# mounts /home/arm from the host). Point it to LOGPATH (/media/arm/logs, created by run.sh at start)
# so the log is persistent and listed in the web UI.
RUN mkdir -p /home/arm && rm -rf /home/arm/logs && ln -s /media/arm/logs /home/arm/logs

# Start a disc insertion watcher (option auto_rip) before the upstream start script.
COPY rootfs/arm_disc_watcher.sh /usr/local/bin/arm_disc_watcher.sh
COPY rootfs/entry_jmb.sh /entry_jmb.sh
RUN chmod +x /usr/local/bin/arm_disc_watcher.sh /entry_jmb.sh
ENTRYPOINT ["/entry_jmb.sh"]

# Default config for new installs: point ABCDE_CONFIG_FILE to the file edited by the web UI,
# and default abcde to FLAC with ALBUMARTIST and plain playlist names.
COPY rootfs/defaults/arm.yaml /defaults/arm.yaml
COPY rootfs/defaults/abcde.conf /defaults/abcde.conf

# Ask Music Assistant to sync after each rip (options ma_url, ma_token, ma_provider).
COPY rootfs/arm_ma_sync.py /usr/local/bin/arm_ma_sync.py
