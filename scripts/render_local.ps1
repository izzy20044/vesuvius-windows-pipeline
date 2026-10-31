# render_local.ps1 <mesh dir> <out.zarr> <volume url> [num_slices]
# Windows VC3D render that does not rely on the process exiting: waits for level 0 to reach 100% and its
# chunk count to stop growing, then stops the renderer and keeps level 0 only.
param([string]$mesh, [string]$out, [string]$vol, [int]$n = 66)
$root = if ($env:VESUVIUS_ROOT) { $env:VESUVIUS_ROOT } else { Join-Path $HOME 'vesuvius' }
$bin = if ($env:VC_RENDER) { $env:VC_RENDER } else {
    (Get-ChildItem -Recurse -Filter vc_render_tifxyz.exe (Join-Path $root 'tools') | Select-Object -First 1).FullName }
$log = "$out.log"
Remove-Item -Recurse -Force $out, $log -ErrorAction SilentlyContinue
$argv = @('--volume', $vol, '--group-idx', '0', '--scale', '1', '--segmentation', $mesh, '--num-slices', "$n",
          '--slice-step', '1', '--cache-gb', '4', '--log-path', $log, '--zarr-output', $out)
$t0 = Get-Date
$p = Start-Process -FilePath $bin -ArgumentList $argv -PassThru -WindowStyle Hidden
$prev = -1; $stable = 0
while ($true) {
    Start-Sleep 5
    $done = (Test-Path $log) -and (Select-String -Path $log -Pattern 'tile-row .*\(100%\)' -Quiet)
    $cnt = (Get-ChildItem -Recurse -File "$out\0" -ErrorAction SilentlyContinue | Measure-Object).Count
    if ($done -and $cnt -eq $prev) { $stable++ } else { $stable = 0 }
    $prev = $cnt
    if ($stable -ge 3 -or $p.HasExited) { break }
    if (((Get-Date) - $t0).TotalMinutes -gt 30) { "TIMEOUT"; break }
}
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
foreach ($l in 1..5) { Remove-Item -Recurse -Force "$out\$l" -ErrorAction SilentlyContinue }
"render done in {0:n0}s, level-0 chunks {1}" -f ((Get-Date) - $t0).TotalSeconds, $prev
Get-Content $log -Tail 2
Get-Content "$out\0\.zarray" -Raw
