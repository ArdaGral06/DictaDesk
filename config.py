from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
HOME_DIR = Path.home()
MEMORY_DIR = BASE_DIR / "memory"
MEMORY_FILE = MEMORY_DIR / "long_term.json"
TEST_SOUNDS_DIR = BASE_DIR / "test_sounds"
RECORDINGS_DIR = BASE_DIR / "recordings"
TRANSCRIPTS_DIR = BASE_DIR / "transcripts"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
COMMANDS_JSON = BASE_DIR / "commands.json"
PROVIDERS_JSON = BASE_DIR / "providers.json"
LAST_TRANSCRIPT_FILE = BASE_DIR / "last_transcript.txt"
SECRETS_JSON = BASE_DIR / "secrets.json"
API_BUDGET_JSON = BASE_DIR / "api_budget.json"
LLM_PROVIDERS_JSON = BASE_DIR / "llm_providers.json"
VLM_PROVIDERS_JSON = BASE_DIR / "vlm_providers.json"
LLM_MODELS_DIR = BASE_DIR / "llm_models"
ACTION_MANIFEST_JSON = BASE_DIR / "actions_manifest.json"
DEBUG_REPLAY_DIR = BASE_DIR / "debug_replays"
TTS_PROVIDERS_JSON = BASE_DIR / "tts_providers.json"
TTS_OUTPUT_DIR = BASE_DIR / "tts_outputs"
TTS_MODELS_DIR = BASE_DIR / "tts_models"
PIPER_MODELS_DIR = TTS_MODELS_DIR / "piper"

SUPPORTED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".flac",
    ".ogg",
    ".aac",
    ".opus",
    ".wma",
    ".aiff",
    ".aif",
}

# UI / Language
DEFAULT_UI_LANG = "tr"
USE_POPUP_STATUS = True
POPUP_DURATION_MS = 4000
AGENT_STEP_POPUP_MS = 5000
AGENT_STEP_PAUSE_SEC = 1.0
AGENT_CODING_STEP_PAUSE_SEC = 1.5
MAX_AGENT_STEPS = 12
MAX_CODING_AGENT_STEPS = 8
PREFER_START_MENU_SHORTCUT = True

# Local model (faster-whisper)
LOCAL_MODEL_SIZE = "small"
LOCAL_DEVICE = "cpu"
LOCAL_COMPUTE_TYPE = "int8"
LOCAL_CPU_THREADS = 4
DEFAULT_SAMPLE_RATE = 16000

# Local model (Vosk)
VOSK_MODELS_DIR = BASE_DIR / "vosk_models"
VOSK_MODEL_TR_NAME = "vosk-model-small-tr-0.3"
VOSK_MODEL_EN_NAME = "vosk-model-small-en-us-0.15"
VOSK_MODEL_TR_DIR = VOSK_MODELS_DIR / "tr"
VOSK_MODEL_EN_DIR = VOSK_MODELS_DIR / "en"

# Local TTS (Piper)
PIPER_BIN = ""  # Optional: full path to piper executable
PIPER_MODEL_PATH = ""  # Optional: full path to .onnx model (auto-detects in tts_models/piper)
PIPER_SPEAKER = ""  # Optional: speaker id (if multi-speaker)

# Local LLM (Phi-3.5-mini GGUF via llama-cpp-python)
LLM_LOCAL_MODEL_PATH = ""  # Optional: full path to .gguf model
LLM_LOCAL_CTX = 8192
LLM_LOCAL_THREADS = 4
LLM_LOCAL_TEMPERATURE = 0.25
LLM_LOCAL_MAX_TOKENS = 4096
LLM_CODING_MAX_TOKENS = 8192
LLM_ROUTER_MAX_TOKENS = 768
CODE_PROJECTS_DIR = HOME_DIR / "Desktop" / "DictaDeskProjects"

# API (multi-provider)
DEFAULT_API_MODEL = "whisper-large-v3-turbo"
DEFAULT_LLM_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
DEFAULT_VLM_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
LLM_API_CONTEXT_MAX_CHARS = 1800
LLM_API_MEMORY_MAX_CHARS = 400
API_TIMEOUT_SEC = 60

