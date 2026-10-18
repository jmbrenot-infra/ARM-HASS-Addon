# Pure helpers for tools/Update-ArmAddon.ps1 (no network, no file writes).
# ASCII only, Windows PowerShell 5.1 compatible.

$script:LabelAddon = 'io.jmbrenot.upstream.addon'
$script:LabelArm = 'io.jmbrenot.upstream.arm'

function Get-LabelValue([string]$Text, [string]$Name) {
    $m = [regex]::Match($Text, [regex]::Escape($Name) + '="([^"]*)"')
    if (-not $m.Success) { return $null }
    return $m.Groups[1].Value
}

function Get-UpstreamLabels {
    param([Parameter(Mandatory = $true)][string]$DockerfileText)
    $addon = Get-LabelValue $DockerfileText $script:LabelAddon
    $arm = Get-LabelValue $DockerfileText $script:LabelArm
    if (-not $addon -or -not $arm) {
        throw "Labels $($script:LabelAddon) / $($script:LabelArm) not found in the Dockerfile"
    }
    return @{ Addon = $addon; Arm = $arm }
}

function Set-DockerfileBase {
    param(
        [Parameter(Mandatory = $true)][string]$DockerfileText,
        [Parameter(Mandatory = $true)][string]$FromImage,
        [string]$Addon,
        [string]$Arm
    )
    $null = Get-UpstreamLabels -DockerfileText $DockerfileText
    $re = New-Object regex '(?m)^FROM [^\r\n]*'
    $text = $re.Replace($DockerfileText, "FROM $FromImage", 1)
    if ($Addon) { $text = $text -replace ([regex]::Escape($script:LabelAddon) + '="[^"]*"'), "$($script:LabelAddon)=`"$Addon`"" }
    if ($Arm) { $text = $text -replace ([regex]::Escape($script:LabelArm) + '="[^"]*"'), "$($script:LabelArm)=`"$Arm`"" }
    return $text
}

function Get-AddonVersion {
    param([Parameter(Mandatory = $true)][string]$ConfigText)
    $m = [regex]::Match($ConfigText, '(?m)^version:\s*"?([^"\r\n]+)"?')
    if (-not $m.Success) { throw 'version not found in config.yaml' }
    return $m.Groups[1].Value.Trim()
}

function Get-NextAddonVersion {
    param(
        [Parameter(Mandatory = $true)][string]$Current,
        [string]$NewAddonBase
    )
    if ($NewAddonBase) { return "$NewAddonBase-jmb.1" }
    $m = [regex]::Match($Current, '^(.+)-jmb\.(\d+)$')
    if (-not $m.Success) { return "$Current-jmb.1" }
    return '{0}-jmb.{1}' -f $m.Groups[1].Value, ([int]$m.Groups[2].Value + 1)
}

function Set-AddonVersion {
    param(
        [Parameter(Mandatory = $true)][string]$ConfigText,
        [Parameter(Mandatory = $true)][string]$Version
    )
    $re = New-Object regex '(?m)^version:[^\r\n]*'
    return $re.Replace($ConfigText, "version: `"$Version`"", 1)
}

function Add-ChangelogEntry {
    param(
        [Parameter(Mandatory = $true)][string]$ChangelogText,
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string]$Date,
        [Parameter(Mandatory = $true)][string[]]$Lines
    )
    $entry = "## [$Version] - $Date`n`n" + (($Lines -join "`n")) + "`n`n"
    $index = $ChangelogText.IndexOf("`n## [")
    if ($index -lt 0) { return $ChangelogText.TrimEnd() + "`n`n" + $entry }
    return $ChangelogText.Substring(0, $index + 1) + $entry + $ChangelogText.Substring($index + 1)
}

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name
    )
    # Reads only the line of this key: the rest of the vault never enters memory or output.
    $match = Select-String -LiteralPath $Path -Pattern ('^' + [regex]::Escape($Name) + '=') | Select-Object -First 1
    if (-not $match) { throw "$Name not found in $Path" }
    $value = $match.Line.Substring($Name.Length + 1).Trim()
    return $value.Trim('"').Trim("'")
}

function Test-ArmIdle {
    param([Parameter(Mandatory = $true)][string]$JoblistJson)
    $data = $JoblistJson | ConvertFrom-Json
    $results = $data.results
    if ($null -eq $results) { return $true }
    if ($results -is [array]) { return ($results.Count -eq 0) }
    return (@($results.PSObject.Properties).Count -eq 0)
}

function Find-LogLine {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$LogText,
        [Parameter(Mandatory = $true)][string]$Pattern
    )
    foreach ($line in ($LogText -split "`r?`n")) {
        if ($line -match $Pattern) { return $line }
    }
    return $null
}

Export-ModuleMember -Function Get-UpstreamLabels, Set-DockerfileBase, Get-AddonVersion, Get-NextAddonVersion,
    Set-AddonVersion, Add-ChangelogEntry, Get-EnvValue, Test-ArmIdle, Find-LogLine
