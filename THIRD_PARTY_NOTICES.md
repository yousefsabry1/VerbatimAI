# Third-Party Software & Model Notices

Verbatim AI incorporates, adapts, or interacts with the following open-source projects, libraries, and models:

---

## 1. Local Meeting Transcriber
- **Source**: https://github.com/AmrAboelhassan/local-meeting-transcriber
- **Author**: Amr Aboelhassan
- **License**: MIT License
- **Notice**:
  Portions of the audio model loading logic, CUDA detection checks, and SRT timestamp calculation patterns were adapted and substantially refactored from Local Meeting Transcriber into a decoupled, modern FastAPI backend service.

---

## 2. Faster-Whisper & CTranslate2
- **Source**: https://github.com/SYSTRAN/faster-whisper
- **Source**: https://github.com/OpenNMT/CTranslate2
- **License**: MIT License
- **Notice**:
  Faster-Whisper is a reimplementation of OpenAI's Whisper model using CTranslate2, a fast inference engine for Transformer models.

---

## 3. OpenAI Whisper Models (Systran conversions)
- **Source**: https://huggingface.co/Systran
- **Original Model**: OpenAI Whisper (MIT License)
- **Model Artifacts**: Systran/faster-whisper-small, Systran/faster-whisper-medium, Systran/faster-whisper-large-v3.

---

## 4. FFmpeg
- **Source**: https://ffmpeg.org
- **License**: LGPL 2.1+ / GPL 3.0+
- **Notice**:
  Audio extraction, format inspection via FFprobe, and high-fidelity local format conversion are powered by FFmpeg.

---

## 5. React, Vite & Tailwind CSS
- **React**: MIT License (Meta Platforms, Inc.)
- **Vite**: MIT License (Evan You & Vite Contributors)
- **Tailwind CSS**: MIT License (Tailwind Labs, Inc.)
- **Lucide Icons**: ISC License (Lucide Contributors)
