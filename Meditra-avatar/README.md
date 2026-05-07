# Meditra Avatar (TTS + Viseme Sequencer)

FastAPI web app that takes any user-entered sentence, generates TTS audio, and renders a lip-sync animation video by sequencing pre-existing viseme video clips.

## Folder layout

```
AI/Meditra-avatar/
  app/
    main.py
    static/
      index.html
      app.js
      visemes/
        ee.mp4
        ih.mp4
        ...
    outputs/
```

## Prereqs

- Python 3.10+
- **FFmpeg installed and on PATH** (required by `pydub` and `moviepy`)

## Fresh Installation (No Dependencies)

### 1. Install Python
```cmd
REM Download from: https://www.python.org/downloads/
REM During installation, check "Add Python to PATH"
python --version
```

### 2. Install FFmpeg
```cmd
REM Option 1: Using Chocolatey (if available)
choco install ffmpeg

REM Option 2: Manual download
REM Download from: https://ffmpeg.org/download.html
REM Extract and add to PATH
```

### 3. Setup Project
```cmd
cd AI/Meditra-avatar
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Quick Start (Alternative)
```cmd
REM Use provided batch file
start.bat
```

## Install (Existing Python Setup)

```bash
cd AI/Meditra-avatar
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Add viseme clips

Put your pre-existing clips into:

- `AI/Meditra-avatar/app/static/visemes/`

Required names (one file per viseme, `.mp4`):

`ee`, `ih`, `ah`, `oh`, `oo`, `ma`, `pa`, `fa`, `tha`, `ta`, `ka`, `sha`, `pause`

Example: `ee.mp4`, `pause.mp4`

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

Open:

- `http://127.0.0.1:8000`

