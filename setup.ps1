<#
  AI Voice Platform v2 - one-time setup
  ------------------------------------------------------------------
  Does everything except the two things only you can do: pasting your
  secrets, and starting the servers.

  Run it from the project root:

      cd "D:\Lemniscate Growth\ai-voice-platform-v2"
      .\setup.ps1

  If PowerShell refuses to run it, this unblocks it for this window only:

      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

  Safe to run more than once. It never overwrites an existing .env.
#>

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Say([string]$text)  { Write-Host "`n$text" -ForegroundColor Cyan }
function Ok([string]$text)   { Write-Host "  [ok]   $text" -ForegroundColor Green }
function Warn([string]$text) { Write-Host "  [warn] $text" -ForegroundColor Yellow }
function Die([string]$text)  { Write-Host "`n  [stop] $text`n" -ForegroundColor Red; exit 1 }

<#
  Why every external program below is called through this wrapper.

  With $ErrorActionPreference = 'Stop', PowerShell treats ANY line an external
  program writes to the error stream as a fatal error, even when the program
  is only logging progress and exits 0. Python libraries log to stderr as a
  matter of habit, so a perfectly successful step like

      INFO livekit.agents | Downloading files for livekit.plugins.openai

  killed this script mid-run. That is a PowerShell quirk, not a real failure.

  Invoke-Native drops back to 'Continue' for the duration of the call, so
  stderr is just text again, and returns the program's real exit code. Every
  caller checks that code instead. PowerShell's own cmdlets keep 'Stop', which
  is where stopping on error is actually wanted.
#>
function Invoke-Native {
  param(
    [Parameter(Mandatory)][scriptblock]$Command,
    [switch]$Quiet
  )
  $previous = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    if ($Quiet) {
      & $Command 2>&1 | Out-Null
    } else {
      & $Command 2>&1 | ForEach-Object { Write-Host "         $_" -ForegroundColor DarkGray }
    }
    return $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previous
  }
}

# ---------------------------------------------------------------------------
# 0. Prerequisites
# ---------------------------------------------------------------------------

Say "Checking what you have installed"

<#
  Windows has three possible names for the same Python, and which one works
  depends on how it was installed:

    python    the classic PATH entry. Absent if "Add Python to PATH" was not
              ticked during install. Worse, Windows ships a stub by this name
              that just opens the Microsoft Store, so it can appear to exist
              while doing nothing.
    py        the Python launcher. Installed by every python.org installer and
              works whether or not PATH was ticked. Usually the one that works.
    python3   what you get from the Microsoft Store build.

  So try all three and take the first that actually reports a version. The
  version-string match is what rules out the Store stub, which prints nothing
  useful.
#>
function Find-Python {
  foreach ($candidate in @('python', 'py', 'python3')) {
    try {
      $output = & $candidate --version 2>&1
      if ($LASTEXITCODE -eq 0 -and "$output" -match 'Python (\d+)\.(\d+)') {
        return [pscustomobject]@{
          Cmd     = $candidate
          Version = "$output".Trim()
          Major   = [int]$Matches[1]
          Minor   = [int]$Matches[2]
        }
      }
    } catch { }
  }
  return $null
}

$py = Find-Python

if (-not $py) {
  Write-Host "`n  [stop] Could not find a working Python.`n" -ForegroundColor Red
  Write-Host "         Tried three names: python, py, python3. None answered.`n" -ForegroundColor Red
  Write-Host "         Check for yourself, one of these may work:" -ForegroundColor Yellow
  Write-Host "           py --version"
  Write-Host "           where python"
  Write-Host "           where py`n"
  Write-Host "         If none of them work, install Python:" -ForegroundColor Yellow
  Write-Host "           1. Go to python.org/downloads"
  Write-Host "           2. Download the latest 3.12 or 3.13 for Windows"
  Write-Host "           3. On the FIRST installer screen, TICK"
  Write-Host "              'Add python.exe to PATH' at the bottom." -ForegroundColor White
  Write-Host "              That one checkbox is what this error is about."
  Write-Host "           4. Install, then CLOSE this window and open a new"
  Write-Host "              PowerShell. PATH changes only apply to new windows."
  Write-Host "           5. Run .\setup.ps1 again`n"
  exit 1
}

