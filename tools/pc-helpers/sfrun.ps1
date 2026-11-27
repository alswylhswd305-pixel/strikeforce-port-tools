param([string]$tag,[int]$secs=200,[string]$shots="110,150,190",[string[]]$extra=@(),[string]$state="state",[switch]$parallel,[int]$startAt=15,[switch]$keepsave,[string]$pad="")
$d='%SF_LOCAL_PATH%'; $st="$d\sfauto\$state"
# One game at a time unless -parallel (approved 14:28 for separate state dirs).
if (-not $parallel -and (Get-Process MyGameRecomp -EA SilentlyContinue)) { "GAME RUNNING - abort"; exit 1 }
$inc="$st\hdd1\cache\BLUS30471\_sf_session_incomplete"
if (Test-Path $inc) { Move-Item $inc "$inc.$(Get-Date -Format yyyyMMdd-HHmmss).old" }   # renamed, never deleted
$sv="$st\gamedata\dev_hdd0\home\00000001\savedata\BLUS30471-SAVEDATA"; if(-not $keepsave -and (Test-Path $sv)){Move-Item $sv "$st\savedata_BLUS30471_bak_$tag"}
$py='%SF_LOCAL_PATH%'
# Start on PRESS START (idle title, not a cutscene) at $startAt s; menu presses keep their old gaps.
$o=$startAt-90; $ps=(@(90,100,108,116,124,132) | % { "$($_+$o):" + $(if ($_ -eq 90) {"0x0008"} else {"0x4000"}) }) -join ","
$xs=$(if (($extra -join "") -match "\|") { $extra -join "|" -split "\|" } else { $extra -join "," -split "," }); $own=$xs | ? { $_ -like "PAD_SCRIPT=*" } | select -last 1; if ($own) { $ps=$own.Substring(11) }; if ($pad) { $ps=$pad }   # a caller PAD_SCRIPT replaces the default (and is what gets logged)
$roots=@(); if ($state -ne "state") { $roots=@("PS3_HDD0_ROOT=$st\hdd0","PS3_HDD1_ROOT=$st\hdd1","PS3_GAMEDATA_ROOT=$st\gamedata","SF_STATE=$state") }
$a=@(@("$d\sfauto\sfauto.py","run","--secs","$secs","--shots",$shots,"--env","SPU_INTERP_UNLIFTED=1","SPU_INTERP_MISS=1","PAD_SCRIPT=$ps","SF_PADMAP=$d\Strikeforce_buttons.ini")+$roots+($xs | ? { $_ -notlike "PAD_SCRIPT=*" })) | Where-Object { $_ -ne "" }
Start-Process $py -ArgumentList $a -WorkingDirectory "$d\sfauto" -RedirectStandardOutput "$d\sfauto\run_$tag.log" -RedirectStandardError "$d\sfauto\run_$tag.err" -WindowStyle Hidden
"started $tag $(Get-Date) state=$state pad=$ps"
