# Verbatim AI — Every Word Matters.

<div align="center">
  <h3>Desktop Web Application for Speech Transcription & Audio Processing</h3>
  <p><strong>100% Local • Zero Cloud APIs • Egyptian Arabic & English Code-Switching • Hardware Accelerated</strong></p>
</div>

---

## 1. Overview

**Verbatim AI** is a local-first speech transcription, audio synchronization, and format conversion application. Built specifically for complex conversational audio—including WhatsApp voice notes, bilingual interviews, academic lectures, and technical meetings—Verbatim AI runs entirely on your local machine with zero external cloud dependencies.

All speech recognition, audio processing, and transcription data are stored in a private local SQLite database on `localhost:8000`. Your voice recordings never leave your computer.

---

## 2. Transcription Mode Presets

Verbatim AI offers two distinct, purpose-built transcription presets designed to fit different hardware profiles and workflow requirements:

| Feature / Metric | ⚡ **Fast Transcription** | 🎯 **Maximum Accuracy — Experimental** |
|---|---|---|
| **Default Selection** | **Yes** (Recommended for daily tasks) | Optional (High-fidelity research mode) |
| **ASR Architecture** | Specialized Whisper Medium (`codeswitched-medium`) | **Hybrid ASR V3** (Dual-Model or Tri-Model Consensus) |
| **Operational Tiers** | Single Model | **Tier 1 (Base)**: Twin Models (Specialized + Turbo)<br>**Tier 2 (Full)**: Twin Models + QwenCleo 4-bit Arbiter |
| **Speed (RTF)** | **~0.044x** (~22x faster than real-time) | **~0.283x** (~3.5x faster than real-time) |
| **Code-Switching WER** | 122.65% (unprotected) / 42.19% (clean audio) | **20.51%** (Best-in-class multi-speaker benchmark) |
| **Multi-Speaker WER** | 111.40% (susceptible to repetition loops) | **30.40%** (Suppresses hallucination loops) |
| **VRAM Consumption** | ~0.94 GB VRAM (CUDA float16) | ~1.50 GB Peak VRAM (Sequential CUDA execution) |
| **CPU Safe Mode** | Supported (int8 quantization) | Supported (CPU-only fusion) |
| **Best Used For** | Fast voice notes, drafts, quick audio conversion | Complex bilingual meetings, technical terms, strict verbatim records |

> [!IMPORTANT]
> **Honest Accuracy Limitations & Operational Tiers**:  
> No automated speech recognition system is 100% error-free.  
> - **Fast Transcription** is optimized for high turnaround speed; however, its single decoder can be sensitive to heavy background noise, rapid overlapping speech, or catastrophic hallucination loops on low-bitrate audio.  
> - **Maximum Accuracy — Experimental (Hybrid ASR V3)** operates in two transparent tiers:
>   - **Tier 1 — Dual-Model Consensus (Default Out-of-the-Box)**: Combines Specialized Whisper Medium (~0.78 GB) and Whisper Large-v3-Turbo (~1.60 GB). Features calibrated ROVER scoring, particle deduplication, and technical transliteration normalization. Operates smoothly on GPU or CPU without heavy disk requirements.
>   - **Tier 2 — Full Tri-Model Consensus (Optional Advanced Mode)**: Adds QwenCleo-ASR 4-bit NF4 (~3.82 GB model weights, ~6.5 GB total space including isolated environment). Requires an NVIDIA GPU with at least 4 GB VRAM. It is only called when a critical code-switching conflict is detected between the twin models to act as an intelligent arbiter. Run `04_SETUP_QWENCLEO_MAX_ACCURACY.bat` to configure it.
> - The application truthfully reports its exact operational tier in the UI and transcript metadata: it never claims three-model execution when only two models ran.
> Always review and verify your transcripts before final publishing.

### Advanced Settings & Individual Models
All standalone ASR models remain accessible via the **Show Advanced Settings** drawer on the Transcription page:
- `Egyptian Arabic & English (Specialized)` (Medium, ~0.78 GB)
- `Whisper Large-v3-Turbo` (800M params, ~1.60 GB)
- `Whisper Medium` (Standard multilingual, ~1.50 GB)
- `Whisper Small` (Lightweight, ~0.48 GB)
- `Whisper Large-v3` (High precision, ~3.10 GB)

---

## 3. System Requirements

### Hardware Requirements
- **Operating System**: Windows 10 or Windows 11 (64-bit).
- **Processor (CPU)**: 4 physical cores minimum (Intel Core i5/i7 or AMD Ryzen 5/7 recommended).
- **RAM**: 8 GB RAM minimum for Fast Mode; 16 GB RAM recommended for Maximum Accuracy Mode.
- **Graphics Card (GPU)**:
  - *Optional but recommended*: NVIDIA GeForce GTX 1650, RTX 3050, or higher with at least 4 GB VRAM.
  - *No GPU?* Verbatim AI features full **CPU Safe Mode** using int8 quantization that runs reliably on any computer without CUDA.
- **Disk Space**: At least 5 GB free disk space for application files and downloaded models.

