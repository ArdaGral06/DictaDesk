# DictaDesk - automated Windows setup
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1
# Optional: -SkipPlaywright   skip Chromium download (~150 MB)
#           -SkipPiper        skip Piper voice + binary download

param(
    [switch]$SkipPlaywright,
    [switch]$SkipPiper
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root
$TotalSteps = 7
$CurrentStep = 0

function Write-Step([string]$Message) {
    $script:CurrentStep++
    Write-Host ""
    Write-Host "==> Step $CurrentStep/$TotalSteps : $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "    OK: $Message" -ForegroundColor Green
}

function Write-Warn([string]$Message) {
    Write-Host "    WARN: $Message" -ForegroundColor Yellow
}

function Write-Fail([string]$Message) {
    Write-Host "    FAIL: $Message" -ForegroundColor Red
}

function Find-Python {
    $candidates = @("python", "py")
    foreach ($cmd in $candidates) {
        try {
            $versionText = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $versionText) {
                $parts = $versionText.Trim().Split(".")
                $major = [int]$parts[0]
                $minor = [int]$parts[1]
                if ($major -eq 3 -and $minor -ge 10) {
                    return @{ Command = $cmd; Major = $major; Minor = $minor }
                }
            }
        } catch {}
    }
    return $null
}

function Ensure-ConfigFiles {
    $secrets = Join-Path $Root "secrets.json"
    $secretsExample = Join-Path $Root "secrets.json.example"
    if (-not (Test-Path $secrets) -and (Test-Path $secretsExample)) {
        Copy-Item $secretsExample $secrets
        Write-Ok "Created secrets.json from template (add API keys when prompted at first run)"
    }

    $memory = Join-Path $Root "memory\long_term.json"
    $memoryExample = Join-Path $Root "memory\long_term.json.example"
    if (-not (Test-Path $memory) -and (Test-Path $memoryExample)) {
        New-Item -ItemType Directory -Force -Path (Split-Path $memory) | Out-Null
        Copy-Item $memoryExample $memory
        Write-Ok "Created memory\long_term.json"
    }
}

function Install-PiperAssets {
    $piperDir = Join-Path $Root "piper"
    $modelDir = Join-Path $Root "tts_models\piper"
    New-Item -ItemType Directory -Force -Path $piperDir, $modelDir | Out-Null

    $piperExe = Join-Path $piperDir "piper.exe"
    if (-not (Test-Path $piperExe)) {
        Write-Host "    Downloading Piper executable..."
        try {
            $release = Invoke-RestMethod -Uri "https://api.github.com/repos/rhasspy/piper/releases/latest" -UseBasicParsing
            $asset = $release.assets | Where-Object { $_.name -match "windows.*amd64.*\.zip$" } | Select-Object -First 1
            if (-not $asset) {
                throw "No Windows amd64 Piper release asset found."
            }
            $zipPath = Join-Path $env:TEMP "piper_windows.zip"
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -UseBasicParsing
            Expand-Archive -Path $zipPath -DestinationPath $piperDir -Force
            Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
            $found = Get-ChildItem -Path $piperDir -Filter "piper.exe" -Recurse | Select-Object -First 1
            if ($found -and $found.FullName -ne $piperExe) {
                Copy-Item $found.FullName $piperExe -Force
            }
            if (-not (Test-Path $piperExe)) {
                throw "piper.exe not found after extraction."
            }
            Write-Ok "Piper executable installed to piper\piper.exe"
        } catch {
            Write-Warn "Could not auto-download Piper: $_"
            Write-Warn "Download manually from https://github.com/rhasspy/piper/releases and place piper.exe in piper\"
        }
    } else {
        Write-Ok "Piper executable already present"
    }

    $onnx = Join-Path $modelDir "en_US-joe-medium.onnx"
    $json = Join-Path $modelDir "en_US-joe-medium.onnx.json"
    $baseUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/joe/medium"
    if (-not (Test-Path $onnx)) {
        Write-Host "    Downloading Piper voice model (en_US-joe-medium.onnx)..."
        try {
            Invoke-WebRequest -Uri "$baseUrl/en_US-joe-medium.onnx" -OutFile $onnx -UseBasicParsing
            Write-Ok "Voice model downloaded"
        } catch {
            Write-Warn "Could not download .onnx model: $_"
        }
    } else {
        Write-Ok "Piper .onnx model already present"
    }
    if (-not (Test-Path $json)) {
        Write-Host "    Downloading Piper voice config..."
        try {
            Invoke-WebRequest -Uri "$baseUrl/en_US-joe-medium.onnx.json" -OutFile $json -UseBasicParsing
            Write-Ok "Voice config downloaded"
        } catch {
            Write-Warn "Could not download .onnx.json: $_"
        }
    } else {
        Write-Ok "Piper .onnx.json already present"
    }
}

