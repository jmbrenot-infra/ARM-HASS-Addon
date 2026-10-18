# Veille amont et mise à jour contrôlée — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alerter par issue GitHub quand mliradelc ou ARM publie une nouvelle version, et fournir un outil PowerShell qui prépare la branche d'upgrade puis déploie l'add-on sur HA de façon contrôlée.

**Architecture:** Deux labels dans `arm/Dockerfile` portent les versions amont de référence. Un workflow planifié les compare aux sources amont et ouvre des issues. Un workflow construit notre propre base ARM, un autre contrôle chaque PR (build + points d'ancrage). `tools/Update-ArmAddon.ps1` orchestre ; ses fonctions pures vivent dans `tools/ArmAddonUpgrade.psm1`.

**Tech Stack:** GitHub Actions, bash + `gh` (`--jq`, pas de `jq` en local), Docker Buildx, PowerShell 5.1, Pester 3.4 (syntaxe `Should Be`).

**Spec:** `docs/superpowers/specs/2026-10-18-upstream-watch-design.md`

## Global Constraints

- Scripts PowerShell : ASCII pur, compatibles PowerShell 5.1 ; pas d'opérateurs `??`, `?.`, ternaire.
- Workflow de veille : `permissions: contents: read, issues: write`, jeton `GITHUB_TOKEN` uniquement.
- `build-base.yml` : `permissions: contents: read, packages: write` ; plateforme `linux/amd64` ; image `ghcr.io/jmbrenot-infra/arm-hass-addon:arm-<version>`.
- Labels : `io.jmbrenot.upstream.addon`, `io.jmbrenot.upstream.arm` ; valeurs initiales `0.2.8` et `2.20.5`.
- Issues : label `upstream`, titres `Amont : add-on mliradelc <v> disponible` et `Amont : ARM <v> disponible`, marqueur `<!-- upstream-watch:image-available -->`.
- HA : entité `update.arm_jmbrenot_infra_mise_a_jour`, slug `65fe9fa6_arm`, `http://192.168.0.55:8123`, joblist `http://192.168.0.55:8089/json?mode=joblist`, `update.install` avec `backup: false`.
- Jeton : `AUZ_HA_TOKEN` lu par `Select-String -Pattern '^AUZ_HA_TOKEN='` sur `%USERPROFILE%\.ha-secrets\.env`, jamais affiché ni écrit.
- Interdits : redémarrer HA, écrire sur `W:`, sauvegarde lors de l'update, `git push`/PR depuis le script.
- Lien wiki : `https://github.com/jmbrenot-infra/Architecture-Generale/blob/main/wiki/13-musique-ripage-cd.md`.

## Review Focus

- Tags amont non semver (ex. `latest`, `v0.2.8-beta`) : ignorés par la veille, pas d'issue fantaisiste → test `semver filter` (Task 2).
- Version amont plus ancienne ou égale à la référence : aucune issue → test `no issue when up to date` (Task 2).
- `joblist` dont `results` est un objet vide `{}` vs liste vide `[]` vs objet avec jobs : seul « vide » autorise → test `Test-ArmIdle` (Task 5).
- `.env` sans ligne `AUZ_HA_TOKEN` ou avec guillemets/CR : erreur claire, valeur nettoyée → test `Get-EnvValue` (Task 5).
- Dockerfile sans labels (ancienne branche) : erreur explicite plutôt que remplacement silencieux → test `Get-UpstreamLabels throws` (Task 4).

---

### Task 1: Labels de référence et activation des issues

**Files:**
- Modify: `arm/Dockerfile` (après la ligne `FROM`)

- [ ] **Step 1:** Ajouter après `FROM ghcr.io/mliradelc/arm-hass-addon:0.2.8` :
  commentaire `# Upstream versions this image is based on (read by the upstream watch and tools/Update-ArmAddon.ps1).` puis
  `LABEL io.jmbrenot.upstream.addon="0.2.8" \` / `      io.jmbrenot.upstream.arm="2.20.5"`.
- [ ] **Step 2:** Vérifier : `grep -n 'io.jmbrenot.upstream' arm/Dockerfile` → 2 lignes.
- [ ] **Step 3:** Commit `feat: record upstream versions as image labels`.
- [ ] **Step 4 (hors git, accord déjà donné) :** `gh repo edit jmbrenot-infra/ARM-HASS-Addon --enable-issues` ; vérifier `hasIssuesEnabled: true`.

### Task 2: Script de veille

**Files:**
- Create: `.github/scripts/upstream_watch.sh`
- Create: `tests/upstream_watch_test.sh`

**Interfaces:**
- Produces: `upstream_watch.sh` ; env `GH_TOKEN`, `GITHUB_REPOSITORY`, `DRY_RUN` (`1` = rien n'écrit), `DOCKERFILE` (défaut `arm/Dockerfile`). Fonctions sourçables (garde `[[ "${BASH_SOURCE[0]}" == "$0" ]] && main`) : `read_label <name>`, `latest_semver` (stdin : tags, stdout : plus grand `N.N.N`, préfixe `v` retiré), `version_gt <a> <b>` (code 0 si a > b, via `sort -V`), `hub_image_exists <version>`.

- [ ] **Step 1: Test** `tests/upstream_watch_test.sh` (bash, sans framework, `fail()` + compteur) qui source le script et vérifie :
  - `printf 'v0.2.8\nv0.2.10\nlatest\nv0.3.0-beta\nv0.2.9\n' | latest_semver` = `0.2.10` (semver filter) ;
  - `version_gt 2.24.4 2.20.5` vrai ; `version_gt 2.20.5 2.20.5` faux ; `version_gt 0.2.10 0.2.9` vrai ;
  - `DOCKERFILE=<fichier temporaire avec les 2 labels> read_label io.jmbrenot.upstream.arm` = `2.20.5`.
- [ ] **Step 2:** `bash tests/upstream_watch_test.sh` → échec (script absent).
- [ ] **Step 3: Implémenter `upstream_watch.sh`** (`set -euo pipefail`). `main` :
  1. lit les deux labels ; erreur si vide ;
  2. `gh api repos/mliradelc/ARM-HASS-Addon/tags --paginate --jq '.[].name' | latest_semver` ;
  3. `gh api repos/automatic-ripping-machine/automatic-ripping-machine/releases/latest --jq '.tag_name,.html_url'` ;
  4. `hub_image_exists` : `curl -fsS -o /dev/null https://hub.docker.com/v2/repositories/1337server/automatic-ripping-machine/tags/<v>` ;
  5. pour chaque source où `version_gt new current` : recherche `gh issue list --state all --label upstream --search "<titre> in:title" --json title --jq` puis comparaison exacte du titre ; si absente → `gh label create upstream --color 0E8A16 --force` puis `gh issue create --title --label upstream --body-file` (ou affichage si `DRY_RUN=1`) ;
  6. ARM, issue ouverte existante, image disponible, aucun commentaire contenant le marqueur (`gh issue view N --json comments --jq`) → `gh issue comment` avec marqueur.
  Si aucune source n'est plus récente : `echo "up to date"`, sortie 0 (no issue when up to date).
  Corps d'issue : versions actuelle → nouvelle, lien notes de version, (ARM) « Image Docker Hub : disponible / pas encore publiée », procédure :
  `.\tools\Update-ArmAddon.ps1 -Phase Prepare -Source Addon|Arm -Version <v> -WhatIf`, puis sans `-WhatIf`, PR via `gestion-de-projet:pr`, fusion, `.\tools\Update-ArmAddon.ps1 -Phase Deploy`, lien wiki.
- [ ] **Step 4:** `bash tests/upstream_watch_test.sh` → PASS ; puis `DRY_RUN=1 GH_TOKEN=$(gh auth token) GITHUB_REPOSITORY=jmbrenot-infra/ARM-HASS-Addon bash .github/scripts/upstream_watch.sh` → affiche une issue ARM 2.24.4 (image pas encore publiée), « mliradelc up to date ».
- [ ] **Step 5:** Commit `feat: upstream watch script`.

### Task 3: Workflows (veille, base, contrôle d'image) et contrôle des ancrages

**Files:**
- Create: `.github/workflows/upstream-watch.yml`, `.github/workflows/build-base.yml`, `.github/workflows/addon-image-check.yml`
- Create: `tests/check_anchors.sh`
- Modify: `.docker/Dockerfile:1` → `ARG ARM_VERSION=latest` puis `FROM docker.io/1337server/automatic-ripping-machine:${ARM_VERSION}`

- [ ] **Step 1: `tests/check_anchors.sh`** (exécuté dans le conteneur, `set -u`, compte les échecs, sortie ≠ 0 si un échec) : les vérifications listées en spec §4 (wrapper `.orig.sh` exécutable ; shim contient `jmbrenot-infra fork` ; `readlink /home/arm/logs` = `/media/arm/logs` ; `/run.sh`, `/entry_jmb.sh`, `/usr/local/bin/arm_disc_watcher.sh` exécutables ; `grep -q /etc/arm/config /run.sh` ; `command -v` udevadm python3 abcde setsid flac ; `python3 -m py_compile` sur `arm_ma_sync.py` vers `/tmp`) ; affiche `ARM version: $(cat /opt/arm/VERSION)` (avertissement si absent).
- [ ] **Step 2: `upstream-watch.yml`** : `on: schedule: cron '0 6 * * 1'` + `workflow_dispatch` (input booléen `dry_run`) ; permissions spec ; checkout ; `bash tests/upstream_watch_test.sh` ; `bash .github/scripts/upstream_watch.sh` avec `GH_TOKEN: ${{ github.token }}`, `DRY_RUN: ${{ inputs.dry_run && '1' || '0' }}`.
- [ ] **Step 3: `build-base.yml`** : `workflow_dispatch` input `arm_version` (string, requis) ; étape de validation `^[0-9]+\.[0-9]+\.[0-9]+$` (via variable d'env, pas d'interpolation directe dans `run`) ; échec si image Docker Hub absente ; `docker/setup-buildx-action@v3`, `docker/login-action@v3` (ghcr, `github.actor`, `GITHUB_TOKEN`), `docker/build-push-action@v5` : `context: .`, `file: .docker/Dockerfile`, `build-args: ARM_VERSION=…`, `platforms: linux/amd64`, `push: true`, `tags: ghcr.io/jmbrenot-infra/arm-hass-addon:arm-<v>`. Dernière étape : rappel dans `$GITHUB_STEP_SUMMARY` « rendre le paquet public si ce n'est pas fait ».
- [ ] **Step 4: `addon-image-check.yml`** : `on: pull_request` (paths `arm/**`, `.docker/**`, `tests/**`, `.github/**`) + `workflow_dispatch` ; `permissions: contents: read`. Job `lint` : `shellcheck` (préinstallé sur ubuntu-latest) sur `arm/rootfs/*.sh` ajoutés par le fork (`arm_disc_watcher.sh`, `docker_arm_wrapper_shim.sh`, `entry_jmb.sh`), `.github/scripts/*.sh`, `tests/*.sh` ; `actionlint` via `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`. Job `image` : `docker build -t arm-addon-check arm/` ; `docker inspect -f '{{json .Config.Entrypoint}}' arm-addon-check` doit contenir `/entry_jmb.sh` ; `docker run --rm --entrypoint /bin/bash -v "$PWD/tests:/tests:ro" arm-addon-check /tests/check_anchors.sh`.
- [ ] **Step 5:** Vérification locale minimale : `bash -n` sur chaque `.sh` ; `python -c "import yaml,sys;[yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/*.yml` sans erreur. Le vrai test est la CI de la PR (Task 7).
- [ ] **Step 6:** Commit `feat: workflows for upstream watch, own ARM base and image anchor checks`.

### Task 4: Module PowerShell — fonctions pures (dépôt)

**Files:**
- Create: `tools/ArmAddonUpgrade.psm1`
- Test: `tools/tests/ArmAddonUpgrade.Tests.ps1`

**Interfaces (Produces):**
- `Get-UpstreamLabels -DockerfileText <string>` → `@{ Addon=<string>; Arm=<string> }` ; lève une erreur si un label manque.
- `Set-DockerfileBase -DockerfileText <string> -FromImage <string> [-Addon <string>] [-Arm <string>]` → string (remplace la ligne `FROM` et les labels fournis).
- `Get-AddonVersion -ConfigText <string>` → string (`0.2.8-jmb.4`).
- `Get-NextAddonVersion -Current <string> [-NewAddonBase <string>]` → `<NewAddonBase>-jmb.1` si fourni, sinon `jmb.N+1`.
- `Set-AddonVersion -ConfigText <string> -Version <string>` → string.
- `Add-ChangelogEntry -ChangelogText <string> -Version <string> -Date <string> -Lines <string[]>` → string (insère `## [<v>] - <date>` + lignes avant le premier `## [`).

- [ ] **Step 1: Tests Pester 3.4** (`Describe`/`It`/`Should Be`) avec les textes réels du dépôt en fixtures (`Get-Content -Raw`) :
  - `Get-UpstreamLabels` sur `arm/Dockerfile` → Addon `0.2.8`, Arm `2.20.5` ;
  - `Get-UpstreamLabels throws` sur un texte sans labels ;
  - `Set-DockerfileBase -FromImage ghcr.io/jmbrenot-infra/arm-hass-addon:arm-2.24.4 -Arm 2.24.4` → ligne `FROM` remplacée, label arm `2.24.4`, label addon inchangé, reste du fichier identique ;
  - `Get-NextAddonVersion -Current 0.2.8-jmb.4` → `0.2.8-jmb.5` ; `-NewAddonBase 0.2.9` → `0.2.9-jmb.1` ;
  - `Set-AddonVersion` → `version: "0.2.8-jmb.5"`, autres lignes inchangées ;
  - `Add-ChangelogEntry` → l'entrée apparaît avant `## [0.2.8-jmb.4]`, l'en-tête du fichier est conservé.
- [ ] **Step 2:** `powershell -NoProfile -c "Invoke-Pester tools/tests"` → échecs (module absent).
- [ ] **Step 3:** Implémenter les fonctions (regex multiline `(?m)`, conservation des fins de ligne LF du dépôt).
- [ ] **Step 4:** `Invoke-Pester tools/tests` → tout PASS ; contrôle ASCII : `grep -P '[^\x00-\x7F]' tools/*.ps*1` vide.
- [ ] **Step 5:** Commit `feat: pure helpers for the add-on upgrade tool`.

### Task 5: Module PowerShell — fonctions pures (HA)

**Files:**
- Modify: `tools/ArmAddonUpgrade.psm1`
- Test: `tools/tests/ArmAddonUpgrade.Tests.ps1`

**Interfaces (Produces):**
- `Get-EnvValue -Path <string> -Name <string>` → string ; lit uniquement la ligne `^<Name>=` via `Select-String`, retire guillemets et `\r` ; erreur `"<Name> not found in <Path>"` sinon (sans afficher de valeur).
- `Test-ArmIdle -JoblistJson <string>` → bool (`results` absent, `{}` ou `[]` → `$true`).
- `Find-LogLine -LogText <string> -Pattern <string>` → première ligne correspondante ou `$null`.

- [ ] **Step 1: Tests** : `.env` temporaire (`TestDrive:`) avec `A=1`, `AUZ_HA_TOKEN="abc"` + CR, `AUZ_HA_TOKEN_X=zz` → `Get-EnvValue … AUZ_HA_TOKEN` = `abc` ; nom absent → throw dont le message ne contient pas `abc` ; `Test-ArmIdle` : `{"results":{}}` vrai, `{"results":[]}` vrai, `{"results":{"0":{"job_id":1}}}` faux ; `Find-LogLine` trouve `[ARM] ma-sync: 1 sync task(s) started` avec motif `\[ARM\] ma-sync: \d+ sync task\(s\) started`.
- [ ] **Step 2:** Pester → échecs. **Step 3:** implémenter (`ConvertFrom-Json`, PS 5.1). **Step 4:** Pester → PASS.
- [ ] **Step 5:** Commit `feat: HA helpers for the add-on upgrade tool`.

### Task 6: Script `tools/Update-ArmAddon.ps1`

**Files:**
- Create: `tools/Update-ArmAddon.ps1`
- Modify: `arm/DOCS.md` (section « Mise à jour depuis l'amont (fork) », 5–8 lignes en anglais comme le reste du fichier, pointant vers le script et l'issue `upstream`)

**Interfaces:**
- Consumes: fonctions des Tasks 4 et 5 (`Import-Module "$PSScriptRoot\ArmAddonUpgrade.psm1"`).
- Paramètres : `-Phase Prepare|Deploy` (requis), `-Source Addon|Arm`, `-Version`, `-ArmVersion`, `-WaitIdle`, `-SkipCdTest`, `-HaUrl` (défaut `http://192.168.0.55:8123`), `-ArmUrl` (défaut `http://192.168.0.55:8089`), `-EnvPath` (défaut `$env:USERPROFILE\.ha-secrets\.env`) ; `[CmdletBinding(SupportsShouldProcess=$true)]`.

- [ ] **Step 1: Phase Prepare** selon spec §5 : contrôles (`git status --porcelain` vide, `git fetch jmb`), `$PSCmdlet.ShouldProcess` autour de chaque écriture (branche, fichiers, `gh workflow run`, commit). En `-WhatIf` : afficher le diff prévu (ancienne/nouvelle ligne `FROM`, labels, version). Source `Arm` : contrôle Docker Hub (`Invoke-WebRequest -UseBasicParsing`), `gh workflow run build-base.yml -R jmbrenot-infra/ARM-HASS-Addon -f arm_version=X`, récupérer l'ID du run (`gh run list -w build-base.yml -L 1 --json databaseId`), `gh run watch <id> --exit-status`, contrôle GHCR anonyme (`https://ghcr.io/token?scope=repository:jmbrenot-infra/arm-hass-addon:pull` puis `HEAD /v2/jmbrenot-infra/arm-hass-addon/manifests/arm-X` avec `Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json`). Fin : message « Branche prête. Ouvrir la PR avec gestion-de-projet:pr (scan git-sans-secret), puis fusionner, puis -Phase Deploy. »
- [ ] **Step 2: Phase Deploy** selon spec §5 (étapes 1–8). Appels : `Invoke-RestMethod` avec en-tête `Authorization: Bearer` construit en mémoire ; `POST /api/services/homeassistant/update_entity`, `GET /api/states/update.arm_jmbrenot_infra_mise_a_jour`, `POST /api/services/update/install` corps `{"entity_id":"update.arm_jmbrenot_infra_mise_a_jour","backup":false}`, `GET /api/hassio/addons/65fe9fa6_arm/logs`. Boucles d'attente avec `Start-Sleep 15` et délais de la spec. Confirmation : `Read-Host` doit valoir `oui`. En `-WhatIf` : lecture seule (joblist, états, journal) et affichage des actions sautées. Le `try/finally` efface la variable du jeton.
- [ ] **Step 3: Simulation** : `powershell -NoProfile -File tools/Update-ArmAddon.ps1 -Phase Prepare -Source Addon -Version 0.2.9 -WhatIf` → diff affiché, `git status` inchangé ; idem `-Source Arm -Version 2.24.4 -WhatIf` → arrêt « image Docker Hub absente » ; `-Phase Deploy -WhatIf -SkipCdTest` → état idle/occupé, versions installée/disponible affichées, aucun POST.
- [ ] **Step 4:** Contrôle ASCII + `Invoke-Pester tools/tests` toujours vert.
- [ ] **Step 5:** Commit `feat: controlled upgrade tool for the ARM add-on`.

### Task 7: Version, CHANGELOG, PR

- [ ] **Step 1:** Pas de bump de `version` (aucun changement d'image ; les labels ne changent pas le comportement) — le noter dans la PR. Ajouter dans `arm/CHANGELOG.md` une section `## [Unreleased]` décrivant veille + outil.
- [ ] **Step 2:** Skill `secrets-et-git:git-sans-secret` sur le diff de la branche.
- [ ] **Step 3:** Skill `gestion-de-projet:pr` (base `master` de `jmbrenot-infra/ARM-HASS-Addon`) ; lier HA-Auzeville#16 (sans fermeture).
- [ ] **Step 4:** Lire la CI de la PR (`addon-image-check`) ; corriger jusqu'au vert.
- [ ] **Step 5:** Après fusion et accord : `gh workflow run upstream-watch.yml -f dry_run=true`, puis réel ; vérifier une seule issue ARM 2.24.4.
- [ ] **Step 6:** Proposer la ligne wiki §13 (dépôt Architecture-Generale, PR, `tooling/Sync-Wiki.ps1`) — sans l'appliquer sans accord.
