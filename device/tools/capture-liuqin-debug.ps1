<#
.SYNOPSIS
  Capture the liuqin kernel USB debug port (CDC ACM, VID_1209&PID_0002, LIQDBG001).
.DESCRIPTION
  Finds only this device: the vendor/product pair AND the synthetic serial number,
  so an unrelated serial adapter is never opened. Opens the port with DTR asserted
  (the kernel only transmits when DTR is set), writes a rolling capture of at most
  32 MiB per file, and can send one read-only command first.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools/capture-liuqin-debug.ps1 -Seconds 600 -Command replay
#>
param(
    [ValidateRange(1, 86400)][int]$Seconds = 600,
    [string]$Port,
    [string]$LogPath = (Join-Path $PSScriptRoot '..\out\liuqin-debug.log'),
    [ValidateSet('help', 'status', 'ping', 'replay')][string]$Command = 'status',
    [switch]$ListOnly
)
$ErrorActionPreference = 'Stop'
$VIDPID = 'VID_1209&PID_0002'
$SERIAL = 'LIQDBG001'
$ROTATE = 32MB

function Find-DebugPort {
    $id = Join-Path 'Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Enum\USB' $VIDPID
    if (-not (Test-Path -LiteralPath $id)) { return }
    foreach ($instance in Get-ChildItem -LiteralPath $id) {
        if ($instance.PSChildName -ne $SERIAL) { continue }
        $params = Join-Path $instance.PSPath 'Device Parameters'
        $found = (Get-ItemProperty -LiteralPath $params -Name PortName -ErrorAction SilentlyContinue).PortName
        if ($found -match '^COM[0-9]+$') { $found }
    }
}

if ($ListOnly) { Find-DebugPort; return }
if ($Port -and $Port -notmatch '^COM[0-9]+$') { throw 'Invalid COM port name' }

$deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
$serial = $null
$stream = $null
$total = 0L
try {
    while ([DateTime]::UtcNow -lt $deadline) {
        if (-not $Port) { $Port = @(Find-DebugPort | Sort-Object -Unique) | Select-Object -First 1 }
        if ($Port) { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $Port) { throw "$SERIAL ($VIDPID) did not enumerate as a COM port before timeout" }

    $serial = [System.IO.Ports.SerialPort]::new($Port, 115200, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
    $serial.DtrEnable = $true
    $serial.RtsEnable = $true
    $serial.ReadTimeout = 500
    $serial.WriteTimeout = 2000
    $serial.Open()

    $resolved = [System.IO.Path]::GetFullPath($LogPath)
    $null = [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($resolved))
    $stream = [System.IO.File]::Open($resolved, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
    Write-Output "Connected $Port; capture $resolved"

    # DTR was just asserted: give the kernel a moment, then log and query.
    Start-Sleep -Milliseconds 300
    $serial.Write($Command + "`n")

    $buffer = New-Object byte[] 4096
    while ([DateTime]::UtcNow -lt $deadline) {
        try { $n = $serial.Read($buffer, 0, $buffer.Length) } catch [TimeoutException] { continue }
        if ($n -le 0) { continue }
        $stream.Write($buffer, 0, $n)
        $stream.Flush()
        $total += $n
        if ($stream.Length -ge $ROTATE) {
            $stream.Dispose()
            $stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
            $resolved = [System.IO.Path]::GetFullPath("$LogPath.$stamp")
            $stream = [System.IO.File]::Open($resolved, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
            Write-Output "Rotated to $resolved"
        }
    }
} finally {
    if ($stream) { $stream.Dispose() }
    if ($serial -and $serial.IsOpen) { $serial.Close() }
    Write-Output "Captured $total bytes"
}
