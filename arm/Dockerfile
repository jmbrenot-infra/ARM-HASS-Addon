# Built locally by the Supervisor (no prebuilt image for this fork).
# Base pinned to the upstream add-on image validated on HAOS (ARM 2.20.5).
FROM ghcr.io/mliradelc/arm-hass-addon:0.2.8

# Fill the udev properties missing outside udev, so the web UI "Manual" start can rip.
RUN mv /opt/arm/scripts/docker/docker_arm_wrapper.sh /opt/arm/scripts/docker/docker_arm_wrapper.orig.sh
COPY rootfs/docker_arm_wrapper_shim.sh /opt/arm/scripts/docker/docker_arm_wrapper.sh
RUN chmod +x /opt/arm/scripts/docker/docker_arm_wrapper.sh /opt/arm/scripts/docker/docker_arm_wrapper.orig.sh

# ARM writes its main log to /home/arm/logs/arm.log, which does not exist in this image (upstream
# mounts /home/arm from the host). Point it to LOGPATH (/media/arm/logs, created by run.sh at start)
# so the log is persistent and listed in the web UI.
RUN mkdir -p /home/arm && rm -rf /home/arm/logs && ln -s /media/arm/logs /home/arm/logs