# API budget protector (user-configurable; default off)
API_BUDGET_DEFAULT_ENABLED = False
API_BUDGET_DEFAULT_SESSION_LIMIT = 80
API_BUDGET_DEFAULT_HOURLY_LIMIT = 120

# Voice activity detection (noise gate)
VAD_ENABLED = True
# Fallback STT language when UI language is not tr/en (single pass, no dual transcribe)
DEFAULT_STT_LANGUAGE = "tr"
# RMS threshold for speech detection (0.0 - 1.0). Increase if false positives.
VAD_RMS_THRESHOLD = 0.01
# Minimum number of "active" chunks to accept recording
VAD_MIN_ACTIVE_FRAMES = 3

# OCR (Tesseract)
TESSERACT_CMD = ""  # Optional: full path to tesseract executable
OCR_LANG_TR = "tur"
OCR_LANG_EN = "eng"
OCR_LANG_BOTH = "eng+tur"

# Automation toggles (default)
GUI_AUTOMATION_DEFAULT = True
WEB_AUTOMATION_DEFAULT = True

# UIA tree walk limits (lower = faster on heavy apps like Chrome/VS Code)
UIA_WALK_MAX_DEPTH = 3
UIA_WALK_MAX_ITEMS = 180
UIA_FIND_MAX_DEPTH = 4
UIA_FIND_MAX_ITEMS = 350
UIA_FORM_MAX_DEPTH = 5
UIA_FORM_MAX_ITEMS = 280

# Web automation (Playwright)
# DuckDuckGo is less likely to trigger bot checks than Google.
PLAYWRIGHT_HEADLESS = False
WEB_SEARCH_URL_PLAYWRIGHT = "https://duckduckgo.com/?q={query}"
# Normal browser search (when not using Playwright)
WEB_SEARCH_URL_BROWSER = "https://www.google.com/search?q={query}"
WEB_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# GUI OCR map
# 0 = no limit (map all detectable items)
GUI_MAP_MAX_ITEMS = 0
GUI_MAP_DIR = BASE_DIR / "mappedscreenshots"
GUI_MAP_MIN_CONF = 20.0
GUI_MAP_MIN_AREA = 80
GUI_MAP_MAX_AREA = 200000
GUI_MAP_RECT_MIN_RATIO = 0.2

# Screenshot reliability
SCREENSHOT_WAIT_TIMEOUT = 5.0
SCREENSHOT_RETRY_COUNT = 5
SCREENSHOT_RETRY_DELAY = 0.3

# Focus reliability
FOCUS_RECHECK_DELAY = 10.0
FOCUS_ATTEMPTS = 2
FOCUS_VERIFY_DELAY = 0.4
FOCUS_POLL_INTERVAL = 0.25

# App launch reliability
APP_LAUNCH_TIMEOUT = 12.0
APP_LAUNCH_RUNNING_EXTRA_TIMEOUT = 8.0
APP_LAUNCH_SETTLE_SEC = 1.2



# Auto-map during automation
AUTO_MAP_ENABLED = True
AUTO_MAP_INTERVAL_SEC = 1.5


