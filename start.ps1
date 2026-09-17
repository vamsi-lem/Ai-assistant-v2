<#
  AI Voice Platform v2 - start everything
  ------------------------------------------------------------------
  Opens three windows: backend, agent, frontend. Each one keeps running
  and prints its own log, so when something breaks you can see which
  part broke.

      cd "D:\Lemniscate Growth\ai-voice-platform-v2"
      .\start.ps1

  Stop everything by closing the three windows, or Ctrl+C in each.

  Run .\setup.ps1 first if you have not already.
#>

param(
  # .\start.ps1 -Phone  flips the backend to the phone path for a Plivo test.
  # Needs PLIVO_* and PUBLIC_BASE_URL filled in, and ngrok running.
  [switch]$Phone
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Say([string]$text)  { Write-Host "`n$text" -ForegroundColor Cyan }
function Ok([string]$text)   { Write-Host "  [ok]   $text" -ForegroundColor Green }
function Die([string]$text)  { Write-Host "`n  [stop] $text`n" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------------------
# Check setup has been run and the config is filled in
# ---------------------------------------------------------------------------

Say "Checking before starting"

$backendPy = Join-Path $root 'backend\.venv\Scripts\python.exe'
$agentPy   = Join-Path $root 'agent\.venv\Scripts\python.exe'

if (-not (Test-Path $backendPy)) { Die "backend\.venv is missing. Run .\setup.ps1 first." }
if (-not (Test-Path $agentPy))   { Die "agent\.venv is missing. Run .\setup.ps1 first." }
Ok "both virtual environments present"

$backendEnv = Join-Path $root 'backend\.env'
$agentEnv   = Join-Path $root 'agent\.env'

if (-not (Test-Path $backendEnv)) { Die "backend\.env is missing. Run .\setup.ps1 first." }
if (-not (Test-Path $agentEnv))   { Die "agent\.env is missing. Run .\setup.ps1 first." }

# Pull a value out of a .env file without needing python.
function Get-EnvValue([string]$file, [string]$key) {
  $line = Select-String -Path $file -Pattern "^\s*$key\s*=" -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $line) { return '' }
  return ($line.Line -replace "^\s*$key\s*=", '').Trim()
}

# Check the values that produce confusing failures when blank, rather than
# letting the servers start and fail in a way that looks like a code bug.
$checks = @(
  @{ File = $backendEnv; Key = 'SUPABASE_URL';        Where = 'backend\.env' },
  @{ File = $backendEnv; Key = 'SUPABASE_SECRET_KEY'; Where = 'backend\.env' },
  @{ File = $backendEnv; Key = 'LIVEKIT_API_KEY';     Where = 'backend\.env' },
  @{ File = $backendEnv; Key = 'AGENT_API_KEY';       Where = 'backend\.env' },
  @{ File = $agentEnv;   Key = 'SARVAM_API_KEY';      Where = 'agent\.env'   },
  @{ File = $agentEnv;   Key = 'AGENT_API_KEY';       Where = 'agent\.env'   }
)

$blank = @()
foreach ($check in $checks) {
  if ((Get-EnvValue $check.File $check.Key) -eq '') { $blank += "$($check.Where) -> $($check.Key)" }
}

# The brain has its own key, and which key depends on LLM_PROVIDER. Sarvam's
# LLM is a closed beta, so an account that works for speech still cannot use
# it. Catch that here instead of on a silent call.
$provider = (Get-EnvValue $agentEnv 'LLM_PROVIDER').ToLower()
if ($provider -eq '') { $provider = 'openai' }

switch ($provider) {
  'openai' { if ((Get-EnvValue $agentEnv 'OPENAI_API_KEY') -eq '') { $blank += "agent\.env -> OPENAI_API_KEY  (LLM_PROVIDER is openai)" } }
  'groq'   { if ((Get-EnvValue $agentEnv 'GROQ_API_KEY')   -eq '') { $blank += "agent\.env -> GROQ_API_KEY  (LLM_PROVIDER is groq)" } }
  'sarvam' { }
  default  { $blank += "agent\.env -> LLM_PROVIDER is '$provider', must be openai, groq or sarvam" }
}

if ($blank.Count -gt 0) {
  Write-Host "`n  [stop] These are still empty:`n" -ForegroundColor Red
  foreach ($item in $blank) { Write-Host "         $item" -ForegroundColor Red }
  Write-Host "`n         Fill them in, then run this again.`n" -ForegroundColor Red
  exit 1
}
Ok "required values are filled in"
Ok "brain: $provider"

if ($provider -eq 'sarvam') {
  Write-Host "  [note] LLM_PROVIDER=sarvam only works if Sarvam has granted your account" -ForegroundColor Yellow
  Write-Host "         beta access to their LLM. If Maya never speaks, that is why." -ForegroundColor Yellow
}

# The agent key must match exactly, or the agent joins the room and is then
# refused when it asks who it is calling. That failure looks like a code bug
# and is not one, so it is worth catching here.
$backendKey = Get-EnvValue $backendEnv 'AGENT_API_KEY'
$agentKey   = Get-EnvValue $agentEnv   'AGENT_API_KEY'

if ($backendKey -ne $agentKey) {
  Die "AGENT_API_KEY differs between backend\.env and agent\.env. They must be identical. Copy and paste, do not retype."
}
Ok "AGENT_API_KEY matches in both files"

# ---------------------------------------------------------------------------
# Phone mode checks
# ---------------------------------------------------------------------------

if ($Phone) {
  Say "Phone mode requested, checking the carrier settings"

  $phoneChecks = @('PLIVO_AUTH_ID', 'PLIVO_AUTH_TOKEN', 'PLIVO_FROM_NUMBER', 'PUBLIC_BASE_URL')
  $phoneBlank = @()
  foreach ($key in $phoneChecks) {
    if ((Get-EnvValue $backendEnv $key) -eq '') { $phoneBlank += $key }
  }

  if ($phoneBlank.Count -gt 0) {
    Write-Host "`n  [stop] Phone mode needs these in backend\.env:`n" -ForegroundColor Red
    foreach ($key in $phoneBlank) { Write-Host "         $key" -ForegroundColor Red }
    Write-Host "`n         PUBLIC_BASE_URL is your ngrok https URL. Plivo cannot use" -ForegroundColor Red
    Write-Host "         inline instructions the way Twilio can, so it has to fetch" -ForegroundColor Red
    Write-Host "         them from a public URL. Run: ngrok http 8000`n" -ForegroundColor Red
    exit 1
  }

  if ((Get-EnvValue $backendEnv 'LIVEKIT_SIP_URI') -eq '') {
    Write-Host "  [note] LIVEKIT_SIP_URI is empty, so the call will speak one test line" -ForegroundColor Yellow
    Write-Host "         and hang up rather than reaching the agent. That is the cheap" -ForegroundColor Yellow
    Write-Host "         way to prove your carrier setup. Costs about a rupee." -ForegroundColor Yellow
  } else {
    Ok "SIP URI set, calls will bridge into the LiveKit room"
  }

  Write-Host "`n  Set these two in backend\.env for phone mode:" -ForegroundColor Yellow
  Write-Host "    CALL_TRANSPORT=phone"
  Write-Host "    TELEPHONY_ENABLED=true`n"
}

# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

Say "Starting three windows"

# -NoExit keeps each window open after the process stops, so a crash leaves
# its error on screen instead of vanishing.
Start-Process powershell -ArgumentList @(
  '-NoExit', '-Command',
  "Set-Location '$root\backend'; Write-Host 'BACKEND' -ForegroundColor Cyan; " +
  "& '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --reload --port 8000"
)
Ok "backend  -> http://localhost:8000/api/health"

Start-Sleep -Seconds 4   # let the backend bind the port before the agent calls it

Start-Process powershell -ArgumentList @(
  '-NoExit', '-Command',
  "Set-Location '$root\agent'; Write-Host 'AGENT' -ForegroundColor Cyan; " +
  "& '.\.venv\Scripts\python.exe' -m src.main dev"
)
Ok "agent    -> watch for 'registered worker'"

Start-Process powershell -ArgumentList @(
  '-NoExit', '-Command',
  "Set-Location '$root\frontend'; Write-Host 'FRONTEND' -ForegroundColor Cyan; npm run dev"
)
Ok "frontend -> http://localhost:5173"

Write-Host "`n"
Write-Host "==============================================================" -ForegroundColor White
Write-Host " Check these three, in order" -ForegroundColor White
Write-Host "==============================================================" -ForegroundColor White
Write-Host @"

  1. http://localhost:8000/api/health
     wants  "database": "connected"
     if not, your Supabase URL or secret key is wrong

  2. the AGENT window
     wants  a line containing 'registered worker'
     if not, read the error, it names the problem

  3. http://localhost:5173
     wants  the footer to say  backend ok - db connected

  Then submit the form with your own details, tick the consent box, allow
  the microphone, and click 'Turn on sound' if it asks. Maya should greet
  you by name.

  Afterwards, in Supabase, open the conversations table and look at the
  messages column. You want BOTH 'assistant' and 'user' entries. That is
  the finish line.

"@
