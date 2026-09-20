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
& $usbPcap `
    -d $FilterDevice `
    --devices $DeviceAddress `
    --inject-descriptors `
    -o $capturePath
