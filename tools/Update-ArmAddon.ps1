<#
.SYNOPSIS
    Controlled upgrade of the ARM add-on (jmbrenot-infra fork) to a new upstream version.

.DESCRIPTION
    Phase Prepare (repository): creates the branch jmb/upstream-<addon|arm>-<version> from jmb/master,
    changes the base image in arm/Dockerfile, bumps arm/config.yaml, adds a CHANGELOG entry and commits
    locally. It never pushes: open the PR with the gestion-de-projet:pr skill (secret scan), let the
    addon-image-check workflow pass, merge.

    Phase Deploy (Home Assistant, after the merge): checks that no rip is running, refreshes the update
    entity, installs the update WITHOUT backup after a typed confirmation, then checks the add-on log
    (disc watcher, then Music Assistant sync after a test CD).

    -WhatIf writes nothing: no file, no git change, no workflow run, no Home Assistant action.
    Never restarts Home Assistant. ASCII only, Windows PowerShell 5.1 compatible.

.EXAMPLE
    .\tools\Update-ArmAddon.ps1 -Phase Prepare -Source Addon -Version 0.2.9 -WhatIf
.EXAMPLE
    .\tools\Update-ArmAddon.ps1 -Phase Prepare -Source Arm -Version 2.24.4
.EXAMPLE
    .\tools\Update-ArmAddon.ps1 -Phase Deploy -WaitIdle
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)][ValidateSet('Prepare', 'Deploy')][string]$Phase,
    [ValidateSet('Addon', 'Arm')][string]$Source,
    [ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version,
    [ValidatePattern('^\d+\.\d+\.\d+$')][string]$ArmVersion,
    [switch]$WaitIdle,
    [switch]$SkipCdTest,
    [string]$HaUrl = 'http://192.168.0.55:8123',
    [string]$ArmUrl = 'http://192.168.0.55:8089',
    [string]$EnvPath = (Join-Path $env:USERPROFILE '.ha-secrets\.env'),
    # Git ref the new version is based on (default jmb/master; another ref is for simulations).
    [string]$BaseRef = 'jmb/master',
    # Deploy: version to install instead of the one in $BaseRef (for simulations).
    [string]$TargetVersion
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ArmAddonUpgrade.psm1') -Force

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Remote = 'jmb'
$GhRepo = 'jmbrenot-infra/ARM-HASS-Addon'
$UpdateEntity = 'update.arm_jmbrenot_infra_mise_a_jour'
$AddonSlug = '65fe9fa6_arm'
$HubImage = '1337server/automatic-ripping-machine'
$OwnBase = 'jmbrenot-infra/arm-hass-addon'
$AddonBase = 'mliradelc/arm-hass-addon'
$WatcherPattern = '\[ARM\] watcher: /dev/sr0 initial media='
$MaSyncPattern = '\[ARM\] ma-sync: \d+ sync task\(s\) started'

function Write-Step([string]$Text) { Write-Host "==> $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host "    OK  $Text" -ForegroundColor Green }
function Write-Warn2([string]$Text) { Write-Host "    !!  $Text" -ForegroundColor Yellow }

# Runs git in the repository and returns its raw stdout (exact bytes as UTF-8, LF kept).
function Invoke-Git {
    param([Parameter(Mandatory = $true)][string[]]$Arguments, [switch]$AllowFailure)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'git'
    $psi.Arguments = ($Arguments | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }) -join ' '
    $psi.WorkingDirectory = $RepoRoot
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $p = [System.Diagnostics.Process]::Start($psi)
    $out = $p.StandardOutput.ReadToEnd()
    $err = $p.StandardError.ReadToEnd()
    $p.WaitForExit()
    if ($p.ExitCode -ne 0 -and -not $AllowFailure) { throw "git $($psi.Arguments) failed: $err" }
    return $out
}

function Invoke-Gh {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $out = & gh @Arguments
    if ($LASTEXITCODE -ne 0) { throw "gh $($Arguments -join ' ') failed (exit $LASTEXITCODE)" }
    return $out
}

function Write-RepoFile([string]$RelativePath, [string]$Text) {
    [IO.File]::WriteAllText((Join-Path $RepoRoot $RelativePath), $Text, (New-Object System.Text.UTF8Encoding($false)))
}

function Test-HubImage([string]$Tag) {
    try {
        $null = Invoke-WebRequest -UseBasicParsing -Uri "https://hub.docker.com/v2/repositories/$HubImage/tags/$Tag" -TimeoutSec 30
        return $true
    } catch { return $false }
}

# True when ghcr.io/<image>:<tag> can be pulled anonymously (as the Supervisor does).
function Test-GhcrImage([string]$Image, [string]$Tag) {
    try {
        $token = (Invoke-RestMethod -Uri "https://ghcr.io/token?scope=repository:${Image}:pull" -TimeoutSec 30).token
        $headers = @{
            Authorization = "Bearer $token"
            Accept        = 'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json'
        }
        $null = Invoke-WebRequest -UseBasicParsing -Method Head -Uri "https://ghcr.io/v2/$Image/manifests/$Tag" -Headers $headers -TimeoutSec 30
        return $true
    } catch { return $false }
}

function Invoke-Prepare {
    if (-not $Source -or -not $Version) { throw '-Phase Prepare needs -Source and -Version' }
    Set-Location $RepoRoot

    Write-Step 'Repository checks'
    if ((Invoke-Git @('status', '--porcelain')).Trim()) { throw 'Working tree not clean: commit or stash first' }
    $null = Invoke-Git @('fetch', $Remote, '--quiet')
    $branch = "jmb/upstream-$($Source.ToLower())-$Version"
    if ((Invoke-Git @('branch', '--list', $branch)).Trim()) { throw "Branch $branch already exists" }
    Write-Ok "clean tree, $Remote fetched, branch $branch is free"

    $base = $BaseRef
    $dockerfile = Invoke-Git @('show', "${base}:arm/Dockerfile")
    $config = Invoke-Git @('show', "${base}:arm/config.yaml")
    $changelog = Invoke-Git @('show', "${base}:arm/CHANGELOG.md")
    $labels = Get-UpstreamLabels -DockerfileText $dockerfile
    $currentVersion = Get-AddonVersion -ConfigText $config
    Write-Ok "current: add-on $currentVersion, upstream add-on $($labels.Addon), ARM $($labels.Arm)"
    $currentUpstream = if ($Source -eq 'Addon') { $labels.Addon } else { $labels.Arm }
    if (-not (Test-VersionGreater -Version $Version -Than $currentUpstream)) {
        throw "$Version is not newer than the current $Source version $currentUpstream"
    }

    if ($Source -eq 'Addon') {
        Write-Step "Checking ghcr.io/${AddonBase}:$Version"
        if (-not (Test-GhcrImage $AddonBase $Version)) { throw "ghcr.io/${AddonBase}:$Version not found" }
        Write-Ok 'image found'
        $from = "ghcr.io/${AddonBase}:$Version"
        $newDockerfile = Set-DockerfileBase -DockerfileText $dockerfile -FromImage $from -Addon $Version -Arm $ArmVersion
        $newVersion = Get-NextAddonVersion -Current $currentVersion -NewAddonBase $Version
        $armText = $labels.Arm
        if ($ArmVersion) { $armText = $ArmVersion } else { Write-Warn2 "-ArmVersion not given: label io.jmbrenot.upstream.arm stays $($labels.Arm) (check the CI log 'ARM version')" }
        $lines = @("- **Changed**: Base image ``$from`` (was ``$($labels.Addon)``), ARM $armText.")
    } else {
        Write-Step "Checking Docker Hub ${HubImage}:$Version"
        if (-not (Test-HubImage $Version)) { throw "${HubImage}:$Version is not on Docker Hub yet: the upgrade cannot be built" }
        Write-Ok 'image found'
        $from = "ghcr.io/${OwnBase}:arm-$Version"
        $newDockerfile = Set-DockerfileBase -DockerfileText $dockerfile -FromImage $from -Arm $Version
        $newVersion = Get-NextAddonVersion -Current $currentVersion
        $lines = @("- **Changed**: ARM $Version (was $($labels.Arm)), on our own base image ``$from`` built by ``build-base.yml`` (linux/amd64) from ``${HubImage}:$Version`` with the mliradelc recipe.")

        Write-Step "Building $from"
        if ($PSCmdlet.ShouldProcess("$GhRepo build-base.yml", "gh workflow run (arm_version=$Version)")) {
            $started = (Get-Date).ToUniversalTime()
            $null = Invoke-Gh @('workflow', 'run', 'build-base.yml', '-R', $GhRepo, '-f', "arm_version=$Version")
            $runId = $null
            for ($i = 0; $i -lt 20 -and -not $runId; $i++) {
                Start-Sleep -Seconds 5
                $runs = (Invoke-Gh @('run', 'list', '-R', $GhRepo, '-w', 'build-base.yml', '-L', '5', '--json', 'databaseId,createdAt')) -join '' | ConvertFrom-Json
                $run = $runs | Where-Object { ([datetime]$_.createdAt).ToUniversalTime() -ge $started.AddSeconds(-30) } | Select-Object -First 1
                if ($run) { $runId = $run.databaseId }
            }
            if (-not $runId) { throw 'build-base.yml run not found' }
            & gh run watch $runId -R $GhRepo --exit-status
            if ($LASTEXITCODE -ne 0) { throw "build-base.yml run $runId failed" }
            Write-Ok "run $runId succeeded"
            if (-not (Test-GhcrImage $OwnBase "arm-$Version")) {
                throw "$from cannot be pulled anonymously: make the package public (GitHub > Packages > arm-hass-addon > Package settings), then run this phase again"
            }
            Write-Ok "$from is public"
        }
    }

    $newConfig = Set-AddonVersion -ConfigText $config -Version $newVersion
    $newChangelog = Add-ChangelogEntry -ChangelogText $changelog -Version $newVersion -Date (Get-Date -Format 'yyyy-MM-dd') -Lines $lines

    Write-Step 'Planned changes'
    Write-Host "    FROM     : $(([regex]::Match($dockerfile, '(?m)^FROM [^\r\n]*')).Value)  ->  FROM $from"
    Write-Host "    labels   : add-on $($labels.Addon) -> $((Get-UpstreamLabels -DockerfileText $newDockerfile).Addon), ARM $($labels.Arm) -> $((Get-UpstreamLabels -DockerfileText $newDockerfile).Arm)"
    Write-Host "    version  : $currentVersion -> $newVersion"
    Write-Host "    CHANGELOG: $($lines -join ' ')"

    if ($PSCmdlet.ShouldProcess($branch, 'create branch, write arm/Dockerfile, arm/config.yaml, arm/CHANGELOG.md, commit')) {
        $null = Invoke-Git @('switch', '--quiet', '-c', $branch, $base)
        Write-RepoFile 'arm/Dockerfile' $newDockerfile
        Write-RepoFile 'arm/config.yaml' $newConfig
        Write-RepoFile 'arm/CHANGELOG.md' $newChangelog
        $null = Invoke-Git @('add', 'arm/Dockerfile', 'arm/config.yaml', 'arm/CHANGELOG.md')
        $subject = if ($Source -eq 'Addon') { "feat: rebase on mliradelc add-on $Version" } else { "feat: upgrade to ARM $Version" }
        $null = Invoke-Git @('commit', '--quiet', '-m', $subject)
        Write-Ok "committed on $branch (not pushed)"
        Write-Step 'Next'
        Write-Host '    1. Open the PR with the gestion-de-projet:pr skill (secret scan), wait for addon-image-check.'
        Write-Host '    2. Merge, then run: .\tools\Update-ArmAddon.ps1 -Phase Deploy -WhatIf, then without -WhatIf.'
    }
}

function Invoke-Ha {
    param([string]$Method, [string]$Path, $Body, [int]$TimeoutSec = 60)
    $headers = @{ Authorization = "Bearer $script:Token" }
    $params = @{ Method = $Method; Uri = "$HaUrl$Path"; Headers = $headers; TimeoutSec = $TimeoutSec; UseBasicParsing = $true }
    if ($null -ne $Body) { $params.Body = ($Body | ConvertTo-Json -Compress); $params.ContentType = 'application/json' }
    return Invoke-RestMethod @params
}

function Get-UpdateState { return Invoke-Ha -Method Get -Path "/api/states/$UpdateEntity" }
# The Supervisor returns the last 100 lines by default; ask for more journal entries with a Range
# header, which Invoke-WebRequest refuses on Windows PowerShell 5.1 (hence HttpClient).
function Get-AddonLog {
    Add-Type -AssemblyName System.Net.Http
    $client = New-Object System.Net.Http.HttpClient
    try {
        $client.Timeout = [TimeSpan]::FromSeconds(60)
        $request = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::Get, "$HaUrl/api/hassio/addons/$AddonSlug/logs")
        $null = $request.Headers.TryAddWithoutValidation('Authorization', "Bearer $script:Token")
        $null = $request.Headers.TryAddWithoutValidation('Range', 'entries=:-3000:')
        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        $null = $response.EnsureSuccessStatusCode()
        return [string]$response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    } finally { $client.Dispose() }
}
function Get-Joblist { return (Invoke-WebRequest -UseBasicParsing -Uri "$ArmUrl/json?mode=joblist" -TimeoutSec 30).Content }

