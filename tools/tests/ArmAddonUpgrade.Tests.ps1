# Pester 3.4 tests for tools/ArmAddonUpgrade.psm1 (run: Invoke-Pester tools/tests)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $here '..\..')
Import-Module (Join-Path $here '..\ArmAddonUpgrade.psm1') -Force

$dockerfile = [IO.File]::ReadAllText((Join-Path $root 'arm\Dockerfile'))
$config = [IO.File]::ReadAllText((Join-Path $root 'arm\config.yaml'))
$changelog = [IO.File]::ReadAllText((Join-Path $root 'arm\CHANGELOG.md'))

Describe 'Get-UpstreamLabels' {
    It 'reads both labels from arm/Dockerfile' {
        $labels = Get-UpstreamLabels -DockerfileText $dockerfile
        $labels.Addon | Should Be '0.2.8'
        $labels.Arm | Should Be '2.20.5'
    }
    It 'throws when the labels are missing' {
        { Get-UpstreamLabels -DockerfileText "FROM x:1`n" } | Should Throw
    }
}

Describe 'Set-DockerfileBase' {
    It 'replaces FROM and the arm label only' {
        $new = Set-DockerfileBase -DockerfileText $dockerfile -FromImage 'ghcr.io/jmbrenot-infra/arm-hass-addon:arm-2.24.4' -Arm '2.24.4'
        $new | Should Match '(?m)^FROM ghcr\.io/jmbrenot-infra/arm-hass-addon:arm-2\.24\.4$'
        $new | Should Not Match 'mliradelc/arm-hass-addon:0\.2\.8'
        $labels = Get-UpstreamLabels -DockerfileText $new
        $labels.Arm | Should Be '2.24.4'
        $labels.Addon | Should Be '0.2.8'
        ($new -replace '(?m)^FROM .*$', '' -replace 'upstream\.arm="[^"]*"', '') | Should Be ($dockerfile -replace '(?m)^FROM .*$', '' -replace 'upstream\.arm="[^"]*"', '')
    }
}

Describe 'Test-OwnArmBase' {
    It 'is false on the mliradelc base' { Test-OwnArmBase -DockerfileText $dockerfile | Should Be $false }
    It 'is true on our own ARM base' {
        $own = Set-DockerfileBase -DockerfileText $dockerfile -FromImage 'ghcr.io/jmbrenot-infra/arm-hass-addon:arm-2.24.4' -Arm '2.24.4'
        Test-OwnArmBase -DockerfileText $own | Should Be $true
    }
}

Describe 'Add-on version' {
    It 'reads the version' {
        Get-AddonVersion -ConfigText $config | Should Be '0.2.8-jmb.4'
    }
    It 'increments jmb.N' {
        Get-NextAddonVersion -Current '0.2.8-jmb.4' | Should Be '0.2.8-jmb.5'
    }
    It 'restarts at jmb.1 on a new add-on base' {
        Get-NextAddonVersion -Current '0.2.8-jmb.4' -NewAddonBase '0.2.9' | Should Be '0.2.9-jmb.1'
    }
    It 'writes the version and nothing else' {
        $new = Set-AddonVersion -ConfigText $config -Version '0.2.8-jmb.5'
        $new | Should Match '(?m)^version: "0\.2\.8-jmb\.5"'
        ($new -replace '(?m)^version: .*$', '') | Should Be ($config -replace '(?m)^version: .*$', '')
    }
}

Describe 'Test-VersionGreater' {
    It 'is true for a newer version' { Test-VersionGreater -Version '2.24.4' -Than '2.20.5' | Should Be $true }
    It 'compares numerically' { Test-VersionGreater -Version '0.2.10' -Than '0.2.9' | Should Be $true }
    It 'is false for the same version' { Test-VersionGreater -Version '0.2.8' -Than '0.2.8' | Should Be $false }
    It 'is false for an older version' { Test-VersionGreater -Version '2.20.4' -Than '2.20.5' | Should Be $false }
}

Describe 'Add-ChangelogEntry' {
    It 'inserts the entry before the first release and keeps the header' {
        $new = Add-ChangelogEntry -ChangelogText $changelog -Version '0.2.8-jmb.5' -Date '2026-10-19' -Lines @('- **Changed**: test.')
        $new.StartsWith('# Changelog') | Should Be $true
        $new.IndexOf('## [0.2.8-jmb.5] - 2026-10-19') | Should BeLessThan $new.IndexOf('## [0.2.8-jmb.4]')
        $new | Should Match '(?m)^- \*\*Changed\*\*: test\.$'
        $new.Length | Should BeGreaterThan $changelog.Length
    }
}

Describe 'Get-EnvValue' {
    $envFile = Join-Path $TestDrive 'test.env'
    [IO.File]::WriteAllText($envFile, "A=1`nAUZ_HA_TOKEN=`"abc`"`r`nAUZ_HA_TOKEN_X=zz`n")
    It 'returns the cleaned value of the exact key' {
        Get-EnvValue -Path $envFile -Name 'AUZ_HA_TOKEN' | Should Be 'abc'
    }
    It 'throws without revealing values when the key is missing' {
        $message = ''
        try { Get-EnvValue -Path $envFile -Name 'MISSING' } catch { $message = $_.Exception.Message }
        $message | Should Match 'MISSING not found'
        $message | Should Not Match 'abc|zz'
    }
}

Describe 'Test-ArmIdle' {
    It 'is idle with an empty object' { Test-ArmIdle -JoblistJson '{"results":{}}' | Should Be $true }
    It 'is idle with an empty list' { Test-ArmIdle -JoblistJson '{"results":[]}' | Should Be $true }
    It 'throws without results (unknown state is not idle)' { { Test-ArmIdle -JoblistJson '{"success":false}' } | Should Throw }
    It 'is busy with a job list' { Test-ArmIdle -JoblistJson '{"results":[{"job_id":1}]}' | Should Be $false }
    It 'is busy with a job' { Test-ArmIdle -JoblistJson '{"results":{"0":{"job_id":1}}}' | Should Be $false }
}

Describe 'Get-LogTextAfter' {
    $old = "[t1] a`n[ARM] ma-sync: 1 sync task(s) started`n[t2] last`n"
    It 'keeps only what follows the last occurrence of the anchor' {
        $new = $old + "[t3] rip`n[ARM] ma-sync: 2 sync task(s) started`n"
        Get-LogTextAfter -LogText $new -Anchor '[t2] last' | Should Be "`n[t3] rip`n[ARM] ma-sync: 2 sync task(s) started`n"
    }
    It 'returns everything when the anchor scrolled out' {
        Get-LogTextAfter -LogText "[t9] x`n" -Anchor '[t2] last' | Should Be "[t9] x`n"
    }
    It 'returns everything with an empty anchor' {
        Get-LogTextAfter -LogText $old -Anchor '' | Should Be $old
    }
}

Describe 'Find-LogLine' {
    $log = "a`n[ARM] watcher: /dev/sr0 initial media=0`n[ARM] ma-sync: 1 sync task(s) started`n"
    It 'finds the first matching line' {
        Find-LogLine -LogText $log -Pattern '\[ARM\] ma-sync: \d+ sync task\(s\) started' | Should Be '[ARM] ma-sync: 1 sync task(s) started'
    }
    It 'returns null when absent' {
        Find-LogLine -LogText $log -Pattern 'nothing' | Should BeNullOrEmpty
    }
}
