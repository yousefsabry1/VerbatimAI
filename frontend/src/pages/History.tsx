import React, { useState, useEffect } from 'react';
import { useI18n } from '../context/I18nContext';
import { Job } from '../types';
import { api } from '../services/api';
import {
  History as HistoryIcon,
  Mic,
  Repeat,
  Download,
  Trash2,
  ExternalLink,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Clock,
  Filter,
} from 'lucide-react';

interface HistoryProps {
  onOpenTranscript: (jobId: string) => void;
}

export const History: React.FC<HistoryProps> = ({ onOpenTranscript }) => {
  const { t } = useI18n();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [filterType, setFilterType] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  const fetchJobs = async () => {
    setLoading(true);
    try {
      const typeParam = filterType === 'all' ? undefined : filterType;
      const res = await api.getHistory(100, typeParam);
      setJobs(res.jobs);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, [filterType]);

  const handleDeleteItem = async (jobId: string) => {
    if (!confirm('Are you sure you want to delete this job and its files?')) return;
    try {
      await api.deleteHistoryItem(jobId);
      setJobs(prev => prev.filter(j => j.id !== jobId));
    } catch (err: any) {
      alert(err.message || 'Failed to delete');
    }
  };

  const handleClearAll = async () => {
    try {
      await api.clearAllHistory();
      setJobs([]);
      setDeleteConfirmOpen(false);
    } catch (err: any) {
      alert(err.message || 'Failed to clear history');
    }
  };

  const formatSeconds = (secs?: number) => {
    if (!secs) return '—';
    const s = Math.max(0, Math.floor(secs));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m.toString().padStart(2, '0')}:${r.toString().padStart(2, '0')}`;
  };

  return (
    <div className="space-y-6 animate-fadeIn pb-16">
      {/* Title & Clear Action */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black text-white light:text-surface-900">
            {t.historyTitle}
          </h1>
          <p className="text-sm text-surface-400 light:text-surface-600">
            {t.historySubtitle}
          </p>
        </div>

        {jobs.length > 0 && (
          <button
            onClick={() => setDeleteConfirmOpen(true)}
            className="flex items-center gap-1.5 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3.5 py-2 text-xs font-bold text-rose-400 hover:bg-rose-500/20 transition-colors"
          >
            <Trash2 className="h-4 w-4" />
            <span>{t.clearHistoryBtn}</span>
          </button>
        )}
      </div>

      {/* Confirmation Modal */}
      {deleteConfirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-surface-800 bg-surface-900 p-6 space-y-4 shadow-2xl light:border-surface-200 light:bg-white">
            <h3 className="text-base font-bold text-white light:text-surface-900">
              {t.confirmClearHistory}
            </h3>
            <p className="text-xs text-surface-400">
              This action cannot be undone. All previous transcript files, subtitles, and converted recordings will be deleted from disk.
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setDeleteConfirmOpen(false)}
                className="rounded-xl border border-surface-800 px-4 py-2 text-xs font-semibold text-surface-300 hover:bg-surface-800"
              >
                Cancel
              </button>
              <button
                onClick={handleClearAll}
                className="rounded-xl bg-rose-600 px-4 py-2 text-xs font-bold text-white hover:bg-rose-500"
              >
                Clear All
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b border-surface-800 pb-3 light:border-surface-200">
        <Filter className="h-4 w-4 text-surface-500" />
        <button
          onClick={() => setFilterType('all')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
            filterType === 'all'
              ? 'bg-brand-600 text-white'
              : 'text-surface-400 hover:text-white light:text-surface-600'
          }`}
        >
          {t.filterAll}
        </button>
        <button
          onClick={() => setFilterType('transcription')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
            filterType === 'transcription'
              ? 'bg-brand-600 text-white'
              : 'text-surface-400 hover:text-white light:text-surface-600'
          }`}
        >
          {t.filterTranscription}
        </button>
        <button
          onClick={() => setFilterType('conversion')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
            filterType === 'conversion'
              ? 'bg-brand-600 text-white'
              : 'text-surface-400 hover:text-white light:text-surface-600'
          }`}
        >
          {t.filterConversion}
        </button>
      </div>

      {/* History Table */}
      <div className="rounded-2xl border border-surface-800 bg-surface-900/40 overflow-hidden light:border-surface-200 light:bg-white shadow-xl">
        {jobs.length === 0 ? (
          <div className="py-12 text-center space-y-3">
            <AlertCircle className="h-10 w-10 text-surface-500 mx-auto" />
            <p className="text-sm text-surface-400 light:text-surface-600">
              No processing history found.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left rtl:text-right text-xs">
              <thead className="border-b border-surface-800 bg-surface-950/60 text-surface-400 light:border-surface-200 light:bg-surface-50 font-semibold">
                <tr>
                  <th className="py-3.5 px-4">{t.colFile}</th>
                  <th className="py-3.5 px-4">{t.colType}</th>
                  <th className="py-3.5 px-4">{t.colDuration}</th>
                  <th className="py-3.5 px-4">{t.colModel}</th>
                  <th className="py-3.5 px-4">{t.colStatus}</th>
                  <th className="py-3.5 px-4">{t.colDate}</th>
                  <th className="py-3.5 px-4 text-right rtl:text-left">{t.colActions}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-800/60 light:divide-surface-100">
                {jobs.map(job => (
                  <tr key={job.id} className="hover:bg-surface-800/30 transition-colors">
                    <td className="py-3.5 px-4 font-medium text-white light:text-surface-900 max-w-xs truncate">
                      {job.input_filename}
                    </td>

                    <td className="py-3.5 px-4">
                      <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold ${
                        job.job_type === 'transcription'
                          ? 'bg-brand-500/10 text-brand-400'
                          : 'bg-indigo-500/10 text-indigo-400'
                      }`}>
                        {job.job_type === 'transcription' ? <Mic className="h-3 w-3" /> : <Repeat className="h-3 w-3" />}
                        {job.job_type === 'transcription' ? 'Transcription' : 'Conversion'}
                      </span>
                    </td>

                    <td className="py-3.5 px-4 text-surface-300 light:text-surface-700 font-mono">
                      {formatSeconds(job.input_duration)}
                    </td>

                    <td className="py-3.5 px-4 text-surface-400">
                      {job.job_type === 'transcription'
                        ? job.model_used || 'medium'
                        : job.metadata?.target_format?.toUpperCase() || 'AUDIO'}
                    </td>

                    <td className="py-3.5 px-4">
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ${
                        job.status === 'completed'
                          ? 'bg-emerald-500/10 text-emerald-400'
                          : job.status === 'failed'
                          ? 'bg-rose-500/10 text-rose-400'
                          : 'bg-amber-500/10 text-amber-400'
                      }`}>
                        {job.status === 'completed' && <CheckCircle2 className="h-3 w-3" />}
                        {job.status === 'failed' && <XCircle className="h-3 w-3" />}
                        {job.status.toUpperCase()}
                      </span>
                    </td>

                    <td className="py-3.5 px-4 text-surface-400">
                      {new Date(job.created_at).toLocaleString()}
                    </td>

                    <td className="py-3.5 px-4 text-right rtl:text-left space-x-2 rtl:space-x-reverse">
                      {job.job_type === 'transcription' && job.status === 'completed' && (
                        <button
                          onClick={() => onOpenTranscript(job.id)}
                          className="text-brand-400 hover:text-brand-300 font-semibold inline-flex items-center gap-1"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                          <span>{t.reopenBtn}</span>
                        </button>
                      )}

                      {job.job_type === 'conversion' && job.status === 'completed' && (
                        <a
                          href={api.getConvertedDownloadUrl(job.id)}
                          download
                          className="text-indigo-400 hover:text-indigo-300 font-semibold inline-flex items-center gap-1"
                        >
                          <Download className="h-3.5 w-3.5" />
                          <span>{t.downloadBtn}</span>
                        </a>
                      )}

                      <button
                        onClick={() => handleDeleteItem(job.id)}
                        className="text-surface-500 hover:text-rose-400 p-1 transition-colors"
                        title="Delete"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
