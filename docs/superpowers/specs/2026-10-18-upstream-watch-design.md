# Veille amont et mise à jour contrôlée de l'add-on ARM (fork jmbrenot-infra)

Date : 2026-10-18 · Contexte : ticket jmbrenot-infra/HA-Auzeville#16, wiki Architecture-Generale chapitre 13.

## Objectif

Être prévenu automatiquement quand l'amont publie une nouvelle version, et disposer d'un outil qui applique la
mise à jour de façon contrôlée, sans casser les ajouts du fork (shim udev, watcher d'insertion, synchro Music
Assistant) ni perdre un rip en cours.

## Constats (2026-10-18)

- Le fork part de `ghcr.io/mliradelc/arm-hass-addon:0.2.8` (ARM 2.20.5). mliradelc n'a plus publié depuis `v0.2.8`.
- ARM est en 2.24.4 (release GitHub du 2026-10-03), mais aucune image n'est publiée au-delà de 2.20.5 :
  `1337server/automatic-ripping-machine:2.2x` absent de Docker Hub, rien de récent sur GHCR.
- Les issues sont désactivées sur le fork : on les active (`gh repo edit --enable-issues`).
- Pas de Docker sur PORTABLE-HP : le contrôle de l'image se fait en CI.
- Côté HA : l'entité `update.arm_jmbrenot_infra_mise_a_jour` accepte `update.install` avec `backup: false`
  (supported_features 29). `/api/hassio/store/reload` est refusé (401) au jeton longue durée.
  Journal (`/api/hassio/addons/65fe9fa6_arm/logs`) et `http://192.168.0.55:8089/json?mode=joblist` accessibles.

## Décisions

