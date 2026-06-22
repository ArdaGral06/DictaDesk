# DictaDesk - fully automated Windows setup
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1
#
# Everything is automatic. Detects/installs Python and Tesseract, adds them to
# PATH, detects the GPU (NVIDIA / AMD / none) and installs ONLY the matching
# local-LLM backend. No manual steps required.
#
# Optional overrides (advanced):
#   -SkipPlaywright   skip Chromium download (~150 MB)
#   -SkipPiper        skip Piper voice + binary download
#   -SkipLocalLlm     do not install the offline local LLM backend
#   -SkipTesseract    do not install Tesseract OCR
#   -ForceCpu         force CPU-only local LLM (ignore GPU)
#   -WithCuda         force NVIDIA CUDA backend
#   -WithVulkan       force AMD / cross-vendor Vulkan backend
#   -WithRocm         force AMD ROCm/HIP backend

param(
    [switch]$SkipPlaywright,
    [switch]$SkipPiper,
    [switch]$SkipLocalLlm,
    [switch]$SkipTesseract,
    [switch]$ForceCpu,
    [switch]$WithCuda,
    [switch]$WithVulkan,
    [switch]$WithRocm
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # faster Invoke-WebRequest downloads
$Root = $PSScriptRoot
Set-Location $Root
$TotalSteps = 11
$CurrentStep = 0

# Pinned fallback installer versions (used only if winget is unavailable).
$PythonVersion = "3.12.10"
$PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
$TesseractVersion = "5.5.0.20241111"
$TesseractUrl = "https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-$TesseractVersion.exe"
$LlamaWhlBase = "https://abetlen.github.io/llama-cpp-python/whl"

function Write-Step([string]$Message) {
    $script:CurrentStep++
    Write-Host ""
    Write-Host "==> Step $CurrentStep/$TotalSteps : $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message)   { Write-Host "    OK: $Message"   -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host "    WARN: $Message" -ForegroundColor Yellow }
function Write-Fail([string]$Message) { Write-Host "    FAIL: $Message" -ForegroundColor Red }
function Write-Info([string]$Message) { Write-Host "    $Message" }

function Test-IsWindows {
    return ($IsWindows -or ($env:OS -match "Windows"))
}

function Refresh-EnvPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = (@($machine, $user) | Where-Object { $_ }) -join ";"
}

function Add-ToUserPath([string]$dir) {
    if (-not $dir) { return }
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $userPath) { $userPath = "" }
    $existing = $userPath.Split(";") | Where-Object { $_ -ne "" }
    if ($existing -notcontains $dir) {
        $new = ($userPath.TrimEnd(";") + ";" + $dir).TrimStart(";")
        [Environment]::SetEnvironmentVariable("Path", $new, "User")
    }
    if (($env:Path.Split(";")) -notcontains $dir) {
        $env:Path = $env:Path.TrimEnd(";") + ";" + $dir
    }
}

function Test-PythonExe([string]$exe) {
    try {
        $v = & $exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) {
            $p = $v.Trim().Split(".")
            if ([int]$p[0] -eq 3 -and [int]$p[1] -ge 10) { return $true }
        }
    } catch {}
    return $false
}

function Find-PythonCommand {
    # 1) py launcher and python on PATH (py first avoids the Store alias).
    foreach ($cmd in @("py", "python")) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            if (Test-PythonExe $cmd) { return $cmd }
        }
    }
    # 2) Common per-user / machine install locations.
    $roots = @(
        "$env:LOCALAPPDATA\Programs\Python",
        "C:\Program Files\Python313",
        "C:\Program Files\Python312",
        "C:\Program Files\Python311",
        "C:\Program Files\Python310"
    )
    foreach ($r in $roots) {
        if (Test-Path $r) {
            $exe = Get-ChildItem -Path $r -Recurse -Filter "python.exe" -ErrorAction SilentlyContinue |
                   Sort-Object FullName -Descending | Select-Object -First 1
            if ($exe -and (Test-PythonExe $exe.FullName)) { return $exe.FullName }
        }
    }
    return $null
}

