import React, { useState, useEffect, useRef } from 'react';
import { useI18n } from '../context/I18nContext';
import { AudioMetadata, HardwareInfo, Job, ModelInfo, Segment, TranscriptResult } from '../types';
import { api } from '../services/api';
import { AudioPlayer, AudioPlayerRef } from '../components/AudioPlayer';
import {
  UploadCloud,
  FileAudio,
  Play,
  Check,
  Copy,
  Download,
  AlertTriangle,
  RotateCcw,
  Sparkles,
  Sliders,
  X,
  Volume2,
  Clock,
  Save,
  CheckCircle2,
  ChevronDown,
  Info,
  Cpu,
  Zap,
  AlertOctagon,
} from 'lucide-react';

interface TranscriptionProps {
  initialJobId?: string | null;
  onClearInitialJob?: () => void;
  hardware: HardwareInfo | null;
}

export const Transcription: React.FC<TranscriptionProps> = ({
  initialJobId,
  onClearInitialJob,
  hardware,
}) => {
  const { t, isRTL } = useI18n();
  const playerRef = useRef<AudioPlayerRef | null>(null);

  // Upload & File State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadedFileId, setUploadedFileId] = useState<string | null>(null);
  const [fileMetadata, setFileMetadata] = useState<AudioMetadata | null>(null);

  // Settings State
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('codeswitched-medium');
  const [language, setLanguage] = useState<string>('ar');
  const [verbatimMode, setVerbatimMode] = useState<'strict' | 'clean'>('strict');
  const [accuracyMode, setAccuracyMode] = useState<'balanced' | 'maximum'>('balanced');
  const [enhanceAudio, setEnhanceAudio] = useState<boolean>(false);
  const [vadFilter, setVadFilter] = useState<boolean>(true);
  const [vocabularyHints, setVocabularyHints] = useState<string>('');
  const [deviceMode, setDeviceMode] = useState<string>('auto');
  const [showAdvanced, setShowAdvanced] = useState<boolean>(false);

  // Job Processing State
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<Job | null>(null);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [jobError, setJobError] = useState<string | null>(null);

  // Review Workspace State
  const [transcriptData, setTranscriptData] = useState<TranscriptResult | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [cleanText, setCleanText] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'segments' | 'clean'>('segments');
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [isSaved, setIsSaved] = useState<boolean>(true);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState<boolean>(false);

  // Load models & recommended hardware defaults
  useEffect(() => {
    api.getModels().then(res => {
      setModels(res.models);
      // Auto select downloaded or recommended model
      const downloaded = res.models.find(m => m.is_downloaded);
      if (downloaded) setSelectedModel(downloaded.id);
      else if (hardware?.recommended?.model) setSelectedModel(hardware.recommended.model);
    }).catch(console.error);
  }, [hardware]);

  // Handle external review trigger (e.g. from Dashboard or History)
  useEffect(() => {
    if (initialJobId) {
      loadCompletedJob(initialJobId);
      if (onClearInitialJob) onClearInitialJob();
    }
  }, [initialJobId]);

  const loadCompletedJob = async (jobId: string) => {
    try {
      const res = await api.getTranscriptionResult(jobId);
      setTranscriptData(res);
      setSegments(res.segments || []);
      setCleanText(res.clean_text || '');
      setActiveJobId(jobId);
      setUploadedFileId(jobId); // or audio stream reference
      setIsProcessing(false);
    } catch (err) {
      console.error('Failed to load completed transcript', err);
    }
  };

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  // Drag and drop handlers
  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileUpload = async (file: File) => {
    setSelectedFile(file);
    setUploading(true);
    setTranscriptData(null);
    try {
      const res = await api.uploadAudio(file);
      setUploadedFileId(res.file_id);
      setFileMetadata(res.metadata);
    } catch (err: any) {
      alert(err.message || 'File upload failed');
      setSelectedFile(null);
    } finally {
      setUploading(false);
    }
  };

  // Submit transcription job
  const handleStartTranscription = async () => {
    if (!uploadedFileId) return;
    setIsProcessing(true);
    setJobError(null);
    setTranscriptData(null);

    try {
      const res = await api.submitTranscription({
        file_id: uploadedFileId,
        model_id: selectedModel,
        language: language === 'auto' ? null : language,
        device_mode: deviceMode,
        compute_mode: 'auto',
        accuracy_mode: accuracyMode,
        verbatim_mode: verbatimMode,
        enhance_audio: enhanceAudio,
        vad_filter: vadFilter,
        vocabulary_hints: vocabularyHints.trim() ? vocabularyHints.trim() : null,
      });

      setActiveJobId(res.job_id);

      // Start polling status
      pollJobStatus(res.job_id);
    } catch (err: any) {
      setJobError(err.message || 'Failed to submit transcription job');
      setIsProcessing(false);
    }
  };

  const pollJobStatus = (jobId: string) => {
    const interval = setInterval(async () => {
      try {
        const job = await api.getTranscriptionStatus(jobId);
        setJobStatus(job);

        if (job.status === 'completed') {
          clearInterval(interval);
          setJobError(null);
          loadCompletedJob(jobId);
        } else if (job.status === 'failed') {
          clearInterval(interval);
          setIsProcessing(false);
          setJobError(job.error_message || 'Transcription failed on both GPU and CPU.');
        } else if (job.status === 'cancelled') {
          clearInterval(interval);
          setIsProcessing(false);
        }
      } catch (err: any) {
        console.error('Polling error', err);
      }
    }, 1200);
  };

  const handleCancel = async () => {
    if (activeJobId) {
      await api.cancelJob(activeJobId);
      setIsProcessing(false);
      setJobStatus(null);
    }
  };

  const handleSegmentTextChange = (id: number, newText: string) => {
    setSegments(prev =>
      prev.map(s => (s.id === id ? { ...s, text: newText } : s))
    );
    setIsSaved(false);
  };

  const handleSaveEdits = async () => {
    if (!activeJobId) return;
    try {
      await api.updateTranscriptSegments(activeJobId, cleanText, segments);
      setIsSaved(true);
      showToast('Changes saved successfully!');
    } catch (err: any) {
      alert('Failed to save changes: ' + err.message);
    }
  };

  const handleCopyTranscript = () => {
    const textToCopy =
      activeTab === 'clean'
        ? cleanText
        : segments.map(s => `[${formatTime(s.start)} - ${formatTime(s.end)}] ${s.text}`).join('\n');

    navigator.clipboard.writeText(textToCopy);
    showToast(t.copiedToast);
  };

  const formatTime = (secs: number) => {
    const s = Math.max(0, Math.floor(secs));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m.toString().padStart(2, '0')}:${r.toString().padStart(2, '0')}`;
  };

  return (
    <div className="space-y-6 animate-fadeIn pb-16">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-3 text-sm font-semibold text-white shadow-2xl animate-bounce">
          <CheckCircle2 className="h-4 w-4" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Page Title */}
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-black text-white light:text-surface-900">
          {t.transcriptionTitle}
        </h1>
        <p className="text-sm text-surface-400 light:text-surface-600">
          {t.transcriptionSubtitle}
        </p>
      </div>

      {/* Upload Zone & Settings Row */}
      {!transcriptData && !isProcessing && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Upload Drop Zone */}
          <div className="lg:col-span-2 space-y-4">
            <div
              onDragOver={e => e.preventDefault()}
              onDrop={handleFileDrop}
              className={`relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 sm:p-12 text-center transition-all ${
                selectedFile
                  ? 'border-brand-500/80 bg-brand-500/5'
                  : 'border-surface-800 bg-surface-900/40 hover:border-surface-700 hover:bg-surface-900/60 light:border-surface-300 light:bg-white'
              }`}
            >
              <input
                type="file"
                id="audio-upload"
                accept="audio/*,video/*,.ogg,.opus,.mp3,.wav,.m4a,.aac,.flac,.mp4"
                onChange={e => e.target.files?.[0] && handleFileUpload(e.target.files[0])}
                className="hidden"
              />

              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-500/10 text-brand-400 border border-brand-500/20 mb-4">
                <UploadCloud className="h-8 w-8" />
              </div>

              <h3 className="text-lg font-bold text-white light:text-surface-900 mb-1">
                {selectedFile ? selectedFile.name : t.uploadAreaTitle}
              </h3>

              <p className="text-xs text-surface-400 light:text-surface-600 max-w-sm mb-4">
                {selectedFile
                  ? `${fileMetadata?.size_formatted || ''} • ${fileMetadata?.duration_formatted || ''} • ${fileMetadata?.format?.toUpperCase() || ''}`
                  : t.uploadAreaSubtitle}
              </p>

              <label
                htmlFor="audio-upload"
                className="cursor-pointer rounded-xl bg-surface-800 px-4 py-2 text-xs font-semibold text-white hover:bg-surface-700 light:bg-surface-100 light:text-surface-800 light:hover:bg-surface-200 transition-colors"
              >
                {selectedFile ? 'Change File' : t.browseFiles}
              </label>

              <p className="mt-4 text-[11px] text-surface-500">
                {t.supportedFormatsNotice}
              </p>
            </div>

            {/* File Metadata Details Card */}
            {fileMetadata && (
              <div className="rounded-xl border border-surface-800 bg-surface-900/60 p-4 light:border-surface-200 light:bg-white grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div>
                  <span className="text-surface-400">Duration:</span>
                  <p className="font-semibold text-white light:text-surface-900">{fileMetadata.duration_formatted}</p>
                </div>
                <div>
                  <span className="text-surface-400">Codec / Format:</span>
                  <p className="font-semibold text-white light:text-surface-900">{fileMetadata.codec} ({fileMetadata.format})</p>
                </div>
                <div>
                  <span className="text-surface-400">Sample Rate:</span>
                  <p className="font-semibold text-white light:text-surface-900">{fileMetadata.sample_rate} Hz ({fileMetadata.channel_layout})</p>
                </div>
                <div>
                  <span className="text-surface-400">File Size:</span>
                  <p className="font-semibold text-white light:text-surface-900">{fileMetadata.size_formatted}</p>
                </div>
              </div>
            )}
          </div>

          {/* Transcription Settings Panel */}
          <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-5">
            <h3 className="font-bold text-white light:text-surface-900 flex items-center gap-2 border-b border-surface-800/80 pb-3 light:border-surface-100">
              <Sliders className="h-4 w-4 text-brand-400" />
              Settings
            </h3>

            {/* Model Selection */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-surface-300 light:text-surface-700">
                {t.modelSelectionLabel}
              </label>
              <select
                value={selectedModel}
                onChange={e => setSelectedModel(e.target.value)}
                className="w-full rounded-xl border border-surface-800 bg-surface-950 px-3 py-2 text-xs text-white light:border-surface-300 light:bg-white light:text-surface-900 focus:outline-none focus:border-brand-500"
              >
                {models.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.name} {m.is_downloaded ? '✓ (Ready)' : `(Needs ~${m.approx_download_gb} GB download)`}
                  </option>
                ))}
              </select>
            </div>

            {/* Language Selection */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-surface-300 light:text-surface-700">
                {t.languageSelectionLabel}
              </label>
              <select
                value={language}
                onChange={e => setLanguage(e.target.value)}
                className="w-full rounded-xl border border-surface-800 bg-surface-950 px-3 py-2 text-xs text-white light:border-surface-300 light:bg-white light:text-surface-900 focus:outline-none focus:border-brand-500"
              >
                <option value="auto">{t.languageAuto}</option>
                <option value="ar">{t.languageArabic}</option>
                <option value="en">{t.languageEnglish}</option>
              </select>
            </div>

            {/* Verbatim Mode vs Clean Mode */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-surface-300 light:text-surface-700">
                {t.modeLabel}
              </label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setVerbatimMode('strict')}
                  className={`rounded-xl p-2.5 text-xs font-semibold border transition-all text-left rtl:text-right ${
                    verbatimMode === 'strict'
                      ? 'border-brand-500 bg-brand-500/10 text-brand-400'
                      : 'border-surface-800 bg-surface-950/60 text-surface-400 light:border-surface-200 light:bg-surface-50'
                  }`}
                >
                  <p className="font-bold">Strict Verbatim</p>
                  <p className="text-[10px] text-surface-500 font-normal">Preserves all spoken words</p>
                </button>
                <button
                  type="button"
                  onClick={() => setVerbatimMode('clean')}
                  className={`rounded-xl p-2.5 text-xs font-semibold border transition-all text-left rtl:text-right ${
                    verbatimMode === 'clean'
                      ? 'border-brand-500 bg-brand-500/10 text-brand-400'
                      : 'border-surface-800 bg-surface-950/60 text-surface-400 light:border-surface-200 light:bg-surface-50'
                  }`}
                >
                  <p className="font-bold">Clean Transcript</p>
                  <p className="text-[10px] text-surface-500 font-normal">Readable paragraphs</p>
                </button>
              </div>
            </div>

            {/* Accuracy Pipeline */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-surface-300 light:text-surface-700">
                {t.accuracyModeLabel}
              </label>
              <select
                value={accuracyMode}
                onChange={e => setAccuracyMode(e.target.value as any)}
                className="w-full rounded-xl border border-surface-800 bg-surface-950 px-3 py-2 text-xs text-white light:border-surface-300 light:bg-white light:text-surface-900 focus:outline-none focus:border-brand-500"
              >
                <option value="balanced">{t.accuracyBalanced}</option>
                <option value="maximum">{t.accuracyMaximum}</option>
              </select>
            </div>

            {/* Quick Optimal Settings Preset for Egyptian Audio */}
            <div className="p-2.5 rounded-xl bg-brand-500/10 border border-brand-500/20 text-xs space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="font-bold text-brand-300 flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5 text-brand-400" />
                  <span>Optimal Egyptian Audio Preset</span>
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedModel('codeswitched-medium');
                    setVadFilter(false);
                    setVocabularyHints('محادثة بالعامية المصرية ومصطلحات تقنية وتنظيمية بالإنجليزية.');
                    setAccuracyMode('maximum');
                    setVerbatimMode('strict');
                    showToast('Applied optimal Egyptian ASR settings!');
                  }}
                  className="px-2 py-0.5 rounded-md bg-brand-600 text-white font-semibold text-[11px] hover:bg-brand-500 transition-colors"
                >
                  Apply Preset
                </button>
              </div>
              <p className="text-[10px] text-surface-400 leading-normal">
                Applies Code-Switched Medium, disables VAD (prevents clipping opening words), sets maximum accuracy, and applies colloquial context.
              </p>
            </div>

            {/* Checkboxes: Enhancement & VAD */}
            <div className="space-y-2 pt-2 border-t border-surface-800/60 light:border-surface-100">
              <label className="flex items-center gap-2 cursor-pointer text-xs text-surface-300 light:text-surface-700">
                <input
                  type="checkbox"
                  checked={enhanceAudio}
                  onChange={e => setEnhanceAudio(e.target.checked)}
                  className="rounded border-surface-700 text-brand-500 focus:ring-0"
                />
                <span>{t.audioEnhancementLabel}</span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer text-xs text-surface-300 light:text-surface-700">
                <input
                  type="checkbox"
                  checked={vadFilter}
                  onChange={e => setVadFilter(e.target.checked)}
                  className="rounded border-surface-700 text-brand-500 focus:ring-0"
                />
                <div>
                  <span className="font-semibold">{t.vadLabel}</span>
                  <span className="text-[10px] text-surface-500 block">
                    (Disable for WhatsApp voice notes or soft intros to prevent clipping opening words)
                  </span>
                </div>
              </label>
            </div>

            {/* Advanced Settings Toggle */}
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-xs text-surface-400 hover:text-white flex items-center gap-1 font-semibold pt-1"
            >
              <span>{t.advancedSettings}</span>
              <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
            </button>

            {showAdvanced && (
              <div className="space-y-3 p-3 rounded-xl bg-surface-950/80 border border-surface-800/80 text-xs">
                <div>
                  <label className="text-surface-400 font-medium block mb-1">{t.deviceModeLabel}</label>
                  <select
                    value={deviceMode}
                    onChange={e => setDeviceMode(e.target.value)}
                    className="w-full rounded-lg border border-surface-800 bg-surface-900 px-2.5 py-1.5 text-xs text-white"
                  >
                    <option value="auto">Auto GPU/CPU Mode (Recommended)</option>
                    <option value="cuda_only">GPU Only — Diagnostic Mode (Strict CUDA)</option>
                    <option value="cpu">CPU Mode (Local Multithreaded)</option>
                  </select>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-surface-400 font-medium">
                      Custom Vocabulary Hints (Optional)
                    </label>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => setVocabularyHints('محادثة بالعامية المصرية ومصطلحات تقنية وتنظيمية بالإنجليزية.')}
                        className="text-[10px] text-brand-400 hover:text-brand-300 underline font-sans"
                      >
                        + Egyptian Context
                      </button>
                      <span className="text-surface-600">•</span>
                      <button
                        type="button"
                        onClick={() => setVocabularyHints('')}
                        className="text-[10px] text-surface-500 hover:text-surface-400 underline font-sans"
                      >
                        Clear
                      </button>
                    </div>
                  </div>
                  <textarea
                    rows={2}
                    value={vocabularyHints}
                    onChange={e => setVocabularyHints(e.target.value)}
                    placeholder="e.g. محادثة بالعامية المصرية ومصطلحات تقنية وتنظيمية بالإنجليزية."
                    className="w-full rounded-lg border border-surface-800 bg-surface-900 p-2 text-xs text-white placeholder:text-surface-600 focus:outline-none focus:border-brand-500 resize-none font-sans"
                    dir="rtl"
                  />
                  <p className="text-[10px] text-surface-500 mt-1">
                    Factual domain terms to improve recognition without biasing colloquial conversation.
                  </p>
                </div>
              </div>
            )}

            {/* Start Button */}
            <button
              type="button"
              disabled={!uploadedFileId || uploading}
              onClick={handleStartTranscription}
              className="w-full flex items-center justify-center gap-2 rounded-xl bg-brand-600 py-3 text-sm font-bold text-white shadow-lg shadow-brand-500/25 hover:bg-brand-500 disabled:opacity-50 disabled:pointer-events-none transition-all active:scale-[0.98]"
            >
              <Sparkles className="h-4 w-4" />
              <span>{t.startTranscriptionBtn}</span>
            </button>
          </div>
        </div>
      )}

      {/* Failure State Card */}
      {jobError && !isProcessing && (
        <div className="rounded-2xl border border-rose-500/40 bg-rose-950/20 p-8 text-center space-y-5 shadow-2xl max-w-xl mx-auto animate-fadeIn light:bg-rose-50 light:border-rose-200">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-rose-500/10 text-rose-400 border border-rose-500/30">
            <AlertOctagon className="h-8 w-8" />
          </div>
          <div className="space-y-2">
            <h3 className="text-lg font-bold text-rose-300 light:text-rose-900">
              Transcription Failed
            </h3>
            <p className="text-xs text-rose-200/90 light:text-rose-800 max-w-md mx-auto font-mono bg-surface-950/60 light:bg-white p-3 rounded-lg border border-rose-500/20 break-words">
              {jobError}
            </p>
            <p className="text-[11px] text-surface-400 light:text-surface-600">
              Both GPU and CPU processing failed or encountered an unrecoverable format or runtime error.
            </p>
          </div>
          <div className="flex justify-center gap-3">
            <button
              onClick={() => {
                setJobError(null);
                setDeviceMode('cpu');
              }}
              className="rounded-xl border border-surface-700 bg-surface-800 px-4 py-2 text-xs font-semibold text-white hover:bg-surface-700 transition-colors"
            >
              Retry on CPU Only
            </button>
            <button
              onClick={() => setJobError(null)}
              className="rounded-xl bg-brand-600 px-4 py-2 text-xs font-semibold text-white hover:bg-brand-500 transition-colors"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Live Processing Card */}
      {isProcessing && (
        <div className="rounded-2xl border border-surface-800 bg-surface-900/80 p-8 text-center space-y-6 shadow-2xl backdrop-blur-md max-w-xl mx-auto light:border-surface-200 light:bg-white animate-fadeIn">
          <div className="relative mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-brand-500/10 text-brand-400 border border-brand-500/20">
            <Sparkles className="h-10 w-10 animate-spin" />
          </div>

          <div className="space-y-2">
            <h3 className="text-xl font-bold text-white light:text-surface-900">
              {jobStatus?.stage || t.processingTitle}
            </h3>
            <p className="text-xs text-surface-400">
              Running Faster-Whisper local AI model. Please keep this application open.
            </p>
          </div>

          {/* Device & Model Status Badges */}
          <div className="flex flex-wrap items-center justify-center gap-2 text-xs">
            {/* Device Badge */}
            <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full font-semibold border ${
              jobStatus?.stage?.includes('CPU') || jobStatus?.device_used === 'cpu'
                ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
            }`}>
              {jobStatus?.stage?.includes('CPU') || jobStatus?.device_used === 'cpu' ? (
                <>
                  <Cpu className="h-3.5 w-3.5" />
                  <span>Device: CPU Mode</span>
                </>
              ) : (
                <>
                  <Zap className="h-3.5 w-3.5" />
                  <span>Device: GPU (CUDA Accelerated)</span>
                </>
              )}
            </span>

            {/* Model Badge */}
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full font-semibold bg-surface-800/80 text-surface-300 border border-surface-700">
              <span>Model: {jobStatus?.model_used || selectedModel}</span>
            </span>
          </div>

          {/* CUDA Fallback Notification Banner */}
          {(jobStatus?.stage?.includes('Switching to CPU') ||
            jobStatus?.stage?.includes('CPU fallback') ||
            jobStatus?.metadata?.cuda_fallback) && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-left rtl:text-right flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
              <div className="text-xs space-y-0.5">
                <p className="font-bold text-amber-300">GPU Acceleration Fallback Triggered</p>
                <p className="text-amber-200/80">
                  A GPU runtime issue occurred. The pipeline automatically switched to CPU mode without losing previously recognized speech.
                </p>
              </div>
            </div>
          )}

          {/* Progress bar */}
          <div className="space-y-1.5">
            <div className="h-2.5 w-full rounded-full bg-surface-800 overflow-hidden light:bg-surface-200">
              <div
                className="h-full bg-gradient-to-r from-brand-600 to-indigo-500 transition-all duration-300"
                style={{ width: `${Math.round((jobStatus?.progress || 0.1) * 100)}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-surface-400">
              <span className="truncate max-w-[70%] text-left rtl:text-right">Stage: {jobStatus?.stage || 'Preparing'}</span>
              <span className="font-mono font-bold text-brand-400">{Math.round((jobStatus?.progress || 0.1) * 100)}%</span>
            </div>
          </div>

          <button
            onClick={handleCancel}
            className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-2 text-xs font-semibold text-rose-400 hover:bg-rose-500/20 transition-colors"
          >
            {t.cancelBtn}
          </button>
        </div>
      )}

      {/* Synchronized Transcript Review Workspace */}
      {transcriptData && (
        <div className="space-y-6">
          {/* Top Audio Player Header */}
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-brand-500/10 text-brand-400 border border-brand-500/20">
                  <FileAudio className="h-6 w-6" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-white light:text-surface-900">
                    {transcriptData.job.input_filename}
                  </h2>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-surface-400 mt-1">
                    <span>Model: <strong className="text-surface-200">{transcriptData.job.model_used}</strong></span>
                    <span>•</span>
                    <span>Language: <strong className="text-surface-200">{transcriptData.job.metadata?.detected_language?.toUpperCase() || 'Auto'}</strong></span>
                    <span>•</span>
                    <span>{segments.length} segments</span>
                    <span>•</span>
                    <span className="inline-flex items-center gap-1 font-semibold">
                      {transcriptData.job.metadata?.cuda_fallback ? (
                        <span className="text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-md border border-amber-500/30">
                          CPU Fallback (from GPU at {formatTime(transcriptData.job.metadata.cuda_checkpoint_time || 0)})
                        </span>
                      ) : (
                        <span className="text-brand-400">
                          Device: {transcriptData.job.device_used?.toUpperCase() || 'GPU'} ({transcriptData.job.compute_used || 'auto'})
                        </span>
                      )}
                    </span>
                  </div>
                </div>
              </div>

              {/* Action Buttons: Save, Copy, Export */}
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSaveEdits}
                  className={`flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-bold transition-all ${
                    isSaved
                      ? 'border border-surface-800 bg-surface-900 text-surface-400 light:border-surface-200 light:bg-white'
                      : 'bg-emerald-600 text-white shadow-lg shadow-emerald-600/20 hover:bg-emerald-500'
                  }`}
                >
                  <Save className="h-4 w-4" />
                  <span>{isSaved ? 'Saved' : t.saveEditsBtn}</span>
                </button>

                <button
                  onClick={handleCopyTranscript}
                  className="flex items-center gap-1.5 rounded-xl border border-surface-800 bg-surface-900 px-3.5 py-2 text-xs font-bold text-surface-200 hover:bg-surface-800 light:border-surface-200 light:bg-white light:text-surface-800 transition-colors"
                >
                  <Copy className="h-4 w-4" />
                  <span>{t.copyTranscriptBtn}</span>
                </button>

                {/* Export Dropdown */}
                <div className="relative">
                  <button
                    onClick={() => setExportOpen(!exportOpen)}
                    className="flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-xs font-bold text-white shadow-md shadow-brand-500/20 hover:bg-brand-500 transition-colors"
                  >
                    <Download className="h-4 w-4" />
                    <span>{t.exportBtn}</span>
                    <ChevronDown className="h-3.5 w-3.5" />
                  </button>

                  {exportOpen && (
                    <div className="absolute right-0 rtl:left-0 rtl:right-auto mt-2 w-48 rounded-xl border border-surface-800 bg-surface-900 p-2 shadow-2xl z-50 text-xs space-y-1 light:border-surface-200 light:bg-white">
                      <a
                        href={api.getExportUrl(activeJobId!, 'txt', 'clean')}
                        download
                        onClick={() => setExportOpen(false)}
                        className="block px-3 py-2 rounded-lg hover:bg-surface-800 text-surface-200 hover:text-white light:hover:bg-surface-100 light:text-surface-800"
                      >
                        Text (.TXT - Clean)
                      </a>
                      <a
                        href={api.getExportUrl(activeJobId!, 'txt', 'original')}
                        download
                        onClick={() => setExportOpen(false)}
                        className="block px-3 py-2 rounded-lg hover:bg-surface-800 text-surface-200 hover:text-white light:hover:bg-surface-100 light:text-surface-800"
                      >
                        Text (.TXT - Timestamped)
                      </a>
                      <a
                        href={api.getExportUrl(activeJobId!, 'srt')}
                        download
                        onClick={() => setExportOpen(false)}
                        className="block px-3 py-2 rounded-lg hover:bg-surface-800 text-surface-200 hover:text-white light:hover:bg-surface-100 light:text-surface-800"
                      >
                        Subtitles (.SRT)
                      </a>
                      <a
                        href={api.getExportUrl(activeJobId!, 'vtt')}
                        download
                        onClick={() => setExportOpen(false)}
                        className="block px-3 py-2 rounded-lg hover:bg-surface-800 text-surface-200 hover:text-white light:hover:bg-surface-100 light:text-surface-800"
                      >
                        WebVTT (.VTT)
                      </a>
                      <a
                        href={api.getExportUrl(activeJobId!, 'json')}
                        download
                        onClick={() => setExportOpen(false)}
                        className="block px-3 py-2 rounded-lg hover:bg-surface-800 text-surface-200 hover:text-white light:hover:bg-surface-100 light:text-surface-800"
                      >
                        Full Data (.JSON)
                      </a>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Audio Player Component */}
            {uploadedFileId && (
              <AudioPlayer
                ref={playerRef}
                src={api.getAudioStreamUrl(uploadedFileId)}
                onTimeUpdate={setCurrentTime}
              />
            )}
          </div>

          {/* Transcript Tabs: Segments vs Full Text */}
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-surface-800 light:border-surface-200 pb-2">
              <div className="flex gap-2">
                <button
                  onClick={() => setActiveTab('segments')}
                  className={`px-4 py-2 text-xs font-bold rounded-lg transition-colors ${
                    activeTab === 'segments'
                      ? 'bg-brand-500/10 text-brand-400 border border-brand-500/20'
                      : 'text-surface-400 hover:text-white light:text-surface-600'
                  }`}
                >
                  {t.tabSegments} ({segments.length})
                </button>
                <button
                  onClick={() => setActiveTab('clean')}
                  className={`px-4 py-2 text-xs font-bold rounded-lg transition-colors ${
                    activeTab === 'clean'
                      ? 'bg-brand-500/10 text-brand-400 border border-brand-500/20'
                      : 'text-surface-400 hover:text-white light:text-surface-600'
                  }`}
                >
                  {t.tabCleanText}
                </button>
              </div>

              <span className="text-xs text-surface-400 hidden sm:block">
                {t.seekToSpeech}
              </span>
            </div>

            {/* Tab 1: Segments List */}
            {activeTab === 'segments' ? (
              <div className="space-y-3">
                {segments.map(seg => {
                  const isCurrent = currentTime >= seg.start && currentTime <= seg.end;
                  return (
                    <div
                      key={seg.id}
                      className={`group rounded-xl border p-4 transition-all duration-200 ${
                        isCurrent
                          ? 'border-brand-500 bg-brand-500/10 ring-1 ring-brand-500 shadow-md'
                          : 'border-surface-800 bg-surface-900/40 hover:border-surface-700 light:border-surface-200 light:bg-white'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        {/* Clickable timestamp */}
                        <button
                          onClick={() => playerRef.current?.seekTo(seg.start)}
                          className="flex items-center gap-1.5 rounded-md bg-surface-800 px-2.5 py-1 text-xs font-mono font-semibold text-brand-400 hover:bg-brand-600 hover:text-white transition-colors light:bg-surface-100"
                          title="Click to jump to this audio position"
                        >
                          <Play className="h-3 w-3 fill-current" />
                          <span>{formatTime(seg.start)} — {formatTime(seg.end)}</span>
                        </button>

                        <div className="flex items-center gap-2">
                          {seg.uncertain && (
                            <span
                              className="flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold text-amber-400 border border-amber-500/20"
                              title={seg.uncertain_reason ? `Flagged: ${seg.uncertain_reason}` : 'Uncertain segment'}
                            >
                              <AlertTriangle className="h-3 w-3" />
                              {t.uncertainBadge}
                              {seg.uncertain_reason && (
                                <span className="opacity-75 font-normal">
                                  ({seg.uncertain_reason.replace(/_/g, ' ')})
                                </span>
                              )}
                            </span>
                          )}
                          <span className="text-[11px] font-mono text-surface-500">#{seg.id}</span>
                        </div>
                      </div>

                      {/* Editable Text Area for Segment */}
                      <textarea
                        rows={2}
                        value={seg.text}
                        onChange={e => handleSegmentTextChange(seg.id, e.target.value)}
                        className="w-full resize-none rounded-lg bg-transparent p-1.5 text-sm text-surface-100 light:text-surface-900 focus:bg-surface-950/50 focus:outline-none focus:ring-1 focus:ring-brand-500 leading-relaxed font-sans"
                        dir="auto"
                      />
                    </div>
                  );
                })}
              </div>
            ) : (
              /* Tab 2: Full Clean Text */
              <div className="rounded-xl border border-surface-800 bg-surface-900/40 p-6 light:border-surface-200 light:bg-white space-y-4">
                <textarea
                  rows={14}
                  value={cleanText}
                  onChange={e => {
                    setCleanText(e.target.value);
                    setIsSaved(false);
                  }}
                  className="w-full resize-y rounded-xl bg-surface-950 p-4 text-sm text-surface-100 light:bg-surface-50 light:text-surface-900 focus:outline-none focus:ring-1 focus:ring-brand-500 leading-relaxed font-sans"
                  dir="auto"
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
