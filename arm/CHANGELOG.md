# Changelog

All notable changes to the ARM Home Assistant add-on are documented in this file. Release dates use the YYYY-MM-DD format.

## [Unreleased]

- **Added**: After a DVD/Blu-ray rip, `arm_video_to_album.py` moves the resulting video (transcoded if HandBrake succeeded, otherwise the raw rip) next to its matching music album under `/media/music/<Artist>/<Album>/`, matched by keyword against the disc's label -- e.g. a bonus DVD bundled with a CD. No unambiguous match: moves to `Unknown Artist/Unknown Album_<job id>` instead of guessing, same convention as unidentified audio CDs. No-op for an audio CD job. (jmbrenot-infra/ARM-HASS-Addon#21)
- **Added**: Workflow `Upstream watch` (every Monday): opens one issue (label `upstream`) per new mliradelc add-on tag or ARM release, and tells whether a Docker image exists for that ARM release. Reference versions are the `io.jmbrenot.upstream.addon` / `io.jmbrenot.upstream.arm` labels of `arm/Dockerfile`.
- **Added**: Workflow `Build ARM base image`: builds `ghcr.io/jmbrenot-infra/arm-hass-addon:arm-<version>` (linux/amd64) from `1337server/automatic-ripping-machine:<version>` with the recipe in `.docker/Dockerfile`, now pinned by `ARG ARM_VERSION`.
- **Added**: Workflow `Add-on image check` on pull requests: builds `arm/Dockerfile` and checks the anchors the fork relies on (`tests/check_anchors.sh`), plus shellcheck and actionlint.
- **Added**: `tools/Update-ArmAddon.ps1`: `-Phase Prepare` prepares the upgrade branch and commit, `-Phase Deploy` installs the update without backup after checking that no rip is running, then checks the add-on log and a test CD. `-WhatIf` changes nothing.

## [0.2.8-jmb.8] - 2026-10-21

- **Fixed**: The MakeMKV rebuilt by #15 was never actually used: `makemkv-bin`'s own `make install` places the binary at `/usr/bin/makemkvcon`, but ARM calls `/usr/local/bin/makemkvcon` (hardcoded) -- the upstream base image's stale one. `/usr/local/bin/makemkvcon` is now a symlink to the freshly built binary. Also removes #17's one-shot startup diagnostic, which did its job identifying this. (jmbrenot-infra/ARM-HASS-Addon#19)

## [0.2.8-jmb.7] - 2026-10-21

- **Added**: Diagnostic logging at container startup for jmbrenot-infra/ARM-HASS-Addon#17 (MakeMKV still reports "too old" after #15's rebuild): logs whether `forum.makemkv.com` is reachable and what the resulting `settings.conf` beta key looks like.

## [0.2.8-jmb.6] - 2026-10-21

