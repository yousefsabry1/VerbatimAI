import React, { useState, useEffect, useRef } from 'react';
import {
  X,
  Sparkles,
  Play,
  Pause,
  Repeat,
  Check,
  Copy,
  RotateCcw,
  AlertTriangle,
  Clock,
  Cpu,
  Layers,
  CheckCircle2,
  ChevronRight,
  ArrowRightLeft
} from 'lucide-react';
import { Segment, AlternativeHypothesis, DiffChunk } from '../types';
import { api } from '../services/api';

interface SegmentVerificationModalProps {
  isOpen: boolean;
  onClose: () => void;
  jobId: string;
  segment: Segment | null;
  currentText: string;
  onApplyText: (newText: string) => void;
  onMarkReviewed: (segmentId: number) => void;
  onSeekAudio: (time: number) => void;
}

export const SegmentVerificationModal: React.FC<SegmentVerificationModalProps> = ({
  isOpen,
  onClose,
  jobId,
  segment,
  currentText,
  onApplyText,
  onMarkReviewed,
  onSeekAudio,
}) => {
  const [selectedModel, setSelectedModel] = useState<string>('qwencleo-asr-4bit');
  const [contextPadding, setContextPadding] = useState<number>(1.0);
  const [loading, setLoading] = useState<boolean>(false);
  const [stage, setStage] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [activeHypothesis, setActiveHypothesis] = useState<AlternativeHypothesis | null>(null);
  const [existingHypotheses, setExistingHypotheses] = useState<AlternativeHypothesis[]>([]);
  const [editableText, setEditableText] = useState<string>(currentText);
  const [copied, setCopied] = useState<boolean>(false);

  // Segment audio mini-player
  const [isPlayingAudio, setIsPlayingAudio] = useState<boolean>(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (segment) {
      setEditableText(currentText);
      setError(null);
      // Fetch existing hypotheses for this segment
      api.getSegmentAlternatives(jobId, segment.id)
        .then(res => {
          setExistingHypotheses(res.hypotheses || []);
          if (res.hypotheses && res.hypotheses.length > 0) {
            setActiveHypothesis(res.hypotheses[0]);
          } else {
            setActiveHypothesis(null);
          }
        })
        .catch(() => {
          setExistingHypotheses([]);
          setActiveHypothesis(null);
        });
    }
  }, [segment, jobId, currentText]);

  if (!isOpen || !segment) return null;

  const duration = Math.max(0.1, segment.end - segment.start);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 10);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${ms}`;
  };

  const handleStartVerification = async (force: boolean = false) => {
    setLoading(true);
    setError(null);
    setStage('Preparing audio & context padding...');

    try {
      setStage('Running second-pass inference on GPU...');
      const res = await api.verifySegment(jobId, segment.id, {
        model_id: selectedModel,
        context_padding: contextPadding,
        device_mode: 'cuda_only',
        force_recompute: force,
      });

      const hyp: AlternativeHypothesis = {
        id: res.hypothesis_id,
        job_id: res.job_id,
        segment_id: res.segment_id,
        model_id: res.model_id,
        model_name: res.model_name,
        start_time: res.start_time,
        end_time: res.end_time,
        extracted_start: res.extracted_start,
        extracted_end: res.extracted_end,
        context_padding: res.context_padding,
        hypothesis_text: res.hypothesis_text,
        primary_text: res.primary_text,
        diff: res.diff,
        disagreement_score: res.disagreement_score,
        device_used: res.device_used,
        compute_used: res.compute_used,
        elapsed_seconds: res.elapsed_seconds,
      };

      setActiveHypothesis(hyp);
      setExistingHypotheses(prev => [hyp, ...prev.filter(h => h.id !== hyp.id)]);
      setStage('');
    } catch (err: any) {
      setError(err.message || 'Verification request failed');
    } finally {
      setLoading(false);
      setStage('');
    }
  };

  const handleApplyAlternativeText = () => {
    if (activeHypothesis) {
      onApplyText(activeHypothesis.hypothesis_text);
      setEditableText(activeHypothesis.hypothesis_text);
      onMarkReviewed(segment.id);
      onClose();
    }
  };

  const handleKeepCurrentText = () => {
    onMarkReviewed(segment.id);
    onClose();
  };

  const handleApplyManualEdit = () => {
    onApplyText(editableText);
    onMarkReviewed(segment.id);
    onClose();
  };

  const handleCopyText = (txt: string) => {
    navigator.clipboard.writeText(txt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const toggleSegmentAudio = () => {
    if (!audioRef.current) return;
    if (isPlayingAudio) {
      audioRef.current.pause();
      setIsPlayingAudio(false);
    } else {
      audioRef.current.play().then(() => setIsPlayingAudio(true)).catch(() => {});
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
      <div className="relative w-full max-w-4xl max-h-[92vh] flex flex-col rounded-3xl border border-surface-800 bg-surface-900 shadow-2xl overflow-hidden light:border-surface-200 light:bg-white">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-surface-800/80 bg-surface-950/60 light:border-surface-200 light:bg-surface-50">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-brand-500/10 border border-brand-500/30 text-brand-400">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-white light:text-surface-900">
                  Verify Segment #{segment.id} with AI
                </h3>
                <span className="px-2 py-0.5 rounded-md text-[11px] font-mono font-bold bg-surface-800 text-surface-300 light:bg-surface-200 light:text-surface-700">
                  {formatTime(segment.start)} — {formatTime(segment.end)} ({duration.toFixed(1)}s)
                </span>
              </div>
              <p className="text-xs text-surface-400">
                Acoustic second-pass inspection using local alternative speech recognition models.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-xl text-surface-400 hover:text-white hover:bg-surface-800 transition-colors light:hover:bg-surface-100 light:hover:text-surface-900"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Controls Bar: Model & Padding Selection */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 rounded-2xl border border-surface-800/80 bg-surface-950/40 light:border-surface-200 light:bg-surface-50">
            {/* Alternative Model */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-surface-300 block">Verification Model:</label>
              <select
                value={selectedModel}
                onChange={e => setSelectedModel(e.target.value)}
                disabled={loading}
                className="w-full rounded-xl border border-surface-700 bg-surface-900 p-2 text-xs text-white focus:border-brand-500 focus:outline-none light:border-surface-300 light:bg-white light:text-surface-900"
              >
                <option value="qwencleo-asr-4bit">QwenCleo-ASR (1.7B, 4-bit) — Best for English Code-Switching</option>
                <option value="large-v3-turbo">Whisper Large-v3-Turbo — Fast Multilingual</option>
                <option value="codeswitched-medium">Specialized Whisper Medium — Baseline Re-check</option>
              </select>
            </div>

            {/* Context Padding */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-surface-300 block">Context Padding (Acoustic Window):</label>
              <div className="flex items-center gap-1.5">
                {[0.0, 1.0, 2.0].map(pad => (
                  <button
                    key={pad}
                    type="button"
                    onClick={() => setContextPadding(pad)}
                    disabled={loading}
                    className={`flex-1 py-1.5 rounded-lg text-xs font-bold border transition-colors ${
                      contextPadding === pad
                        ? 'bg-brand-500/20 border-brand-500 text-brand-300'
                        : 'bg-surface-900 border-surface-700 text-surface-400 hover:text-white light:bg-white light:border-surface-300'
                    }`}
                  >
                    {pad === 0.0 ? '0s (Exact)' : `±${pad}s`}
                  </button>
                ))}
              </div>
            </div>

            {/* Verification Action Button */}
            <div className="flex items-end">
              <button
                type="button"
                onClick={() => handleStartVerification(true)}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 py-2 px-4 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-bold transition-all shadow-md disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <Sparkles className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                <span>{loading ? (stage || 'Verifying...') : 'Re-Listen with AI'}</span>
              </button>
            </div>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-300 flex items-center gap-2.5">
              <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
              <span>{error}</span>
            </div>
          )}

          {/* Audio Playback Controls for Segment */}
          <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-2xl border border-surface-800 bg-surface-950/80 light:border-surface-200 light:bg-surface-100">
            <div className="flex items-center gap-2">
              <audio
                ref={audioRef}
                src={api.getSegmentAudioUrl(jobId, segment.id, contextPadding)}
                onEnded={() => setIsPlayingAudio(false)}
              />
              <button
                type="button"
                onClick={toggleSegmentAudio}
                className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-bold transition-colors shadow-sm"
              >
                {isPlayingAudio ? <Pause className="h-3.5 w-3.5 fill-current" /> : <Play className="h-3.5 w-3.5 fill-current" />}
                <span>{isPlayingAudio ? 'Pause Segment Audio' : 'Play Segment Audio'}</span>
              </button>

              <button
                type="button"
                onClick={() => onSeekAudio(segment.start)}
                className="px-3 py-1.5 rounded-xl bg-surface-800 hover:bg-surface-700 text-surface-300 hover:text-white text-xs font-semibold transition-colors border border-surface-700 light:bg-white light:border-surface-300 light:text-surface-800"
                title="Seek main audio player to this segment"
              >
                Seek Main Player
              </button>
            </div>

            {activeHypothesis && (
              <div className="flex items-center gap-3 text-[11px] text-surface-400 font-mono">
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  <span>{activeHypothesis.elapsed_seconds}s</span>
                </span>
                <span className="flex items-center gap-1">
                  <Cpu className="h-3 w-3" />
                  <span>{activeHypothesis.device_used} ({activeHypothesis.compute_used})</span>
                </span>
                <span className={`px-2 py-0.5 rounded font-bold ${
                  activeHypothesis.disagreement_score > 0.3
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                    : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                }`}>
                  Disagreement: {(activeHypothesis.disagreement_score * 100).toFixed(0)}%
                </span>
              </div>
            )}
          </div>

          {/* Three-Way Comparison Columns */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* 1. Primary AI Transcript (Original Immutable) */}
            <div className="flex flex-col rounded-2xl border border-surface-800 bg-surface-950/60 p-4 space-y-2.5 light:border-surface-200 light:bg-surface-50">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-surface-400 uppercase tracking-wider text-[10px]">
                  1. Primary ASR (Specialized Whisper)
                </span>
                <span className="text-[10px] text-surface-500 font-mono">Original Output</span>
              </div>
              <div
                className="p-3.5 rounded-xl bg-surface-900 border border-surface-800/80 text-sm text-surface-200 leading-relaxed font-sans text-right select-text light:bg-white light:border-surface-200 light:text-surface-800"
                dir="rtl"
                style={{ unicodeBidi: 'plaintext' }}
              >
                {segment.original_text || segment.text}
              </div>
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => handleCopyText(segment.original_text || segment.text)}
                  className="flex items-center gap-1 text-[11px] text-surface-400 hover:text-white"
                >
                  <Copy className="h-3 w-3" />
                  <span>Copy</span>
                </button>
              </div>
            </div>

            {/* 2. Alternative AI Hypothesis (With Diff Highlighting) */}
            <div className="flex flex-col rounded-2xl border border-brand-500/30 bg-brand-500/5 p-4 space-y-2.5">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-1.5 text-brand-400 font-bold">
                  <Sparkles className="h-3.5 w-3.5" />
                  <span>2. Alternative AI ({activeHypothesis?.model_name || 'Not run yet'})</span>
                </div>
                {activeHypothesis?.is_cached && (
                  <span className="text-[10px] text-surface-500 uppercase tracking-wide">Cached</span>
                )}
              </div>

              {activeHypothesis ? (
                <>
                  <div
                    className="p-3.5 rounded-xl bg-surface-900 border border-surface-800/80 text-sm text-white leading-relaxed font-sans text-right select-text light:bg-white light:border-surface-200 light:text-surface-900"
                    dir="rtl"
                    style={{ unicodeBidi: 'plaintext' }}
                  >
                    {/* Render diff chunks with visual highlighting */}
                    {activeHypothesis.diff && activeHypothesis.diff.length > 0 ? (
                      <div className="flex flex-wrap flex-row-reverse gap-x-1.5 gap-y-1">
                        {activeHypothesis.diff.map((c: DiffChunk, idx: number) => {
                          if (c.type === 'equal') {
                            return <span key={idx} className="text-surface-200">{c.alternative}</span>;
                          }
                          if (c.type === 'substitute') {
                            return (
                              <span
                                key={idx}
                                className="px-1 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-semibold"
                                title={`Replaces: ${c.primary}`}
                              >
                                {c.alternative}
                              </span>
                            );
                          }
                          if (c.type === 'insert') {
                            return (
                              <span
                                key={idx}
                                className="px-1 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 font-semibold"
                                title="Extra word in alternative"
                              >
                                {c.alternative}
                              </span>
                            );
                          }
                          return null;
                        })}
                      </div>
                    ) : (
                      <span>{activeHypothesis.hypothesis_text}</span>
                    )}
                  </div>

                  <div className="flex items-center justify-between text-xs pt-1">
                    <button
                      type="button"
                      onClick={() => handleCopyText(activeHypothesis.hypothesis_text)}
                      className="flex items-center gap-1 text-[11px] text-surface-400 hover:text-white"
                    >
                      <Copy className="h-3 w-3" />
                      <span>Copy Full Hypothesis</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleApplyAlternativeText}
                      className="px-3 py-1 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-xs font-bold transition-colors shadow-sm"
                    >
                      Adopt Alternative Text
                    </button>
                  </div>
                </>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center p-6 text-center text-surface-500 text-xs">
                  <p>Click "Re-Listen with AI" above to generate an alternative prediction with {selectedModel}.</p>
                </div>
              )}
            </div>
          </div>

          {/* 3. Human-Corrected Transcript (Active Editable Workspace) */}
          <div className="rounded-2xl border border-surface-800 bg-surface-950/60 p-4 space-y-2.5 light:border-surface-200 light:bg-surface-50">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-brand-300 uppercase tracking-wider text-[10px]">
                3. Human-Corrected Transcript (Final Canonical Evidence)
              </span>
              <span className="text-[10px] text-surface-400">Directly editable below</span>
            </div>
            <textarea
              value={editableText}
              onChange={e => setEditableText(e.target.value)}
              rows={3}
              className="w-full rounded-xl border border-surface-700 bg-surface-900 p-3 text-sm text-white focus:border-brand-500 focus:outline-none font-sans leading-relaxed text-right light:border-surface-300 light:bg-white light:text-surface-900"
              dir="rtl"
              style={{ unicodeBidi: 'plaintext' }}
              placeholder="Edit transcript text manually..."
            />
          </div>
        </div>

        {/* Footer Human Action Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 p-5 border-t border-surface-800 bg-surface-950/80 light:border-surface-200 light:bg-surface-100">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleKeepCurrentText}
              className="px-3.5 py-2 rounded-xl border border-surface-700 bg-surface-800 text-surface-300 hover:text-white hover:bg-surface-700 text-xs font-semibold transition-colors light:bg-white light:border-surface-300 light:text-surface-800"
            >
              Keep Current & Mark Reviewed
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3.5 py-2 rounded-xl text-surface-400 hover:text-white text-xs font-semibold transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleApplyManualEdit}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-bold transition-all shadow-md"
            >
              <Check className="h-4 w-4" />
              <span>Save Changes & Complete Review</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