### Automated Dependency Bootstrapping
You do **not** need to manually install Python, Node.js, FFmpeg, or virtual environments ahead of time. The included installer (`00_INSTALL.bat`) automatically:
- Detects or securely bootstraps **Python 3.11** (user-scope, no admin privileges required).
- Detects or bootstraps verified **FFmpeg** and **FFprobe** audio binaries.
- Detects or bootstraps **Node.js** and compiles the production React frontend bundle to `frontend/dist`.
- Configures the backend Python virtual environment (`backend/.venv`) and installs core libraries.
- Validates the complete stack with end-to-end import checks before completion.

---

## 4. Source Code vs Model Weights Availability

> [!NOTE]
> **Model Weights are NOT stored in the GitHub repository.**  
> Neural network weights (ranging from 450 MB to 3.8 GB) are hosted on Hugging Face to keep the repository clone small, fast, and lightweight.

Models are downloaded **on-demand upon first selection** via the interactive UI with verified progress bars, integrity checks, and resumable transfers:
- **Specialized Whisper Medium**: `Seif-Eldeen-Sameh/whisper-medium-arabic-codeswitched-ct2` (~0.78 GB)
- **Whisper Large-v3-Turbo**: `deepdml/faster-whisper-large-v3-turbo-ct2` (~1.60 GB)
- **Whisper Medium**: `Systran/faster-whisper-medium` (~1.43 GB)
- **Whisper Small**: `Systran/faster-whisper-small` (~0.45 GB)
- **Hybrid ASR V3 (Twin Models)**: Specialized Medium + Large-v3-Turbo (~2.38 GB combined)
- **QwenCleo-ASR (4-bit NF4)**: `mohammedaly22/QwenCleo-ASR` (~3.82 GB, optional code-switch arbiter)

All downloaded weights are stored locally inside `backend/storage/models/`.

---

## 5. One-Click Windows Installation & Launch

Verbatim AI includes pre-configured Windows batch launchers in the project root:

```text
VerbatimAI/
├── 00_INSTALL.bat                      <-- Step 1: Double-click to install & configure everything automatically
├── 01_START_VERBATIM_AI.bat            <-- Step 2: Double-click to launch application (GPU/Auto)
├── 02_CPU_SAFE_START.bat               <-- Alternative: Double-click for 100% CPU Safe Mode on any laptop
├── 03_CHECK_SYSTEM.bat                 <-- Diagnostic tool to audit hardware, drivers, and tier readiness
└── 04_SETUP_QWENCLEO_MAX_ACCURACY.bat   <-- Optional: Sets up QwenCleo 4-bit arbiter for Tri-Model Consensus
```

### Installation Steps & Realistic Timing
1. **Download & Extract**:
   Download the latest VerbatimAI ZIP from GitHub and extract it to any folder on your machine (paths with spaces or non-C drives are fully supported).
2. **Run Installer**:
   Double-click `00_INSTALL.bat`.
   - **Realistic Time Expectation**:
     - On typical broadband (15–50 Mbps): ~5 to 10 minutes.
     - On high-speed fiber (100+ Mbps): ~3 to 5 minutes.
     - If dependencies (Python 3.11, Node.js, FFmpeg) already exist: under 2 minutes.
   - The installer checks your Windows environment, RAM, and disk space.
   - Automatically bootstraps Python 3.11, FFmpeg, and Node.js if missing.
   - Creates the backend virtual environment at `backend/.venv` and installs dependencies.
   - Automatically compiles the production frontend React bundle to `frontend/dist`.
   - Records all diagnostic steps into a timestamped log (`logs/install-YYYYMMDD-HHMMSS.log`).
   - Idempotent: running it a second time quickly verifies and repairs missing components without re-downloading.
3. **Launch Application**:
   Double-click `01_START_VERBATIM_AI.bat`.
   - Pre-verifies backend imports and port 8000 availability.
   - Polls the `/api/health` healthcheck endpoint until the server is confirmed healthy.
   - Automatically opens your default web browser to `http://127.0.0.1:8000`.
   - If Verbatim AI is already running, it brings up your existing session without crashing.
4. **CPU-Safe Fallback**:
   On laptops or PCs without an NVIDIA GPU (or in case of CUDA driver issues), double-click `02_CPU_SAFE_START.bat`. It forces CPU int8 quantization and bypasses all CUDA GPU allocations.
5. **Optional Full Tri-Model Consensus**:
   For users with an NVIDIA GPU (>= 4 GB VRAM) who want the full 3-model code-switching arbiter:
   - Double-click `04_SETUP_QWENCLEO_MAX_ACCURACY.bat`.
   - Downloads QwenCleo-ASR 4-bit weights (~3.8 GB) and configures the isolated `experimental_venv` (~10–20 minutes depending on bandwidth).