if ($py.Major -lt 3 -or ($py.Major -eq 3 -and $py.Minor -lt 10)) {
  Die "You have $($py.Version) (as '$($py.Cmd)'). This project needs Python 3.10 or newer."
}

Ok "$($py.Version), found as '$($py.Cmd)'"

try { $nodeVersion = (node --version 2>&1); Ok "Node $nodeVersion" } catch {
  Die "Node is not on your PATH. Install it from nodejs.org."
}

# ---------------------------------------------------------------------------
# 1. Backend
#
# Note we call the venv's python.exe directly rather than "activating" the
# venv. Same result, and it sidesteps PowerShell's execution policy entirely.
# ---------------------------------------------------------------------------

Say "Setting up the backend"

$backend   = Join-Path $root 'backend'
$backendPy = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path $backendPy)) {
  Push-Location $backend
  # $py.Cmd rather than a bare "python": on this machine the working command
  # might be "py" or "python3", and it was detected above.
  Invoke-Native { & $py.Cmd -m venv .venv } | Out-Null
  Pop-Location
  if (-not (Test-Path $backendPy)) {
    Die "Creating backend\.venv failed. Scroll up for the error from '$($py.Cmd) -m venv'."
  }
  Ok "created backend\.venv"
} else {
  Ok "backend\.venv already exists"
}

Push-Location $backend
Invoke-Native -Quiet { & $backendPy -m pip install --quiet --upgrade pip } | Out-Null
$code = Invoke-Native { & $backendPy -m pip install --quiet -r requirements.txt }
Pop-Location
if ($code -ne 0) { Die "Backend dependencies failed to install. Scroll up for the error." }
Ok "backend dependencies installed"

# ---------------------------------------------------------------------------
# 2. Agent
# ---------------------------------------------------------------------------

Say "Setting up the agent (this one is a bigger download, give it a few minutes)"

$agent   = Join-Path $root 'agent'
$agentPy = Join-Path $agent '.venv\Scripts\python.exe'

if (-not (Test-Path $agentPy)) {
  Push-Location $agent
  Invoke-Native { & $py.Cmd -m venv .venv } | Out-Null
  Pop-Location
  if (-not (Test-Path $agentPy)) {
    Die "Creating agent\.venv failed. Scroll up for the error from '$($py.Cmd) -m venv'."
  }
  Ok "created agent\.venv"
} else {
  Ok "agent\.venv already exists"
}

Push-Location $agent
Invoke-Native -Quiet { & $agentPy -m pip install --quiet --upgrade pip } | Out-Null
$code = Invoke-Native { & $agentPy -m pip install --quiet -r requirements.txt }
Pop-Location
if ($code -ne 0) { Die "Agent dependencies failed to install. Scroll up for the error." }
Ok "agent dependencies installed"

# ---------------------------------------------------------------------------
# 3. Frontend
# ---------------------------------------------------------------------------

Say "Setting up the frontend"

$frontend = Join-Path $root 'frontend'
Push-Location $frontend
$code = Invoke-Native { npm install --silent }
Pop-Location
if ($code -ne 0) { Die "npm install failed. Scroll up for the error." }
Ok "frontend dependencies installed"

# ---------------------------------------------------------------------------
# 4. Config files
#
# Created from the templates but never overwritten, so re-running this script
# can't wipe secrets you have already pasted in.
# ---------------------------------------------------------------------------

Say "Creating the .env files"

$pairs = @(
  @{ Dir = $backend;  Name = 'backend'  },
  @{ Dir = $agent;    Name = 'agent'    },
  @{ Dir = $frontend; Name = 'frontend' }
)

$created = @()

foreach ($pair in $pairs) {
  $target   = Join-Path $pair.Dir '.env'
  $template = Join-Path $pair.Dir '.env.example'

  if (Test-Path $target) {
    Ok "$($pair.Name)\.env already exists, left untouched"
  } elseif (Test-Path $template) {
    Copy-Item $template $target
    $created += $pair.Name
    Ok "created $($pair.Name)\.env from the template"
  } else {
    Warn "no .env.example found in $($pair.Name), skipped"
  }
}

