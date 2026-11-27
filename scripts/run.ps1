# Run the recompiled build with the settings that reached the title screen. Logs go to $SF_ROOT\runs\<tag>.
# For automated runs + screenshots + findings.json use tools\sfauto\sfauto.py instead.
param([int]$Secs = 90, [string]$Tag = (Get-Date -Format 'yyyyMMdd-HHmmss'))
$d = $env:SF_ROOT; $rd = "$d\runs\$Tag"
$env:PS3_VFS_ROOT      = "$d\vfs\dev_bdvd"        # KEY: /dev_bdvd/X -> <root>/X
$env:PS3_HDD0_ROOT     = "$d\state\hdd0"
$env:PS3_HDD1_ROOT     = "$d\state\hdd1"
$env:PS3_GAMEDATA_ROOT = "$d\state\gamedata"      # trophies persist -> no 'insufficient free space' dialog
$env:PS3_DEV_FLASH     = $env:SF_DEV_FLASH        # read only; supplies flashATRAC.pic
$env:SPU_INTERP_UNLIFTED = '1'                    # run dev_flash SPU code (ATRAC) in the SPU interpreter
New-Item -ItemType Directory -Force "$rd\cwd",$env:PS3_HDD0_ROOT,$env:PS3_HDD1_ROOT,$env:PS3_GAMEDATA_ROOT | Out-Null
$p = Start-Process "$d\port\bld\MyGameRecomp.exe" -ArgumentList "`"$env:SF_ELF`"" -WorkingDirectory "$rd\cwd" `
       -RedirectStandardOutput "$rd\stdout.log" -RedirectStandardError "$rd\stderr.log" -PassThru
while (((Get-Date) - $p.StartTime).TotalSeconds -lt $Secs -and -not $p.HasExited) { Start-Sleep 1 }
$alive = -not $p.HasExited; if ($alive) { Stop-Process -Id $p.Id -Force }
"alive=$alive  logs: $rd"
