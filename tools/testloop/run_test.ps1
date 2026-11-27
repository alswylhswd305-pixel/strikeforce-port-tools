param([string]$Exe = "latest", [string]$Route = "village", [string]$Env = "", [switch]$AlongsideSaud)
# Thin wrapper: run_test.ps1 -Exe <build folder under sfauto\exe_copies> -Route <route> [-Env <file of KEY=VALUE>]
# Everything (wait, launch, PAD_FILE route, PrintWindow shots, close own pid, compare, marks, report, status) is in testloop.py.
$py = 'python'
if (-not (Test-Path $py)) { $py = 'py' }
$a = @("$PSScriptRoot\testloop.py", "all", "--build", $Exe, "--route", $Route)
if ($Env) { $a += @("--env", $Env) }
if ($AlongsideSaud) { $a += "--alongside-saud" }
$env:PYTHONIOENCODING = "utf-8"; $env:TESTLOOP_SHAPE = "0"
& $py @a
exit $LASTEXITCODE
