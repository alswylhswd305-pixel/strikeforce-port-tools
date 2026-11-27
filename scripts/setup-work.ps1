# 1) Clone ps3recomp v0.20.0 (d81c393) into $SF_ROOT\ps3recomp, 2) copy the project template to $SF_ROOT\port,
# 3) add the Strikeforce overrides and apply the patches. Run from the repo root after loading env.local.ps1.
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent; $d = $env:SF_ROOT
New-Item -ItemType Directory -Force $d,"$d\logs","$d\out" | Out-Null
if (-not (Test-Path "$d\ps3recomp")) {
  git clone https://github.com/sp00nznet/ps3recomp "$d\ps3recomp"
  git -C "$d\ps3recomp" checkout d81c393
}
if (-not (Test-Path "$d\port")) { Copy-Item "$d\ps3recomp\templates\project" "$d\port" -Recurse }
Copy-Item "$repo\port\*.inc" "$d\port\" -Force
# patches 0001/0002 target templates/project/*; apply them inside the port copy
foreach ($p in '0001-template-stubs-register-strikeforce-overrides.diff','0002-template-main-start-sampler-diagnostic.diff') {
  git -C "$d\port" apply -p3 "$repo\patches\$p"
}
git -C "$d\ps3recomp" apply "$repo\patches\0003-runtime-syscall352-real-user-memory-size.diff"
# optional (Plan D stopgap, not needed for the title screen):
# git -C "$d\ps3recomp" apply "$repo\patches\optional-planD-spurs-ef-force-count.diff"
"setup done: $d"