# If a program isn't found by name (e.g. "chrome"),
# you can map it to a full path here.
# Env vars like %LOCALAPPDATA% and %PROGRAMFILES% are supported.
APP_ALIASES = {
    "chrome": [
        r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
        r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    ],
    "edge": [
        r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe",
        r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe",
        r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe",
    ],
    "firefox": [
        r"%PROGRAMFILES%\Mozilla Firefox\firefox.exe",
        r"%PROGRAMFILES(X86)%\Mozilla Firefox\firefox.exe",
    ],
    "brave": [
        r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"%PROGRAMFILES(X86)%\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
    "opera": [
        r"%PROGRAMFILES%\Opera\launcher.exe",
        r"%PROGRAMFILES%\Opera GX\launcher.exe",
        r"%LOCALAPPDATA%\Programs\Opera\launcher.exe",
        r"%LOCALAPPDATA%\Programs\Opera GX\launcher.exe",
    ],
    "vscode": [
        r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
        r"%PROGRAMFILES%\Microsoft VS Code\Code.exe",
        r"%PROGRAMFILES%\Microsoft VS Code\bin\code.cmd",
    ],
    "notepad++": [
        r"%PROGRAMFILES%\Notepad++\notepad++.exe",
        r"%PROGRAMFILES(X86)%\Notepad++\notepad++.exe",
    ],
    "vlc": [
        r"%PROGRAMFILES%\VideoLAN\VLC\vlc.exe",
        r"%PROGRAMFILES(X86)%\VideoLAN\VLC\vlc.exe",
    ],
    "obs": [
        r"%PROGRAMFILES%\obs-studio\bin\64bit\obs64.exe",
        r"%PROGRAMFILES(X86)%\obs-studio\bin\32bit\obs32.exe",
    ],
    "steam": [
        r"%PROGRAMFILES(X86)%\Steam\Steam.exe",
    ],
    "epic": [
        r"%PROGRAMFILES%\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
        r"%PROGRAMFILES(X86)%\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
    ],
    "battlenet": [
        r"%PROGRAMFILES%\Battle.net\Battle.net.exe",
        r"%PROGRAMFILES(X86)%\Battle.net\Battle.net.exe",
    ],
    "spotify": [
        r"%APPDATA%\Spotify\Spotify.exe",
        r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe",
    ],
    "telegram": [
        r"%APPDATA%\Telegram Desktop\Telegram.exe",
    ],
    "whatsapp": [
        r"%LOCALAPPDATA%\WhatsApp\WhatsApp.exe",
        r"%LOCALAPPDATA%\Microsoft\WindowsApps\WhatsApp.exe",
    ],
    "discord": [
        r"%LOCALAPPDATA%\Microsoft\WindowsApps\Discord.exe",
    ],
}

# Special Windows/UWP app profiles. These apps may run under wrapper processes
# such as ApplicationFrameHost.exe, so focus must also verify visible window titles.
APP_PROFILES = {
    "discord": {
        "aliases": ["discord"],
        "start": ["discord"],
        "window_titles": ["discord"],
        "processes": ["Discord.exe", "DiscordPTB.exe", "DiscordCanary.exe", "Update.exe"],
        "title_required_processes": [],
    },
    "calculator": {
        "aliases": ["calc", "calculator", "hesap makinesi"],
        "start": ["calc.exe"],
        "window_titles": ["calculator", "hesap makinesi"],
        "processes": ["CalculatorApp.exe", "ApplicationFrameHost.exe"],
        "title_required_processes": ["ApplicationFrameHost.exe"],
    },
    "settings": {
        "aliases": ["settings", "windows settings", "ayarlar"],
        "start": ["ms-settings:"],
        "window_titles": ["settings", "ayarlar"],
        "processes": ["SystemSettings.exe", "ApplicationFrameHost.exe"],
        "title_required_processes": ["ApplicationFrameHost.exe"],
    },
    "microsoft_store": {
        "aliases": ["microsoft store"],
        "start": ["ms-windows-store:"],
        "window_titles": ["microsoft store"],
        "processes": ["WinStore.App.exe", "ApplicationFrameHost.exe"],
        "title_required_processes": ["ApplicationFrameHost.exe"],
    },
    "notepad": {
        "aliases": ["notepad", "not defteri", "note pad"],
        "start": ["notepad.exe"],
        "window_titles": ["notepad", "not defteri"],
        "processes": ["Notepad.exe"],
        "title_required_processes": [],
    },
}

# Blocklist for potentially dangerous targets when using open/start.
# Customize as needed.
OPEN_BLOCKLIST = {
    "cmd",
    "powershell",
    "regedit",
    "registry",
    "taskmgr",
    "task manager",
    "msconfig",
    "services",
}

# File search (for open action if a full path isn't provided)
FILE_SEARCH_DIRS = [
    BASE_DIR,
    HOME_DIR / "Desktop",
    HOME_DIR / "Documents",
    HOME_DIR / "Downloads",
]
FILE_SEARCH_MAX_DEPTH = 4
FILE_SEARCH_MAX_FILES = 30000
