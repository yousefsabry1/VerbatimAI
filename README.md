# Verbatim AI — Every Word Matters.

<div align="center">
  <h3>Premium Local AI Transcription & Audio Conversion Application</h3>
  <p><strong>100% Local • Zero Cloud APIs • Egyptian Arabic & English Optimized • Hardware Accelerated</strong></p>
</div>

---

## Overview

**Verbatim AI** is a professional, local-first desktop web application designed for high-accuracy speech transcription, synchronized audio editing, and high-fidelity audio format conversion.

Powered by **Faster-Whisper (CTranslate2)** and **FFmpeg**, Verbatim AI keeps all your recordings, voice notes, and transcripts strictly on your local machine.

---

## Key Features

### 1. High-Accuracy AI Transcription
- **WhatsApp Voice Note Precision**: Built and tested against real-world compressed audio (Opus / OGG).
- **Egyptian Arabic & English Code-Switching**: Tuned with vocabulary prompts for real colloquial conversations, business meetings, and tech terminology (e.g. *meeting, deadline, sprint, project, call*).
- **Strict Verbatim Mode**: Captures raw speech fidelity including filler words, hesitations, repetitions, and spoken slang without silent paraphrasing.
- **Clean Transcript Mode**: Provides readable, well-punctuated paragraphs while preserving all original timestamped segments.
- **Maximum Accuracy Pipeline**: Deep verification pass that assesses speech probability, average logprob, and flags suspicious or uncertain intervals for human review.
- **Voice Activity Detection (VAD)**: Intelligent Silero VAD segmentation prevents word truncation and eliminates timestamp drift.

### 2. Synchronized Transcript Review Workspace
- **Click-to-Seek Audio**: Click any timestamp in the transcript to immediately jump audio playback to that exact second.
- **Active Segment Highlighting**: Visual pulse highlight tracks the spoken words in real time as audio plays.
- **Uncertainty Markers**: Low-confidence speech segments are automatically flagged with warning badges for human review.
- **Inline Editing**: Correct typos, split, or refine segment text directly in the browser.
- **Flexible Exports**: One-click download in **TXT (clean or timestamped)**, **SRT (subtitles)**, **WebVTT**, and **JSON (with word timestamps)**.

### 3. Local Audio Converter
- **Genuine FFmpeg Engine**: Real format conversion across **MP3, WAV, OGG, OPUS, M4A, AAC, FLAC, AIFF, and WEBM**.
- **Quality Presets**:
  - *Smaller File*: High compression, ideal for voice notes and messaging.
  - *Balanced*: Recommended default for high audio fidelity with balanced file size.
  - *High Quality*: Maximum bitrate / lossless audio preservation.
  - *Custom*: Full manual control over bitrate (64k–320k), sample rate (16kHz–48kHz), and channels (Mono/Stereo).
- **Before & After Audio Preview**: Side-by-side audio playback with exact storage savings calculation.
- **Batch Processing**: Queue multiple files with controlled concurrency and download all converted outputs as a single ZIP archive.

### 4. Local-First Privacy & Zero Telemetry
- Runs 100% on `localhost:8000`.
- No cloud accounts, no subscription keys, and no telemetry tracking.
- Audio and transcript data are stored in a local SQLite database and never leave your hardware.

---

## Architecture

```text
VerbatimAI/
├── frontend/             # React 19 + TypeScript + Vite + Tailwind CSS
│   ├── src/
│   │   ├── components/   # Synchronized AudioPlayer, Navbar, UI controls
│   │   ├── pages/        # Dashboard, Transcription, Converter, History, Settings
│   │   ├── context/      # I18n (English/Arabic RTL), Theme (Dark/Light)
│   │   └── services/     # Typed API client
│   └── dist/             # Production build served directly by FastAPI
│
├── backend/              # Python 3.11+ FastAPI Application
│   └── app/
│       ├── api/          # Documented REST API (Health, Hardware, Models, Audio, Jobs)
│       ├── core/         # SQLite database & storage configuration
│       ├── audio/        # FFprobe inspection & filename validation
│       ├── conversion/   # FFmpeg conversion engine with presets
│       ├── transcription/# Faster-Whisper pipeline, VAD, CUDA fallback
│       └── exports/      # SRT, VTT, TXT, and JSON formatters
│
├── tests/                # Automated pytest unit & integration test suite
├── scripts/              # Windows batch installation and launch scripts
└── storage/              # Local models, uploads, outputs (excluded from Git)
```

---

## One-Click Windows Installation & Startup

Non-technical Windows users can install and launch Verbatim AI with zero command-line configuration:

1. **Install**: Double-click `00_INSTALL.bat`
   - Automatically checks Python and FFmpeg.
   - Configures the virtual environment and installs dependencies.
   - Builds the production web interface.
2. **Launch**: Double-click `01_START_VERBATIM_AI.bat`
   - Starts the local backend server.
   - Automatically opens your default web browser to `http://127.0.0.1:8000`.
3. **Safe CPU Mode**: If running on a PC without an NVIDIA GPU, double-click `02_CPU_SAFE_START.bat`.
4. **Diagnostics**: Double-click `03_CHECK_SYSTEM.bat` to verify your GPU, CUDA drivers, and FFmpeg installation.

---

## Developer Setup (Manual)

### Backend

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend (Development Server)

```powershell
cd frontend
npm install
npm run dev
```

### Run Automated Tests

```powershell
py -3.11 -m pytest tests/
```

---

## Upstream Attribution & License

Verbatim AI is open-source under the **MIT License**.

- Portions of the model loading and CUDA detection patterns were adapted from [Local Meeting Transcriber](https://github.com/AmrAboelhassan/local-meeting-transcriber) by Amr Aboelhassan.
- Faster-Whisper is copyright (c) 2023 SYSTRAN.
- CTranslate2 is copyright (c) 2020 OpenNMT.
- For full third-party notices, see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
