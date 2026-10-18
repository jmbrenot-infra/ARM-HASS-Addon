#!/bin/bash
# Upstream watch (jmbrenot-infra fork).
#
# Compares the upstream versions recorded as labels in arm/Dockerfile with the latest
# mliradelc/ARM-HASS-Addon tag and the latest automatic-ripping-machine release, and opens
# one issue (label `upstream`) per new version. Never opens the same title twice.
#
# Env: GH_TOKEN, GITHUB_REPOSITORY, DRY_RUN=1 (print only), DOCKERFILE (default arm/Dockerfile).

ADDON_REPO=mliradelc/ARM-HASS-Addon
ARM_REPO=automatic-ripping-machine/automatic-ripping-machine
HUB_IMAGE=1337server/automatic-ripping-machine
WIKI_URL=https://github.com/jmbrenot-infra/Architecture-Generale/blob/main/wiki/13-musique-ripage-cd.md
IMAGE_MARKER='<!-- upstream-watch:image-available -->'
LABEL=upstream

# Value of a LABEL key in the Dockerfile.
read_label() {
    sed -n "s/.*$1=\"\([^\"]*\)\".*/\1/p" "${DOCKERFILE:-arm/Dockerfile}" | head -n 1
}

# Highest N.N.N version on stdin (one tag per line, optional v prefix); other tags are ignored.
latest_semver() {
    sed -n 's/^v\{0,1\}\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)$/\1/p' | sort -V | tail -n 1
}

# True when version $1 is strictly greater than version $2.
version_gt() {
    [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -n 1)" = "$1" ]
}

# True when the Docker Hub image exists for this ARM version.
hub_image_exists() {
    curl -fs -o /dev/null "https://hub.docker.com/v2/repositories/${HUB_IMAGE}/tags/$1"
}

# Number of the issue with exactly this title (open or closed), empty if none.
find_issue() {
    gh issue list -R "$GITHUB_REPOSITORY" --state all --label "$LABEL" --limit 200 \
        --json number,title --jq ".[] | select(.title == \"$1\") | .number" | head -n 1
}

procedure() {
    cat <<EOF
## Procédure

1. Simulation : \`.\\tools\\Update-ArmAddon.ps1 -Phase Prepare -Source $1 -Version $2 -WhatIf\`
2. Préparation : même commande sans \`-WhatIf\` (branche + commit local, rien n'est poussé).
3. PR avec le skill \`gestion-de-projet:pr\` (scan \`git-sans-secret\`), attendre le contrôle \`addon-image-check\`, fusionner.
4. Déploiement : \`.\\tools\\Update-ArmAddon.ps1 -Phase Deploy -WhatIf\`, puis sans \`-WhatIf\`
   (vérifie qu'aucun rip ne tourne, met à jour sans sauvegarde, contrôle le journal, CD de test).

Contexte et pièges : [wiki chapitre 13]($WIKI_URL).
EOF
}

open_issue() {
    local title=$1 body=$2
    if [ -n "$(find_issue "$title")" ]; then
        echo "exists: $title"
        return 0
    fi
    if [ "${DRY_RUN:-0}" = "1" ]; then
        printf 'DRY RUN, would open: %s\n%s\n---\n' "$title" "$body"
        return 0
    fi
    gh label create "$LABEL" -R "$GITHUB_REPOSITORY" --color 0E8A16 \
        --description "New upstream version" --force >/dev/null
    gh issue create -R "$GITHUB_REPOSITORY" --title "$title" --label "$LABEL" --body "$body"
}

check_addon() {
    local current=$1 latest
    latest=$(gh api "repos/${ADDON_REPO}/tags" --paginate --jq '.[].name' | latest_semver)
    if [ -z "$latest" ] || ! version_gt "$latest" "$current"; then
        echo "mliradelc up to date ($current, latest ${latest:-none})"
        return 0
    fi
    open_issue "Amont : add-on mliradelc $latest disponible" "$(cat <<EOF
Nouveau tag amont de l'add-on : **$latest** (image actuelle : \`ghcr.io/mliradelc/arm-hass-addon:$current\`).

- Tag : https://github.com/${ADDON_REPO}/releases/tag/v$latest
- Changelog : https://github.com/${ADDON_REPO}/blob/v$latest/arm/CHANGELOG.md

$(procedure Addon "$latest")
EOF
)"
}

check_arm() {
    local current=$1 tag url latest available title number
    tag=$(gh api "repos/${ARM_REPO}/releases/latest" --jq '.tag_name')
    url=$(gh api "repos/${ARM_REPO}/releases/latest" --jq '.html_url')
    latest=$(echo "$tag" | latest_semver)
    if [ -z "$latest" ] || ! version_gt "$latest" "$current"; then
        echo "ARM up to date ($current, latest ${tag:-none})"
        return 0
    fi
    if hub_image_exists "$latest"; then available=yes; else available=no; fi
    title="Amont : ARM $latest disponible"
    number=$(find_issue "$title")
    if [ -n "$number" ]; then
        echo "exists: $title (#$number)"
        if [ "$available" = yes ] && [ "$(gh issue view "$number" -R "$GITHUB_REPOSITORY" --json state --jq .state)" = OPEN ] \
            && ! gh issue view "$number" -R "$GITHUB_REPOSITORY" --json comments --jq '.comments[].body' | grep -qF "$IMAGE_MARKER"; then
            if [ "${DRY_RUN:-0}" = "1" ]; then
                echo "DRY RUN, would comment on #$number: image available"
            else
                gh issue comment "$number" -R "$GITHUB_REPOSITORY" --body "$IMAGE_MARKER
L'image \`${HUB_IMAGE}:$latest\` est maintenant publiée sur Docker Hub : l'outil \`-Source Arm -Version $latest\` est utilisable."
            fi
        fi
        return 0
    fi
    local image_line
    if [ "$available" = yes ]; then
        image_line="Image Docker Hub \`${HUB_IMAGE}:$latest\` : **disponible**, l'outil est utilisable."
    else
        image_line="Image Docker Hub \`${HUB_IMAGE}:$latest\` : **pas encore publiée**. L'outil refusera la mise à jour tant qu'elle manque ; un commentaire sera ajouté ici quand elle paraîtra."
    fi
    open_issue "$title" "$(cat <<EOF
Nouvelle release ARM : **$latest** (version embarquée : $current).

- Notes de version : $url
- $image_line

La mise à jour passe par notre propre base \`ghcr.io/jmbrenot-infra/arm-hass-addon:arm-$latest\` (workflow \`build-base.yml\`, lancé par l'outil).

$(procedure Arm "$latest")
EOF
)"
}

main() {
    set -euo pipefail
    : "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
    local addon arm
    addon=$(read_label io.jmbrenot.upstream.addon)
    arm=$(read_label io.jmbrenot.upstream.arm)
    if [ -z "$addon" ] || [ -z "$arm" ]; then
        echo "::error::upstream labels missing in ${DOCKERFILE:-arm/Dockerfile}"
        exit 1
    fi
    check_addon "$addon"
    check_arm "$arm"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