function Install-PythonAuto {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Info "Installing Python $PythonVersion via winget (per-user, adds to PATH)..."
        try {
            winget install --id Python.Python.3.12 -e --silent `
                --accept-package-agreements --accept-source-agreements `
                --override "/quiet PrependPath=1 Include_pip=1 Include_launcher=1" | Out-Null
        } catch { Write-Warn "winget Python install reported: $_" }
        Refresh-EnvPath
        if (Find-PythonCommand) { return $true }
    }
    Write-Info "Downloading the official Python $PythonVersion installer..."
    try {
        $exe = Join-Path $env:TEMP "dictadesk-python-$PythonVersion.exe"
        Invoke-WebRequest -Uri $PythonUrl -OutFile $exe -UseBasicParsing
        Write-Info "Installing Python (per-user, adds to PATH)..."
        Start-Process -FilePath $exe -Wait -ArgumentList @(
            "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_pip=1", "Include_launcher=1"
        )
        Remove-Item $exe -Force -ErrorAction SilentlyContinue
        Refresh-EnvPath
        return [bool](Find-PythonCommand)
    } catch {
        Write-Warn "Python auto-install failed: $_"
        return $false
    }
}

function Get-GpuBackend {
    $names = @()
    try {
        $names = Get-CimInstance Win32_VideoController -ErrorAction Stop |
                 Select-Object -ExpandProperty Name
    } catch {
        try { $names = (wmic path win32_VideoController get name) 2>$null } catch {}
    }
    $hasNvidia = $false
    $hasAmd = $false
    foreach ($n in $names) {
        if ($n -match "NVIDIA") { $hasNvidia = $true }
        if ($n -match "AMD|Radeon|ATI") { $hasAmd = $true }
    }
    if (-not $hasNvidia -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
        $hasNvidia = $true
    }
    if ($hasNvidia) { return @{ Backend = "cuda";   Gpu = ($names -join ", ") } }
    if ($hasAmd)    { return @{ Backend = "vulkan"; Gpu = ($names -join ", ") } }
    return @{ Backend = "cpu"; Gpu = ($names -join ", ") }
}

function Install-LocalLlm([string]$backend, [string]$venvPython) {
    $note = ""
    # --only-binary=:all: => never compile from source. A source build pulls the
    # huge llama.cpp tree whose nested paths exceed 260 chars and fails on any
    # Windows without Long Path support. If no prebuilt wheel exists we skip
    # cleanly instead of crashing - the local LLM is optional.
    $pipArgs = @("-m", "pip", "install", "llama-cpp-python", "--only-binary=:all:", "--prefer-binary")
    switch ($backend) {
        "cuda"   { $pipArgs += @("--extra-index-url", "$LlamaWhlBase/cu124"); $note = "NVIDIA CUDA" }
        "vulkan" { $pipArgs += @("--extra-index-url", "$LlamaWhlBase/vulkan"); $note = "AMD / Vulkan" }
        "rocm"   {
            if (Test-IsWindows) { $pipArgs += @("--extra-index-url", "$LlamaWhlBase/hip-radeon"); $note = "AMD HIP (Windows)" }
            else                { $pipArgs += @("--extra-index-url", "$LlamaWhlBase/rocm72");     $note = "AMD ROCm (Linux)" }
        }
        default  { $pipArgs += @("--extra-index-url", "$LlamaWhlBase/cpu"); $note = "CPU" }
    }
    Write-Info "Installing local LLM backend: $note (prebuilt wheel only)..."
    & $venvPython @pipArgs
    if ($LASTEXITCODE -ne 0 -and $backend -ne "cpu") {
        Write-Warn "$note wheel unavailable - trying the prebuilt CPU wheel instead."
        & $venvPython -m pip install llama-cpp-python --only-binary=:all: --prefer-binary --extra-index-url "$LlamaWhlBase/cpu"
        $note = "CPU (GPU wheel unavailable)"
    }
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "llama-cpp-python installed ($note). LOCAL_AI_DEVICE='auto' picks the GPU at runtime."
    } else {
        Write-Warn "No prebuilt local-LLM wheel for this Python/OS - skipped (optional)."
        Write-Info "The cloud agent (Groq etc.) works fully without it. To add it later, install"
        Write-Info "a llama-cpp-python wheel manually, or enable Windows Long Paths and build from source."
    }
}