# ---------------------------------------------------------------------------
# 5. Voice detection model
#
# Pulled now rather than mid-call. Without this the agent tries to download it
# on its first job, which is slow at best and fails on a read-only host.
# ---------------------------------------------------------------------------

Say "Downloading the voice detection model"

Push-Location $agent
$code = Invoke-Native { & $agentPy -m src.main download-files }
Pop-Location

if ($code -eq 0) {
  Ok "model files ready"
} else {
  Warn "the download did not finish. It needs SARVAM_API_KEY and the LiveKit keys in agent\.env first."
  Warn "Fill those in, then run:  cd agent; .\.venv\Scripts\python.exe -m src.main download-files"
}

# ---------------------------------------------------------------------------
# 6. What is left for you
# ---------------------------------------------------------------------------

Write-Host "`n"
Write-Host "==============================================================" -ForegroundColor White
Write-Host " Setup done. Two things left, and only you can do them." -ForegroundColor White
Write-Host "==============================================================" -ForegroundColor White

Say "1. Generate the shared secret (one value, used in TWO files)"

# Generated in PowerShell rather than by shelling out to Python, so this last
# and most important step cannot be lost to a subprocess quirk. Same shape as
# Python's secrets.token_urlsafe(32): 32 cryptographically random bytes, then
# URL-safe base64 with the padding stripped.
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$secret = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
Write-Host "`n     AGENT_API_KEY=$secret`n" -ForegroundColor Magenta
Write-Host "   Paste that same line into BOTH backend\.env and agent\.env."
Write-Host "   It must match character for character or the agent gets a 401."

Say "2. Fill in the rest. Nine values in total."

Write-Host @"

   backend\.env
   ------------
   SUPABASE_URL           Supabase: the Project ID from Settings > General,
                          wrapped as https://<id>.supabase.co
   SUPABASE_SECRET_KEY    Supabase: Settings > API Keys, the sb_secret_ one.
                          NOT the publishable key.
   LIVEKIT_URL            your existing wss://...livekit.cloud
   LIVEKIT_API_KEY        LiveKit Cloud: Settings > Keys
   LIVEKIT_API_SECRET     same page
   AGENT_API_KEY          the value printed above
   CALL_TRANSPORT         leave as browser

   agent\.env
   ----------
   LIVEKIT_URL            same three LiveKit values as the backend
   LIVEKIT_API_KEY
   LIVEKIT_API_SECRET
   BACKEND_BASE_URL       leave as http://localhost:8000/api
   AGENT_API_KEY          the value printed above, identical
   SARVAM_API_KEY         dashboard.sarvam.ai > API Keys

   frontend\.env
   -------------
   nothing to change for local work

   Leave every PLIVO_ variable and LIVEKIT_SIP_URI empty. They are for the
   phone path and the code skips it cleanly while they are blank.

"@

Say "3. Then run the SQL"
Write-Host "   Supabase > SQL Editor > New query, paste all of:"
Write-Host "     supabase\migrations\0001_init.sql" -ForegroundColor White
Write-Host "   Run it. You should then see three tables in the Table Editor."

Say "4. Then start everything"
Write-Host "     .\start.ps1" -ForegroundColor White
Write-Host "   That opens three windows: backend, agent, frontend.`n"

# Open the two files that need editing, whenever they are still unfilled.
# Keyed on whether the work is actually done rather than on whether this run
# created them, so a second run after a failed first run still opens them.
$needsFilling = -not (Select-String -Path (Join-Path $backend '.env') `
                        -Pattern '^\s*SUPABASE_URL\s*=\s*\S' -Quiet -ErrorAction SilentlyContinue)

if ($needsFilling) {
  Warn "Opening backend\.env and agent\.env so you can paste the values in."
  Start-Sleep -Seconds 2
  Start-Process notepad (Join-Path $backend '.env')
  Start-Process notepad (Join-Path $agent   '.env')
} else {
  Ok "backend\.env already has values, not reopening it"
}
