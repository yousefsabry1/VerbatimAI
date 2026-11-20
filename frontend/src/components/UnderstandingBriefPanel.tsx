import React, { useState } from 'react';
import {
  Lightbulb,
  FileText,
  Clock,
  Play,
  Download,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  RefreshCw,
  X,
  ExternalLink,
  ShieldCheck,
  Tag,
  ArrowRight,
} from 'lucide-react';
import { UnderstandingBrief, InstructionItem } from '../types';
import { api } from '../services/api';

interface UnderstandingBriefPanelProps {
  brief: UnderstandingBrief | null;
  loading: boolean;
  onRefresh: () => void;
  onSeekAudio: (seconds: number) => void;
  onClose?: () => void;
  jobId: string;
}

type CategoryFilter = 'all' | 'required_changes' | 'content_to_remove' | 'responsibilities' | 'negative_instructions' | 'wording_corrections' | 'confirmed_decisions' | 'uncertain_statements';

export const UnderstandingBriefPanel: React.FC<UnderstandingBriefPanelProps> = ({
  brief,
  loading,
  onRefresh,
  onSeekAudio,
  onClose,
  jobId,
}) => {
  const [selectedFilter, setSelectedFilter] = useState<CategoryFilter>('all');

  if (loading) {
    return (
      <div className="rounded-2xl border border-surface-800 bg-surface-900/90 p-8 text-center space-y-3 backdrop-blur-md light:bg-white light:border-surface-200 animate-fadeIn">
        <RefreshCw className="h-8 w-8 text-brand-400 animate-spin mx-auto" />
        <h4 className="text-sm font-bold text-white light:text-surface-900">
          Extracting Evidence-Grounded Speech Understanding...
        </h4>
        <p className="text-xs text-surface-400 max-w-md mx-auto">
          Analyzing spoken instructions, Egyptian colloquial negations, organizational responsibilities, and grounding all claims to audio timestamps.
        </p>
      </div>
    );
  }

  if (!brief) {
    return (
      <div className="rounded-2xl border border-surface-800 bg-surface-900/90 p-6 text-center space-y-4 backdrop-blur-md light:bg-white light:border-surface-200 animate-fadeIn">
        <div className="p-3 rounded-full bg-brand-500/10 text-brand-400 w-fit mx-auto border border-brand-500/20">
          <Lightbulb className="h-6 w-6" />
        </div>
        <div className="space-y-1">
          <h4 className="text-sm font-bold text-white light:text-surface-900">
            Generate Actionable Spoken Brief (Mode 2)
          </h4>
          <p className="text-xs text-surface-400 max-w-lg mx-auto">
            Extract what the speaker is asking for without altering the strict verbatim transcript. Identifies requested additions, removals, responsibilities, and mid-sentence corrections.
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-bold text-xs shadow-md transition-colors inline-flex items-center gap-2"
        >
          <Lightbulb className="h-4 w-4" />
          <span>Analyze Spoken Instructions</span>
        </button>
      </div>
    );
  }

  const allItems: InstructionItem[] = [];
  const categories = brief.categories || {};
  Object.keys(categories).forEach(catKey => {
    const list = categories[catKey] || [];
    list.forEach(item => allItems.push(item));
  });

  const filteredItems = selectedFilter === 'all'
    ? allItems
    : categories[selectedFilter] || [];

  const getCategoryBadge = (cat: string) => {
    switch (cat) {
      case 'content_to_remove':
        return { label: 'إزالة محتوى (Remove)', bg: 'bg-rose-500/10 text-rose-400 border-rose-500/30' };
      case 'negative_instructions':
        return { label: 'اشتراط نفي (Negative Instruction)', bg: 'bg-red-500/10 text-red-300 border-red-500/30' };
      case 'responsibilities':
        return { label: 'توزيع مسؤوليات (Responsibility)', bg: 'bg-blue-500/10 text-blue-300 border-blue-500/30' };
      case 'required_changes':
        return { label: 'تعديل مطلوب (Required Change)', bg: 'bg-brand-500/10 text-brand-300 border-brand-500/30' };
      case 'wording_corrections':
        return { label: 'تدقيق صياغة (Wording & Casing)', bg: 'bg-amber-500/10 text-amber-300 border-amber-500/30' };
      case 'confirmed_decisions':
        return { label: 'قرار معتمد (Decision)', bg: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' };
      case 'uncertain_statements':
        return { label: 'غير محسوم (Uncertain)', bg: 'bg-purple-500/10 text-purple-300 border-purple-500/30' };
      default:
        return { label: cat, bg: 'bg-surface-800 text-surface-300 border-surface-700' };
    }
  };

  const getProvenanceBadge = (prov: string) => {
    switch (prov) {
      case 'explicitly_spoken':
        return { label: 'Explicitly Spoken', bg: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' };
      case 'interpreted_from_context':
        return { label: 'Context Inference', bg: 'bg-blue-500/10 text-blue-300 border-blue-500/30' };
      case 'needs_human_verification':
      default:
        return { label: 'Needs Human Verification', bg: 'bg-amber-500/10 text-amber-300 border-amber-500/30' };
    }
  };

  return (
    <div className="rounded-2xl border border-surface-800 bg-surface-900/95 p-5 space-y-5 shadow-2xl backdrop-blur-md light:bg-white light:border-surface-200 animate-fadeIn">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-800 pb-4 light:border-surface-200">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-brand-500/10 border border-brand-500/20 text-brand-400">
            <Lightbulb className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white light:text-surface-900 flex items-center gap-2">
              <span>{brief.title || 'Evidence-Grounded Action Brief'}</span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-brand-500/20 text-brand-300 font-mono">
                {allItems.length} Grounded Points
              </span>
            </h3>
            <p className="text-[11px] text-surface-400">
              Extracted project instructions linked to exact audio timestamps without altering verbatim speech
            </p>
          </div>
        </div>

        {/* Export & Actions */}
        <div className="flex items-center gap-2">
          <a
            href={api.getUnderstandingMarkdownUrl(jobId)}
            download
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-surface-800 hover:bg-surface-700 text-surface-200 hover:text-white border border-surface-700 text-xs font-semibold transition-colors light:bg-surface-100 light:border-surface-200 light:text-surface-700"
            title="Download executive brief as Markdown report"
          >
            <Download className="h-3.5 w-3.5" />
            <span>Markdown (.MD)</span>
          </a>

          <a
            href={api.getUnderstandingJsonUrl(jobId)}
            download
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-surface-800 hover:bg-surface-700 text-surface-200 hover:text-white border border-surface-700 text-xs font-semibold transition-colors light:bg-surface-100 light:border-surface-200 light:text-surface-700"
            title="Export structured JSON"
          >
            <FileText className="h-3.5 w-3.5" />
            <span>JSON</span>
          </a>

          <button
            type="button"
            onClick={onRefresh}
            className="p-1.5 rounded-xl bg-surface-800 hover:bg-surface-700 text-surface-300 hover:text-white border border-surface-700 transition-colors"
            title="Re-analyze transcript"
          >
            <RefreshCw className="h-4 w-4" />
          </button>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-xl text-surface-400 hover:text-white hover:bg-surface-800 transition-colors"
              title="Close Understanding Panel"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Recording Overview Box */}
      <div className="p-4 rounded-xl bg-surface-950/80 border border-brand-500/20 space-y-1.5 light:bg-surface-50 light:border-surface-200">
        <span className="text-[10px] font-bold uppercase tracking-wider text-brand-400 flex items-center gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5" />
          <span>Recording Context & Subject:</span>
        </span>
        <p
          className="text-xs text-surface-200 leading-relaxed font-sans text-right light:text-surface-800"
          dir="rtl"
        >
          {brief.topic_overview}
        </p>
      </div>

      {/* Category Filter Chips */}
      <div className="flex flex-wrap items-center gap-1.5 pb-1">
        <button
          type="button"
          onClick={() => setSelectedFilter('all')}
          className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${
            selectedFilter === 'all'
              ? 'bg-brand-600 text-white'
              : 'bg-surface-950 text-surface-400 hover:text-white border border-surface-800 light:bg-surface-100 light:text-surface-600'
          }`}
        >
          All ({allItems.length})
        </button>

        {Object.keys(brief.summary_counts || {}).map(catKey => {
          const count = brief.summary_counts[catKey];
          if (count === 0) return null;
          const badge = getCategoryBadge(catKey);
          return (
            <button
              key={catKey}
              type="button"
              onClick={() => setSelectedFilter(catKey as CategoryFilter)}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-colors ${
                selectedFilter === catKey
                  ? 'bg-surface-800 text-white border-brand-500 shadow-sm'
                  : 'bg-surface-950/60 text-surface-400 hover:text-white border-surface-800 light:bg-surface-100 light:text-surface-700'
              }`}
            >
              <span>{badge.label} ({count})</span>
            </button>
          );
        })}
      </div>

      {/* Instruction Cards List */}
      <div className="space-y-3 max-h-[480px] overflow-y-auto pr-1">
        {filteredItems.length === 0 ? (
          <div className="p-8 text-center text-surface-400 border border-dashed border-surface-800 rounded-xl space-y-1">
            <p className="text-xs font-semibold text-surface-300">No instructions in this category</p>
            <p className="text-[11px] text-surface-500">Try selecting another filter above.</p>
          </div>
        ) : (
          filteredItems.map(item => {
            const catBadge = getCategoryBadge(item.category);
            const provBadge = getProvenanceBadge(item.provenance);
            const ev = item.evidence;

            return (
              <div
                key={item.id}
                className="p-4 rounded-xl border border-surface-800 bg-surface-950/70 hover:border-surface-700 transition-all space-y-2.5 text-xs light:bg-surface-50 light:border-surface-200"
              >
                {/* Top Row: Category, Provenance, Audio Seek Button */}
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${catBadge.bg}`}>
                      {catBadge.label}
                    </span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${provBadge.bg}`}>
                      {provBadge.label}
                    </span>
                    {item.reversal_detected && (
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30 flex items-center gap-1">
                        <AlertTriangle className="h-3 w-3" />
                        <span>Self-Correction</span>
                      </span>
                    )}
                  </div>

                  {/* Audio Timestamp Jump */}
                  {ev && (
                    <button
                      type="button"
                      onClick={() => onSeekAudio(ev.start)}
                      className="flex items-center gap-1 font-mono text-[11px] px-2.5 py-1 rounded-lg bg-surface-800 hover:bg-brand-600 text-brand-300 hover:text-white border border-surface-700/80 transition-colors"
                      title="Seek audio to the exact speech evidence"
                    >
                      <Play className="h-2.5 w-2.5 fill-current" />
                      <span>{ev.time_formatted}</span>
                    </button>
                  )}
                </div>

                {/* Title & Description */}
                <div className="space-y-1 text-right" dir="rtl">
                  <h5 className="text-sm font-bold text-white font-sans light:text-surface-900">
                    {item.title}
                  </h5>
                  <p className="text-xs text-surface-300 font-sans leading-relaxed light:text-surface-700">
                    {item.description}
                  </p>
                </div>

                {/* Grounded Quote Block */}
                {ev && ev.quote && (
                  <div
                    className="p-2.5 rounded-lg bg-surface-900/90 border border-surface-800/80 text-surface-400 text-xs font-sans text-right italic light:bg-white light:border-surface-200"
                    dir="rtl"
                  >
                    <span className="text-[10px] uppercase font-bold text-surface-500 block not-italic mb-1">
                      النص المنطوق في التسجيل:
                    </span>
                    "{ev.quote}"
                  </div>
                )}

                {/* Reversal Details if present */}
                {item.reversal_details && (
                  <div className="text-[11px] text-amber-300/90 bg-amber-500/5 border border-amber-500/20 p-2 rounded-lg">
                    <strong>تنبيه مراجعة:</strong> {item.reversal_details}
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
