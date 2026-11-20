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
} from 'lucide-react';

interface BenchmarkProps {
  hardware: HardwareInfo | null;
}

export const Benchmark: React.FC<BenchmarkProps> = ({ hardware }) => {
  const { t, isRTL } = useI18n();

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
      description: 'Strict unseen out-of-sample holdout audio interval (05:00 - 05:45). Reference left blank for manual human transcription.',
    },
  ]);
  const [activeSampleId, setActiveSampleId] = useState<string>('test_180_225');

  // Human Reference & Boundaries State
  const [refText, setRefText] = useState<string>('');
  const [isHumanVerified, setIsHumanVerified] = useState<boolean>(false);
  const [verificationBadge, setVerificationBadge] = useState<string>('UNVERIFIED — No valid WER/CER available');
  const [certificationChecked, setCertificationChecked] = useState<boolean>(false);

  const [startTime, setStartTime] = useState<number>(180.0);
  const [endTime, setEndTime] = useState<number>(225.0);
  const [selectedModels, setSelectedModels] = useState<string[]>([
    'codeswitched-medium',
    'medium',
    'large-v3-turbo',
  ]);
  const [deviceMode, setDeviceMode] = useState<string>('auto');
  const [evalMode, setEvalMode] = useState<'normalized' | 'raw'>('normalized');
  const [vadFilter, setVadFilter] = useState<boolean>(false); // False prevents clipping conversational onsets
  const [useHints, setUseHints] = useState<boolean>(false);
  const [customHints, setCustomHints] = useState<string>('');

  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [results, setResults] = useState<BenchmarkRunResult[]>([]);
  const [selectedResultIndex, setSelectedResultIndex] = useState<number>(0);
  const [compareIndexB, setCompareIndexB] = useState<number>(1);
  const [isComparingSideBySide, setIsComparingSideBySide] = useState<boolean>(false);

  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Live Human Correction State
  const [editedHypText, setEditedHypText] = useState<string>('');
  const [isLiveAligning, setIsLiveAligning] = useState<boolean>(false);

  // Audio Playback State
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isLooping, setIsLooping] = useState<boolean>(true);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0);
  const [currentTime, setCurrentTime] = useState<number>(0.0);
  const [audioDuration, setAudioDuration] = useState<number>(45.0);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
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

    loadSampleData('test_180_225');
  }, []);

  const loadSampleData = async (sampleId: string) => {
    setActiveSampleId(sampleId);
    try {
      const refRes = await api.getBenchmarkReference(sampleId);
      setRefText(refRes.raw_text || '');
      setIsHumanVerified(Boolean(refRes.is_human_verified));
      setVerificationBadge(refRes.verification_status || (refRes.is_human_verified ? 'Verified Human Reference' : 'UNVERIFIED — No valid WER/CER available'));
      setCertificationChecked(Boolean(refRes.is_human_verified));

      if (refRes.start_time !== undefined) setStartTime(refRes.start_time);
      if (refRes.end_time !== undefined) setEndTime(refRes.end_time);

      const resultsRes = await api.getBenchmarkResults(sampleId);
      if (resultsRes.has_results && resultsRes.results.length > 0) {
        setResults(resultsRes.results);
        setSelectedResultIndex(0);
        if (resultsRes.results.length > 1) setCompareIndexB(1);
      } else {
        setResults([]);
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
    loadSampleData(sampleId);
  };

  // Update edited hypothesis whenever selected result changes
  useEffect(() => {
    if (results[selectedResultIndex]?.predicted_text) {
      setEditedHypText(results[selectedResultIndex].predicted_text || '');
    }
  }, [selectedResultIndex, results]);

  const handleSaveReference = async () => {
    if (!refText.trim()) {
      alert('Please enter reference text before saving.');
      return;
    }

    if (activeSampleId === 'test_180_225' && !certificationChecked) {
      alert('Integrity Safeguard: You must certify that this transcript was verified manually by a human against the audio before saving.');
      return;
    }

    try {
      const res = await api.saveBenchmarkReference({
        sample_id: activeSampleId,
        reference_text: refText.trim(),
        start_time: startTime,
        end_time: endTime,
        is_human_verified: certificationChecked,
        verification_statement: certificationChecked
          ? 'Human user manually transcribed and verified against dd.ogg recording.'
          : undefined,
      });

      setIsHumanVerified(res.is_human_verified);
      setVerificationBadge(res.is_human_verified ? `Verified Human Reference (${refText.trim().split(/\s+/).length} words)` : 'UNVERIFIED — No valid WER/CER available');

      // Refresh samples list
      const samplesRes = await api.getBenchmarkSamples();
      if (samplesRes.samples) setSamples(samplesRes.samples);

      showToast(res.message || 'Reference saved successfully!');
    } catch (err: any) {
      alert('Failed to save reference: ' + err.message);
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

  const handleRunBenchmark = async () => {
    setIsRunning(true);
    setStatusMessage(`Running candidate models on ${activeSampleId === 'test_180_225' ? 'Independent Test Sample (03:00 - 03:45)' : 'Development Sample'}...`);

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
      });

      setResults(res.results || []);
      setSelectedResultIndex(0);
      if (res.results && res.results.length > 1) {
        setCompareIndexB(1);
      }

      if (res.is_human_verified) {
        showToast('Benchmark run completed with verified WER/CER metrics!');
      } else {
        showToast('Transcription generated. Metrics marked UNVERIFIED pending human reference.');
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

  const handleRecalculateAlignment = async () => {
    if (!refText.trim() || !editedHypText.trim()) return;
    setIsLiveAligning(true);
    try {
      const res = await api.liveAlign(refText, editedHypText, evalMode);
      if (res.status === 'success' && res.metrics) {
        const m = res.metrics;
        const updated = [...results];
        if (updated[selectedResultIndex]) {
          updated[selectedResultIndex] = {
            ...updated[selectedResultIndex],
            norm_wer: m.wer_percent,
            norm_cer: m.cer_percent,
            norm_sub: m.substitutions,
            norm_del: m.deletions,
            norm_ins: m.insertions,
            norm_hits: m.hits,
            predicted_text: editedHypText,
            word_alignment: m.word_alignment,
          };
          setResults(updated);
          showToast('Live alignment recalculated successfully!');
        }
      }
    } catch (e: any) {
      alert('Alignment calculation failed: ' + e.message);
    } finally {
      setIsLiveAligning(false);
    }
  };

  const handleExportReport = () => {
    if (results.length === 0) return;
    const dateStr = new Date().toISOString().replace('T', ' ').substring(0, 19);
    let md = `# VerbatimAI Accuracy Benchmark Report\n\n`;
    md += `**Date**: ${dateStr}\n`;
    md += `**Sample**: ${activeSampleId === 'test_180_225' ? 'Independent Test Sample (03:00 - 03:45)' : 'Development Sample (00:00 - 01:43)'}\n`;
    md += `**Verification Status**: ${isHumanVerified ? 'VERIFIED HUMAN GROUND TRUTH' : 'UNVERIFIED — No valid WER/CER available'}\n`;
    md += `**Evaluation Mode**: ${evalMode}\n\n`;
    md += `## Candidate Performance Matrix\n\n`;
    md += `| Model | Device | Status | WER (%) | CER (%) | Sub (S) | Del (D) | Ins (I) | Time (s) | Speedup |\n`;
    md += `| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n`;
    results.forEach(r => {
      const isVer = r.is_verified && r.norm_wer !== null;
      const werStr = isVer ? `${(evalMode === 'normalized' ? r.norm_wer : r.raw_wer)?.toFixed(2)}%` : 'UNVERIFIED';
      const cerStr = isVer ? `${(evalMode === 'normalized' ? r.norm_cer : r.raw_cer)?.toFixed(2)}%` : '—';
      const sub = isVer ? (evalMode === 'normalized' ? r.norm_sub : r.raw_sub) : '—';
      const del = isVer ? (evalMode === 'normalized' ? r.norm_del : r.raw_del) : '—';
      const ins = isVer ? (evalMode === 'normalized' ? r.norm_ins : r.raw_ins) : '—';
      md += `| **${r.name}** | ${r.device || 'N/A'} (${r.compute || ''}) | ${isVer ? 'Verified' : 'Unverified'} | ${werStr} | ${cerStr} | ${sub} | ${del} | ${ins} | ${r.elapsed_seconds || 0}s | ${r.speedup || 0}x |\n`;
    });
    md += `\n## Human Reference\n\n\`\`\`text\n${refText || '[No human reference provided yet]'}\n\`\`\`\n\n`;
    md += `## Model Predictions\n\n`;
    results.forEach(r => {
      md += `### ${r.name}\n\n\`\`\`text\n${r.predicted_text || 'No prediction'}\n\`\`\`\n\n`;
    });

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `verbatim_ai_benchmark_${activeSampleId}_${Math.round(startTime)}s_${Math.round(endTime)}s.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showToast('Benchmark report exported as Markdown!');
  };

  const activeResult = results[selectedResultIndex] || null;
  const compareResult = results[compareIndexB] || null;

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
          if (audioRef.current) setAudioDuration(audioRef.current.duration || 45.0);
        }}
        onEnded={handleAudioEnded}
      />

      {/* Page Title & Integrity Badge */}
      <div className="space-y-1">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-black text-white light:text-surface-900 flex items-center gap-2.5">
              <BarChart3 className="h-7 w-7 text-brand-400" />
              <span>ASR Accuracy Benchmark & Integrity Review</span>
            </h1>
            <p className="text-xs sm:text-sm text-surface-400 light:text-surface-600">
              Controlled speech recognition benchmarking with strict human-verification safeguards and zero synthetic ground truth.
            </p>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2">
            {results.length > 0 && (
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
            The previously reported 30.22% WER on audio slice 245s–295s has been invalidated because the reference was bootstrapped using model assistance rather than human transcription. In Verbatim AI, no transcript is considered ground truth without explicit human certification.
          </p>
        </div>
      </div>

      {/* Benchmark Sample Switcher Tabs */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {samples.map(s => {
          const isSelected = s.sample_id === activeSampleId;
          const isVerified = s.status === 'VERIFIED';

          return (
            <div
              key={s.sample_id}
              onClick={() => handleSelectSample(s.sample_id)}
              className={`p-4 rounded-2xl border cursor-pointer transition-all ${
                isSelected
                  ? 'border-brand-500/80 bg-brand-500/10 ring-1 ring-brand-500/40 shadow-lg'
                  : 'border-surface-800 bg-surface-900/40 hover:bg-surface-850 hover:border-surface-700'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-bold text-white flex items-center gap-2">
                  <FileText className={`h-4 w-4 ${isSelected ? 'text-brand-400' : 'text-surface-400'}`} />
                  <span>{s.name}</span>
                </span>
                <span
                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wide uppercase border ${
                    isVerified
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                      : 'bg-amber-500/20 text-amber-300 border-amber-500/30'
                  }`}
                >
                  {isVerified ? 'VERIFIED HUMAN' : 'UNVERIFIED'}
                </span>
              </div>
              <p className="text-xs text-surface-400 leading-relaxed mb-3">{s.description}</p>
              <div className="flex items-center justify-between text-[11px] font-mono text-surface-400 pt-2 border-t border-surface-800/60">
                <span>Duration: {s.duration.toFixed(1)}s</span>
                <span>Word Count: {s.word_count} words</span>
                <span className="font-sans font-semibold text-brand-300">
                  {isSelected ? '● Active Sample' : 'Click to Switch'}
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
              max={audioDuration || 45.0}
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
            <label className="text-[11px] font-semibold text-surface-400 block flex items-center gap-1.5">
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
                  </div>
                  <span className="text-[10px] text-surface-500 font-mono">
                    {m.is_downloaded ? 'Ready' : 'Download Needed'}
                  </span>
                </label>
              ))}
            </div>
          </div>
        </div>

        {/* Human Ground Truth Reference Panel */}
        <div className="lg:col-span-2 rounded-2xl border border-surface-800 bg-surface-900/50 p-5 light:border-surface-200 light:bg-white space-y-4 flex flex-col justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-bold text-white light:text-surface-900 flex items-center gap-2">
                <FileText className="h-4 w-4 text-emerald-400" />
                <span>Human Ground-Truth Reference</span>
              </h3>

              <div className="flex items-center gap-2">
                <span
                  className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold tracking-wide uppercase border ${
                    isHumanVerified
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                      : 'bg-amber-500/20 text-amber-300 border-amber-500/30 animate-pulse'
                  }`}
                >
                  {isHumanVerified ? 'VERIFIED' : 'UNVERIFIED — No valid WER/CER available'}
                </span>
                <span className="text-xs font-mono text-surface-400">
                  {refText.split(/\s+/).filter(Boolean).length} words
                </span>
              </div>
            </div>

            {/* Unverified Warning Banner if in test sample */}
            {activeSampleId === 'test_180_225' && !isHumanVerified && (
              <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/25 text-xs text-amber-200 space-y-1">
                <span className="font-bold flex items-center gap-1.5 text-amber-300">
                  <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
                  <span>Manual Human Verification Required</span>
                </span>
                <p className="text-[11px] text-amber-200/90 leading-relaxed">
                  This 45-second audio slice (03:00 - 03:45) is an independent test sample. Play the audio on the left, transcribe the spoken words into the editor below, and check the certification box to unlock verified WER/CER benchmarking.
                </p>
              </div>
            )}

            <textarea
              rows={6}
              value={refText}
              onChange={e => setRefText(e.target.value)}
              placeholder={
                activeSampleId === 'test_180_225'
                  ? 'Listen to the 45-second audio and type the human ground-truth transcript here...'
                  : 'Paste or edit the human ground-truth reference transcript...'
              }
              className="w-full rounded-xl border border-surface-800 bg-surface-950/80 p-3.5 text-xs text-white placeholder:text-surface-600 focus:outline-none focus:border-brand-500 resize-none font-sans leading-relaxed"
              dir="rtl"
            />

            {/* Human Verification Certification Checkbox */}
            {activeSampleId === 'test_180_225' && (
              <label className="flex items-start gap-2.5 p-3 rounded-xl bg-surface-950/60 border border-surface-800/80 text-xs text-surface-200 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={certificationChecked}
                  onChange={e => setCertificationChecked(e.target.checked)}
                  className="mt-0.5 rounded border-surface-700 bg-surface-800 text-brand-500 focus:ring-brand-500"
                />
                <span className="text-[11px] leading-relaxed">
                  <strong className="text-white">Human Certification:</strong> I certify that this transcript was verified manually by a human against the audio recording and was not copied or generated from an unverified ASR model prediction.
                </span>
              </label>
            )}
          </div>

          {/* Controls & Run Button */}
          <div className="pt-3 border-t border-surface-800/80 flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex flex-wrap items-center gap-3">
              <div>
                <label className="text-surface-400 mr-2">Evaluation Mode:</label>
                <select
                  value={evalMode}
                  onChange={e => setEvalMode(e.target.value as any)}
                  className="rounded-lg border border-surface-800 bg-surface-900 px-2.5 py-1 text-xs text-white"
                >
                  <option value="normalized">Normalized (Standard Arabic/English)</option>
                  <option value="raw">Raw (Exact Punctuation & Casing)</option>
                </select>
              </div>

              <div>
                <label className="text-surface-400 mr-2">VAD Filter:</label>
                <select
                  value={vadFilter ? 'true' : 'false'}
                  onChange={e => setVadFilter(e.target.value === 'true')}
                  className="rounded-lg border border-surface-800 bg-surface-900 px-2.5 py-1 text-xs text-white"
                >
                  <option value="false">Disabled (Optimal Egyptian Preset)</option>
                  <option value="true">Enabled (Silero VAD)</option>
                </select>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleSaveReference}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-surface-700 bg-surface-800 text-xs font-semibold text-white hover:bg-surface-700 transition-colors"
              >
                <Save className="h-3.5 w-3.5" />
                <span>Save Reference</span>
              </button>

              <button
                type="button"
                disabled={isRunning}
                onClick={handleRunBenchmark}
                className="flex items-center gap-2 px-5 py-2 rounded-xl bg-brand-600 text-xs font-bold text-white shadow-lg shadow-brand-500/25 hover:bg-brand-500 disabled:opacity-50 transition-all active:scale-[0.98]"
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
      {results.length > 0 && (
        <div className="space-y-6 animate-fadeIn">
          <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-4">
            <h3 className="text-base font-bold text-white light:text-surface-900 flex items-center justify-between">
              <span className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5 text-brand-400" />
                <span>Candidate Performance Matrix ({evalMode === 'normalized' ? 'Normalized Metrics' : 'Raw Metrics'})</span>
              </span>
              <span className="text-xs font-normal text-surface-400">
                Sample: {activeSampleId === 'test_180_225' ? 'Independent Test (03:00 - 03:45)' : 'Development Sample (00:00 - 01:43)'}
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
                  {results.map((r, idx) => {
                    const isSuccess = r.status === 'success';
                    const isCurrent = idx === selectedResultIndex;
                    const isVerified = r.is_verified && r.norm_wer !== null;

                    const wer = evalMode === 'normalized' ? r.norm_wer : r.raw_wer;
                    const cer = evalMode === 'normalized' ? r.norm_cer : r.raw_cer;
                    const sub = evalMode === 'normalized' ? r.norm_sub : r.raw_sub;
                    const del = evalMode === 'normalized' ? r.norm_del : r.raw_del;
                    const ins = evalMode === 'normalized' ? r.norm_ins : r.raw_ins;

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
                            {r.model_id === 'codeswitched-medium' && (
                              <span className="px-1.5 py-0.5 rounded text-[9px] bg-brand-500/20 text-brand-300 border border-brand-500/30">
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
                            isVerified ? (
                              <span className={wer! < 60 ? 'text-emerald-400' : 'text-amber-400'}>
                                {wer?.toFixed(2)}%
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded text-[10px] bg-amber-500/15 text-amber-300 border border-amber-500/30">
                                UNVERIFIED — No valid WER/CER available
                              </span>
                            )
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="p-3 text-center font-bold text-sm">
                          {isSuccess && isVerified ? (
                            <span className={cer! < 35 ? 'text-emerald-400' : 'text-amber-400'}>
                              {cer?.toFixed(2)}%
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="p-3 text-center text-amber-400">{isSuccess && isVerified ? sub : '—'}</td>
                        <td className="p-3 text-center text-rose-400">{isSuccess && isVerified ? del : '—'}</td>
                        <td className="p-3 text-center text-purple-400">{isSuccess && isVerified ? ins : '—'}</td>
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
                    {activeResult.is_verified
                      ? 'Inspecting prediction against verified human ground truth with edit operations.'
                      : 'Unverified sample prediction. Review spoken audio against this candidate to prepare human reference.'}
                  </p>
                </div>

                {activeResult.is_verified && results.length > 1 && (
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
              {activeResult.is_verified && activeResult.word_alignment && activeResult.word_alignment.length > 0 && (
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
    </div>
  );
};