function Wait-Until {
    param([scriptblock]$Condition, [int]$Minutes, [string]$What, [int]$EverySeconds = 15)
    $deadline = (Get-Date).AddMinutes($Minutes)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return $true }
        Write-Host "    ... waiting: $What" -ForegroundColor DarkGray
        Start-Sleep -Seconds $EverySeconds
    }
    return $false
}

function Assert-ArmIdle {
    if (Test-ArmIdle -JoblistJson (Get-Joblist)) { Write-Ok 'no active rip'; return }
    if ($WhatIfPreference) { Write-Warn2 'a rip is running: a real run would stop here (or wait with -WaitIdle)'; return }
    if (-not $WaitIdle) { throw "A rip is running ($ArmUrl): do not update now (use -WaitIdle to wait for it)" }
    if (-not (Wait-Until -Condition { Test-ArmIdle -JoblistJson (Get-Joblist) } -Minutes 120 -What 'rip in progress' -EverySeconds 60)) {
        throw 'Still ripping after 2 hours'
    }
    Write-Ok 'no active rip'
}

function Show-LogTail {
    $log = Get-AddonLog
    Write-Host '    --- last add-on log lines ---'
    ($log -split "`r?`n" | Select-Object -Last 30) | ForEach-Object {
        $line = $_
        if ($line.Length -gt 200) { $line = $line.Substring(0, 200) + ' [...]' }
        Write-Host "    $line"
    }
}

