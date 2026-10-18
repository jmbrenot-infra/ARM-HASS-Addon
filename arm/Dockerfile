# Built locally by the Supervisor (no prebuilt image for this fork).
# Base pinned to the upstream add-on image validated on HAOS (ARM 2.20.5).
FROM ghcr.io/mliradelc/arm-hass-addon:0.2.8

# Upstream versions this image is based on (read by the upstream watch and tools/Update-ArmAddon.ps1).
LABEL io.jmbrenot.upstream.addon="0.2.8" \
      io.jmbrenot.upstream.arm="2.20.5"

# Fill the udev properties missing outside udev, so the web UI "Manual" start can rip.
RUN mv /opt/arm/scripts/docker/docker_arm_wrapper.sh /opt/arm/scripts/docker/docker_arm_wrapper.orig.sh
COPY rootfs/docker_arm_wrapper_shim.sh /opt/arm/scripts/docker/docker_arm_wrapper.sh
RUN chmod +x /opt/arm/scripts/docker/docker_arm_wrapper.sh /opt/arm/scripts/docker/docker_arm_wrapper.orig.sh

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
