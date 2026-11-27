# Loads MSVC env from vcvars64 and prepends optional portable tool folders. Dot-sourced by build/rebuild.
if (-not (Test-Path $env:SF_VCVARS)) { throw "SF_VCVARS not found: $env:SF_VCVARS" }
cmd /c "`"$env:SF_VCVARS`" >nul && set" | % { if($_ -match '^([^=]+)=(.*)$'){ Set-Item "env:$($matches[1])" $matches[2] } }
if ($env:SF_TOOL_PATHS) { $env:PATH = $env:SF_TOOL_PATHS + ';' + $env:PATH }
$env:PYTHONDONTWRITEBYTECODE = '1'