function Invoke-Deploy {
    Set-Location $RepoRoot
    Write-Step 'Target version'
    $null = Invoke-Git @('fetch', $Remote, '--quiet')
    $target = Get-AddonVersion -ConfigText (Invoke-Git @('show', "${BaseRef}:arm/config.yaml"))
    if ($TargetVersion) { $target = $TargetVersion }
    Write-Ok "target $target ($BaseRef)"

    $script:Token = Get-EnvValue -Path $EnvPath -Name 'AUZ_HA_TOKEN'
    try {
        $state = Get-UpdateState
        Write-Ok "installed $($state.attributes.installed_version), available $($state.attributes.latest_version)"
        if ($state.attributes.installed_version -eq $target) { Write-Ok 'already installed, nothing to do'; return }

        Write-Step 'Active rips'
        Assert-ArmIdle

        Write-Step 'Refreshing the update entity'
        if ($PSCmdlet.ShouldProcess($UpdateEntity, 'homeassistant.update_entity')) {
            $null = Invoke-Ha -Method Post -Path '/api/services/homeassistant/update_entity' -Body @{ entity_id = $UpdateEntity }
            $seen = Wait-Until -Condition { (Get-UpdateState).attributes.latest_version -eq $target } -Minutes 5 -What "latest_version = $target"
            if (-not $seen) {
                Write-Warn2 'Not seen yet: in Home Assistant, Settings > System > Updates > menu > "Check for updates".'
                $seen = Wait-Until -Condition { (Get-UpdateState).attributes.latest_version -eq $target } -Minutes 10 -What "latest_version = $target"
            }
            if (-not $seen) { throw "Home Assistant does not offer $target yet" }
            Write-Ok "$target offered"
        }

        Write-Step "Install $target without backup"
        if ($PSCmdlet.ShouldProcess($UpdateEntity, "update.install $target (backup: false)")) {
            $answer = Read-Host "    Type 'oui' to install $target now (the add-on restarts, no Home Assistant restart)"
            if ($answer -ne 'oui') { Write-Warn2 'Cancelled'; return }
            Assert-ArmIdle
            try {
                $null = Invoke-Ha -Method Post -Path '/api/services/update/install' -Body @{ entity_id = $UpdateEntity; backup = $false } -TimeoutSec 30
            } catch [System.Net.WebException] {
                if ($_.Exception.Status -ne [System.Net.WebExceptionStatus]::Timeout) { throw }
                Write-Host '    (install still running in Home Assistant)' -ForegroundColor DarkGray
            }
            if (-not (Wait-Until -Condition { (Get-UpdateState).attributes.installed_version -eq $target } -Minutes 30 -What "installed_version = $target" -EverySeconds 30)) {
                Show-LogTail
                throw "$target not installed after 30 min"
            }
            Write-Ok "$target installed"
        }

        Write-Step 'Disc watcher'
        if ($WhatIfPreference) {
            $line = Find-LogLine -LogText (Get-AddonLog) -Pattern $WatcherPattern
            if ($line) { Write-Ok "current log: $line" } else { Write-Warn2 'no watcher line in the current log (expected right after the update)' }
            Write-Warn2 'simulation: CD test skipped'
            return
        }
        if (Wait-Until -Condition { Find-LogLine -LogText (Get-AddonLog) -Pattern $WatcherPattern } -Minutes 5 -What 'watcher line in the add-on log') {
            Write-Ok (Find-LogLine -LogText (Get-AddonLog) -Pattern $WatcherPattern)
        } else {
            Show-LogTail
            throw 'Watcher line not found (option auto_rip off, or the add-on did not start)'
        }

        if ($SkipCdTest) { Write-Warn2 'CD test skipped'; return }
        Write-Step 'Test CD'
        $anchor = ((Get-AddonLog).TrimEnd() -split "`r?`n" | Select-Object -Last 1)
        $null = Read-Host '    Insert an audio CD, then press Enter (rip takes 10 to 17 min)'
        if (Wait-Until -Condition { Find-LogLine -LogText (Get-LogTextAfter -LogText (Get-AddonLog) -Anchor $anchor) -Pattern $MaSyncPattern } -Minutes 30 -What 'ma-sync line' -EverySeconds 30) {
            Write-Ok (Find-LogLine -LogText (Get-LogTextAfter -LogText (Get-AddonLog) -Anchor $anchor) -Pattern $MaSyncPattern)
            Write-Step "Done: $target installed and verified"
        } else {
            Show-LogTail
            throw 'No ma-sync line after 30 min'
        }
    } finally {
        $script:Token = $null
        Remove-Variable -Name Token -Scope Script -ErrorAction SilentlyContinue -WhatIf:$false
    }
}

if ($Phase -eq 'Prepare') { Invoke-Prepare } else { Invoke-Deploy }