> [!TIP]
> **Windows SmartScreen Note**:  
> When running downloaded `.bat` or `.ps1` files on a fresh Windows PC, Windows SmartScreen may display: *"Windows protected your PC"*.  
> This standard Windows notification occurs because open-source scripts do not carry paid commercial code-signing certificates.  
> You can safely inspect all batch files and PowerShell scripts in any text editor—everything is transparent, open-source, and executes locally.  
> To run: Click **More info** -> **Run anyway**. Never disable Windows SmartScreen or security features globally.

---

## 6. Complete User Journey

1. **Upload Audio**: Drag and drop any voice note or audio file into the workspace.
2. **Select Mode**:
   - Choose **Fast Transcription** for quick results.
   - Choose **Maximum Accuracy — Experimental** for complex or code-switched recordings.
3. **Download Model (First-Time Only)**: If the selected model is not on your disk, click **Download Model** directly inside the card.
4. **Start Transcription**: Click **Start Transcription**. Progress is streamed live with stage updates.
5. **Interactive Review**:
   - **Click-to-Seek**: Click any timestamp in the transcript to jump playback to that exact point in time.
   - **Visual Highlighting**: Words illuminate in sync with playback.
   - **Review Queue**: Segments with low confidence or potential repetitions are surfaced in a dedicated review queue.
   - **Inline Editing**: Fix any misrecognized words directly. Edits auto-save to the local SQLite database.
6. **Export Options**: Export your verified transcript with one click in:
   - **TXT**: Clean paragraphs or verbatim with timestamps.
   - **SRT**: Standard subtitle format with millisecond intervals.
   - **WebVTT**: Web-ready video caption format.
   - **JSON**: Comprehensive machine-readable export with word-level alignments.
7. **Audio Converter**: Convert any audio file between MP3, WAV, OGG, OPUS, M4A, AAC, and FLAC with real-time before/after playback comparison.
8. **History**: Re-open and review any past transcription job at any time.

---

## 7. Supported Audio Formats

Verbatim AI natively supports decoding and conversion across all common formats:

| Format / Codec | Extension | Optimal Purpose |
|---|---|---|
| **OGG / Opus** | `.ogg`, `.opus` | WhatsApp voice notes, Telegram voice messages |
| **MP3** | `.mp3` | Podcasts, voice recordings, general audio |
| **WAV** | `.wav` | Uncompressed studio audio, professional interviews |
| **M4A / AAC** | `.m4a`, `.aac` | Apple voice memos, mobile audio recordings |
| **FLAC / AIFF** | `.flac`, `.aiff` | Lossless archival audio |
| **WEBM** | `.webm` | Browser and web-recorded audio |
| **Video Containers** | `.mp4`, `.mov`, `.mkv` | Automatic audio track extraction from video |

---

## 8. Privacy & Local Operation Details

- **Zero External Calls**: Audio is processed entirely inside your local machine. No speech fragments, metadata, or logs are uploaded to any third-party server.
- **Localhost Binding**: The backend binds exclusively to `127.0.0.1:8000`. It does not listen on external network interfaces.
- **Local SQLite Database**: All transcripts, review notes, and job records are kept in `backend/storage/verbatim.db`.
- **Private Audio Storage**: Stored uploads (`backend/storage/uploads/`) and outputs are excluded from Git version control by default.

---

## 9. Troubleshooting & FAQ

### Python or dependencies missing on a clean machine
- Simply double-click `00_INSTALL.bat`. The bootstrapper detects missing components (Python 3.11, FFmpeg, Node.js) and configures them automatically without requiring manual setup or administrator privileges.

### How to diagnose installation or system issues
- Run `03_CHECK_SYSTEM.bat` to see a colorized diagnostic check of your OS, Python, FFmpeg, Node.js, GPU, and models.
- Review the installation log files in `logs/install-YYYYMMDD-HHMMSS.log` for full details.

### Port 8000 is already in use
- `01_START_VERBATIM_AI.bat` automatically detects if Verbatim AI is already running and opens your browser without crashing.
- If a different application is occupying port 8000, close that application or terminate it via PowerShell:
  ```powershell
  Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess -Force
  ```

### CUDA out-of-memory or GPU driver warnings
- If your computer has no NVIDIA GPU, less than 4 GB VRAM, or an older driver, run `02_CPU_SAFE_START.bat`.
- It activates 100% CPU Safe Mode with int8 quantization, bypassing all GPU requirements while maintaining high transcription quality.

### Repairing an incomplete or interrupted installation
- If an installation was interrupted (e.g. power outage or closed window), re-run `00_INSTALL.bat`. It is idempotent and safely repairs missing dependencies. You can also force a complete repair by running:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1 -Repair
  ```

---

## 10. License & Attributions

Verbatim AI is open-source under the **MIT License**.

- Faster-Whisper: Copyright (c) 2023 SYSTRAN.
- CTranslate2: Copyright (c) 2020 OpenNMT.
- Specialized Arabic Whisper Model: Fine-tuned by Seif-Eldeen Sameh (`Seif-Eldeen-Sameh/whisper-medium-arabic-codeswitched-ct2`).
- QwenCleo-ASR: Developed by Mohammed Aly (`mohammedaly22/QwenCleo-ASR`).
- See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for complete license text.