- **Fixed**: MakeMKV (bundled in the upstream base image) had hit its hard version-expiry and refused to run at all, even with a key ("This application version is too old"), blocking every DVD/Blu-ray rip. `arm/Dockerfile` now rebuilds MakeMKV from the current latest release on every image build, so it stays current automatically. (jmbrenot-infra/ARM-HASS-Addon#15)

## [0.2.8-jmb.4] - 2026-10-18

- **Added**: Options `ma_url`, `ma_token`, `ma_provider`: after each rip, the add-on asks Music Assistant to sync that provider (API command `music/sync`), so the album shows up without waiting for the 12-hour scheduled sync. Empty options disable it.
- **Changed**: New installs default abcde to FLAC, write `ALBUMARTIST` (through `COMMENT`) and name playlists `Artist-Album.m3u`.

## [0.2.8-jmb.3] - 2026-10-17

- **Added**: Option `auto_rip` (default `true`): a watcher polls the udev database every 5 s and starts a rip when a disc is inserted, since Home Assistant OS runs no udev rule for ARM. Discs already present at start are ignored. The web UI "Manual" start still works.
- **Fixed**: The shim creates `LOGPATH/progress`, which ARM lists when cleaning old logs (`LOGLIFE` >= 1) and crashed on when missing.
- **Fixed**: New installs default `ABCDE_CONFIG_FILE` to `/etc/arm/config/abcde.conf`, the file edited by the web UI "abcde Config" tab. Before, rips used abcde defaults (Ogg, interactive, output in the container) because `/media/arm/config/abcde.conf` did not exist. Existing installs keep their `arm.yaml`: change the setting in the web UI.

## [0.2.8-jmb.2] - 2026-10-17

- **Fixed**: Rips started by the shim crashed with `FileNotFoundError: /home/arm/logs/arm.log`. `/home/arm/logs` is now a link to `LOGPATH` (`/media/arm/logs`), so the log is kept and listed in the web UI.

## [0.2.8-jmb.1] - 2026-10-17

- **Fixed**: The web UI "Manual" start no longer ejects audio CDs without ripping. A shim installed over `docker_arm_wrapper.sh` reads the udev properties (`ID_CDROM_MEDIA_*`, `ID_FS_TYPE`) with `udevadm info` when they are missing, then runs the original wrapper in the background and logs to the add-on log.
- **Changed**: The image is built locally by the Supervisor from `arm/Dockerfile`, based on the pinned upstream image `ghcr.io/mliradelc/arm-hass-addon:0.2.8`.

## [0.2.8] - 2025-10-30

- **Fixed**: Added the `root` user to the `cdrom` and `disk` groups within the container to resolve device permission errors when accessing optical drives.

## [0.2.5] - 2025-10-29

- **Warning**: Expanded privileges by setting `privileged: true` in addition to `full_access: true`, granting the container every host capability for deep troubleshooting.

## [0.2.4] - 2025-10-29

- **Warning**: Marked the add-on as experimental and enabled unrestricted host filesystem access to aid troubleshooting; only install when you require deep debugging.

## [0.2.3] - 2025-10-29

- **Added**: Enabled `udev` and kernel module access (`kernel_modules: true`) so ARM can interact with optical drives requiring additional device nodes.

## [0.2.2] - 2025-10-28

- **Added**: Exposed `/dev/sg0` by default so ARM can interact with optical drives that require the generic SCSI node.
- **Changed**: Refreshed addon artwork (logo/icon/banner) for improved branding.
- **Changed**: Updated the Supervisor sidebar icon to `mdi:compact-disc` to better represent the add-on.

## [0.2.1] - 2025-10-27

- **Breaking**: Home Assistant does not overwrite existing `arm.yaml`; update `WEBSERVER_PORT` to `8089` manually in `/addon_configs/local_arm/arm.yaml` if you upgraded from an earlier release.
- **Changed**: Aligned ARM's internal web server to use port 8089, matching the external port to simplify networking and ingress.
- **Fixed**: Updated health checks, default configuration, and documentation to reference the unified port mapping.
- **Added**: Included the project MIT license for distribution clarity.
- **Docs**: Embedded the add-on logo in README and DOCS for clearer branding.

## [0.2.0] - 2025-10-27

- **Added**: Enabled Home Assistant ingress so the ARM web UI can open inside the Supervisor sidebar.
- **Added**: Automatically provision raw, transcode, completed, log, and database directories based on the active `arm.yaml` values.
- **Fixed**: Prevent dashboard warnings about `/media/media/completed/` by creating the configured output paths on startup.
- **Documentation**: Updated add-on docs to mention ingress access and the automatic directory bootstrapping.

## [0.1.14] - 2025-10-26

- **Added**: Introduced a container health check that polls the ARM UI using `netcat-openbsd` before the Supervisor watchdog intervenes.
- **Fixed**: Corrected the port mapping so external port 8089 aligned with the container listener.

## [0.1.13] - 2025-10-26

- **Added**: Declared the `webui` metadata entry so Home Assistant shows a direct link to the ARM interface.
- **Changed**: Simplified environment handling by relying on Home Assistant metadata instead of redundant exports.

## [0.1.12] - 2025-10-26

- **Fixed**: Forced the ARM web server to bind to `0.0.0.0`, resolving connection issues for remote browsers, and improved startup logging to show the configured bind address.

## [0.1.11] - 2025-10-26

- **Added**: Migrated all configuration files to persistent storage under `/addon_configs/local_arm/` so edits survive container restarts.
- **Added**: Documented the new configuration workflow and updated helper scripts accordingly.
- **Breaking**: Users must migrate existing custom configurations from the previous ephemeral path to the new persistent location.

## [0.1.10] - 2025-10-26

- **Fixed**: Disabled the upstream image health check to avoid conflicts with the Home Assistant Supervisor watchdog.

## [0.1.9] - 2025-10-26

- **Fixed**: Ensured ARM listens on all interfaces and simplified the watchdog URL to the canonical external port.

## [0.1.8] - 2025-10-26

- **Fixed**: Updated the watchdog configuration to reference the correct port mapping placeholder syntax (`[PORT:8089]`).

## [0.1.7] - 2025-10-26

- **Fixed**: Adjusted the watchdog URL format to align with Supervisor validation rules.

## [0.1.6] - 2025-10-26

- **Fixed**: Pointed the watchdog to ARM's internal web port to match the service binding.

## [0.1.5] - 2025-10-26

- **Changed**: Switched the exposed port from 8080 to 8089 to avoid collisions with common services.

## [0.1.4] - 2025-10-26

- **Added**: Added a Supervisor watchdog endpoint and set the startup type to `application` to keep the add-on alive during boots.

## [0.1.3] - 2025-10-26

- **Added**: Bundled a complete `apprise.yaml` to support all notification transports and copied it during startup.

## [0.1.2] - 2025-10-26

- **Fixed**: Updated `run.sh` to launch the ARM UI with `python3`, preventing shell execution errors.

## [0.1.1] - 2025-10-26

- **Fixed**: Cleaned up legacy configuration symlinks and improved repo structure following the Home Assistant add-on conventions.

## [0.1.0] - 2025-10-25

- **Added**: Initial beta release of the ARM add-on with multi-architecture images, default configuration files, and GitHub Actions automation.
