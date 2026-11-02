param(
    [ValidateSet('settings','start','stop-capture','sequential','teleop','compare','lab')]
    [string]$Action = 'settings',
    [string]$Distribution = 'Ubuntu'
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
if ($root -match '^\\(?:wsl\.localhost|wsl\$)\\([^\\]+)(\\.*)$') {
    $Distribution = $Matches[1]
    $linuxRoot = $Matches[2].Replace('\','/')
} else {
    $linuxRoot = (& wsl.exe -d $Distribution -- wslpath -u $root).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve repository path in WSL.' }
}
$package = "$linuxRoot/ros2_ws/src/ino_camera_sim"
switch ($Action) {
    'lab' { & wsl.exe -d $Distribution -- "$linuxRoot/.venv/bin/python" "$linuxRoot/tools/module_test_lab/app.py" }
    'settings' { & wsl.exe -d $Distribution -- bash "$package/scripts/settings.sh" }
    'start' { & wsl.exe -d $Distribution -- bash "$package/scripts/start.sh" 'capture_mode:=continuous' }
    'stop-capture' { & wsl.exe -d $Distribution -- bash "$package/scripts/start.sh" 'capture_mode:=stop' }
    'sequential' { & wsl.exe -d $Distribution -- bash "$package/scripts/start.sh" 'capture_mode:=sequential' }
    'teleop' { & wsl.exe -d $Distribution -- bash "$package/scripts/teleop.sh" }
    'compare' { & wsl.exe -d $Distribution -- bash "$package/scripts/compare.sh" '--quick' }
}
exit $LASTEXITCODE
