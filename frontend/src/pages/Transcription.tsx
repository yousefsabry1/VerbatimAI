import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useI18n } from '../context/I18nContext';
import { AudioMetadata, HardwareInfo, Job, ModelInfo, Segment, TranscriptResult } from '../types';
import { api } from '../services/api';
import { AudioPlayer, AudioPlayerRef } from '../components/AudioPlayer';
import {
  UploadCloud,
  FileAudio,
  Play,
  Pause,
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
  Repeat,
  Undo2,
  Redo2,
  Keyboard,
  RefreshCw,
  PlusCircle,
  FileText,
  AlertCircle,
  Columns,
  List,
} from 'lucide-react';

interface TranscriptionProps {
  initialJobId?: string | null;
  onJobActive?: (jobId: string) => void;
  onClearInitialJob?: () => void;
  hardware: HardwareInfo | null;
}

type ReviewMode = 'corrected' | 'original' | 'diff';
type SaveStatus = 'saved' | 'saving' | 'unsaved' | 'error' | 'draft_restored';

interface AlternativeSuggestionState {
  loading: boolean;
  modelName: string;
  suggestedText: string | null;
  error?: string | null;
}

export const Transcription: React.FC<TranscriptionProps> = ({
  initialJobId,
  onJobActive,
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
  const [accuracyMode, setAccuracyMode] = useState<'balanced' | 'maximum'>('maximum');
  const [enhanceAudio, setEnhanceAudio] = useState<boolean>(false);
  const [vadFilter, setVadFilter] = useState<boolean>(false); // False is recommended for Egyptian audio
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
  const [originalSegments, setOriginalSegments] = useState<Segment[]>([]);
  const [originalCleanText, setOriginalCleanText] = useState<string>('');

  // Editor Modes & Options
  const [reviewMode, setReviewMode] = useState<ReviewMode>('corrected');
  const [activeTab, setActiveTab] = useState<'segments' | 'clean'>('segments');
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [activeSegmentId, setActiveSegmentId] = useState<number | null>(null);
  const [autoScroll, setAutoScroll] = useState<boolean>(true);
  const [loopingSegmentId, setLoopingSegmentId] = useState<number | null>(null);

  // Save & Autosave State
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('saved');
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [draftRecovered, setDraftRecovered] = useState<boolean>(false);
  const [exportOpen, setExportOpen] = useState<boolean>(false);
  const [exportVersion, setExportVersion] = useState<'edited' | 'original'>('edited');
  const [showShortcutsModal, setShowShortcutsModal] = useState<boolean>(false);

  // Undo / Redo History Stack
  const [history, setHistory] = useState<Segment[][]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);

  // Alternative Model Suggestions Map (segmentId -> AlternativeSuggestionState)
  const [alternativeMap, setAlternativeMap] = useState<{ [segmentId: number]: AlternativeSuggestionState }>({});

  // Element refs for segment scrolling
  const segmentRefs = useRef<{ [key: number]: HTMLDivElement | null }>({});
  const autosaveTimerRef = useRef<any>(null);

  // Load models & recommended hardware defaults
  useEffect(() => {
    api.getModels().then(res => {
      setModels(res.models);
      const cs = res.models.find(m => m.id === 'codeswitched-medium');
      if (cs && cs.is_downloaded) {
        setSelectedModel('codeswitched-medium');
      } else {
        const downloaded = res.models.find(m => m.is_downloaded);
        if (downloaded) setSelectedModel(downloaded.id);
        else if (hardware?.recommended?.model) setSelectedModel(hardware.recommended.model);
      }
    }).catch(console.error);
  }, [hardware]);

  // Session Recovery on Mount / Tab Switch
  useEffect(() => {
    if (transcriptData || isProcessing) return;

    try {
      const urlJobId = new URLSearchParams(window.location.search).get('job_id');
      const storedJobId = localStorage.getItem('verbatim_active_job_id');
      const targetJobId = initialJobId || urlJobId || storedJobId;

      if (targetJobId && targetJobId !== activeJobId) {
        loadCompletedJob(targetJobId);
      }
    } catch (e) {
      console.warn('Session restoration check failed:', e);
    }
  }, [initialJobId]);

  // Window beforeunload prompt if unsaved changes exist
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (saveStatus === 'unsaved' || saveStatus === 'saving') {
        e.preventDefault();
        e.returnValue = 'You have unsaved changes in your transcript. Are you sure you want to leave?';
        return e.returnValue;
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [saveStatus]);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const loadCompletedJob = async (jobId: string) => {
    try {
      const res = await api.getTranscriptionResult(jobId);
      if (!res.is_complete || !res.segments) {
        console.warn('Job is not completed yet:', res);
        return;
      }

      setTranscriptData(res);
      setActiveJobId(jobId);
      setUploadedFileId(jobId);
      setIsProcessing(false);

      if (onJobActive) onJobActive(jobId);
      localStorage.setItem('verbatim_active_job_id', jobId);

      // Hydrate metadata duration
      if (res.job?.input_duration) {
        setFileMetadata({
          duration: res.job.input_duration,
          duration_formatted: formatTime(res.job.input_duration),
          sample_rate: 16000,
          channels: 1,
          channel_layout: 'Mono',
          codec: 'opus',
          bitrate: 0,
          bitrate_kbps: null,
          format: res.job.input_format || 'audio',
          size: res.job.input_size || 0,
          size_formatted: '',
          is_valid_audio: true,
          has_video: false,
        });
      }

      const serverSegments: Segment[] = (res.segments || []).map((s: any) => ({
        ...s,
        original_text: s.original_text || s.text,
      }));

      setOriginalSegments(serverSegments);
      setOriginalCleanText(res.original_text || res.clean_text || '');

      // Check LocalStorage Draft Recovery
      const draftKey = `verbatim_draft_${jobId}`;
      const savedDraft = localStorage.getItem(draftKey);
      let loadedSegments = serverSegments;

      if (savedDraft) {
        try {
          const parsed = JSON.parse(savedDraft);
          if (Array.isArray(parsed) && parsed.length === serverSegments.length) {
            const hasDifference = parsed.some((pSeg, idx) => pSeg.text !== serverSegments[idx]?.text);
            if (hasDifference) {
              loadedSegments = parsed;
              setDraftRecovered(true);
              setSaveStatus('draft_restored');
              showToast('Restored your unsaved draft session from local storage!');
            }
          }
        } catch (e) {
          console.error('Failed to parse local draft:', e);
        }
      }

      setSegments(loadedSegments);
      setCleanText(loadedSegments.map(s => s.text).join(' '));
      setHistory([loadedSegments]);
      setHistoryIndex(0);
      if (!draftRecovered) {
        setSaveStatus('saved');
      }
    } catch (err) {
      console.error('Failed to load completed transcript', err);
      localStorage.removeItem('verbatim_active_job_id');
      if (onClearInitialJob) onClearInitialJob();
    }
  };

  const handleDiscardDraft = () => {
    if (!activeJobId) return;
    localStorage.removeItem(`verbatim_draft_${activeJobId}`);
    setSegments(originalSegments);
    setCleanText(originalCleanText);
    setHistory([originalSegments]);
    setHistoryIndex(0);
    setDraftRecovered(false);
    setSaveStatus('saved');
    showToast('Draft discarded. Restored original ASR transcript.');
  };

  const handleNewTranscription = () => {
    if (saveStatus === 'unsaved') {
      if (!window.confirm('You have unsaved changes. Are you sure you want to start a new transcription?')) {
        return;
      }
    }
    setTranscriptData(null);
    setActiveJobId(null);
    setSelectedFile(null);
    setUploadedFileId(null);
    setSegments([]);
    setCleanText('');
    setOriginalSegments([]);
    setDraftRecovered(false);
    setSaveStatus('saved');
    localStorage.removeItem('verbatim_active_job_id');
    if (onClearInitialJob) onClearInitialJob();
  };

  // Push state to Undo History
  const pushHistory = useCallback((newSegments: Segment[]) => {
    setHistory(prev => {
      const sliced = prev.slice(0, historyIndex + 1);
      const next = [...sliced, newSegments];
      if (next.length > 40) next.shift();
      return next;
    });
    setHistoryIndex(prev => Math.min(prev + 1, 39));
  }, [historyIndex]);

  const handleUndo = useCallback(() => {
    if (historyIndex > 0) {
      const targetState = history[historyIndex - 1];
      setHistoryIndex(prev => prev - 1);
      setSegments(targetState);
      setCleanText(targetState.map(s => s.text).join(' '));
      setSaveStatus('unsaved');
      if (activeJobId) {
        localStorage.setItem(`verbatim_draft_${activeJobId}`, JSON.stringify(targetState));
      }
      showToast('Undo');
    }
  }, [historyIndex, history, activeJobId]);

  const handleRedo = useCallback(() => {
    if (historyIndex < history.length - 1) {
      const targetState = history[historyIndex + 1];
      setHistoryIndex(prev => prev + 1);
      setSegments(targetState);
      setCleanText(targetState.map(s => s.text).join(' '));
      setSaveStatus('unsaved');
      if (activeJobId) {
        localStorage.setItem(`verbatim_draft_${activeJobId}`, JSON.stringify(targetState));
      }
      showToast('Redo');
    }
  }, [historyIndex, history, activeJobId]);

  // Debounced Autosave (1.5 seconds after typing stops)
  useEffect(() => {
    if (saveStatus === 'unsaved' && activeJobId && segments.length > 0) {
      if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);

      autosaveTimerRef.current = setTimeout(async () => {
        setSaveStatus('saving');
        try {
          const computedClean = segments.map(s => s.text).join(' ');
          await api.updateTranscriptSegments(activeJobId, computedClean, segments);
          setSaveStatus('saved');
        } catch (e) {
          console.error('Autosave error:', e);
          setSaveStatus('error');
        }
      }, 1500);
    }

    return () => {
      if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    };
  }, [segments, saveStatus, activeJobId]);

  // Track active segment by currentTime
  useEffect(() => {
    const active = segments.find(s => currentTime >= s.start && currentTime <= s.end);
    if (active) {
      setActiveSegmentId(active.id);
      if (autoScroll && segmentRefs.current[active.id]) {
        segmentRefs.current[active.id]?.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest',
        });
      }
    } else {
      setActiveSegmentId(null);
    }
  }, [currentTime, segments, autoScroll]);

  // Global Keyboard Shortcuts (Non-conflicting with Windows browser navigation)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isTyping = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA';

      // Alt+Space or Space (when not typing in textarea): Play / Pause
      if ((e.code === 'Space' && !isTyping) || (e.altKey && e.code === 'Space')) {
        e.preventDefault();
        playerRef.current?.togglePlay();
        return;
      }

      // Shift+Left / Shift+Right: Skip 5s (safe on Windows)
      if (e.shiftKey && e.key === 'ArrowLeft') {
        e.preventDefault();
        playerRef.current?.seekRelative(-5);
        return;
      }
      if (e.shiftKey && e.key === 'ArrowRight') {
        e.preventDefault();
        playerRef.current?.seekRelative(5);
        return;
      }

      // Alt+Up / Alt+Down: Previous / Next Segment
      if (e.altKey && e.key === 'ArrowUp') {
        e.preventDefault();
        handleNavigateSegment('prev');
        return;
      }
      if (e.altKey && e.key === 'ArrowDown') {
        e.preventDefault();
        handleNavigateSegment('next');
        return;
      }

      // Alt+L: Loop active segment
      if (e.altKey && (e.key === 'l' || e.key === 'L')) {
        e.preventDefault();
        handleToggleLoopCurrentSegment();
        return;
      }

      // Ctrl+S / Cmd+S: Save immediately to database
      if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
        e.preventDefault();
        handleSaveEdits();
        return;
      }

      // Ctrl+Z / Ctrl+Y: Undo / Redo
      if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z') && !e.shiftKey) {
        if (!isTyping) {
          e.preventDefault();
          handleUndo();
        }
      }
      if ((e.ctrlKey || e.metaKey) && ((e.key === 'y' || e.key === 'Y') || (e.shiftKey && (e.key === 'z' || e.key === 'Z')))) {
        if (!isTyping) {
          e.preventDefault();
          handleRedo();
        }
      }

      // Question mark (?): open shortcuts modal
      if (e.key === '?' && !isTyping) {
        e.preventDefault();
        setShowShortcutsModal(true);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeSegmentId, segments, handleUndo, handleRedo]);

  const handleNavigateSegment = (direction: 'prev' | 'next') => {
    if (segments.length === 0) return;
    const currentIdx = activeSegmentId ? segments.findIndex(s => s.id === activeSegmentId) : 0;
    let targetIdx = direction === 'next' ? currentIdx + 1 : currentIdx - 1;
    if (targetIdx < 0) targetIdx = 0;
    if (targetIdx >= segments.length) targetIdx = segments.length - 1;

    const targetSeg = segments[targetIdx];
    if (targetSeg) {
      playerRef.current?.seekTo(targetSeg.start);
    }
  };

  const handleToggleLoopCurrentSegment = () => {
    if (!activeSegmentId) return;
    const currentSeg = segments.find(s => s.id === activeSegmentId);
    if (!currentSeg) return;

    if (loopingSegmentId === currentSeg.id) {
      playerRef.current?.clearLoop();
      setLoopingSegmentId(null);
      showToast('Loop cleared');
    } else {
      playerRef.current?.loopSegment(currentSeg.start, currentSeg.end);
      setLoopingSegmentId(currentSeg.id);
      showToast(`Looping Segment #${currentSeg.id} (${formatTime(currentSeg.start)} — ${formatTime(currentSeg.end)})`);
    }
  };

  const handleLoopSpecificSegment = (seg: Segment) => {
    if (loopingSegmentId === seg.id) {
      playerRef.current?.clearLoop();
      setLoopingSegmentId(null);
      showToast('Loop cleared');
    } else {
      playerRef.current?.loopSegment(seg.start, seg.end);
      setLoopingSegmentId(seg.id);
      showToast(`Looping Segment #${seg.id} (${formatTime(seg.start)} — ${formatTime(seg.end)})`);
    }
  };

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

  const handleStartTranscription = async () => {
    if (!uploadedFileId) return;

    setIsProcessing(true);
    setJobError(null);
    setTranscriptData(null);
    setDraftRecovered(false);

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
        vocabulary_hints: vocabularyHints || undefined,
      });

      setActiveJobId(res.job_id);
      localStorage.setItem('verbatim_active_job_id', res.job_id);
      if (onJobActive) onJobActive(res.job_id);
      pollJobStatus(res.job_id);
    } catch (err: any) {
      setIsProcessing(false);
      setJobError(err.message || 'Transcription submission failed');
    }
  };

  const pollJobStatus = async (jobId: string) => {
    const interval = setInterval(async () => {
      try {
        const job = await api.getTranscriptionStatus(jobId);
        setJobStatus(job);

        if (job.status === 'completed') {
          clearInterval(interval);
          loadCompletedJob(jobId);
        } else if (job.status === 'failed') {
          clearInterval(interval);
          setIsProcessing(false);
          setJobError(job.error_message || 'Transcription processing failed');
        }
      } catch (err) {
        console.error('Job polling error:', err);
      }
    }, 1000);
  };

  const handleSegmentTextChange = (segId: number, newText: string) => {
    const updated = segments.map(s => (s.id === segId ? { ...s, text: newText } : s));
    setSegments(updated);
    setCleanText(updated.map(s => s.text).join(' '));
    pushHistory(updated);
    setSaveStatus('unsaved');

    // Instant local draft protection
    if (activeJobId) {
      localStorage.setItem(`verbatim_draft_${activeJobId}`, JSON.stringify(updated));
    }
  };

  const handleRevertSegment = (segId: number) => {
    const orig = originalSegments.find(s => s.id === segId);
    if (!orig) return;

    const updated = segments.map(s => (s.id === segId ? { ...s, text: orig.original_text || orig.text } : s));
    setSegments(updated);
    setCleanText(updated.map(s => s.text).join(' '));
    pushHistory(updated);
    setSaveStatus('unsaved');

    if (activeJobId) {
      localStorage.setItem(`verbatim_draft_${activeJobId}`, JSON.stringify(updated));
    }
    showToast(`Segment #${segId} reverted to original ASR prediction`);
  };

  const handleSaveEdits = async () => {
    if (!activeJobId) return;

    setSaveStatus('saving');
    try {
      const computedClean = segments.map(s => s.text).join(' ');
      await api.updateTranscriptSegments(activeJobId, computedClean, segments);
      setSaveStatus('saved');
      showToast('All changes saved to database!');
    } catch (err: any) {
      console.error(err);
      setSaveStatus('error');
      alert(err.message || 'Failed to save changes to database');
    }
  };

  const handleCopyTranscript = () => {
    const textToCopy =
      activeTab === 'clean'
        ? cleanText
        : segments.map(s => `[${formatTime(s.start)} - ${formatTime(s.end)}] ${s.text}`).join('\n');

    navigator.clipboard.writeText(textToCopy);
    showToast(t.copiedToast || 'Copied transcript to clipboard!');
  };

  // Alternative Model Suggestion on specific difficult segment
  const handleRequestAlternative = async (seg: Segment, targetModelId: string = 'large-v3-turbo') => {
    if (!activeJobId) return;

    setAlternativeMap(prev => ({
      ...prev,
      [seg.id]: {
        loading: true,
        modelName: targetModelId === 'large-v3-turbo' ? 'Whisper Large-v3-Turbo' : 'Specialized Medium',
        suggestedText: null,
      },
    }));

    try {
      const res = await api.suggestAlternativeSegment({
        job_id: activeJobId,
        start: seg.start,
        end: seg.end,
        model_id: targetModelId,
      });

      setAlternativeMap(prev => ({
        ...prev,
        [seg.id]: {
          loading: false,
          modelName: res.model_name,
          suggestedText: res.suggested_text,
        },
      }));
      showToast(`Alternative candidate generated by ${res.model_name}`);
    } catch (e: any) {
      setAlternativeMap(prev => ({
        ...prev,
        [seg.id]: {
          loading: false,
          modelName: targetModelId,
          suggestedText: null,
          error: e.message || 'Failed to generate suggestion',
        },
      }));
    }
  };

  const handleApplyAlternative = (segId: number, text: string) => {
    handleSegmentTextChange(segId, text);
    setAlternativeMap(prev => {
      const copy = { ...prev };
      delete copy[segId];
      return copy;
    });
    showToast(`Applied alternative candidate to Segment #${segId}`);
  };

  const handleDismissAlternative = (segId: number) => {
    setAlternativeMap(prev => {
      const copy = { ...prev };
      delete copy[segId];
      return copy;
    });
  };

  const formatTime = (secs: number) => {
    if (isNaN(secs) || !isFinite(secs) || secs < 0) return '00:00';
    const s = Math.floor(secs);
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m.toString().padStart(2, '0')}:${r.toString().padStart(2, '0')}`;
  };

  const activeDuration = transcriptData?.job?.input_duration || fileMetadata?.duration || 0;
  const activeFilename = transcriptData?.job?.input_filename || selectedFile?.name || 'Recording';

  return (
    <div className="space-y-6 animate-fadeIn pb-16">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-3 text-sm font-semibold text-white shadow-2xl animate-bounce">
          <CheckCircle2 className="h-4 w-4" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Keyboard Shortcuts Modal */}
      {showShortcutsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-fadeIn">
          <div className="w-full max-w-md rounded-2xl border border-surface-800 bg-surface-900 p-6 shadow-2xl space-y-4 light:border-surface-200 light:bg-white">
            <div className="flex items-center justify-between border-b border-surface-800 pb-3 light:border-surface-200">
              <h3 className="text-base font-bold text-white light:text-surface-900 flex items-center gap-2">
                <Keyboard className="h-5 w-5 text-brand-400" />
                <span>Keyboard Shortcuts Reference</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowShortcutsModal(false)}
                className="text-surface-400 hover:text-white p-1 rounded-lg"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between p-2 rounded-lg bg-surface-950/60 border border-surface-800/80 light:bg-surface-50 light:border-surface-200">
                <span className="text-surface-300 light:text-surface-700">Play / Pause Audio</span>
                <kbd className="px-2 py-0.5 rounded bg-surface-800 font-mono text-brand-300 border border-surface-700 light:bg-surface-200 light:text-surface-800">Space</kbd>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-surface-950/60 border border-surface-800/80 light:bg-surface-50 light:border-surface-200">
                <span className="text-surface-300 light:text-surface-700">Play / Pause (inside Editor)</span>
                <kbd className="px-2 py-0.5 rounded bg-surface-800 font-mono text-brand-300 border border-surface-700 light:bg-surface-200 light:text-surface-800">Alt + Space</kbd>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-surface-950/60 border border-surface-800/80 light:bg-surface-50 light:border-surface-200">
                <span className="text-surface-300 light:text-surface-700">Jump -5s / +5s</span>
                <kbd className="px-2 py-0.5 rounded bg-surface-800 font-mono text-brand-300 border border-surface-700 light:bg-surface-200 light:text-surface-800">Shift + ← / →</kbd>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-surface-950/60 border border-surface-800/80 light:bg-surface-50 light:border-surface-200">
                <span className="text-surface-300 light:text-surface-700">Previous / Next Segment</span>
                <kbd className="px-2 py-0.5 rounded bg-surface-800 font-mono text-brand-300 border border-surface-700 light:bg-surface-200 light:text-surface-800">Alt + ↑ / ↓</kbd>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-surface-950/60 border border-surface-800/80 light:bg-surface-50 light:border-surface-200">
                <span className="text-surface-300 light:text-surface-700">Loop Current Segment</span>
                <kbd className="px-2 py-0.5 rounded bg-surface-800 font-mono text-brand-300 border border-surface-700 light:bg-surface-200 light:text-surface-800">Alt + L</kbd>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-surface-950/60 border border-surface-800/80 light:bg-surface-50 light:border-surface-200">
                <span className="text-surface-300 light:text-surface-700">Undo Changes</span>
                <kbd className="px-2 py-0.5 rounded bg-surface-800 font-mono text-brand-300 border border-surface-700 light:bg-surface-200 light:text-surface-800">Ctrl + Z</kbd>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-surface-950/60 border border-surface-800/80 light:bg-surface-50 light:border-surface-200">
                <span className="text-surface-300 light:text-surface-700">Redo Changes</span>
                <kbd className="px-2 py-0.5 rounded bg-surface-800 font-mono text-brand-300 border border-surface-700 light:bg-surface-200 light:text-surface-800">Ctrl + Y</kbd>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-surface-950/60 border border-surface-800/80 light:bg-surface-50 light:border-surface-200">
                <span className="text-surface-300 light:text-surface-700">Save Edits to Database</span>
                <kbd className="px-2 py-0.5 rounded bg-surface-800 font-mono text-brand-300 border border-surface-700 light:bg-surface-200 light:text-surface-800">Ctrl + S</kbd>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setShowShortcutsModal(false)}
              className="w-full py-2 bg-brand-600 text-white rounded-xl font-bold text-xs hover:bg-brand-500 transition-colors"
            >
              Close Shortcuts
            </button>
          </div>
        </div>
      )}

      {/* Page Title & Controls Header */}
      <div className="space-y-1">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-black text-white light:text-surface-900 flex items-center gap-2.5">
              <FileAudio className="h-7 w-7 text-brand-400" />
              <span>AI Transcription & Review</span>
            </h1>
            <p className="text-xs sm:text-sm text-surface-400 light:text-surface-600">
              Transcribe, review, and export every word with confidence.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowShortcutsModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-surface-700 bg-surface-800 text-xs font-semibold text-surface-200 hover:text-white light:border-surface-300 light:bg-white light:text-surface-700 transition-colors"
              title="View Keyboard Shortcuts (?)"
            >
              <Keyboard className="h-3.5 w-3.5 text-brand-400" />
              <span>Shortcuts</span>
            </button>

            {transcriptData && (
              <button
                type="button"
                onClick={handleNewTranscription}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-brand-600/20 border border-brand-500/40 text-xs font-bold text-brand-300 hover:bg-brand-600/30 transition-colors"
                title="Start a new transcription"
              >
                <PlusCircle className="h-3.5 w-3.5 text-brand-400" />
                <span>New Transcription</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Draft Recovery Notification Banner */}
      {draftRecovered && (
        <div className="p-3.5 rounded-2xl bg-brand-500/10 border border-brand-500/30 flex items-center justify-between text-xs text-brand-200 animate-fadeIn">
          <div className="flex items-center gap-2">
            <Info className="h-4 w-4 text-brand-400 shrink-0" />
            <span>
              <strong>Restored Local Session:</strong> We restored your recent uncommitted edits from local storage.
            </span>
          </div>
          <button
            type="button"
            onClick={handleDiscardDraft}
            className="px-3 py-1 rounded-lg bg-surface-800 text-surface-300 hover:text-white hover:bg-surface-700 font-semibold text-[11px]"
          >
            Discard Draft & Revert to ASR
          </button>
        </div>
      )}

      {/* Transcription Setup Section (If no active completed transcript) */}
      {!transcriptData && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* File Upload Area */}
          <div className="lg:col-span-1 rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-4">
            <h3 className="text-sm font-bold text-white light:text-surface-900 flex items-center gap-2">
              <UploadCloud className="h-4 w-4 text-brand-400" />
              <span>Audio Upload</span>
            </h3>

            <div
              onDragOver={e => e.preventDefault()}
              onDrop={handleFileDrop}
              className={`border-2 border-dashed rounded-2xl p-6 text-center cursor-pointer transition-all ${
                selectedFile
                  ? 'border-brand-500/60 bg-brand-500/5'
                  : 'border-surface-700 hover:border-brand-500/50 bg-surface-950/40'
              }`}
            >
              <input
                type="file"
                id="audio-upload-input"
                className="hidden"
                accept="audio/*,video/*,.ogg,.mp3,.wav,.m4a,.flac"
                onChange={e => e.target.files && e.target.files[0] && handleFileUpload(e.target.files[0])}
              />
              <label htmlFor="audio-upload-input" className="cursor-pointer block space-y-2">
                <FileAudio className="h-10 w-10 text-brand-400 mx-auto" />
                <span className="text-xs font-bold text-white block">
                  {selectedFile ? selectedFile.name : 'Choose audio recording or drag & drop'}
                </span>
                <span className="text-[11px] text-surface-400 block">
                  Supports WhatsApp Voice Notes (.ogg), MP3, WAV, M4A, FLAC
                </span>
              </label>
            </div>

            {uploading && (
              <div className="flex items-center justify-center gap-2 text-xs text-brand-400 py-2">
                <RefreshCw className="h-4 w-4 animate-spin" />
                <span>Uploading and extracting audio metadata...</span>
              </div>
            )}

            {fileMetadata && (
              <div className="rounded-xl border border-surface-800 bg-surface-950/60 p-3 space-y-2 text-xs">
                <div className="flex justify-between font-semibold text-white">
                  <span>File:</span>
                  <span className="truncate max-w-[180px]">{selectedFile?.name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-surface-500">Format:</span>
                  <span className="uppercase font-mono text-brand-300">{fileMetadata.format} ({fileMetadata.codec})</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-surface-500">Duration:</span>
                  <span className="font-mono">{fileMetadata.duration_formatted}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-surface-500">Sample Rate:</span>
                  <span>{fileMetadata.sample_rate} Hz</span>
                </div>
              </div>
            )}
          </div>

          {/* Model & Processing Options */}
          <div className="lg:col-span-2 rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-5">
            <h3 className="text-sm font-bold text-white light:text-surface-900 flex items-center gap-2">
              <Sliders className="h-4 w-4 text-brand-400" />
              <span>ASR Engine & Acoustic Preset</span>
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Model Selection */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-surface-300">Whisper Model:</label>
                <select
                  value={selectedModel}
                  onChange={e => setSelectedModel(e.target.value)}
                  className="w-full rounded-xl border border-surface-700 bg-surface-950 p-2.5 text-xs text-white focus:border-brand-500 focus:outline-none"
                >
                  {models.map(m => (
                    <option key={m.id} value={m.id}>
                      {m.name} ({m.is_downloaded ? 'Downloaded' : 'Download Needed'})
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-surface-400">
                  Recommended: <strong>Egyptian Arabic & English (Specialized)</strong> for local colloquial voice notes.
                </p>
              </div>

              {/* Language Selection */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-surface-300">Spoken Language:</label>
                <select
                  value={language}
                  onChange={e => setLanguage(e.target.value)}
                  className="w-full rounded-xl border border-surface-700 bg-surface-950 p-2.5 text-xs text-white focus:border-brand-500 focus:outline-none"
                >
                  <option value="ar">Arabic (العربية)</option>
                  <option value="en">English</option>
                  <option value="auto">Auto-Detect</option>
                </select>
              </div>

              {/* Verbatim Mode */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-surface-300">Transcription Mode:</label>
                <select
                  value={verbatimMode}
                  onChange={e => setVerbatimMode(e.target.value as any)}
                  className="w-full rounded-xl border border-surface-700 bg-surface-950 p-2.5 text-xs text-white focus:border-brand-500 focus:outline-none"
                >
                  <option value="strict">Strict Verbatim (Word-for-Word, No Filtering)</option>
                  <option value="clean">Clean Verbatim (Filtered Fillers)</option>
                </select>
              </div>

              {/* Accuracy Mode */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-surface-300">Accuracy & Beam Search:</label>
                <select
                  value={accuracyMode}
                  onChange={e => setAccuracyMode(e.target.value as any)}
                  className="w-full rounded-xl border border-surface-700 bg-surface-950 p-2.5 text-xs text-white focus:border-brand-500 focus:outline-none"
                >
                  <option value="maximum">Maximum Accuracy (Beam Size 5, High Context)</option>
                  <option value="balanced">Balanced (Fast, Beam Size 3)</option>
                </select>
              </div>
            </div>

            {/* Egyptian Audio Preset Info Card */}
            <div className="rounded-xl border border-brand-500/20 bg-brand-500/5 p-3.5 text-xs text-surface-300 space-y-1">
              <div className="flex items-center gap-2 text-brand-300 font-bold">
                <Zap className="h-4 w-4" />
                <span>Egyptian Arabic Preset Applied</span>
              </div>
              <p className="text-[11px] text-surface-400">
                Acoustic VAD filter is set to <strong>OFF</strong> by default for WhatsApp voice notes to preserve quiet Egyptian utterances and code-switched terms.
              </p>
            </div>

            {/* Advanced Settings Toggle */}
            <div className="pt-1">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="text-xs font-semibold text-brand-400 hover:text-brand-300 flex items-center gap-1"
              >
                <span>{showAdvanced ? 'Hide Advanced Settings' : 'Show Advanced Settings'}</span>
                <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
              </button>

              {showAdvanced && (
                <div className="mt-3 p-3.5 rounded-xl border border-surface-800 bg-surface-950 space-y-3 text-xs animate-fadeIn">
                  <div className="flex items-center justify-between">
                    <span>Voice Activity Detection (VAD):</span>
                    <input
                      type="checkbox"
                      checked={vadFilter}
                      onChange={e => setVadFilter(e.target.checked)}
                      className="rounded accent-brand-500 h-4 w-4"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="block text-surface-400">Contextual Vocabulary Hints (comma-separated):</label>
                    <input
                      type="text"
                      placeholder="e.g. IEEE, CIS, Proposal, Collaboration"
                      value={vocabularyHints}
                      onChange={e => setVocabularyHints(e.target.value)}
                      className="w-full rounded-lg border border-surface-800 bg-surface-900 p-2 text-xs text-white"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Submit Action Button */}
            <div className="pt-2">
              <button
                type="button"
                disabled={!uploadedFileId || isProcessing}
                onClick={handleStartTranscription}
                className="w-full py-3.5 px-6 rounded-xl bg-gradient-to-r from-brand-600 to-indigo-600 text-white font-bold text-sm shadow-xl shadow-brand-500/20 hover:from-brand-500 hover:to-indigo-500 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
              >
                {isProcessing ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    <span>Processing with GPU Acceleration...</span>
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 fill-current" />
                    <span>Start Transcription with CUDA Acceleration</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Live Processing Card */}
      {isProcessing && jobStatus && (
        <div className="p-6 rounded-2xl border border-brand-500/40 bg-surface-900/80 space-y-4 shadow-2xl animate-fadeIn">
          <div className="flex items-center justify-between text-xs font-semibold">
            <span className="text-white flex items-center gap-2">
              <RefreshCw className="h-4 w-4 animate-spin text-brand-400" />
              <span>{jobStatus.stage || 'Transcribing audio...'}</span>
            </span>
            <span className="font-mono text-brand-300">{Math.round((jobStatus.progress || 0) * 100)}%</span>
          </div>

          <div className="h-2 w-full rounded-full bg-surface-800 overflow-hidden">
            <div
              className="h-full bg-brand-500 transition-all duration-300"
              style={{ width: `${Math.round((jobStatus.progress || 0) * 100)}%` }}
            />
          </div>
        </div>
      )}

      {/* Error Banner */}
      {jobError && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-rose-400 shrink-0" />
            <span>{jobError}</span>
          </div>
          <button type="button" onClick={() => setJobError(null)} className="text-rose-400 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* ========================================================================= */}
      {/* PROFESSIONAL TRANSCRIPT REVIEW WORKSPACE */}
      {/* ========================================================================= */}
      {transcriptData && (
        <div className="space-y-6 animate-fadeIn">
          {/* Top Review Header & Audio Player Container */}
          <div className="rounded-2xl border border-surface-800 bg-surface-900/60 p-5 space-y-4 light:border-surface-200 light:bg-white shadow-xl">
            {/* Review Header Metadata & Save Status */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-800/80 pb-3 light:border-surface-200">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="font-bold text-white light:text-surface-900 text-sm flex items-center gap-1.5">
                  <FileText className="h-4 w-4 text-brand-400" />
                  <span>Transcript Review</span>
                </span>
                <span className="text-surface-500">•</span>
                <span className="rounded-lg bg-surface-800 px-2 py-0.5 font-medium text-surface-300 light:bg-surface-100 light:text-surface-700">
                  {activeFilename}
                </span>
                <span className="rounded-lg bg-surface-800 px-2 py-0.5 font-mono text-brand-300 light:bg-surface-100">
                  {formatTime(activeDuration)}
                </span>
                <span className="rounded-lg bg-surface-800 px-2 py-0.5 text-surface-400 light:bg-surface-100">
                  {segments.length} segments
                </span>
                <span className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-emerald-400 font-mono text-[11px]">
                  {transcriptData.job?.device_used === 'cuda' ? 'CUDA int8_float16' : 'CPU Mode'}
                </span>
              </div>

              {/* Truthful Save Status Indicator */}
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono border bg-surface-950 border-surface-800 light:bg-surface-100 light:border-surface-200">
                  {saveStatus === 'saving' && (
                    <>
                      <RefreshCw className="h-3 w-3 text-brand-400 animate-spin" />
                      <span className="text-brand-300 font-medium">Saving to database...</span>
                    </>
                  )}
                  {saveStatus === 'saved' && (
                    <>
                      <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                      <span className="text-emerald-300 font-medium">All changes saved</span>
                    </>
                  )}
                  {saveStatus === 'unsaved' && (
                    <>
                      <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
                      <span className="text-amber-300 font-medium">Unsaved changes</span>
                    </>
                  )}
                  {saveStatus === 'error' && (
                    <>
                      <AlertCircle className="h-3 w-3 text-rose-400" />
                      <span className="text-rose-300 font-medium">Save failed</span>
                    </>
                  )}
                  {saveStatus === 'draft_restored' && (
                    <>
                      <Info className="h-3 w-3 text-purple-400" />
                      <span className="text-purple-300 font-medium">Draft restored</span>
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* Review Workspace Toolbar */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              {/* Left: Transcript View Toggle */}
              <div className="flex items-center gap-1 bg-surface-950/80 border border-surface-800 p-1 rounded-xl text-xs font-semibold light:bg-surface-100 light:border-surface-200">
                <button
                  type="button"
                  onClick={() => setReviewMode('corrected')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors ${
                    reviewMode === 'corrected'
                      ? 'bg-brand-600 text-white shadow-sm'
                      : 'text-surface-400 hover:text-white light:text-surface-600'
                  }`}
                >
                  <List className="h-3.5 w-3.5" />
                  <span>Human-Corrected</span>
                </button>
                <button
                  type="button"
                  onClick={() => setReviewMode('original')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors ${
                    reviewMode === 'original'
                      ? 'bg-brand-600 text-white shadow-sm'
                      : 'text-surface-400 hover:text-white light:text-surface-600'
                  }`}
                >
                  <FileText className="h-3.5 w-3.5" />
                  <span>Original ASR</span>
                </button>
                <button
                  type="button"
                  onClick={() => setReviewMode('diff')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors ${
                    reviewMode === 'diff'
                      ? 'bg-brand-600 text-white shadow-sm'
                      : 'text-surface-400 hover:text-white light:text-surface-600'
                  }`}
                >
                  <Columns className="h-3.5 w-3.5" />
                  <span>Side-by-Side Diff</span>
                </button>
              </div>

              {/* Right: Actions, Auto-Scroll, Export */}
              <div className="flex flex-wrap items-center gap-2">
                {/* Undo / Redo */}
                <div className="flex items-center gap-1 bg-surface-950/80 border border-surface-800 p-1 rounded-xl light:bg-surface-100 light:border-surface-200">
                  <button
                    type="button"
                    onClick={handleUndo}
                    disabled={historyIndex <= 0}
                    className="p-1.5 rounded-lg text-surface-300 hover:text-white hover:bg-surface-800 disabled:opacity-40 transition-colors"
                    title="Undo Edit (Ctrl+Z)"
                  >
                    <Undo2 className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={handleRedo}
                    disabled={historyIndex >= history.length - 1}
                    className="p-1.5 rounded-lg text-surface-300 hover:text-white hover:bg-surface-800 disabled:opacity-40 transition-colors"
                    title="Redo Edit (Ctrl+Y)"
                  >
                    <Redo2 className="h-3.5 w-3.5" />
                  </button>
                </div>

                {/* Auto-Scroll Toggle */}
                <button
                  type="button"
                  onClick={() => setAutoScroll(!autoScroll)}
                  className={`px-3 py-1.5 rounded-xl border text-xs font-semibold transition-colors ${
                    autoScroll
                      ? 'bg-brand-500/15 text-brand-300 border-brand-500/30'
                      : 'bg-surface-950 text-surface-400 border-surface-800 light:bg-surface-100 light:border-surface-200'
                  }`}
                  title="Toggle automatic scrolling to the currently playing segment"
                >
                  Auto-Scroll: {autoScroll ? 'ON' : 'OFF'}
                </button>

                {/* Manual Save */}
                <button
                  type="button"
                  onClick={handleSaveEdits}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-surface-800 border border-surface-700 text-xs font-semibold text-white hover:bg-surface-700 light:border-surface-300 light:bg-white light:text-surface-800 transition-colors"
                  title="Save edits to database (Ctrl+S)"
                >
                  <Save className="h-3.5 w-3.5" />
                  <span>Save</span>
                </button>

                {/* Copy */}
                <button
                  type="button"
                  onClick={handleCopyTranscript}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-surface-800 border border-surface-700 text-xs font-semibold text-white hover:bg-surface-700 light:border-surface-300 light:bg-white light:text-surface-800 transition-colors"
                  title="Copy transcript to clipboard"
                >
                  <Copy className="h-3.5 w-3.5" />
                  <span>Copy</span>
                </button>

                {/* Versioned Export Dropdown */}
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setExportOpen(!exportOpen)}
                    className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-brand-600 text-white text-xs font-bold hover:bg-brand-500 shadow-md transition-colors"
                  >
                    <Download className="h-3.5 w-3.5" />
                    <span>Export</span>
                    <ChevronDown className="h-3.5 w-3.5 ml-0.5" />
                  </button>

                  {exportOpen && (
                    <div className="absolute right-0 top-full mt-2 w-60 rounded-2xl border border-surface-800 bg-surface-900 p-2 shadow-2xl z-40 text-xs animate-fadeIn space-y-1 light:border-surface-200 light:bg-white">
                      <div className="p-2 border-b border-surface-800 text-[11px] text-surface-400 light:border-surface-200">
                        <label className="block mb-1 font-semibold text-white light:text-surface-900">Export Version:</label>
                        <select
                          value={exportVersion}
                          onChange={e => setExportVersion(e.target.value as any)}
                          className="w-full bg-surface-950 border border-surface-800 rounded p-1 text-white text-xs light:bg-surface-50 light:border-surface-200 light:text-surface-900"
                        >
                          <option value="edited">Human-Corrected Version</option>
                          <option value="original">Original ASR Version</option>
                        </select>
                      </div>

                      <a
                        href={`/api/exports/${activeJobId}/txt?version=${exportVersion}`}
                        download
                        onClick={() => setExportOpen(false)}
                        className="block px-3 py-2 rounded-lg hover:bg-surface-800 text-surface-200 hover:text-white light:text-surface-700 light:hover:bg-surface-100"
                      >
                        Text (.TXT - Timestamped)
                      </a>
                      <a
                        href={`/api/exports/${activeJobId}/txt?version=clean`}
                        download
                        onClick={() => setExportOpen(false)}
                        className="block px-3 py-2 rounded-lg hover:bg-surface-800 text-surface-200 hover:text-white light:text-surface-700 light:hover:bg-surface-100"
                      >
                        Text (.TXT - Plain Words)
                      </a>
                      <a
                        href={`/api/exports/${activeJobId}/srt?version=${exportVersion}`}
                        download
                        onClick={() => setExportOpen(false)}
                        className="block px-3 py-2 rounded-lg hover:bg-surface-800 text-surface-200 hover:text-white light:text-surface-700 light:hover:bg-surface-100"
                      >
                        Subtitles (.SRT)
                      </a>
                      <a
                        href={`/api/exports/${activeJobId}/vtt?version=${exportVersion}`}
                        download
                        onClick={() => setExportOpen(false)}
                        className="block px-3 py-2 rounded-lg hover:bg-surface-800 text-surface-200 hover:text-white light:text-surface-700 light:hover:bg-surface-100"
                      >
                        WebVTT (.VTT)
                      </a>
                      <a
                        href={`/api/exports/${activeJobId}/json?version=${exportVersion}`}
                        download
                        onClick={() => setExportOpen(false)}
                        className="block px-3 py-2 rounded-lg hover:bg-surface-800 text-surface-200 hover:text-white light:text-surface-700 light:hover:bg-surface-100"
                      >
                        Full Data (.JSON)
                      </a>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Audio Player Component */}
            {activeJobId && (
              <AudioPlayer
                ref={playerRef}
                src={api.getAudioStreamUrl(activeJobId, true)}
                knownDuration={activeDuration}
                onTimeUpdate={setCurrentTime}
              />
            )}
          </div>

          {/* Mode Notification Banner */}
          {reviewMode === 'original' && (
            <div className="p-3.5 rounded-xl bg-surface-950 border border-surface-800 text-xs text-surface-400 flex items-center justify-between light:bg-surface-100 light:border-surface-200">
              <span>Viewing <strong>Original Immutable ASR Recognition Output</strong>. Edits are disabled in this mode.</span>
              <button
                type="button"
                onClick={() => setReviewMode('corrected')}
                className="text-brand-400 hover:underline font-semibold"
              >
                Switch to Human-Corrected Mode
              </button>
            </div>
          )}

          {/* Transcript Segments List */}
          <div className="space-y-4">
            {segments.map((seg, idx) => {
              const isCurrent = currentTime >= seg.start && currentTime <= seg.end;
              const isLoopingThis = loopingSegmentId === seg.id;
              const isEdited = seg.text !== seg.original_text;
              const altState = alternativeMap[seg.id];

              return (
                <div
                  key={seg.id}
                  ref={el => {
                    segmentRefs.current[seg.id] = el;
                  }}
                  className={`group rounded-2xl border p-4 sm:p-5 transition-all duration-200 ${
                    isCurrent
                      ? 'border-brand-500 bg-brand-500/10 ring-1 ring-brand-500/50 shadow-xl'
                      : isEdited
                      ? 'border-amber-500/30 bg-surface-900/60 light:bg-white light:border-amber-400/40'
                      : 'border-surface-800 bg-surface-900/40 hover:border-surface-700 light:border-surface-200 light:bg-white'
                  }`}
                >
                  {/* Segment Top Metadata Bar */}
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                    <div className="flex items-center gap-2">
                      {/* Play Segment Button */}
                      <button
                        type="button"
                        onClick={() => playerRef.current?.seekTo(seg.start)}
                        className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-mono font-bold transition-all ${
                          isCurrent
                            ? 'bg-brand-600 text-white shadow-md'
                            : 'bg-surface-800 text-brand-300 hover:bg-brand-600 hover:text-white light:bg-surface-100 light:text-brand-600'
                        }`}
                        title="Seek & play this segment"
                      >
                        <Play className="h-3 w-3 fill-current" />
                        <span>{formatTime(seg.start)} — {formatTime(seg.end)}</span>
                      </button>

                      {/* Loop Segment Button */}
                      <button
                        type="button"
                        onClick={() => handleLoopSpecificSegment(seg)}
                        className={`p-1.5 rounded-xl border text-xs transition-colors ${
                          isLoopingThis
                            ? 'bg-brand-500 text-white border-brand-400'
                            : 'bg-surface-800 text-surface-400 border-surface-700 hover:text-white light:bg-surface-100 light:border-surface-200'
                        }`}
                        title={isLoopingThis ? 'Stop looping this segment' : 'Loop this segment continuously (Alt+L)'}
                      >
                        <Repeat className={`h-3.5 w-3.5 ${isLoopingThis ? 'animate-spin' : ''}`} style={isLoopingThis ? { animationDuration: '4s' } : undefined} />
                      </button>

                      {/* Revert to Original if edited */}
                      {isEdited && reviewMode === 'corrected' && (
                        <button
                          type="button"
                          onClick={() => handleRevertSegment(seg.id)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-xl text-[11px] font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/30 hover:bg-amber-500/20 transition-colors"
                          title="Revert to original ASR prediction"
                        >
                          <RotateCcw className="h-3 w-3" />
                          <span>Revert</span>
                        </button>
                      )}
                    </div>

                    <div className="flex items-center gap-2">
                      {/* Alternative Suggestion Trigger */}
                      {reviewMode === 'corrected' && (
                        <button
                          type="button"
                          disabled={altState?.loading}
                          onClick={() => handleRequestAlternative(seg, 'large-v3-turbo')}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-xl bg-surface-800 hover:bg-surface-700 text-surface-300 hover:text-white text-[11px] font-semibold transition-colors border border-surface-700/80 light:bg-surface-100 light:border-surface-200 light:text-surface-700"
                          title="Query Large-v3-Turbo for an alternative candidate transcript of this segment"
                        >
                          <Sparkles className={`h-3 w-3 text-brand-400 ${altState?.loading ? 'animate-spin' : ''}`} />
                          <span>{altState?.loading ? 'Checking...' : 'Alternative Model'}</span>
                        </button>
                      )}

                      {seg.uncertain && (
                        <span
                          className="flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold text-amber-400 border border-amber-500/20"
                          title={seg.uncertain_reason ? `Flagged: ${seg.uncertain_reason}` : 'Acoustically uncertain segment'}
                        >
                          <AlertTriangle className="h-3 w-3" />
                          <span>Uncertain</span>
                        </span>
                      )}

                      <span className="text-xs font-mono font-bold text-surface-500">#{seg.id}</span>
                    </div>
                  </div>

                  {/* Alternative Candidate Suggestion Box (if requested) */}
                  {altState && (
                    <div className="mb-3 p-3.5 rounded-xl bg-surface-950 border border-brand-500/30 space-y-2 text-xs animate-fadeIn light:bg-surface-50">
                      <div className="flex items-center justify-between text-brand-300 font-bold">
                        <span className="flex items-center gap-1.5">
                          <Sparkles className="h-3.5 w-3.5 text-brand-400" />
                          <span>Alternative Suggestion: {altState.modelName}</span>
                        </span>
                        <span className="text-[10px] text-surface-500 uppercase tracking-wide">Local On-Demand</span>
                      </div>

                      {altState.loading ? (
                        <div className="py-2 text-surface-400 flex items-center gap-2">
                          <RefreshCw className="h-3.5 w-3.5 animate-spin text-brand-400" />
                          <span>Transcribing segment interval with {altState.modelName}...</span>
                        </div>
                      ) : altState.suggestedText ? (
                        <>
                          <div
                            className="p-3 rounded-lg bg-surface-900 border border-surface-800 text-sm text-white font-sans leading-relaxed light:bg-white light:border-surface-200 light:text-surface-900 text-right"
                            dir="rtl"
                            style={{ unicodeBidi: 'plaintext' }}
                          >
                            {altState.suggestedText}
                          </div>
                          <div className="flex items-center gap-2 pt-1">
                            <button
                              type="button"
                              onClick={() => handleApplyAlternative(seg.id, altState.suggestedText!)}
                              className="px-3.5 py-1.5 rounded-lg bg-brand-600 text-white font-bold text-xs hover:bg-brand-500 transition-colors shadow-sm"
                            >
                              Accept Suggestion
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDismissAlternative(seg.id)}
                              className="px-3 py-1.5 text-surface-400 hover:text-white text-xs light:text-surface-600"
                            >
                              Dismiss
                            </button>
                          </div>
                        </>
                      ) : (
                        <div className="text-rose-400 text-xs">{altState.error || 'No prediction available.'}</div>
                      )}
                    </div>
                  )}

                  {/* Segment Content Depending on Review Mode */}
                  {reviewMode === 'diff' ? (
                    /* Side-by-Side Comparison Mode */
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs pt-1">
                      <div className="p-3.5 rounded-xl bg-surface-950/80 border border-surface-800/80 space-y-1.5 light:bg-surface-50 light:border-surface-200">
                        <span className="text-[10px] font-bold uppercase text-surface-500 tracking-wider">
                          Original ASR Recognition:
                        </span>
                        <p
                          className="text-surface-200 text-sm font-sans leading-relaxed text-right select-text light:text-surface-800"
                          dir="rtl"
                          style={{ unicodeBidi: 'plaintext' }}
                        >
                          {seg.original_text || seg.text}
                        </p>
                      </div>

                      <div className="p-3.5 rounded-xl bg-brand-500/5 border border-brand-500/25 space-y-1.5">
                        <span className="text-[10px] font-bold uppercase text-brand-400 tracking-wider">
                          Human-Corrected Output:
                        </span>
                        <textarea
                          rows={2}
                          value={seg.text}
                          onChange={e => handleSegmentTextChange(seg.id, e.target.value)}
                          className="w-full resize-none rounded-lg bg-transparent p-1.5 text-sm text-white focus:bg-surface-950 focus:outline-none focus:ring-1 focus:ring-brand-500 leading-relaxed font-sans text-right light:text-surface-900 light:focus:bg-white"
                          dir="rtl"
                          style={{ unicodeBidi: 'plaintext' }}
                        />
                      </div>
                    </div>
                  ) : reviewMode === 'original' ? (
                    /* Read-Only Original ASR Mode */
                    <div
                      className="p-2 text-sm text-surface-200 leading-relaxed font-sans text-right select-text light:text-surface-800"
                      dir="rtl"
                      style={{ unicodeBidi: 'plaintext' }}
                    >
                      {seg.original_text || seg.text}
                    </div>
                  ) : (
                    /* Default Human-Corrected Editable Mode */
                    <textarea
                      rows={2}
                      value={seg.text}
                      onChange={e => handleSegmentTextChange(seg.id, e.target.value)}
                      className="w-full resize-none rounded-xl bg-transparent p-2 text-sm text-surface-100 focus:bg-surface-950/70 focus:outline-none focus:ring-1 focus:ring-brand-500 leading-relaxed font-sans text-right light:text-surface-900 light:focus:bg-white"
                      dir="rtl"
                      style={{ unicodeBidi: 'plaintext' }}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