| Sujet | Décision |
|---|---|
| Sources suivies | Les deux : tags mliradelc et releases ARM |
| Alertes | Issues du fork (activées), `GITHUB_TOKEN` seulement |
| Contrôle de l'image | CI sur chaque PR (build + script dans le conteneur) |
| Voie « ARM direct » | Notre propre base `ghcr.io/jmbrenot-infra/arm-hass-addon:arm-<version>`, construite en CI depuis `1337server/automatic-ripping-machine:<version>` ; utilisable seulement quand cette image existe |
| Plateforme de notre base | `linux/amd64` seulement (PC HAOS d'Auzeville ; HandBrake en arm64 sous QEMU trop long) |
| PR | Ouverte par le skill `gestion-de-projet:pr` (scan `git-sans-secret`), jamais par le script |

## 1. Versions de référence

Deux labels dans `arm/Dockerfile`, juste après le `FROM` (resté littéral) :

```dockerfile
LABEL io.jmbrenot.upstream.addon="0.2.8" \
      io.jmbrenot.upstream.arm="2.20.5"
```

Ce sont les seules sources de vérité pour la comparaison ; elles restent justes quand le `FROM` pointe sur notre base.

## 2. Détection — `.github/workflows/upstream-watch.yml`

- Déclencheurs : `schedule` (lundi 06:00 UTC) et `workflow_dispatch`.
- Permissions : `contents: read`, `issues: write`. Jeton : `GITHUB_TOKEN`.
- Logique dans `.github/scripts/upstream_watch.sh` (bash + `gh`, `GH_TOKEN`, `GITHUB_REPOSITORY`) ; option
  `DRY_RUN=1` : affiche les issues qui seraient créées sans rien écrire.
- mliradelc : plus grand tag semver de `mliradelc/ARM-HASS-Addon` (préfixe `v` retiré) comparé à `upstream.addon`.
- ARM : `releases/latest` de `automatic-ripping-machine/automatic-ripping-machine` comparé à `upstream.arm` ;
  disponibilité de l'image testée par `https://hub.docker.com/v2/repositories/1337server/automatic-ripping-machine/tags/<version>` (200 = disponible).
- Une issue par source, pour la version la plus récente uniquement, label `upstream` (créé au besoin).
  Titres : `Amont : add-on mliradelc <v> disponible`, `Amont : ARM <v> disponible`.
- Pas de doublon : recherche d'une issue (ouverte ou fermée) au titre identique ; si trouvée, rien n'est créé.
- Issue ARM ouverte, image absente à la création, image disponible ensuite : un seul commentaire contenant le
  marqueur `<!-- upstream-watch:image-available -->`.
- Corps : versions actuelle / nouvelle, lien vers les notes de version, disponibilité de l'image (ARM), procédure
  (commandes `tools/Update-ArmAddon.ps1`), lien vers le chapitre 13 du wiki
  (`https://github.com/jmbrenot-infra/Architecture-Generale/blob/main/wiki/13-musique-ripage-cd.md`).

## 3. Base ARM — `.github/workflows/build-base.yml`

- `workflow_dispatch`, entrée `arm_version` (obligatoire, format `N.N.N`).
- Permissions : `contents: read`, `packages: write`.
- Échec immédiat si l'image Docker Hub `1337server/automatic-ripping-machine:<arm_version>` n'existe pas.
- Construit `.docker/Dockerfile` (recette mliradelc) avec `--build-arg ARM_VERSION=<arm_version>` ;
  `.docker/Dockerfile` devient `ARG ARM_VERSION=latest` / `FROM docker.io/1337server/automatic-ripping-machine:${ARM_VERSION}`.
- Plateforme `linux/amd64`, publie `ghcr.io/jmbrenot-infra/arm-hass-addon:arm-<arm_version>`.
- Étape manuelle unique : rendre le paquet GHCR public (UI GitHub), sinon le Supervisor ne peut pas le télécharger.
- Le workflow amont `build-and-push.yml` (tags `v*`) n'est pas modifié.

## 4. Contrôle des points d'ancrage — `.github/workflows/addon-image-check.yml`

- Sur `pull_request` (chemins `arm/**`, `.docker/**`, `tests/**`, le workflow lui-même) et `workflow_dispatch`.
- Job `lint` : `shellcheck` sur les scripts shell du dépôt ajoutés par le fork, `actionlint` sur les workflows.
- Job `image` : `docker build arm/` (amd64, chargé localement), puis `tests/check_anchors.sh` exécuté dans le
  conteneur (`--entrypoint /bin/bash`). Vérifie :
  - `/opt/arm/scripts/docker/docker_arm_wrapper.orig.sh` exécutable ;
  - `/opt/arm/scripts/docker/docker_arm_wrapper.sh` = notre shim (chaîne `jmbrenot-infra fork`) ;
  - `/home/arm/logs` lien vers `/media/arm/logs` ;
  - `/run.sh`, `/entry_jmb.sh`, `/usr/local/bin/arm_disc_watcher.sh` exécutables ; `/run.sh` contient `/etc/arm/config` ;
  - commandes `udevadm`, `python3`, `abcde`, `setsid`, `flac` ;
  - `/usr/local/bin/arm_ma_sync.py` compile (`python3 -m py_compile`) ;
  - affiche la version d'ARM de l'image (`/opt/arm/VERSION`).
  L'entrypoint de l'image (`/entry_jmb.sh`) est vérifié hors conteneur par `docker inspect`.

## 5. Outil — `tools/Update-ArmAddon.ps1`

ASCII pur, PowerShell 5.1, `[CmdletBinding(SupportsShouldProcess)]` : `-WhatIf` n'écrit rien (fichiers, git, HA).
Fonctions pures dans `tools/ArmAddonUpgrade.psm1` (testées par Pester), orchestration dans le script.

### Phase `Prepare` — `-Phase Prepare -Source Addon|Arm -Version X [-ArmVersion Y]`

1. Arbre propre, `git fetch jmb`, branche `jmb/upstream-<addon|arm>-<X>` depuis `jmb/master`.
2. `Addon` : `FROM ghcr.io/mliradelc/arm-hass-addon:X`, `upstream.addon=X`, `upstream.arm=Y` si fourni (sinon
   inchangé, avec avertissement), version `X-jmb.1`.
   `Arm` : image Docker Hub présente, sinon arrêt ; `gh workflow run build-base.yml -f arm_version=X` puis
   `gh run watch` ; image GHCR accessible anonymement (manifeste `ghcr.io/v2/.../manifests/arm-X` via jeton anonyme),
   sinon arrêt avec rappel « rendre le paquet public » ; `FROM ghcr.io/jmbrenot-infra/arm-hass-addon:arm-X`,
   `upstream.arm=X`, version `jmb.N` → `jmb.N+1`.
3. Entrée datée en tête de `arm/CHANGELOG.md`, commit local, arrêt avec la consigne : ouvrir la PR avec
   `gestion-de-projet:pr`.

### Phase `Deploy` — `-Phase Deploy [-WaitIdle] [-SkipCdTest]`

1. Version cible = `version` de `config.yaml` sur `jmb/master` (après `git fetch`).
2. Jeton : `Select-String -Pattern '^AUZ_HA_TOKEN='` sur `%USERPROFILE%\.ha-secrets\.env`, valeur gardée en mémoire,
   jamais affichée.
3. `json?mode=joblist` : `results` vide, sinon arrêt (ou attente avec `-WaitIdle`, contrôle toutes les 60 s).
4. `homeassistant.update_entity` sur `update.arm_jmbrenot_infra_mise_a_jour`, attente de `latest_version` = cible
   (5 min), puis invite à cliquer « Rechercher des mises à jour » et attente prolongée (15 min au total).
5. Confirmation clavier `oui`, re-vérification du joblist, puis `update.install` `{entity_id, backup: false}` ;
   attente de `installed_version` = cible (30 min).
6. Journal : `[ARM] watcher: /dev/sr0 initial media=` (5 min).
7. Sauf `-SkipCdTest` : invite à insérer un CD, attente de `[ARM] ma-sync: N sync task(s) started` (30 min).
8. Bilan ; en cas d'échec ou d'expiration, les 30 dernières lignes du journal.

Jamais : redémarrage de HA, écriture sur `W:`, sauvegarde, action HA sans confirmation.

## Tests

- Pester : lecture/écriture des labels et du `FROM`, calcul de version, insertion CHANGELOG.
- `-WhatIf` des deux phases sur le poste.
- `DRY_RUN=1 bash .github/scripts/upstream_watch.sh` en local, puis `workflow_dispatch` après fusion (accord requis).
- CI : `shellcheck`, `actionlint`, contrôle d'image sur la PR elle-même.

## Hors périmètre

- Compiler ARM depuis les sources tant qu'aucune image 2.2x n'est publiée.
- Base arm64.
- Report Gruissan : non applicable (pas de lecteur CD, wiki chapitre 13).
