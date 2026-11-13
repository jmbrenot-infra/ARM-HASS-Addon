# Scripts de maintenance NASPLUS

Scripts Python déployés sur NASPLUS (`/volume1/scripts/`), exécutés par la tâche planifiée DSM
horaire existante (ID 11, "Normalize Unknown Album Tags" -- `synoschedtask` n'a pas de `--add`/`--set`,
impossible d'en créer une seconde depuis le CLI).

- `normalize_unknown_album_tags.py` -- point d'entrée de la tâche planifiée. Désambiguïse les tags
  `ALBUM` des CD non identifiés (`Unknown Album` -> `Unknown Album (<hash cddb>)`), puis appelle
  `fix_multidisc_albums.py`.
- `fix_multidisc_albums.py` -- réorganise en `CD1/CD2/.../CDN` les albums dont plusieurs disques
  physiques ont été rippés dans le même dossier Artiste/Album (abcde n'a pas d'`OUTPUTFORMAT` sensible
  au disque). Détection par ordre de fiabilité : préfixe de disque dans le nom de fichier
  (`2-01 - Titre.flac`), préfixe à 3 chiffres (`104 Titre.flac` = disque 1 piste 04), tag `cddb`
  (un hash distinct par disque physique), puis en dernier recours un écart de date de modification
  entre pistes (peu fiable, loggué comme tel). Régénère aussi le `.m3u` racine de l'album
  (`<Artiste>-<Album>.m3u`) pour pointer vers les nouveaux chemins `CDn/`.
- `apply_unknown_album_tag_plan.py`, `export_unknown_album_discids.py`, `inventory_unknown_albums.py`,
  `query_gnudb.py`, `verify_unknown_album_state.py` -- outils d'investigation/application ponctuels
  utilisés pour le correctif rétroactif initial (ticket HA-Auzeville#16).

## Déploiement

Automatique via `tools/Update-ArmAddon.ps1 -Phase Deploy` (fonction `Deploy-NasplusScripts`) : à chaque
mise à jour réussie de l'add-on, ces fichiers sont poussés vers `/volume1/scripts/` sur le NAS
(`scp` vers `/tmp`, puis `sudo mv`/`chown`/`chmod`, le compte utilisé n'ayant pas les droits
d'écriture directs sur ce dossier appartenant à `root`).

### Réglages (dans le coffre, jamais dans ce dépôt)

Ce dépôt est public : l'hôte, le compte et la clé ne figurent pas dans le code. Le script les lit par
leur nom dans le coffre local (`%USERPROFILE%\.ha-secrets\.env`) :

| Clé | Rôle |
|---|---|
| `ARM_NAS_SCRIPTS_HOST` | Nom ou adresse du NAS cible |
| `ARM_NAS_SCRIPTS_USER` | Compte SSH utilisé pour le dépôt |
| `ARM_NAS_SCRIPTS_SSH_PRIVATE_KEY_B64` | Clé privée SSH de ce compte, encodée en Base64 |
| `ARM_NAS_SCRIPTS_KNOWN_HOSTS` | Chemin du fichier `known_hosts` contenant la clé d'hôte du NAS |

Si l'un de ces réglages manque dans le coffre, l'étape est sautée avec un avertissement (la mise à
jour de l'add-on n'échoue pas).

Pour un déploiement manuel ponctuel (sans passer par une mise à jour de l'add-on) :

```powershell
Import-Module .\tools\ArmAddonUpgrade.psm1 -Force
. .\tools\Update-ArmAddon.ps1  # ou copier la fonction Deploy-NasplusScripts dans une session
Deploy-NasplusScripts
```

### Prérequis sur le NAS (persistant, à ne faire qu'une fois)

Le compte de dépôt n'a pas les droits d'écriture sur `/volume1/scripts` (appartient à `root:root`).
Une règle sudoers dédiée, limitée à exactement ces 3 commandes, est créée en root sur le NAS, dans un
fichier de `/etc/sudoers.d/` (permissions 0440) :

```
<compte> ALL=(root) NOPASSWD: /bin/mv /tmp/*.py /volume1/scripts/*.py, /bin/chown root\:root /volume1/scripts/*.py, /bin/chmod 755 /volume1/scripts/*.py
```

Vérifier qu'elle est toujours active : `sudo -l -U <compte>` (en root sur le NAS) doit lister ces
3 commandes en `NOPASSWD`.

**Persistance** : `/etc/sudoers.d/` et `/volume1/scripts/` survivent aux redémarrages normaux du NAS
(comportement standard DSM). **Pas de garantie en revanche lors d'une mise à jour majeure de DSM** :
Synology peut dans ce cas régénérer certains fichiers système. Si les scripts de maintenance
s'arrêtent de fonctionner après une telle mise à jour, revérifier `sudo -l -U <compte>` en premier et
recréer la règle ci-dessus si besoin -- aucune automatisation ne la recrée toute seule.

L'authentification SSH se fait par clé (clé `ARM_NAS_SCRIPTS_SSH_PRIVATE_KEY_B64` du coffre), jamais
par mot de passe -- piper un mot de passe à `sudo -S` à travers PowerShell s'est révélé peu fiable
(voir le commentaire dans `Deploy-NasplusScripts`), d'où la clé et la règle sudoers limitée plutôt
qu'une saisie de mot de passe à distance.
