import React, { useState, useMemo } from 'react';
import {
  ListFilter,
  AlertTriangle,
  Sparkles,
  CheckCircle2,
  Clock,
  Play,
  Layers,
  ChevronRight,
  ChevronDown,
  X,
  Search,
  Check,
  ShieldCheck,
  ExternalLink,
} from 'lucide-react';
import { SegmentReviewItem } from '../types';

interface ReviewQueuePanelProps {
  items: SegmentReviewItem[];
  totalSegments: number;
  flaggedCount: number;
  reviewedCount: number;
  activeSegmentId: number | null;
  onSelectSegment: (segmentId: number, startTime: number) => void;
  onOpenVerification: (segmentId: number) => void;
  onMarkReviewed: (segmentId: number) => void;
  isOpen: boolean;
  onClose?: () => void;
}

type QueueFilter = 'all' | 'flagged' | 'disagreements' | 'reviewed' | 'unreviewed';

export const ReviewQueuePanel: React.FC<ReviewQueuePanelProps> = ({
  items,
  totalSegments,
  flaggedCount,
  reviewedCount,
  activeSegmentId,
  onSelectSegment,
  onOpenVerification,
  onMarkReviewed,
  isOpen,
  onClose,
}) => {
  const [filter, setFilter] = useState<QueueFilter>('flagged');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const disagreementCount = useMemo(() => {
    return items.filter(
      item => item.alternatives_count > 0 || item.flag_reasons.some(r => r.toLowerCase().includes('disagreement'))
    ).length;
  }, [items]);

  const filteredItems = useMemo(() => {
    return items.filter(item => {
      // Filter tab logic
      if (filter === 'flagged') {
        if (!item.is_flagged && item.review_status !== 'review_suggested') return false;
      } else if (filter === 'disagreements') {
        if (item.alternatives_count === 0 && !item.flag_reasons.some(r => r.toLowerCase().includes('disagreement'))) return false;
      } else if (filter === 'reviewed') {
        if (item.review_status !== 'human_reviewed') return false;
      } else if (filter === 'unreviewed') {
        if (item.review_status === 'human_reviewed') return false;
      }

      // Search query logic
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesText = item.text.toLowerCase().includes(q) || item.original_text.toLowerCase().includes(q);
        const matchesReason = item.flag_reasons.some(r => r.toLowerCase().includes(q));
        const matchesId = item.segment_id.toString().includes(q);
        return matchesText || matchesReason || matchesId;
      }

      return true;
    });
  }, [items, filter, searchQuery]);

  const progressPercent = totalSegments > 0 ? Math.round((reviewedCount / totalSegments) * 100) : 0;

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const getReasonBadge = (reason: string) => {
    if (reason.toLowerCase().includes('missing') || reason.toLowerCase().includes('sparse')) {
      return { label: 'Possible Missing Speech', bg: 'bg-orange-500/10 text-orange-400 border-orange-500/30' };
    }
    if (reason.toLowerCase().includes('repetition')) {
      return { label: 'Repetition Loop', bg: 'bg-rose-500/10 text-rose-400 border-rose-500/30' };
    }
    if (reason.toLowerCase().includes('confidence') || reason.toLowerCase().includes('logprob')) {
      return { label: 'Low Acoustic Confidence', bg: 'bg-amber-500/10 text-amber-400 border-amber-500/30' };
    }
    if (reason.toLowerCase().includes('disagreement')) {
      return { label: 'ASR Model Disagreement', bg: 'bg-purple-500/10 text-purple-400 border-purple-500/30' };
    }
    if (reason.toLowerCase().includes('gap')) {
      return { label: 'Speech Boundary Gap', bg: 'bg-blue-500/10 text-blue-400 border-blue-500/30' };
    }
    return { label: reason, bg: 'bg-surface-800 text-surface-300 border-surface-700' };
  };

  if (!isOpen) return null;

  return (
    <div className="rounded-2xl border border-surface-800 bg-surface-900/90 p-4 space-y-4 shadow-xl backdrop-blur-md light:border-surface-200 light:bg-white animate-fadeIn">
      {/* Header & Overall Review Progress */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-800 pb-3 light:border-surface-200">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-brand-500/10 border border-brand-500/20 text-brand-400">
            <ListFilter className="h-4 w-4" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-white light:text-surface-900 flex items-center gap-1.5">
              <span>Segment Review Queue</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-brand-500/20 text-brand-300 font-mono">
                {items.length} segments
              </span>
            </h4>
            <p className="text-[10px] text-surface-400">
              Interactive triage for acoustic uncertainty, repetition loops, and model disagreements
            </p>
          </div>
        </div>

        {/* Progress Metric */}
        <div className="flex items-center gap-3">
          <div className="text-right">
            <span className="text-[11px] font-mono text-emerald-400 font-bold">{progressPercent}%</span>
            <span className="text-[10px] text-surface-400 ml-1">verified ({reviewedCount}/{totalSegments})</span>
          </div>
          <div className="w-24 h-2 rounded-full bg-surface-800 overflow-hidden light:bg-surface-200">
            <div
              className="h-full bg-emerald-500 transition-all duration-300 rounded-full"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-1 rounded-lg text-surface-400 hover:text-white hover:bg-surface-800 light:hover:bg-surface-100"
              title="Close Queue Panel"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Filter Tabs and Search */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1 bg-surface-950 p-1 rounded-xl border border-surface-800 text-xs light:bg-surface-100 light:border-surface-200">
          <button
            type="button"
            onClick={() => setFilter('flagged')}
            className={`px-2.5 py-1 rounded-lg font-semibold flex items-center gap-1.5 transition-colors ${
              filter === 'flagged'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                : 'text-surface-400 hover:text-white light:text-surface-600'
            }`}
          >
            <AlertTriangle className="h-3 w-3" />
            <span>Needs Review ({flaggedCount})</span>
          </button>

          <button
            type="button"
            onClick={() => setFilter('disagreements')}
            className={`px-2.5 py-1 rounded-lg font-semibold flex items-center gap-1.5 transition-colors ${
              filter === 'disagreements'
                ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                : 'text-surface-400 hover:text-white light:text-surface-600'
            }`}
          >
            <Sparkles className="h-3 w-3" />
            <span>Disagreements ({disagreementCount})</span>
          </button>

          <button
            type="button"
            onClick={() => setFilter('reviewed')}
            className={`px-2.5 py-1 rounded-lg font-semibold flex items-center gap-1.5 transition-colors ${
              filter === 'reviewed'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                : 'text-surface-400 hover:text-white light:text-surface-600'
            }`}
          >
            <CheckCircle2 className="h-3 w-3" />
            <span>Reviewed ({reviewedCount})</span>
          </button>

          <button
            type="button"
            onClick={() => setFilter('all')}
            className={`px-2.5 py-1 rounded-lg font-semibold flex items-center gap-1.5 transition-colors ${
              filter === 'all'
                ? 'bg-brand-600 text-white'
                : 'text-surface-400 hover:text-white light:text-surface-600'
            }`}
          >
            <span>All ({totalSegments})</span>
          </button>
        </div>

        {/* Search in queue */}
        <div className="relative min-w-[180px]">
          <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-surface-500" />
          <input
            type="text"
            placeholder="Search queue..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 rounded-xl bg-surface-950 border border-surface-800 text-xs text-white placeholder-surface-500 focus:outline-none focus:border-brand-500 light:bg-surface-50 light:border-surface-200 light:text-surface-900"
          />
        </div>
      </div>

      {/* Segment Queue Scrollable List */}
      <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1">
        {filteredItems.length === 0 ? (
          <div className="p-8 text-center text-surface-400 border border-dashed border-surface-800 rounded-xl space-y-2">
            <ShieldCheck className="h-8 w-8 text-emerald-400/60 mx-auto" />
            <p className="text-xs font-semibold text-surface-300">No segments match this filter</p>
            <p className="text-[11px] text-surface-500">
              {filter === 'flagged'
                ? 'Great! There are no unresolved acoustic flags or suspicious regions.'
                : filter === 'disagreements'
                ? 'No segment disagreements currently recorded for this transcript.'
                : 'Try selecting a different filter above.'}
            </p>
          </div>
        ) : (
          filteredItems.map(item => {
            const isActive = activeSegmentId === item.segment_id;
            const isReviewed = item.review_status === 'human_reviewed';

            return (
              <div
                key={item.segment_id}
                className={`p-3 rounded-xl border transition-all text-xs space-y-2 ${
                  isActive
                    ? 'border-brand-500 bg-brand-500/10 shadow-sm'
                    : isReviewed
                    ? 'border-surface-800/80 bg-surface-950/40 opacity-75 hover:opacity-100 hover:border-surface-700'
                    : item.is_flagged
                    ? 'border-amber-500/30 bg-amber-500/5 hover:border-amber-500/50'
                    : 'border-surface-800 bg-surface-950 hover:border-surface-700'
                }`}
              >
                {/* Top Row: Segment ID, Timestamp, Badges, and Quick Seek */}
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-surface-400">#{item.segment_id}</span>
                    <button
                      type="button"
                      onClick={() => onSelectSegment(item.segment_id, item.start)}
                      className="flex items-center gap-1 font-mono text-[11px] px-2 py-0.5 rounded-lg bg-surface-800 hover:bg-brand-600 text-surface-300 hover:text-white transition-colors"
                      title="Seek audio to this segment"
                    >
                      <Play className="h-2.5 w-2.5 fill-current" />
                      <span>{formatTime(item.start)} — {formatTime(item.end)}</span>
                    </button>

                    {/* Status Badge */}
                    {isReviewed ? (
                      <span className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                        <CheckCircle2 className="h-3 w-3" />
                        <span>Reviewed</span>
                      </span>
                    ) : item.alternatives_count > 0 ? (
                      <span className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30">
                        <Sparkles className="h-3 w-3" />
                        <span>Alternative Ready ({item.alternatives_count})</span>
                      </span>
                    ) : item.is_flagged ? (
                      <span className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
                        <AlertTriangle className="h-3 w-3" />
                        <span>Review Suggested</span>
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-surface-800 text-surface-400">
                        Unreviewed
                      </span>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1.5">
                    {/* Verify with AI Button */}
                    <button
                      type="button"
                      onClick={() => onOpenVerification(item.segment_id)}
                      className="flex items-center gap-1 px-2 py-1 rounded-lg bg-brand-600/20 text-brand-300 hover:bg-brand-600 hover:text-white border border-brand-500/30 font-semibold text-[11px] transition-colors"
                      title="Open Second-Pass Verification Modal"
                    >
                      <Sparkles className="h-3 w-3 text-brand-400" />
                      <span>Verify with AI</span>
                    </button>

                    {/* Quick Review Toggle */}
                    <button
                      type="button"
                      onClick={() => onMarkReviewed(item.segment_id)}
                      className={`p-1 rounded-lg border text-xs transition-colors ${
                        isReviewed
                          ? 'bg-emerald-500 text-white border-emerald-400'
                          : 'bg-surface-800 text-surface-400 border-surface-700 hover:text-white'
                      }`}
                      title={isReviewed ? 'Segment reviewed (click to unmark)' : 'Mark segment as reviewed'}
                    >
                      <Check className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                {/* Text Preview */}
                <div
                  className="text-surface-200 text-xs font-sans text-right line-clamp-2 leading-relaxed"
                  dir="rtl"
                  style={{ unicodeBidi: 'plaintext' }}
                >
                  {item.text}
                </div>

                {/* Flag Reasons Tags */}
                {item.flag_reasons.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    {item.flag_reasons.map((reason, idx) => {
                      const badge = getReasonBadge(reason);
                      return (
                        <span
                          key={idx}
                          className={`px-2 py-0.5 rounded text-[10px] font-medium border ${badge.bg}`}
                        >
                          {badge.label}
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