function Set-ConfigTesseractCmd([string]$exePath) {
    $cfg = Join-Path $Root "config.py"
    if (-not (Test-Path $cfg)) { return }
    try {
        $content = Get-Content -Path $cfg -Raw
        $escaped = $exePath.Replace("\", "\\")
        $new = $content -replace 'TESSERACT_CMD\s*=\s*"[^"]*"', ('TESSERACT_CMD = "{0}"' -f $escaped)
        if ($new -ne $content) {
            Set-Content -Path $cfg -Value $new -Encoding UTF8 -NoNewline
            Write-Ok "config.py TESSERACT_CMD set to the detected install path"
        }
    } catch {
        Write-Warn "Could not update TESSERACT_CMD in config.py: $_"
    }
}

function Find-TesseractExe {
    $cmd = Get-Command tesseract -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "C:\Program Files\Tesseract-OCR\tesseract.exe",
        "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        "$env:LOCALAPPDATA\Programs\Tesseract-OCR\tesseract.exe",
        "$env:LOCALAPPDATA\Tesseract-OCR\tesseract.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return $null
}

function Install-TesseractAuto {
    $exe = Find-TesseractExe
    if ($exe) { return $exe }

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Info "Installing Tesseract OCR via winget..."
        try {
            winget install --id UB-Mannheim.TesseractOCR -e --silent `
                --accept-package-agreements --accept-source-agreements | Out-Null
        } catch { Write-Warn "winget Tesseract install reported: $_" }
        Refresh-EnvPath
        $exe = Find-TesseractExe
        if ($exe) { return $exe }
    }

    Write-Info "Downloading the UB Mannheim Tesseract installer ($TesseractVersion)..."
    try {
        $setup = Join-Path $env:TEMP "dictadesk-tesseract-setup.exe"
        Invoke-WebRequest -Uri $TesseractUrl -OutFile $setup -UseBasicParsing
        Write-Info "Installing Tesseract silently (a security prompt may appear once)..."
        Start-Process -FilePath $setup -Wait -ArgumentList "/S"
        Remove-Item $setup -Force -ErrorAction SilentlyContinue
        Refresh-EnvPath
        $exe = Find-TesseractExe
    } catch {
        Write-Warn "Tesseract auto-install failed: $_"
    }
    return $exe
}

function Install-TurkishOcrPack([string]$tesseractExe) {
    if (-not $tesseractExe) { return }
    $tessDir = Split-Path $tesseractExe -Parent
    $tessData = Join-Path $tessDir "tessdata"
    $turFile = Join-Path $tessData "tur.traineddata"
    if (Test-Path $turFile) { Write-Ok "Turkish OCR language pack already installed"; return }
    Write-Info "Downloading Turkish OCR language pack (tur.traineddata)..."
    try {
        New-Item -ItemType Directory -Force -Path $tessData | Out-Null
        Invoke-WebRequest `
            -Uri "https://github.com/tesseract-ocr/tessdata/raw/main/tur.traineddata" `
            -OutFile $turFile -UseBasicParsing
        Write-Ok "Turkish OCR pack installed"
    } catch {
        Write-Warn "Could not download tur.traineddata: $_"
    }
}

function Ensure-ConfigFiles {
    $secrets = Join-Path $Root "secrets.json"
    $secretsExample = Join-Path $Root "secrets.json.example"
    if (-not (Test-Path $secrets) -and (Test-Path $secretsExample)) {
        Copy-Item $secretsExample $secrets
        Write-Ok "Created secrets.json from template"
    }
    $memory = Join-Path $Root "memory\long_term.json"
    $memoryExample = Join-Path $Root "memory\long_term.json.example"
    if (-not (Test-Path $memory) -and (Test-Path $memoryExample)) {
        New-Item -ItemType Directory -Force -Path (Split-Path $memory) | Out-Null
        Copy-Item $memoryExample $memory
        Write-Ok "Created memory\long_term.json"
    }
    $budget = Join-Path $Root "api_budget.json"
    $budgetExample = Join-Path $Root "api_budget.json.example"
    if (-not (Test-Path $budget) -and (Test-Path $budgetExample)) {
        Copy-Item $budgetExample $budget
        Write-Ok "Created api_budget.json (budget protector defaults to off)"
    }
}

function Install-PiperAssets {
    $piperDir = Join-Path $Root "piper"
    $modelDir = Join-Path $Root "tts_models\piper"
    New-Item -ItemType Directory -Force -Path $piperDir, $modelDir | Out-Null

    $piperExe = Join-Path $piperDir "piper.exe"
    if (-not (Test-Path $piperExe)) {
        Write-Info "Downloading Piper executable..."
        try {
            $release = Invoke-RestMethod -Uri "https://api.github.com/repos/rhasspy/piper/releases/latest" -UseBasicParsing
            $asset = $release.assets | Where-Object { $_.name -match "windows.*amd64.*\.zip$" } | Select-Object -First 1
            if (-not $asset) { throw "No Windows amd64 Piper release asset found." }
            $zipPath = Join-Path $env:TEMP "piper_windows.zip"
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -UseBasicParsing
            Expand-Archive -Path $zipPath -DestinationPath $piperDir -Force
            Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
            $found = Get-ChildItem -Path $piperDir -Filter "piper.exe" -Recurse | Select-Object -First 1
            if ($found -and $found.FullName -ne $piperExe) { Copy-Item $found.FullName $piperExe -Force }
            if (-not (Test-Path $piperExe)) { throw "piper.exe not found after extraction." }
            Write-Ok "Piper executable installed"
        } catch {
            Write-Warn "Could not auto-download Piper: $_"
        }
    } else {
        Write-Ok "Piper executable already present"
    }

    $onnx = Join-Path $modelDir "en_US-joe-medium.onnx"
    $json = Join-Path $modelDir "en_US-joe-medium.onnx.json"
    $baseUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/joe/medium"
    if (-not (Test-Path $onnx)) {
        Write-Info "Downloading Piper voice model..."
        try { Invoke-WebRequest -Uri "$baseUrl/en_US-joe-medium.onnx" -OutFile $onnx -UseBasicParsing; Write-Ok "Voice model downloaded" }
        catch { Write-Warn "Could not download .onnx model: $_" }
    } else { Write-Ok "Piper .onnx model already present" }
    if (-not (Test-Path $json)) {
        Write-Info "Downloading Piper voice config..."
        try { Invoke-WebRequest -Uri "$baseUrl/en_US-joe-medium.onnx.json" -OutFile $json -UseBasicParsing; Write-Ok "Voice config downloaded" }
        catch { Write-Warn "Could not download .onnx.json: $_" }
    } else { Write-Ok "Piper .onnx.json already present" }
}

function Test-InstallReady([string]$tesseractExe) {
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    $piperExe = Join-Path $Root "piper\piper.exe"
    $onnx = Join-Path $Root "tts_models\piper\en_US-joe-medium.onnx"
    $issues = @()
    if (-not (Test-Path $venvPython)) { $issues += "Python virtual environment (.venv) is missing" }
    if (-not (Test-Path $piperExe))   { $issues += "Piper executable missing (piper\piper.exe)" }
    if (-not (Test-Path $onnx))       { $issues += "Piper voice model missing (tts_models\piper\*.onnx)" }
    if (Test-Path $venvPython) {
        & $venvPython -c "import keyring" 2>$null
        if ($LASTEXITCODE -ne 0) { $issues += "keyring package missing (required for API key storage)" }
    }
    if (-not $tesseractExe) { $issues += "Tesseract OCR not installed (on-screen text clicks limited)" }
    return @{ Ready = ($issues.Count -eq 0); Issues = $issues }
}

# --------------------------------------------------------------------------
Write-Host ""
Write-Host "DictaDesk Setup (fully automatic)" -ForegroundColor White -BackgroundColor DarkBlue
Write-Host "Project folder: $Root"

Write-Step "Checking / installing Python"
$pythonCmd = Find-PythonCommand
if (-not $pythonCmd) {
    Write-Info "Python 3.10+ not found - installing automatically..."
    if (Install-PythonAuto) { $pythonCmd = Find-PythonCommand }
}
if (-not $pythonCmd) {
    Write-Fail "Could not install Python automatically."
    Write-Host "Install Python 3.12 from https://www.python.org/downloads/ (check 'Add python.exe to PATH'), then re-run install.bat." -ForegroundColor Yellow
    exit 1
}
Write-Ok "Python ready: $pythonCmd"

Write-Step "Creating virtual environment (.venv)"
$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    & $pythonCmd -m venv (Join-Path $Root ".venv")
    if (-not (Test-Path $venvPython)) { Write-Fail "Failed to create .venv"; exit 1 }
    Write-Ok "Virtual environment created"
} else {
    Write-Ok "Virtual environment already exists"
}

Write-Step "Installing Python packages"
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit 1 }
& $venvPython -m pip install -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Fail "pip install failed. Check your internet connection and Python version."
    exit 1
}
Write-Ok "requirements.txt installed (includes keyring for secure API key storage)"

Write-Step "Detecting GPU and installing local AI backend"
$gpu = Get-GpuBackend
if ($gpu.Gpu) { Write-Info "Detected graphics: $($gpu.Gpu)" }
if ($ForceCpu)      { $backend = "cpu" }
elseif ($WithCuda)  { $backend = "cuda" }
elseif ($WithVulkan){ $backend = "vulkan" }
elseif ($WithRocm)  { $backend = "rocm" }
else                { $backend = $gpu.Backend }
if ($SkipLocalLlm) {
    Write-Warn "Skipped local LLM backend (-SkipLocalLlm). Cloud agent (Groq etc.) still works."
} else {
    Write-Info "Selected local AI backend: $backend"
    Install-LocalLlm -backend $backend -venvPython $venvPython
}

Write-Step "Verifying keyring (required for API keys)"
& $venvPython -c "import keyring; print('keyring ok')"
if ($LASTEXITCODE -ne 0) {
    Write-Fail "keyring package failed to import. Re-run install.bat."
    exit 1
}
Write-Ok "keyring is ready (API keys stored in Windows Credential Manager when possible)"

Write-Step "Creating config files"
Ensure-ConfigFiles

Write-Step "Creating runtime data folders"
& $venvPython -c "from runtime_dirs import ensure_runtime_dirs; ensure_runtime_dirs()"
Write-Ok "Runtime folders ready"

if (-not $SkipPlaywright) {
    Write-Step "Installing Playwright Chromium (web automation)"
    & $venvPython -m playwright install chromium
    Write-Ok "Playwright Chromium installed"
} else {
    Write-Step "Playwright (skipped)"
    Write-Warn "Skipped Playwright (web automation will be unavailable)"
}

if (-not $SkipPiper) {
    Write-Step "Installing Piper TTS"
    Install-PiperAssets
} else {
    Write-Step "Piper TTS (skipped)"
    Write-Warn "Skipped Piper download"
}

Write-Step "Installing Tesseract OCR + Turkish language pack"
$tesseractExe = $null
if ($SkipTesseract) {
    Write-Warn "Skipped Tesseract (-SkipTesseract). On-screen text clicking will be limited."
} else {
    $tesseractExe = Install-TesseractAuto
    if ($tesseractExe) {
        Write-Ok "Tesseract ready: $tesseractExe"
        Add-ToUserPath (Split-Path $tesseractExe -Parent)
        Set-ConfigTesseractCmd $tesseractExe
        Install-TurkishOcrPack $tesseractExe
    } else {
        Write-Warn "Tesseract could not be installed automatically. Install from https://github.com/UB-Mannheim/tesseract/wiki and re-run."
    }
}

Write-Step "Setup complete"
$check = Test-InstallReady $tesseractExe
Write-Host ""
if ($check.Ready) {
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  All set. Double-click start.bat to launch DictaDesk." -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} else {
    Write-Host "============================================================" -ForegroundColor Yellow
    Write-Host "  Setup finished with warnings:" -ForegroundColor Yellow
    foreach ($issue in $check.Issues) { Write-Host "    - $issue" -ForegroundColor Yellow }
    Write-Host "============================================================" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Local AI device: auto (GPU backend installed: $backend)" -ForegroundColor Cyan
Write-Host "How to use DictaDesk:" -ForegroundColor Green
Write-Host "  1. Double-click start.bat (every time)"
Write-Host "  2. First run: pick UI language, then STT/LLM (Groq API key is free at console.groq.com)"
Write-Host ""
Write-Host "Recommended first-run choices:" -ForegroundColor Yellow
Write-Host "  STT: 1 (Whisper)  |  TTS: 1 (Off)  |  LLM: 3 (Groq API)"
Write-Host ""
Write-Host "Main menu -> option 3 (Self-check) verifies your setup (incl. GPU)." -ForegroundColor Cyan
Write-Host ""
