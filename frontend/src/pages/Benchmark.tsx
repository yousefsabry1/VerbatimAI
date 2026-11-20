import React, { useState, useEffect, useRef } from 'react';
import { useI18n } from '../context/I18nContext';
import { HardwareInfo, ModelInfo, BenchmarkRunResult, WordAlignmentOp, BenchmarkSample } from '../types';
import { api } from '../services/api';
import {
  Sparkles,
  Play,
  Pause,
  Repeat,
  CheckCircle2,
  AlertTriangle,
  Cpu,
  Zap,
  Save,
  RotateCcw,
  BarChart3,
  Layers,
  FileText,
  Volume2,
  Clock,
  ArrowRight,
  Info,
  Download,
  Columns,
  RefreshCw,
  Check,
  ShieldAlert,
  Sliders,
  HelpCircle,
  Calculator,
  ShieldCheck,
  Plus,
  Trash2,
  X,
  FileAudio,
} from 'lucide-react';

interface BenchmarkProps {
  hardware: HardwareInfo | null;
  initialCreateJobId?: string | null;
  onClearInitialCreateJob?: () => void;
}

export const Benchmark: React.FC<BenchmarkProps> = ({
  hardware,
  initialCreateJobId,
  onClearInitialCreateJob,
}) => {
  const { t, isRTL } = useI18n();

  // Create Sample Modal State
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [sourceRecordings, setSourceRecordings] = useState<
    Array<{
      job_id: string;
      filename: string;
      path: string;
      duration: number;
      duration_formatted: string;
      format: string;
      created_at: string;
    }>
  >([]);
  const [selectedSourceJobId, setSelectedSourceJobId] = useState<string>('');
  const [newSampleName, setNewSampleName] = useState<string>('');
  const [newSampleStart, setNewSampleStart] = useState<number>(0);
  const [newSampleEnd, setNewSampleEnd] = useState<number>(45);
  const [newSampleDescription, setNewSampleDescription] = useState<string>('');
  const [isLoadingRecordings, setIsLoadingRecordings] = useState<boolean>(false);
  const [isCreatingSample, setIsCreatingSample] = useState<boolean>(false);
  const [previewPlaying, setPreviewPlaying] = useState<boolean>(false);
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);

  const formatTime = (secs: number): string => {
    const s = Math.max(0, Math.floor(secs));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m.toString().padStart(2, '0')}:${r.toString().padStart(2, '0')}`;
  };

  // Benchmark Sample Catalog State
  const [samples, setSamples] = useState<BenchmarkSample[]>([
    {
      sample_id: 'dev_0_103',
      name: 'Development Sample (00:00 - 01:43)',
      start_time: 0.0,
      end_time: 103.5,
      duration: 103.5,
      audio_url: '/api/benchmark/audio/dev_0_103',
      status: 'VERIFIED',
      verification_badge: 'Verified Human Reference (203 words)',
      has_human_reference: true,
      word_count: 203,
      description: 'Original human ground-truth transcript provided by the user. Baseline: 52.71% Normalized WER.',
    },
    {
      sample_id: 'test_180_225',
      name: 'Independent Test Sample (03:00 - 03:45)',
      start_time: 180.0,
      end_time: 225.0,
      duration: 45.0,
      audio_url: '/api/benchmark/audio/test_180_225',
      status: 'VERIFIED',
      verification_badge: 'Verified Human Reference (111 words)',
      has_human_reference: true,
      word_count: 111,
      description: 'Independent 45s out-of-sample audio interval. Human reference verified against dd.ogg.',
    },
    {
      sample_id: 'holdout_300_345',
      name: 'Unseen Holdout Sample (05:00 - 05:45)',
      start_time: 300.0,
      end_time: 345.0,
      duration: 45.0,
      audio_url: '/api/benchmark/audio/holdout_300_345',
      status: 'UNVERIFIED',
      verification_badge: 'UNVERIFIED — Pending Human Transcription',
      has_human_reference: false,
      word_count: 0,
      description: 'Strict unseen out-of-sample holdout audio interval (05:00 - 05:45). Reference manually transcribed by user.',
    },
  ]);
  const [activeSampleId, setActiveSampleId] = useState<string>('holdout_300_345');
  const activeSampleRef = useRef<string>('holdout_300_345');

  // Human Reference & State
  const [refText, setRefText] = useState<string>('');
  const [savedRefText, setSavedRefText] = useState<string>('');
  const [isHumanVerified, setIsHumanVerified] = useState<boolean>(false);
  const [verificationBadge, setVerificationBadge] = useState<string>('UNVERIFIED — Pending Human Transcription');
  const [certificationChecked, setCertificationChecked] = useState<boolean>(false);

  const [startTime, setStartTime] = useState<number>(300.0);
  const [endTime, setEndTime] = useState<number>(345.0);
  const [selectedModels, setSelectedModels] = useState<string[]>([
    'codeswitched-medium',
    'medium',
    'large-v3-turbo',
  ]);
  const [deviceMode, setDeviceMode] = useState<string>('auto');
  const [evalMode, setEvalMode] = useState<'normalized' | 'raw'>('normalized');
  const [vadFilter, setVadFilter] = useState<boolean>(false);
  const [audioFilter, setAudioFilter] = useState<'none' | 'highpass_gain'>('none');
  const [useHints, setUseHints] = useState<boolean>(false);
  const [customHints, setCustomHints] = useState<string>('');

  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);

  // Results per sample to guarantee complete isolation and zero cross-sample contamination
  const [resultsBySample, setResultsBySample] = useState<Record<string, BenchmarkRunResult[]>>({});
  const [selectedResultIndex, setSelectedResultIndex] = useState<number>(0);
  const [compareIndexB, setCompareIndexB] = useState<number>(1);
  const [isComparingSideBySide, setIsComparingSideBySide] = useState<boolean>(false);

  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [isCalculatingAccuracy, setIsCalculatingAccuracy] = useState<boolean>(false);
  const [isSavingDraft, setIsSavingDraft] = useState<boolean>(false);
  const [isVerifying, setIsVerifying] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Audio Playback State
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isLooping, setIsLooping] = useState<boolean>(true);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0);
  const [currentTime, setCurrentTime] = useState<number>(0.0);
  const [audioDuration, setAudioDuration] = useState<number>(45.0);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  const countWords = (text: string): number => {
    return text.trim().split(/\s+/).filter(Boolean).length;
  };

  // Load samples and active reference on mount
  useEffect(() => {
    api.getBenchmarkSamples().then(res => {
      if (res.samples && res.samples.length > 0) {
        setSamples(res.samples);
      }
    }).catch(() => {});

    api.getModels().then(res => {
      setAvailableModels(res.models);
    }).catch(() => {});

    loadSampleData('holdout_300_345');
  }, []);

  const loadSampleData = async (sampleId: string) => {
    setActiveSampleId(sampleId);
    activeSampleRef.current = sampleId;

    try {
      const refRes = await api.getBenchmarkReference(sampleId);
      // Ensure response matches active sample (reject stale responses)
      if (activeSampleRef.current !== sampleId) return;

      const raw = refRes.raw_text || '';
      setRefText(raw);
      setSavedRefText(raw);
      const verified = Boolean(refRes.is_human_verified);
      setIsHumanVerified(verified);
      setCertificationChecked(verified);
      setVerificationBadge(
        refRes.verification_badge ||
          (verified
            ? `Verified Human Reference (${countWords(raw)} words)`
            : countWords(raw) > 0
            ? `Draft Saved (${countWords(raw)} words) — Unverified`
            : 'UNVERIFIED — Pending Human Transcription')
      );

      if (refRes.start_time !== undefined) setStartTime(refRes.start_time);
      if (refRes.end_time !== undefined) setEndTime(refRes.end_time);

      const resultsRes = await api.getBenchmarkResults(sampleId);
      if (activeSampleRef.current !== sampleId) return;

      if (resultsRes.has_results && resultsRes.results.length > 0) {
        setResultsBySample(prev => ({ ...prev, [sampleId]: resultsRes.results }));
        setSelectedResultIndex(0);
        if (resultsRes.results.length > 1) setCompareIndexB(1);
      } else {
        setResultsBySample(prev => ({ ...prev, [sampleId]: [] }));
      }

      if (audioRef.current) {
        audioRef.current.pause();
        setIsPlaying(false);
        audioRef.current.src = api.getBenchmarkAudioUrl(sampleId);
        audioRef.current.load();
      }
    } catch (e: any) {
      console.error('Failed to load sample data:', e);
    }
  };

  const handleSelectSample = (sampleId: string) => {
    if (sampleId === activeSampleId) return;
    loadSampleData(sampleId);
  };

  // Open Create Modal & Fetch Recordings
  const handleOpenCreateModal = async (preselectedJobId?: string) => {
    setIsLoadingRecordings(true);
    setShowCreateModal(true);
    try {
      const res = await api.getSourceRecordings();
      const recs = res.recordings || [];
      setSourceRecordings(recs);

      let targetRec = recs[0];
      if (preselectedJobId) {
        const found = recs.find(r => r.job_id === preselectedJobId);
        if (found) targetRec = found;
      }

      if (targetRec) {
        setSelectedSourceJobId(targetRec.job_id);
        const start = 0;
        const end = Math.min(45, Math.floor(targetRec.duration));
        setNewSampleStart(start);
        setNewSampleEnd(end);
        const cleanName = targetRec.filename.replace(/^[a-f0-9]+_/, '');
        setNewSampleName(`${cleanName} (${formatTime(start)} - ${formatTime(end)})`);
        setNewSampleDescription(`Benchmark evaluation sample from ${cleanName}.`);
      }
    } catch (err: any) {
      console.error('Failed to load source recordings:', err);
    } finally {
      setIsLoadingRecordings(false);
    }
  };

  // Preselected Job from Navigation Hook
  useEffect(() => {
    if (initialCreateJobId) {
      handleOpenCreateModal(initialCreateJobId);
      if (onClearInitialCreateJob) onClearInitialCreateJob();
    }
  }, [initialCreateJobId]);

  const handleSelectRecording = (jobId: string) => {
    setSelectedSourceJobId(jobId);
    const rec = sourceRecordings.find(r => r.job_id === jobId);
    if (rec) {
      const start = 0;
      const end = Math.min(45, Math.floor(rec.duration));
      setNewSampleStart(start);
      setNewSampleEnd(end);
      const cleanName = rec.filename.replace(/^[a-f0-9]+_/, '');
      setNewSampleName(`${cleanName} (${formatTime(start)} - ${formatTime(end)})`);
      setNewSampleDescription(`Benchmark evaluation sample from ${cleanName}.`);
    }
    if (previewAudioRef.current) {
      previewAudioRef.current.pause();
      setPreviewPlaying(false);
    }
  };

  const handleTogglePreview = () => {
    if (!previewAudioRef.current) return;
    if (previewPlaying) {
      previewAudioRef.current.pause();
      setPreviewPlaying(false);
    } else {
      const url = api.getBenchmarkPreviewUrl(selectedSourceJobId, newSampleStart, newSampleEnd);
      previewAudioRef.current.src = url;
      previewAudioRef.current.play().then(() => setPreviewPlaying(true)).catch(() => {});
    }
  };

  const handleCreateSampleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSampleName.trim()) {
      alert('Please enter a sample name.');
      return;
    }
    if (!selectedSourceJobId) {
      alert('Please select a source recording.');
      return;
    }
    if (newSampleEnd <= newSampleStart) {
      alert('End time must be greater than start time.');
      return;
    }

    setIsCreatingSample(true);
    try {
      const res = await api.createBenchmarkSample({
        name: newSampleName.trim(),
        source_path_or_id: selectedSourceJobId,
        start_time: newSampleStart,
        end_time: newSampleEnd,
        description: newSampleDescription.trim() || undefined,
      });

      const samplesRes = await api.getBenchmarkSamples();
      if (samplesRes.samples) {
        setSamples(samplesRes.samples);
      }

      setShowCreateModal(false);
      if (previewAudioRef.current) {
        previewAudioRef.current.pause();
        setPreviewPlaying(false);
      }

      await loadSampleData(res.sample.sample_id);
      showToast(`Benchmark sample "${res.sample.name}" created! Ready for human transcription.`);
    } catch (err: any) {
      alert('Failed to create benchmark sample: ' + err.message);
    } finally {
      setIsCreatingSample(false);
    }
  };

  const handleDeleteSample = async (sampleId: string, sampleName: string) => {
    if (
      !confirm(
        `Are you sure you want to delete benchmark sample "${sampleName}"? All candidate predictions and reference text for this sample will be permanently removed.`
      )
    ) {
      return;
    }

    try {
      await api.deleteBenchmarkSample(sampleId);
      showToast(`Sample "${sampleName}" deleted.`);

      const samplesRes = await api.getBenchmarkSamples();
      const updatedSamples = samplesRes.samples || [];
      setSamples(updatedSamples);

      if (activeSampleId === sampleId) {
        const nextId = updatedSamples[0]?.sample_id || 'holdout_300_345';
        loadSampleData(nextId);
      }
    } catch (err: any) {
      alert('Failed to delete sample: ' + err.message);
    }
  };

  const currentResults = resultsBySample[activeSampleId] || [];
  const activeResult = currentResults[selectedResultIndex];
  const activeSample = samples.find(s => s.sample_id === activeSampleId) || samples[0];

  // Derive reference status
  const currentWordCount = countWords(refText);
  const isDirty = refText.trim() !== savedRefText.trim();

  let referenceStatusKey: 'NO_REFERENCE' | 'UNSAVED_CHANGES' | 'DRAFT_SAVED' | 'HUMAN_VERIFIED';
  let referenceStatusLabel: string;
  let referenceStatusClass: string;

  if (currentWordCount === 0) {
    referenceStatusKey = 'NO_REFERENCE';
    referenceStatusLabel = 'No Reference';
    referenceStatusClass = 'bg-surface-800 text-surface-400 border-surface-700';
  } else if (isDirty) {
    referenceStatusKey = 'UNSAVED_CHANGES';
    referenceStatusLabel = 'Unsaved Changes';
    referenceStatusClass = 'bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse';
  } else if (isHumanVerified) {
    referenceStatusKey = 'HUMAN_VERIFIED';
    referenceStatusLabel = 'Human Verified';
    referenceStatusClass = 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
  } else {
    referenceStatusKey = 'DRAFT_SAVED';
    referenceStatusLabel = 'Draft Saved (Unverified)';
    referenceStatusClass = 'bg-blue-500/20 text-blue-300 border-blue-500/40';
  }

  // Handle Save Draft (Explicitly unverified)
  const handleSaveDraft = async () => {
    if (!refText.trim()) {
      alert('Please enter reference text before saving draft.');
      return;
    }

    setIsSavingDraft(true);
    try {
      const res = await api.saveBenchmarkReference({
        sample_id: activeSampleId,
        reference_text: refText.trim(),
        action: 'save_draft',
        start_time: startTime,
        end_time: endTime,
        is_human_verified: false,
      });

      setSavedRefText(refText.trim());
      setIsHumanVerified(false);
      setCertificationChecked(false);
      setVerificationBadge(`Draft Saved (${countWords(refText)} words) — Unverified`);

      // Refresh samples list
      const samplesRes = await api.getBenchmarkSamples();
      if (samplesRes.samples) setSamples(samplesRes.samples);

      // If results existed, refresh them as unverified
      const resultsRes = await api.getBenchmarkResults(activeSampleId);
      if (resultsRes.results) {
        setResultsBySample(prev => ({ ...prev, [activeSampleId]: resultsRes.results }));
      }

      showToast(res.message || 'Reference draft saved successfully. Verification is still required before accuracy metrics can be calculated.');
    } catch (err: any) {
      alert('Failed to save draft: ' + err.message);
    } finally {
      setIsSavingDraft(false);
    }
  };

  // Handle Save & Verify Reference (Explicit human certification)
  const handleSaveAndVerify = async () => {
    if (!refText.trim()) {
      alert('Please enter reference text before certifying.');
      return;
    }

    if (!certificationChecked) {
      alert(
        'Integrity Safeguard:\n\nYou must explicitly check the confirmation checkbox:\n"I confirm that I personally listened to the original audio and manually verified this transcript against what was actually spoken."\n\nThis prevents unverified transcripts from generating false accuracy metrics.'
      );
      return;
    }

    setIsVerifying(true);
    try {
      const res = await api.saveBenchmarkReference({
        sample_id: activeSampleId,
        reference_text: refText.trim(),
        action: 'save_and_verify',
        start_time: startTime,
        end_time: endTime,
        is_human_verified: true,
        verification_statement:
          'I confirm that I personally listened to the original audio and manually verified this transcript against what was actually spoken.',
      });

      setSavedRefText(refText.trim());
      setIsHumanVerified(true);
      setVerificationBadge(`Verified Human Reference (${countWords(refText)} words)`);

      // Refresh samples list
      const samplesRes = await api.getBenchmarkSamples();
      if (samplesRes.samples) setSamples(samplesRes.samples);

      // If candidate predictions exist for this sample, automatically calculate accuracy
      const resultsRes = await api.getBenchmarkResults(activeSampleId);
      if (resultsRes.results && resultsRes.results.length > 0) {
        setResultsBySample(prev => ({ ...prev, [activeSampleId]: resultsRes.results }));
      }

      showToast(res.message || 'Human reference verified successfully. Accuracy evaluation is now available.');
    } catch (err: any) {
      alert('Verification failed: ' + err.message);
    } finally {
      setIsVerifying(false);
    }
  };

  // Dedicated Action: Calculate Accuracy without re-running models
  const handleCalculateAccuracy = async () => {
    if (!isHumanVerified) {
      alert('Cannot calculate accuracy: Please verify the human reference first.');
      return;
    }

    setIsCalculatingAccuracy(true);
    try {
      const res = await api.calculateBenchmarkAccuracy({
        sample_id: activeSampleId,
        eval_mode: evalMode,
      });

      if (res.results) {
        setResultsBySample(prev => ({ ...prev, [activeSampleId]: res.results }));
        setSelectedResultIndex(0);
        showToast('Accuracy metrics calculated successfully from stored candidate predictions!');
      }
    } catch (err: any) {
      alert('Failed to calculate accuracy: ' + err.message);
    } finally {
      setIsCalculatingAccuracy(false);
    }
  };

  const handleToggleModel = (modelId: string) => {
    if (selectedModels.includes(modelId)) {
      if (selectedModels.length > 1) {
        setSelectedModels(selectedModels.filter(m => m !== modelId));
      }
    } else {
      setSelectedModels([...selectedModels, modelId]);
    }
  };

  // Run Benchmark inference
  const handleRunBenchmark = async () => {
    setIsRunning(true);
    setStatusMessage(`Running candidate models on ${activeSample.name}...`);

    try {
      const res = await api.runBenchmark({
        sample_id: activeSampleId,
        start_time: startTime,
        end_time: endTime,
        model_ids: selectedModels,
        device_mode: deviceMode,
        use_hints: useHints,
        custom_hints: customHints.trim() ? customHints.trim() : null,
        eval_mode: evalMode,
        vad_filter: vadFilter,
        audio_filter: audioFilter,
      });

      // Reject stale responses if user switched sample during inference
      if (res.sample_id === activeSampleRef.current) {
        setResultsBySample(prev => ({ ...prev, [res.sample_id]: res.results || [] }));
        setSelectedResultIndex(0);
        if (res.results && res.results.length > 1) {
          setCompareIndexB(1);
        }

        if (res.is_human_verified) {
          showToast('Benchmark run completed with verified WER/CER metrics!');
        } else {
          showToast('Model inference completed. Verify the human reference to unlock accuracy metrics.');
        }
      }
    } catch (err: any) {
      alert('Benchmark run failed: ' + err.message);
    } finally {
      setIsRunning(false);
      setStatusMessage(null);
    }
  };

  const handlePlayPause = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
    }
  };

  const handleSpeedChange = (speed: number) => {
    setPlaybackSpeed(speed);
    if (audioRef.current) {
      audioRef.current.playbackRate = speed;
    }
  };

  const handleTimeUpdate = () => {
    if (!audioRef.current) return;
    setCurrentTime(audioRef.current.currentTime);
  };

  const handleAudioEnded = () => {
    if (isLooping && audioRef.current) {
      audioRef.current.currentTime = 0;
      audioRef.current.play().catch(() => {});
    } else {
      setIsPlaying(false);
    }
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    setCurrentTime(val);
    if (audioRef.current) {
      audioRef.current.currentTime = val;
    }
  };

  const handleExportReport = () => {
    const reportData = {
      benchmark_report_title: `Verbatim AI Accuracy Benchmark — ${activeSample.name}`,
      exported_at: new Date().toISOString(),
      sample_id: activeSampleId,
      sample_name: activeSample.name,
      audio_interval: `${activeSample.start_time}s - ${activeSample.end_time}s (${activeSample.duration}s)`,
      is_human_verified: isHumanVerified,
      reference_text: refText,
      evaluation_mode: evalMode,
      audio_filter: audioFilter,
      results: currentResults,
    };
    const blob = new Blob([JSON.stringify(reportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `benchmark_${activeSampleId}_${evalMode}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Determine lowest WER model ONLY when verified and metrics are numerically valid
  const validEvaluatedResults = currentResults.filter(
    r => r.status === 'success' && r.is_verified && (evalMode === 'normalized' ? r.norm_wer != null : r.raw_wer != null)
  );

  const lowestWer =
    isHumanVerified && validEvaluatedResults.length > 0
      ? Math.min(
          ...validEvaluatedResults.map(r => (evalMode === 'normalized' ? r.norm_wer! : r.raw_wer!))
        )
      : null;

  return (
    <div className="space-y-6 animate-fadeIn pb-16">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-3 text-sm font-semibold text-white shadow-2xl animate-bounce">
          <CheckCircle2 className="h-4 w-4" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Audio element for dedicated sample streaming */}
      <audio
        ref={audioRef}
        src={api.getBenchmarkAudioUrl(activeSampleId)}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={() => {
          if (audioRef.current) setAudioDuration(audioRef.current.duration || activeSample.duration || 45.0);
        }}
        onEnded={handleAudioEnded}
      />

      {/* Page Title & GPU Badge */}
      <div className="space-y-1">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-black text-white light:text-surface-900 flex items-center gap-2.5">
              <BarChart3 className="h-7 w-7 text-brand-400" />
              <span>ASR Accuracy Benchmark & Integrity Review</span>
            </h1>
            <p className="text-xs sm:text-sm text-surface-400 light:text-surface-600">
              Scientific speech recognition benchmarking with strict human-verification safeguards and zero synthetic ground truth.
            </p>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2">
            {currentResults.length > 0 && (
              <button
                type="button"
                onClick={handleExportReport}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-surface-700 bg-surface-800 text-xs font-semibold text-surface-200 hover:bg-surface-700 hover:text-white transition-colors"
              >
                <Download className="h-3.5 w-3.5" />
                <span>Export Report</span>
              </button>
            )}

            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-surface-900 border border-surface-800 text-xs">
              <Zap className="h-3.5 w-3.5 text-emerald-400" />
              <span className="text-surface-300 font-semibold">{hardware?.gpu_name || 'RTX 3050 Laptop GPU'}</span>
              <span className="text-surface-500">•</span>
              <span className="text-emerald-400 font-mono">CUDA 12 Active</span>
            </div>
          </div>
        </div>
      </div>

      {/* Audit Invalidation Notice Banner */}
      <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/25 text-xs text-amber-200 flex items-start gap-3">
        <ShieldAlert className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <span className="font-bold block text-amber-300">
            Benchmark Integrity Notice — Formal Retraction of Slice 245s–295s (30.22% WER)
          </span>
          <p className="text-[11px] text-amber-200/80 leading-relaxed">
            The previously reported 30.22% WER on audio slice 245s–295s was retracted because the reference was generated using model assistance rather than human transcription. In Verbatim AI, no transcript is considered ground truth without explicit human certification.
          </p>
        </div>
      </div>

      {/* Benchmark Catalog Header & Add Button */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
        <div>
          <h2 className="text-base font-bold text-white light:text-surface-900 flex items-center gap-2">
            <Layers className="h-5 w-5 text-brand-400" />
            <span>Benchmark Evaluation Samples</span>
          </h2>
          <p className="text-xs text-surface-400 light:text-surface-600">
            Compare models on standardized human-verified intervals or create a custom benchmark from any recording.
          </p>
        </div>

        <button
          type="button"
          onClick={() => handleOpenCreateModal()}
          className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-gradient-to-r from-brand-600 to-indigo-600 text-white font-bold text-xs shadow-lg shadow-brand-500/20 hover:from-brand-500 hover:to-indigo-500 transition-all hover:scale-[1.02]"
        >
          <Plus className="h-4 w-4" />
          <span>+ Create Benchmark Sample</span>
        </button>
      </div>

      {/* Benchmark Sample Switcher Tabs */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {samples.map(s => {
          const isSelected = s.sample_id === activeSampleId;
          const isVerified = s.status === 'VERIFIED';

          return (
            <div
              key={s.sample_id}
              onClick={() => handleSelectSample(s.sample_id)}
              className={`p-4 rounded-2xl border cursor-pointer transition-all relative group ${
                isSelected
                  ? 'border-brand-500/80 bg-brand-500/10 ring-1 ring-brand-500/40 shadow-lg'
                  : 'border-surface-800 bg-surface-900/40 hover:bg-surface-850 hover:border-surface-700'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-bold text-white flex items-center gap-2 max-w-[70%] truncate">
                  <FileText className={`h-4 w-4 shrink-0 ${isSelected ? 'text-brand-400' : 'text-surface-400'}`} />
                  <span className="truncate" title={s.name}>{s.name}</span>
                </span>
                <div className="flex items-center gap-1.5">
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wide uppercase border ${
                      isVerified
                        ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                        : 'bg-amber-500/20 text-amber-300 border-amber-500/30'
                    }`}
                  >
                    {isVerified ? 'VERIFIED' : 'UNVERIFIED'}
                  </span>
                  {s.is_dynamic && (
                    <button
                      type="button"
                      onClick={e => {
                        e.stopPropagation();
                        handleDeleteSample(s.sample_id, s.name);
                      }}
                      className="p-1 rounded-lg text-surface-500 hover:text-rose-400 hover:bg-rose-500/20 transition-colors"
                      title="Delete dynamic benchmark sample"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
              <p className="text-xs text-surface-400 leading-relaxed mb-3 line-clamp-2">{s.description}</p>
              <div className="flex items-center justify-between text-[11px] font-mono text-surface-400 pt-2 border-t border-surface-800/60">
                <span>Duration: {s.duration.toFixed(1)}s</span>
                <span>Word Count: {s.word_count} words</span>
                <span className="font-sans font-semibold text-brand-300">
                  {isSelected ? '● Active' : 'Switch'}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Top Grid: Audio Player Controls & Human Reference Editor */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Audio Player & Playback Speed Card */}
        <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-5 light:border-surface-200 light:bg-white space-y-4">
          <h3 className="text-sm font-bold text-white light:text-surface-900 flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Volume2 className="h-4 w-4 text-brand-400" />
              <span>Audio Playback & Verification Player</span>
            </span>
            <span className="text-xs font-mono text-brand-300">
              {Math.floor(currentTime / 60)}:{(Math.floor(currentTime) % 60).toString().padStart(2, '0')} /{' '}
              {Math.floor(audioDuration / 60)}:{(Math.floor(audioDuration) % 60).toString().padStart(2, '0')}
            </span>
          </h3>

          {/* Scrubber */}
          <div className="space-y-1">
            <input
              type="range"
              min="0"
              max={audioDuration || activeSample.duration || 45.0}
              step="0.1"
              value={currentTime}
              onChange={handleSeek}
              className="w-full accent-brand-500 cursor-pointer h-1.5 bg-surface-800 rounded-lg"
            />
          </div>

          {/* Primary Audio Player Controls */}
          <div className="p-3 rounded-xl bg-surface-950/80 border border-surface-800/80 flex items-center justify-between">
            <button
              type="button"
              onClick={handlePlayPause}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-brand-600 text-white font-bold text-xs hover:bg-brand-500 transition-colors shadow-md"
            >
              {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              <span>{isPlaying ? 'Pause Audio' : 'Play Audio'}</span>
            </button>

            <button
              type="button"
              onClick={() => setIsLooping(!isLooping)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-semibold transition-colors ${
                isLooping
                  ? 'bg-brand-500/20 text-brand-300 border-brand-500/40'
                  : 'bg-surface-900 text-surface-400 border-surface-800 hover:text-surface-200'
              }`}
              title="Toggle Audio Looping"
            >
              <Repeat className="h-3.5 w-3.5" />
              <span>Loop: {isLooping ? 'ON' : 'OFF'}</span>
            </button>
          </div>

          {/* Playback Speed Controls */}
          <div className="space-y-1.5">
            <label className="text-[11px] font-semibold text-surface-400 flex items-center gap-1.5">
              <Sliders className="h-3.5 w-3.5 text-brand-400" />
              <span>Playback Speed (for Human Transcription):</span>
            </label>
            <div className="grid grid-cols-5 gap-1.5">
              {[0.5, 0.75, 1.0, 1.25, 1.5].map(spd => (
                <button
                  key={spd}
                  type="button"
                  onClick={() => handleSpeedChange(spd)}
                  className={`py-1.5 rounded-lg text-xs font-mono font-semibold transition-colors border ${
                    playbackSpeed === spd
                      ? 'bg-brand-600 text-white border-brand-500'
                      : 'bg-surface-950 text-surface-400 border-surface-800 hover:bg-surface-800 hover:text-surface-200'
                  }`}
                >
                  {spd}x
                </button>
              ))}
            </div>
          </div>

          {/* Candidate Models to Compare */}
          <div className="space-y-2 pt-2 border-t border-surface-800/60">
            <label className="text-xs font-semibold text-surface-300 block">Candidate Models for Comparison:</label>
            <div className="space-y-1.5">
              {availableModels.map(m => (
                <label
                  key={m.id}
                  className={`flex items-center justify-between p-2.5 rounded-xl border cursor-pointer transition-colors text-xs ${
                    selectedModels.includes(m.id)
                      ? 'border-brand-500/50 bg-brand-500/10 text-white'
                      : 'border-surface-800 bg-surface-900/40 text-surface-400 hover:border-surface-700'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={selectedModels.includes(m.id)}
                      onChange={() => handleToggleModel(m.id)}
                      className="rounded border-surface-700 bg-surface-800 text-brand-500"
                    />
                    <span className="font-semibold">{m.name}</span>
                    {m.is_experimental && (
                      <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[9px] font-bold text-amber-400 border border-amber-500/30">
                        Experimental
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] text-surface-500 font-mono">
                    {m.is_downloaded ? 'Ready' : 'Download Needed'}
                  </span>
                </label>
              ))}
            </div>
          </div>

          {/* Audio Preprocessing Option */}
          <div className="space-y-1.5 pt-2 border-t border-surface-800/60 text-xs">
            <label className="text-surface-400 font-semibold block">Audio Preprocessing Preset:</label>
            <select
              value={audioFilter}
              onChange={e => setAudioFilter(e.target.value as any)}
              className="w-full rounded-lg border border-surface-800 bg-surface-950 p-2 text-xs text-white"
            >
              <option value="none">Standard Audio (Baseline)</option>
              <option value="highpass_gain">80Hz High-Pass + 3dB Gain (Acoustic Filter)</option>
            </select>
          </div>
        </div>

        {/* Human Ground Truth Reference Panel */}
        <div className="lg:col-span-2 rounded-2xl border border-surface-800 bg-surface-900/50 p-5 light:border-surface-200 light:bg-white space-y-4 flex flex-col justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-bold text-white light:text-surface-900 flex items-center gap-2">
                  <FileText className="h-4 w-4 text-emerald-400" />
                  <span>Human Ground-Truth Reference</span>
                </h3>
                <span className="text-xs text-surface-400 font-normal">
                  {activeSample.name} ({activeSample.start_time.toFixed(1)}s - {activeSample.end_time.toFixed(1)}s)
                </span>
              </div>

              <div className="flex items-center gap-2">
                <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold tracking-wide uppercase border ${referenceStatusClass}`}>
                  {referenceStatusLabel}
                </span>
                <span className="text-xs font-mono text-surface-400">
                  {currentWordCount} words
                </span>
              </div>
            </div>

            {/* Reference Editor Textarea */}
            <textarea
              rows={6}
              value={refText}
              onChange={e => setRefText(e.target.value)}
              placeholder="Listen to the audio and transcribe the exact words spoken by human speakers (Egyptian Arabic + English technical loanwords)..."
              className="w-full rounded-xl border border-surface-800 bg-surface-950/80 p-3.5 text-xs text-white placeholder:text-surface-600 focus:outline-none focus:border-brand-500 resize-none font-sans leading-relaxed"
              dir="rtl"
            />

            {/* Human Verification Certification Checkbox */}
            <div className="p-3 rounded-xl bg-surface-950/70 border border-surface-800/90 text-xs space-y-1">
              <label className="flex items-start gap-2.5 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={certificationChecked}
                  onChange={e => setCertificationChecked(e.target.checked)}
                  className="mt-0.5 rounded border-surface-700 bg-surface-800 text-brand-500 focus:ring-brand-500 cursor-pointer h-4 w-4"
                />
                <span className="text-[11px] text-surface-200 leading-relaxed">
                  <strong className="text-white font-semibold">Human Certification Check:</strong>{' '}
                  I confirm that I personally listened to the original audio and manually verified this transcript against what was actually spoken.
                </span>
              </label>
            </div>
          </div>

          {/* Controls & Action Buttons */}
          <div className="pt-3 border-t border-surface-800/80 flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex flex-wrap items-center gap-3">
              <div>
                <label className="text-surface-400 mr-2">Evaluation Mode:</label>
                <select
                  value={evalMode}
                  onChange={e => setEvalMode(e.target.value as any)}
                  className="rounded-lg border border-surface-800 bg-surface-900 px-2.5 py-1 text-xs text-white"
                >
                  <option value="normalized">Normalized (Arabic/English Standard)</option>
                  <option value="raw">Raw (Exact Casing & Punctuation)</option>
                </select>
              </div>

              <div>
                <label className="text-surface-400 mr-2">VAD Filter:</label>
                <select
                  value={vadFilter ? 'true' : 'false'}
                  onChange={e => setVadFilter(e.target.value === 'true')}
                  className="rounded-lg border border-surface-800 bg-surface-900 px-2.5 py-1 text-xs text-white"
                >
                  <option value="false">Disabled (Optimal for Speech Note)</option>
                  <option value="true">Enabled (Silero VAD)</option>
                </select>
              </div>
            </div>

            {/* Action Buttons: Save Draft, Save & Verify, Calculate Accuracy, Run Benchmark */}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={isSavingDraft || isVerifying || isRunning}
                onClick={handleSaveDraft}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-surface-700 bg-surface-800 text-xs font-semibold text-white hover:bg-surface-700 disabled:opacity-50 transition-colors"
                title="Save transcript as draft without certifying. Verification is required before accuracy metrics can be calculated."
              >
                <Save className="h-3.5 w-3.5 text-surface-300" />
                <span>{isSavingDraft ? 'Saving Draft...' : 'Save Draft'}</span>
              </button>

              <button
                type="button"
                disabled={isSavingDraft || isVerifying || isRunning}
                onClick={handleSaveAndVerify}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-emerald-500/40 bg-emerald-600/20 text-xs font-semibold text-emerald-300 hover:bg-emerald-600/30 disabled:opacity-50 transition-colors shadow-sm"
                title="Certify transcript as manually verified by a human to unlock valid WER/CER calculations."
              >
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                <span>{isVerifying ? 'Certifying...' : 'Save & Verify Reference'}</span>
              </button>

              {currentResults.length > 0 && isHumanVerified && (
                <button
                  type="button"
                  disabled={isCalculatingAccuracy || isRunning}
                  onClick={handleCalculateAccuracy}
                  className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-brand-500/40 bg-brand-500/20 text-xs font-semibold text-brand-300 hover:bg-brand-500/30 disabled:opacity-50 transition-colors"
                  title="Recalculate WER/CER from cached candidate predictions without re-running models"
                >
                  <Calculator className={`h-3.5 w-3.5 text-brand-400 ${isCalculatingAccuracy ? 'animate-spin' : ''}`} />
                  <span>{isCalculatingAccuracy ? 'Calculating...' : 'Calculate Accuracy'}</span>
                </button>
              )}

              <button
                type="button"
                disabled={isRunning}
                onClick={handleRunBenchmark}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-600 text-xs font-bold text-white shadow-lg shadow-brand-500/25 hover:bg-brand-500 disabled:opacity-50 transition-all active:scale-[0.98]"
              >
                <Sparkles className={`h-4 w-4 ${isRunning ? 'animate-spin' : ''}`} />
                <span>{isRunning ? 'Evaluating...' : 'Run Benchmark'}</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Status banner while benchmarking */}
      {statusMessage && (
        <div className="rounded-xl border border-brand-500/30 bg-brand-500/10 p-4 text-center text-xs font-semibold text-brand-300 animate-pulse">
          {statusMessage}
        </div>
      )}

      {/* Candidate Performance Matrix Table */}
      {currentResults.length > 0 && (
        <div className="space-y-6 animate-fadeIn">
          <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-4">
            <h3 className="text-base font-bold text-white light:text-surface-900 flex items-center justify-between">
              <span className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5 text-brand-400" />
                <span>Candidate Performance Matrix ({evalMode === 'normalized' ? 'Normalized Metrics' : 'Raw Metrics'})</span>
              </span>
              <span className="text-xs font-normal text-surface-400">
                Sample: {activeSample.name} ({activeSample.start_time.toFixed(1)}s - {activeSample.end_time.toFixed(1)}s)
              </span>
            </h3>

            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left rtl:text-right">
                <thead className="bg-surface-950/80 text-surface-400 uppercase text-[10px] font-bold tracking-wider">
                  <tr>
                    <th className="p-3">Model Candidate</th>
                    <th className="p-3">Device / Compute</th>
                    <th className="p-3 text-center">WER (%)</th>
                    <th className="p-3 text-center">CER (%)</th>
                    <th className="p-3 text-center">Sub (S)</th>
                    <th className="p-3 text-center">Del (D)</th>
                    <th className="p-3 text-center">Ins (I)</th>
                    <th className="p-3 text-center">Inference Time</th>
                    <th className="p-3 text-center">Speedup</th>
                    <th className="p-3 text-right rtl:text-left">Inspect</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-800/60 font-mono">
                  {currentResults.map((r, idx) => {
                    const isSuccess = r.status === 'success';
                    const isCurrent = idx === selectedResultIndex;
                    const isRowVerified = Boolean(r.is_verified && isHumanVerified && r.norm_wer !== null);

                    const wer = evalMode === 'normalized' ? r.norm_wer : r.raw_wer;
                    const cer = evalMode === 'normalized' ? r.norm_cer : r.raw_cer;
                    const sub = evalMode === 'normalized' ? r.norm_sub : r.raw_sub;
                    const del = evalMode === 'normalized' ? r.norm_del : r.raw_del;
                    const ins = evalMode === 'normalized' ? r.norm_ins : r.raw_ins;

                    const isLowestError =
                      isRowVerified &&
                      lowestWer !== null &&
                      typeof wer === 'number' &&
                      Math.abs(wer - lowestWer) < 0.001 &&
                      validEvaluatedResults.length > 1;

                    return (
                      <tr
                        key={idx}
                        className={`transition-colors cursor-pointer ${
                          isCurrent ? 'bg-brand-500/10' : 'hover:bg-surface-800/40'
                        }`}
                        onClick={() => setSelectedResultIndex(idx)}
                      >
                        <td className="p-3 font-sans font-bold text-white">
                          <div className="flex items-center gap-2">
                            <span>{r.name}</span>
                            {isLowestError && (
                              <span className="px-1.5 py-0.5 rounded text-[9px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                                Lowest Error Rate
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="p-3 text-surface-300">
                          {isSuccess ? (
                            <span className="inline-flex items-center gap-1 font-semibold text-emerald-400">
                              {r.device === 'cuda' ? <Zap className="h-3 w-3" /> : <Cpu className="h-3 w-3" />}
                              <span>{r.device?.toUpperCase()} ({r.compute})</span>
                            </span>
                          ) : (
                            <span className="text-rose-400 font-sans">{r.status}</span>
                          )}
                        </td>
                        <td className="p-3 text-center font-bold text-sm">
                          {isSuccess ? (
                            isRowVerified && typeof wer === 'number' ? (
                              <span className={wer < 60 ? 'text-emerald-400' : 'text-amber-400'}>
                                {wer.toFixed(2)}%
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded text-[10px] bg-amber-500/15 text-amber-300 border border-amber-500/30">
                                UNVERIFIED — Draft
                              </span>
                            )
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="p-3 text-center font-bold text-sm">
                          {isSuccess && isRowVerified && typeof cer === 'number' ? (
                            <span className={cer < 35 ? 'text-emerald-400' : 'text-amber-400'}>
                              {cer.toFixed(2)}%
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="p-3 text-center text-amber-400">{isSuccess && isRowVerified ? sub : '—'}</td>
                        <td className="p-3 text-center text-rose-400">{isSuccess && isRowVerified ? del : '—'}</td>
                        <td className="p-3 text-center text-purple-400">{isSuccess && isRowVerified ? ins : '—'}</td>
                        <td className="p-3 text-center text-surface-300">
                          {isSuccess ? `${r.elapsed_seconds}s` : '—'}
                        </td>
                        <td className="p-3 text-center font-bold text-brand-300">
                          {isSuccess ? `${r.speedup}x` : '—'}
                        </td>
                        <td className="p-3 text-right rtl:text-left">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedResultIndex(idx);
                            }}
                            className={`px-2.5 py-1 rounded-lg text-xs font-sans font-semibold transition-colors ${
                              isCurrent ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-300 hover:bg-surface-700'
                            }`}
                          >
                            {isCurrent ? 'Viewing' : 'Inspect'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* If inference complete but unverified reference */}
            {!isHumanVerified && currentResults.length > 0 && (
              <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/30 text-xs text-blue-200 flex items-center justify-between gap-4">
                <span className="flex items-center gap-2">
                  <Info className="h-4 w-4 text-blue-400 shrink-0" />
                  <span>Model inference completed. Verify the human reference above to unlock accuracy metrics.</span>
                </span>
                <button
                  type="button"
                  onClick={handleSaveAndVerify}
                  className="px-3 py-1.5 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-500 text-xs shrink-0"
                >
                  Certify & Calculate
                </button>
              </div>
            )}
          </div>

          {/* Model Transcript Inspection Panel */}
          {activeResult && activeResult.status === 'success' && (
            <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="text-base font-bold text-white light:text-surface-900 flex items-center gap-2">
                    <Layers className="h-5 w-5 text-brand-400" />
                    <span>Candidate Transcript: {activeResult.name}</span>
                  </h3>
                  <p className="text-xs text-surface-400">
                    {activeResult.is_verified && isHumanVerified
                      ? 'Inspecting prediction against verified human ground truth with edit operations.'
                      : 'Unverified sample prediction. Review spoken audio against this candidate to prepare human reference.'}
                  </p>
                </div>

                {activeResult.is_verified && isHumanVerified && currentResults.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setIsComparingSideBySide(!isComparingSideBySide)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-surface-700 bg-surface-800 text-xs font-semibold text-white hover:bg-surface-700"
                  >
                    <Columns className="h-3.5 w-3.5" />
                    <span>{isComparingSideBySide ? 'Single View' : 'Side-by-Side'}</span>
                  </button>
                )}
              </div>

              {/* Prediction Text Display */}
              <div className="p-4 rounded-xl bg-surface-950/80 border border-surface-800 text-sm text-white font-sans leading-relaxed" dir="rtl">
                {activeResult.predicted_text || 'No prediction generated.'}
              </div>

              {/* Word-Level Diff (only if verified) */}
              {activeResult.is_verified && isHumanVerified && activeResult.word_alignment && activeResult.word_alignment.length > 0 && (
                <div className="space-y-3 pt-3 border-t border-surface-800/60">
                  <span className="text-xs font-bold text-surface-300 block">Visual Word-Level Alignment:</span>
                  <div className="p-4 rounded-xl bg-surface-950/60 border border-surface-800 flex flex-wrap gap-1.5 text-xs leading-loose" dir="rtl">
                    {activeResult.word_alignment.map((op, i) => {
                      if (op.type === 'equal') {
                        return (
                          <span key={i} className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                            {op.hyp}
                          </span>
                        );
                      }
                      if (op.type === 'substitute') {
                        return (
                          <span key={i} className="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 line-through decoration-rose-400">
                            {op.hyp} <span className="text-[10px] text-surface-400 font-mono no-underline">({op.ref})</span>
                          </span>
                        );
                      }
                      if (op.type === 'delete') {
                        return (
                          <span key={i} className="px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30">
                            [{op.ref}]
                          </span>
                        );
                      }
                      if (op.type === 'insert') {
                        return (
                          <span key={i} className="px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30">
                            +{op.hyp}
                          </span>
                        );
                      }
                      return null;
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Create Benchmark Sample Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-xl rounded-2xl border border-surface-700 bg-surface-900 p-6 shadow-2xl space-y-5 text-white">
            <div className="flex items-center justify-between border-b border-surface-800 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-brand-500/20 text-brand-400">
                  <Plus className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">Create Benchmark Sample</h3>
                  <p className="text-xs text-surface-400">
                    Extract an audio interval from any uploaded recording for human transcription & evaluation.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowCreateModal(false);
                  if (previewAudioRef.current) {
                    previewAudioRef.current.pause();
                    setPreviewPlaying(false);
                  }
                }}
                className="p-1.5 rounded-lg hover:bg-surface-800 text-surface-400 hover:text-white transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {isLoadingRecordings ? (
              <div className="py-8 text-center space-y-2">
                <RefreshCw className="h-6 w-6 animate-spin text-brand-400 mx-auto" />
                <p className="text-xs text-surface-400">Loading uploaded recordings from history...</p>
              </div>
            ) : sourceRecordings.length === 0 ? (
              <div className="py-8 text-center space-y-2">
                <AlertTriangle className="h-6 w-6 text-amber-400 mx-auto" />
                <p className="text-xs text-surface-300">No completed recordings found in History.</p>
                <p className="text-[11px] text-surface-500">Please upload and transcribe an audio recording first.</p>
              </div>
            ) : (
              <form onSubmit={handleCreateSampleSubmit} className="space-y-4">
                {/* Source Recording Dropdown */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-surface-300 block">Source Recording:</label>
                  <select
                    value={selectedSourceJobId}
                    onChange={e => handleSelectRecording(e.target.value)}
                    className="w-full rounded-xl border border-surface-700 bg-surface-950 p-2.5 text-xs text-white focus:outline-none focus:border-brand-500"
                  >
                    {sourceRecordings.map(rec => (
                      <option key={rec.job_id} value={rec.job_id}>
                        {rec.filename.replace(/^[a-f0-9]+_/, '')} ({rec.duration_formatted}) • {new Date(rec.created_at).toLocaleDateString()}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Interval Boundaries */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-surface-300 block">Start Timestamp (seconds):</label>
                    <input
                      type="number"
                      step="0.5"
                      min="0"
                      value={newSampleStart}
                      onChange={e => {
                        const val = Math.max(0, parseFloat(e.target.value) || 0);
                        setNewSampleStart(val);
                        const rec = sourceRecordings.find(r => r.job_id === selectedSourceJobId);
                        if (rec) {
                          const cleanName = rec.filename.replace(/^[a-f0-9]+_/, '');
                          setNewSampleName(`${cleanName} (${formatTime(val)} - ${formatTime(newSampleEnd)})`);
                        }
                      }}
                      className="w-full rounded-xl border border-surface-700 bg-surface-950 p-2.5 text-xs text-white focus:outline-none focus:border-brand-500 font-mono"
                    />
                    <span className="text-[10px] text-surface-400 font-mono">{formatTime(newSampleStart)}</span>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-surface-300 block">End Timestamp (seconds):</label>
                    <input
                      type="number"
                      step="0.5"
                      min={newSampleStart + 1}
                      value={newSampleEnd}
                      onChange={e => {
                        const val = Math.max(newSampleStart + 0.5, parseFloat(e.target.value) || 0);
                        setNewSampleEnd(val);
                        const rec = sourceRecordings.find(r => r.job_id === selectedSourceJobId);
                        if (rec) {
                          const cleanName = rec.filename.replace(/^[a-f0-9]+_/, '');
                          setNewSampleName(`${cleanName} (${formatTime(newSampleStart)} - ${formatTime(val)})`);
                        }
                      }}
                      className="w-full rounded-xl border border-surface-700 bg-surface-950 p-2.5 text-xs text-white focus:outline-none focus:border-brand-500 font-mono"
                    />
                    <span className="text-[10px] text-surface-400 font-mono">{formatTime(newSampleEnd)}</span>
                  </div>
                </div>

                {/* Duration Badge & Presets */}
                <div className="flex items-center justify-between p-2.5 rounded-xl bg-surface-950 border border-surface-800">
                  <div className="flex items-center gap-2">
                    <Clock className="h-4 w-4 text-brand-400" />
                    <span className="text-xs text-surface-300">Selected Interval Duration:</span>
                    <span className="px-2 py-0.5 rounded-md bg-brand-500/20 text-brand-300 font-mono text-xs font-bold">
                      {Math.max(0, newSampleEnd - newSampleStart).toFixed(1)}s
                    </span>
                  </div>

                  {/* Interval Presets */}
                  <div className="flex items-center gap-1.5">
                    <span className="text-[11px] text-surface-500 mr-1">Presets:</span>
                    {[30, 45, 60].map(dur => (
                      <button
                        key={dur}
                        type="button"
                        onClick={() => {
                          const rec = sourceRecordings.find(r => r.job_id === selectedSourceJobId);
                          const maxDur = rec?.duration || 300;
                          const newEnd = Math.min(maxDur, newSampleStart + dur);
                          setNewSampleEnd(newEnd);
                          if (rec) {
                            const cleanName = rec.filename.replace(/^[a-f0-9]+_/, '');
                            setNewSampleName(`${cleanName} (${formatTime(newSampleStart)} - ${formatTime(newEnd)})`);
                          }
                        }}
                        className="px-2 py-1 rounded-lg border border-surface-700 bg-surface-850 hover:bg-surface-750 text-[10px] font-semibold text-surface-300 transition-colors"
                      >
                        +{dur}s
                      </button>
                    ))}
                  </div>
                </div>

                {/* Audio Preview Card */}
                <div className="p-3 rounded-xl bg-surface-950 border border-surface-800 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Volume2 className="h-4 w-4 text-emerald-400" />
                    <div className="text-left">
                      <span className="text-xs font-semibold text-white block">Preview Interval Audio</span>
                      <span className="text-[10px] text-surface-400">Listen to verify speaker voices and boundaries before saving</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={handleTogglePreview}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs transition-colors shadow-md"
                  >
                    {previewPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                    <span>{previewPlaying ? 'Pause' : 'Listen Preview'}</span>
                  </button>
                </div>

                {/* Hidden Audio Tag for Modal Preview */}
                <audio
                  ref={previewAudioRef}
                  onEnded={() => setPreviewPlaying(false)}
                  onError={() => setPreviewPlaying(false)}
                />

                {/* Sample Name Input */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-surface-300 block">Sample Display Name:</label>
                  <input
                    type="text"
                    value={newSampleName}
                    onChange={e => setNewSampleName(e.target.value)}
                    placeholder="e.g., new dd.ogg (00:30 - 01:15)"
                    className="w-full rounded-xl border border-surface-700 bg-surface-950 p-2.5 text-xs text-white focus:outline-none focus:border-brand-500"
                    required
                  />
                </div>

                {/* Sample Description */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-surface-300 block">Description & Research Notes (Optional):</label>
                  <input
                    type="text"
                    value={newSampleDescription}
                    onChange={e => setNewSampleDescription(e.target.value)}
                    placeholder="e.g., Technical team sync with fast Egyptian colloquial Arabic and English terms"
                    className="w-full rounded-xl border border-surface-700 bg-surface-950 p-2 text-xs text-white focus:outline-none focus:border-brand-500"
                  />
                </div>

                {/* Modal Action Buttons */}
                <div className="flex items-center justify-end gap-3 pt-3 border-t border-surface-800">
                  <button
                    type="button"
                    onClick={() => {
                      setShowCreateModal(false);
                      if (previewAudioRef.current) {
                        previewAudioRef.current.pause();
                        setPreviewPlaying(false);
                      }
                    }}
                    className="px-4 py-2 rounded-xl border border-surface-700 bg-surface-800 hover:bg-surface-700 text-xs font-semibold text-surface-300 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isCreatingSample}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-bold text-xs transition-colors shadow-lg shadow-brand-500/20 disabled:opacity-50"
                  >
                    {isCreatingSample ? (
                      <>
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        <span>Extracting & Creating Sample...</span>
                      </>
                    ) : (
                      <>
                        <Check className="h-3.5 w-3.5" />
                        <span>Create Benchmark Sample</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