function Install-TesseractTurkish {
    $tesseract = $null
    try {
        $tesseract = (Get-Command tesseract -ErrorAction Stop).Source
    } catch {
        $default = "C:\Program Files\Tesseract-OCR\tesseract.exe"
        if (Test-Path $default) { $tesseract = $default }
    }
    if (-not $tesseract) {
        Write-Warn "Tesseract not found. Install from https://github.com/UB-Mannheim/tesseract/wiki for GUI text clicking."
        Write-Warn "After installing, re-run install.ps1 to fetch the Turkish language pack automatically."
        return
    }

    $tessDir = Split-Path $tesseract -Parent
    $tessData = Join-Path $tessDir "tessdata"
    $turFile = Join-Path $tessData "tur.traineddata"
    if (Test-Path $turFile) {
        Write-Ok "Turkish OCR language pack already installed"
        return
    }

    Write-Host "    Downloading Turkish OCR language pack (tur.traineddata)..."
    try {
        New-Item -ItemType Directory -Force -Path $tessData | Out-Null
        Invoke-WebRequest `
            -Uri "https://github.com/tesseract-ocr/tessdata/raw/main/tur.traineddata" `
            -OutFile $turFile `
            -UseBasicParsing
        Write-Ok "Turkish OCR pack installed to $turFile"
    } catch {
        Write-Warn "Could not download tur.traineddata: $_"
        Write-Warn "Download manually from https://github.com/tesseract-ocr/tessdata/raw/main/tur.traineddata"
    }
}

function Test-InstallReady {
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    $piperExe = Join-Path $Root "piper\piper.exe"
    $onnx = Join-Path $Root "tts_models\piper\en_US-joe-medium.onnx"
    $issues = @()

    if (-not (Test-Path $venvPython)) {
        $issues += "Python virtual environment (.venv) is missing"
    }
    if (-not (Test-Path $piperExe)) {
        $issues += "Piper executable missing (piper\piper.exe)"
    }
    if (-not (Test-Path $onnx)) {
        $issues += "Piper voice model missing (tts_models\piper\*.onnx)"
    }

    return @{
        Ready = ($issues.Count -eq 0)
        Issues = $issues
    }
}

Write-Host ""
Write-Host "DictaDesk Setup" -ForegroundColor White -BackgroundColor DarkBlue
Write-Host "Project folder: $Root"

Write-Step "Checking Python"
$py = Find-Python
if (-not $py) {
    Write-Fail "Python 3.10+ not found."
    Write-Host "Install Python 3.12 from https://www.python.org/downloads/ and check 'Add Python to PATH'." -ForegroundColor Yellow
    exit 1
}
Write-Ok "Found Python $($py.Major).$($py.Minor) via '$($py.Command)'"

Write-Step "Creating virtual environment (.venv)"
$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    & $py.Command -m venv (Join-Path $Root ".venv")
    Write-Ok "Virtual environment created"
} else {
    Write-Ok "Virtual environment already exists"
}

Write-Step "Installing Python packages"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $Root "requirements.txt")
Write-Ok "requirements.txt installed"

Write-Step "Creating config files"
Ensure-ConfigFiles

if (-not $SkipPlaywright) {
    Write-Step "Installing Playwright Chromium (web automation)"
    & $venvPython -m playwright install chromium
    Write-Ok "Playwright Chromium installed"
} else {
    Write-Warn "Skipped Playwright (use -SkipPlaywright only if you will not use web automation)"
}

if (-not $SkipPiper) {
    Write-Step "Installing Piper TTS (required to start DictaDesk)"
    Install-PiperAssets
} else {
    Write-Warn "Skipped Piper download - you must install piper.exe + voice model manually"
}

Write-Step "Checking Tesseract OCR + Turkish language pack"
Install-TesseractTurkish

Write-Step "Setup complete"
$check = Test-InstallReady
Write-Host ""
if ($check.Ready) {
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  All required parts are installed. You can run start.bat." -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} else {
    Write-Host "============================================================" -ForegroundColor Yellow
    Write-Host "  Setup finished with warnings - fix these before start.bat:" -ForegroundColor Yellow
    foreach ($issue in $check.Issues) {
        Write-Host "    - $issue" -ForegroundColor Yellow
    }
    Write-Host "============================================================" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "How to use DictaDesk:" -ForegroundColor Green
Write-Host "  1. Double-click start.bat (every time)"
Write-Host "  2. Read GETTING_STARTED.txt if this is your first time"
Write-Host ""
Write-Host "Recommended first-run choices:" -ForegroundColor Yellow
Write-Host "  STT: 1 (Whisper)  |  TTS: 1 (Off)  |  LLM: 3 (Groq API - free key at console.groq.com)"
Write-Host ""
Write-Host "Optional (not required to start):" -ForegroundColor DarkGray
Write-Host "  - Tesseract OCR for clicking text on screen (install from UB-Mannheim wiki, then re-run install.bat)"
Write-Host "  - Local LLM .gguf only if you pick Local Agent at startup"
Write-Host ""
Write-Host "Main menu -> option 3 (Self-check) verifies your setup." -ForegroundColor Cyan
Write-Host ""
