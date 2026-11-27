# Shared movie/cutscene guard for the pad driver.
# Detects cellSail/cellPamf movies from [sf-movie] lines in the game stderr log.
# If the state is active OR unsure, callers must not write PAD_FILE.
# In-engine story cutscenes do not always emit [sf-movie]; treat those as unsure
# unless the sequence step is explicitly marked kind=gameplay or kind=menu.

function Get-SfLogTail {
    param([string]$LogFile, [ref]$Offset)
    $r = New-Object psobject -Property @{ Text = ""; Ok = $false }
    if (-not $LogFile -or -not (Test-Path -LiteralPath $LogFile)) { return $r }
    try {
        $fs = [IO.File]::Open($LogFile, 'Open', 'Read', 'ReadWrite')
        try {
            $len = $fs.Length
            $from = [int64]$Offset.Value
            if ($from -lt 0) { $from = 0 }
            if ($from -gt $len) { $from = $len }
            $fs.Seek($from, 'Begin') | Out-Null
            $sr = New-Object IO.StreamReader($fs)
            $r.Text = $sr.ReadToEnd()
            $sr.Close()
            $Offset.Value = $len
            $r.Ok = $true
        } finally { $fs.Dispose() }
    } catch { $r.Ok = $false }
    return $r
}

# Parse new log text and update a state hashtable:
#   Active (bool), Unsure (bool), Starts, Stops, LastEvent, LastTime, Reason
function Update-SfMovieState {
    param([hashtable]$State, [string]$Chunk, [bool]$LogOk)
    if (-not $State.ContainsKey('Starts')) { $State.Starts = 0 }
    if (-not $State.ContainsKey('Stops')) { $State.Stops = 0 }
    if (-not $State.ContainsKey('Active')) { $State.Active = $false }
    if (-not $State.ContainsKey('Unsure')) { $State.Unsure = $true }
    if (-not $State.ContainsKey('SeenMovieLog')) { $State.SeenMovieLog = $false }
    if (-not $State.ContainsKey('Reason')) { $State.Reason = 'no-log-yet' }

    if (-not $LogOk) {
        $State.Unsure = $true
        $State.Reason = 'log-unreadable'
        return $State
    }
    if ($Chunk) {
        foreach ($line in ($Chunk -split "`n")) {
            if ($line -match '\[sf-movie\]') { $State.SeenMovieLog = $true }
            if ($line -match '\[sf-movie\].*PlayerStart') {
                $State.Starts++
                $State.Active = $true
                $State.Unsure = $false
                $State.LastEvent = 'PlayerStart'
                $State.Reason = 'PlayerStart'
            } elseif ($line -match '\[sf-movie\].*PlayerStop' -or $line -match '\[sf-movie\].*PlayerFinalize') {
                $State.Stops++
                $State.Active = $false
                $State.Unsure = $false
                $State.LastEvent = if ($line -match 'PlayerFinalize') { 'PlayerFinalize' } else { 'PlayerStop' }
                $State.Reason = $State.LastEvent
            }
        }
    }
    if (-not $State.SeenMovieLog) {
        # Log is readable but no movie lines yet: could be before the first
        # movie, or SF_MOVIE_LOG is off. Do not press.
        $State.Unsure = $true
        if (-not $State.Reason) { $State.Reason = 'no-sf-movie-lines' }
    }
    return $State
}

function Test-SfPadBlocked {
    param([hashtable]$State)
    if ($State.Active) { return @{ Blocked = $true; Why = "movie-active:$($State.Reason)" } }
    if ($State.Unsure) { return @{ Blocked = $true; Why = "unsure:$($State.Reason)" } }
    return @{ Blocked = $false; Why = 'idle' }
}
