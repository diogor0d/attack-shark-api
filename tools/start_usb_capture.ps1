param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]*$')]
    [string] $CaptureName,

    [Parameter(Mandatory)]
    [ValidateRange(1, 127)]
    [int] $DeviceAddress,

    [string] $FilterDevice = '\\.\USBPcap2'
)

$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'USBPcap capture requires an Administrator PowerShell session.'
}

$usbPcap = 'C:\Program Files\USBPcap\USBPcapCMD.exe'
if (-not (Test-Path -LiteralPath $usbPcap -PathType Leaf)) {
    throw "USBPcapCMD was not found at $usbPcap"
}

$captureDir = Join-Path $env:LOCALAPPDATA 'AttackSharkX68HE\captures'
$fileName = if ($CaptureName.EndsWith('.pcap')) { $CaptureName } else { "$CaptureName.pcap" }
$capturePath = Join-Path $captureDir $fileName
New-Item -ItemType Directory -Path $captureDir -Force | Out-Null
if (Test-Path -LiteralPath $capturePath) {
    throw "Capture already exists: $capturePath"
}

Write-Host "Capturing USB address $DeviceAddress on $FilterDevice"
Write-Host "Output: $capturePath"
Write-Host 'Press Ctrl+C after the controlled action finishes.'
$arguments = @(
    '-d', $FilterDevice,
    '--devices', $DeviceAddress.ToString(),
    '--inject-descriptors',
    '-o', ('"{0}"' -f $capturePath)
)

# Start-Process -Wait waits for the process tree on Windows. Direct invocation
# can return as soon as USBPcapCMD detaches its capture child, leaving a capture
# running after PowerShell has returned to the prompt.
$capture = Start-Process `
    -FilePath $usbPcap `
    -ArgumentList $arguments `
    -NoNewWindow `
    -PassThru `
    -Wait

if ($capture.ExitCode -ne 0) {
    $failed = Get-Item -LiteralPath $capturePath -ErrorAction SilentlyContinue
    if ($null -ne $failed -and $failed.Length -eq 0) {
        Remove-Item -LiteralPath $failed.FullName -Force
    }
    throw "USBPcapCMD failed with exit code $($capture.ExitCode)"
}
