import React, { useState, useEffect, useRef } from 'react';
import { useI18n } from '../context/I18nContext';
import { HardwareInfo, ModelInfo, BenchmarkRunResult, WordAlignmentOp } from '../types';
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
} from 'lucide-react';

interface BenchmarkProps {
  hardware: HardwareInfo | null;
}

export const Benchmark: React.FC<BenchmarkProps> = ({ hardware }) => {
  const { t, isRTL } = useI18n();

  // State
  const [refText, setRefText] = useState<string>('');
  const [startTime, setStartTime] = useState<number>(0.0);
  const [endTime, setEndTime] = useState<number>(103.0);
  const [selectedModels, setSelectedModels] = useState<string[]>(['codeswitched-medium', 'medium']);
  const [deviceMode, setDeviceMode] = useState<string>('auto');
  const [evalMode, setEvalMode] = useState<'normalized' | 'raw'>('normalized');
  const [useHints, setUseHints] = useState<boolean>(false);
  const [customHints, setCustomHints] = useState<string>('');

  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [results, setResults] = useState<BenchmarkRunResult[]>([]);
  const [selectedResultIndex, setSelectedResultIndex] = useState<number>(0);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Audio Playback State
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isLooping, setIsLooping] = useState<boolean>(false);

  // Load initial reference and models
  useEffect(() => {
    api.getBenchmarkReference().then(res => {
      if (res.has_reference) {
        setRefText(res.raw_text);
        if (res.start_time !== undefined) setStartTime(res.start_time);
        if (res.end_time !== undefined) setEndTime(res.end_time);
      }
    });

    api.getModels().then(res => {
      setAvailableModels(res.models);
    });

    api.getBenchmarkResults().then(res => {
      if (res.has_results && res.results.length > 0) {
        setResults(res.results);
      }
    });
  }, []);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const handleSaveReference = async () => {
    try {
      await api.saveBenchmarkReference(refText, startTime, endTime);
      showToast('Human reference saved locally!');
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
    if (!refText.trim()) {
      alert('Please enter or preserve a human reference transcript first.');
      return;
    }
    setIsRunning(true);
    setStatusMessage('Running benchmark on audio interval (00:00 - 01:43)...');

    try {
      const res = await api.runBenchmark({
        start_time: startTime,
        end_time: endTime,
        model_ids: selectedModels,
        device_mode: deviceMode,
        use_hints: useHints,
        custom_hints: customHints.trim() ? customHints.trim() : null,
        eval_mode: evalMode,
      });

      setResults(res.results || []);
      setSelectedResultIndex(0);
      showToast('Benchmark run completed successfully!');
    } catch (err: any) {
      alert('Benchmark failed: ' + err.message);
    } finally {
      setIsRunning(false);
      setStatusMessage(null);
    }
  };

  const handlePlayAudioInterval = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.currentTime = startTime;
      audioRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
    }
  };

  const handleTimeUpdate = () => {
    if (!audioRef.current) return;
    if (audioRef.current.currentTime >= endTime) {
      if (isLooping) {
        audioRef.current.currentTime = startTime;
        audioRef.current.play();
      } else {
        audioRef.current.pause();
        setIsPlaying(false);
      }
    }
  };

  const activeResult = results[selectedResultIndex] || null;

  return (
    <div className="space-y-6 animate-fadeIn pb-16">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-3 text-sm font-semibold text-white shadow-2xl animate-bounce">
          <CheckCircle2 className="h-4 w-4" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Hidden audio element for interval playback */}
      <audio
        ref={audioRef}
        src="/api/audio/file/dd.ogg"
        onTimeUpdate={handleTimeUpdate}
        onEnded={() => setIsPlaying(false)}
      />

      {/* Page Title */}
      <div className="space-y-1">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-black text-white light:text-surface-900 flex items-center gap-2.5">
              <BarChart3 className="h-7 w-7 text-brand-400" />
              <span>Accuracy Benchmark & Model Comparison</span>
            </h1>
            <p className="text-xs sm:text-sm text-surface-400 light:text-surface-600">
              Quantitative Word Error Rate (WER) and Character Error Rate (CER) evaluation against human ground truth.
            </p>
          </div>

          {/* Quick Hardware Status */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-surface-900 border border-surface-800 text-xs">
            <Zap className="h-3.5 w-3.5 text-emerald-400" />
            <span className="text-surface-300 font-semibold">{hardware?.gpu_name || 'RTX 3050 Laptop GPU'}</span>
            <span className="text-surface-500">•</span>
            <span className="text-emerald-400 font-mono">CUDA 12 Ready</span>
          </div>
        </div>
      </div>

      {/* Top Grid: Audio Interval & Configuration */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Audio Interval Selection Card */}
        <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-5 light:border-surface-200 light:bg-white space-y-4">
          <h3 className="text-sm font-bold text-white light:text-surface-900 flex items-center gap-2">
            <Volume2 className="h-4 w-4 text-brand-400" />
            <span>Audio Interval Alignment</span>
          </h3>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <label className="text-surface-400 font-medium block mb-1">Start Time (sec)</label>
              <input
                type="number"
                step="0.5"
                min="0"
                value={startTime}
                onChange={e => setStartTime(parseFloat(e.target.value) || 0)}
                className="w-full rounded-lg border border-surface-800 bg-surface-900 px-3 py-1.5 text-xs text-white font-mono"
              />
            </div>
            <div>
              <label className="text-surface-400 font-medium block mb-1">End Time (sec)</label>
              <input
                type="number"
                step="0.5"
                min="1"
                value={endTime}
                onChange={e => setEndTime(parseFloat(e.target.value) || 103.0)}
                className="w-full rounded-lg border border-surface-800 bg-surface-900 px-3 py-1.5 text-xs text-white font-mono"
              />
            </div>
          </div>

          <div className="p-3 rounded-xl bg-surface-950/60 border border-surface-800/80 text-xs flex items-center justify-between">
            <div className="space-y-0.5">
              <span className="text-surface-400 block text-[11px]">Evaluation Audio Window:</span>
              <span className="font-bold text-brand-300 font-mono">
                {Math.floor(startTime / 60)}:{(Math.floor(startTime) % 60).toString().padStart(2, '0')} —{' '}
                {Math.floor(endTime / 60)}:{(Math.floor(endTime) % 60).toString().padStart(2, '0')} ({(endTime - startTime).toFixed(1)}s)
              </span>
            </div>

            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={handlePlayAudioInterval}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-brand-600 text-white font-semibold hover:bg-brand-500 transition-colors"
              >
                {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                <span>{isPlaying ? 'Pause' : 'Play'}</span>
              </button>
              <button
                type="button"
                onClick={() => setIsLooping(!isLooping)}
                className={`p-1.5 rounded-lg border transition-colors ${
                  isLooping ? 'bg-brand-500/20 text-brand-400 border-brand-500/40' : 'bg-surface-800 text-surface-400 border-surface-700'
                }`}
                title="Loop Interval Playback"
              >
                <Repeat className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {/* Model Selection */}
          <div className="space-y-2 pt-1">
            <label className="text-xs font-semibold text-surface-300 block">Candidate Models to Compare:</label>
            <div className="space-y-1.5">
              {availableModels.map(m => (
                <label
                  key={m.id}
                  className={`flex items-center justify-between p-2.5 rounded-xl border cursor-pointer transition-colors text-xs ${
                    selectedModels.includes(m.id)
                      ? 'border-brand-500/50 bg-brand-500/5 text-white'
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
                    {m.is_downloaded ? 'Downloaded' : 'Download Needed'}
                  </span>
                </label>
              ))}
            </div>
          </div>
        </div>

        {/* Human Ground Truth Reference Panel */}
        <div className="lg:col-span-2 rounded-2xl border border-surface-800 bg-surface-900/50 p-5 light:border-surface-200 light:bg-white space-y-3 flex flex-col justify-between">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-white light:text-surface-900 flex items-center gap-2">
                <FileText className="h-4 w-4 text-emerald-400" />
                <span>Human Ground-Truth Reference (00:00 - 01:43)</span>
              </h3>
              <span className="text-xs font-mono text-surface-400">
                {refText.split(/\s+/).filter(Boolean).length} words
              </span>
            </div>

            <textarea
              rows={6}
              value={refText}
              onChange={e => setRefText(e.target.value)}
              placeholder="Paste or edit the human ground-truth reference transcript..."
              className="w-full rounded-xl border border-surface-800 bg-surface-950/80 p-3 text-xs text-white placeholder:text-surface-600 focus:outline-none focus:border-brand-500 resize-none font-sans leading-relaxed"
              dir="rtl"
            />

            <p className="text-[11px] text-surface-500 flex items-center gap-1.5">
              <Info className="h-3.5 w-3.5 text-brand-400 shrink-0" />
              <span>
                Preserved as human ground-truth reference. Excluded from Git and never injected into model prompts.
              </span>
            </p>
          </div>

          {/* Evaluation Controls & Run Button */}
          <div className="pt-2 border-t border-surface-800/80 flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-3">
              <div>
                <label className="text-surface-400 mr-2">Evaluation Mode:</label>
                <select
                  value={evalMode}
                  onChange={e => setEvalMode(e.target.value as any)}
                  className="rounded-lg border border-surface-800 bg-surface-900 px-2.5 py-1 text-xs text-white"
                >
                  <option value="normalized">Normalized (Documented Arabic/English)</option>
                  <option value="raw">Raw (Exact Characters & Casing)</option>
                </select>
              </div>

              <div>
                <label className="text-surface-400 mr-2">Device Mode:</label>
                <select
                  value={deviceMode}
                  onChange={e => setDeviceMode(e.target.value)}
                  className="rounded-lg border border-surface-800 bg-surface-900 px-2.5 py-1 text-xs text-white"
                >
                  <option value="auto">Auto GPU/CPU</option>
                  <option value="cuda_only">GPU Only (Strict CUDA)</option>
                  <option value="cpu">CPU Mode</option>
                </select>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleSaveReference}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-surface-700 bg-surface-800 text-xs font-semibold text-white hover:bg-surface-700 transition-colors"
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
                <span>{isRunning ? 'Benchmarking...' : 'Run Benchmark'}</span>
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

      {/* Benchmark Results Section */}
      {results.length > 0 && (
        <div className="space-y-6 animate-fadeIn">
          {/* Candidate Comparison Table */}
          <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-4">
            <h3 className="text-base font-bold text-white light:text-surface-900 flex items-center justify-between">
              <span className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5 text-brand-400" />
                <span>Candidate Performance Matrix ({evalMode === 'normalized' ? 'Normalized Metrics' : 'Raw Metrics'})</span>
              </span>
              <span className="text-xs font-normal text-surface-400">
                Ground Truth: 00:00 - 01:43 ({Math.round(endTime - startTime)}s)
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
                    <th className="p-3 text-right rtl:text-left">Select</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-800/60 font-mono">
                  {results.map((r, idx) => {
                    const isSuccess = r.status === 'success';
                    const isCurrent = idx === selectedResultIndex;
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
                                Recommended
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
                            <span className={wer! < 70 ? 'text-emerald-400' : 'text-amber-400'}>
                              {wer?.toFixed(2)}%
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="p-3 text-center font-bold text-sm">
                          {isSuccess ? (
                            <span className={cer! < 45 ? 'text-emerald-400' : 'text-amber-400'}>
                              {cer?.toFixed(2)}%
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="p-3 text-center text-amber-400">{isSuccess ? sub : '—'}</td>
                        <td className="p-3 text-center text-rose-400">{isSuccess ? del : '—'}</td>
                        <td className="p-3 text-center text-purple-400">{isSuccess ? ins : '—'}</td>
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

          {/* Word-Level Diff & Visual Alignment Inspector */}
          {activeResult && activeResult.status === 'success' && (
            <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="text-base font-bold text-white light:text-surface-900 flex items-center gap-2">
                    <Layers className="h-5 w-5 text-brand-400" />
                    <span>Word-Level Alignment & Error Inspection: {activeResult.name}</span>
                  </h3>
                  <p className="text-xs text-surface-400">
                    Inspecting prediction against human ground truth with colour-coded edit operations.
                  </p>
                </div>

                {/* Diff Legend */}
                <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold">
                  <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                    Match (Correct)
                  </span>
                  <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">
                    Substitution
                  </span>
                  <span className="px-2 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/30">
                    Deletion (Missing)
                  </span>
                  <span className="px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/30">
                    Insertion (Extra)
                  </span>
                </div>
              </div>

              {/* Visual Diff Badges */}
              <div className="p-4 rounded-xl bg-surface-950/80 border border-surface-800 text-xs leading-loose flex flex-wrap gap-1.5" dir="rtl">
                {activeResult.word_alignment?.map((op, opIdx) => {
                  if (op.type === 'equal') {
                    return (
                      <span
                        key={opIdx}
                        className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20"
                        title="Exact Word Match"
                      >
                        {op.ref}
                      </span>
                    );
                  }
                  if (op.type === 'substitute') {
                    return (
                      <span
                        key={opIdx}
                        className="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30"
                        title={`Substitution: Ref='${op.ref}' | Hyp='${op.hyp}'`}
                      >
                        <span className="line-through opacity-70 text-[10px] ml-1">{op.ref}</span>
                        <strong className="underline">{op.hyp}</strong>
                      </span>
                    );
                  }
                  if (op.type === 'delete') {
                    return (
                      <span
                        key={opIdx}
                        className="px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30 line-through"
                        title={`Missing from AI Prediction: '${op.ref}'`}
                      >
                        {op.ref}
                      </span>
                    );
                  }
                  if (op.type === 'insert') {
                    return (
                      <span
                        key={opIdx}
                        className="px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30"
                        title={`Extra / Hallucinated: '${op.hyp}'`}
                      >
                        +{op.hyp}
                      </span>
                    );
                  }
                  return null;
                })}
              </div>

              {/* Side-by-Side Full Transcript Compare */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div className="space-y-1.5">
                  <h4 className="font-bold text-surface-300 flex items-center justify-between">
                    <span>Human Ground-Truth Reference:</span>
                    <span className="text-[10px] text-surface-500 font-mono">103.0s</span>
                  </h4>
                  <div className="p-3 rounded-xl bg-surface-950/60 border border-surface-800 text-surface-200 leading-relaxed max-h-48 overflow-y-auto" dir="rtl">
                    {refText}
                  </div>
                </div>

                <div className="space-y-1.5">
                  <h4 className="font-bold text-surface-300 flex items-center justify-between">
                    <span>Model Prediction ({activeResult.name}):</span>
                    <span className="text-[10px] text-brand-400 font-mono">{activeResult.elapsed_seconds}s</span>
                  </h4>
                  <div className="p-3 rounded-xl bg-surface-950/60 border border-surface-800 text-surface-200 leading-relaxed max-h-48 overflow-y-auto" dir="rtl">
                    {activeResult.predicted_text}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
