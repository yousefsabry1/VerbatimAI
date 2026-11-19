import React, { useEffect, useState } from 'react';
import { useI18n } from '../context/I18nContext';
import { HardwareInfo, Job, ModelInfo } from '../types';
import { api } from '../services/api';
import {
  Mic,
  Repeat,
  Zap,
  Cpu,
  CheckCircle2,
  Clock,
  ArrowRight,
  ShieldCheck,
  Sparkles,
  FileText,
  AlertCircle,
} from 'lucide-react';

interface DashboardProps {
  setActiveTab: (tab: string) => void;
  hardware: HardwareInfo | null;
  onSelectJobForReview: (jobId: string) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({
  setActiveTab,
  hardware,
  onSelectJobForReview,
}) => {
  const { t, isRTL } = useI18n();
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [recentJobs, setRecentJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [modelsRes, historyRes] = await Promise.all([
          api.getModels().catch(() => ({ models: [] })),
          api.getHistory(5).catch(() => ({ jobs: [] })),
        ]);
        setModels(modelsRes.models);
        setRecentJobs(historyRes.jobs);
      } catch (err) {
        console.error('Failed to load dashboard data', err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const downloadedModelsCount = models.filter(m => m.is_downloaded).length;

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Hero Welcome */}
      <div className="relative overflow-hidden rounded-3xl border border-surface-800 bg-gradient-to-b from-surface-900/90 via-surface-900/50 to-surface-950 p-6 sm:p-10 shadow-2xl backdrop-blur-xl light:border-surface-200 light:from-white light:via-brand-50/30 light:to-white">
        <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-brand-500/10 blur-3xl pointer-events-none" />
        <div className="absolute -left-20 -bottom-20 h-64 w-64 rounded-full bg-indigo-500/10 blur-3xl pointer-events-none" />

        <div className="relative z-10 max-w-3xl space-y-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-brand-500/30 bg-brand-500/10 px-3 py-1 text-xs font-semibold text-brand-400">
            <Sparkles className="h-3.5 w-3.5" />
            <span>Verbatim AI — v1.0.0</span>
          </div>

          <h1 className="text-3xl sm:text-5xl font-black tracking-tight text-white light:text-surface-900">
            {t.welcomeTitle}
          </h1>

          <p className="text-base sm:text-lg text-surface-400 light:text-surface-600 leading-relaxed">
            {t.welcomeSubtitle}
          </p>

          <div className="flex flex-wrap items-center gap-4 pt-2">
            <div className="flex items-center gap-2 text-xs font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-lg">
              <ShieldCheck className="h-4 w-4" />
              <span>100% Local & Private (Zero Cloud Dependencies)</span>
            </div>
            <div className="flex items-center gap-2 text-xs font-medium text-surface-300 bg-surface-800/50 border border-surface-700/50 px-3 py-1.5 rounded-lg light:text-surface-700 light:bg-surface-100 light:border-surface-200">
              <CheckCircle2 className="h-4 w-4 text-brand-400" />
              <span>Egyptian Arabic & English Optimized</span>
            </div>
          </div>
        </div>
      </div>

      {/* Primary Action Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Transcription Card */}
        <div
          onClick={() => setActiveTab('transcription')}
          className="group relative cursor-pointer overflow-hidden rounded-2xl border border-surface-800 bg-surface-900/60 p-6 sm:p-8 transition-all duration-300 hover:border-brand-500/50 hover:bg-surface-900/90 hover:shadow-xl hover:shadow-brand-500/10 light:border-surface-200 light:bg-white light:hover:border-brand-400"
        >
          <div className="flex items-start justify-between">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-600/10 text-brand-400 border border-brand-500/20 group-hover:bg-brand-600 group-hover:text-white transition-all duration-300">
              <Mic className="h-7 w-7" />
            </div>
            <span className="flex items-center gap-1 text-xs font-semibold text-brand-400 group-hover:translate-x-1 transition-transform rtl:group-hover:-translate-x-1">
              {t.quickActionTranscribe} <ArrowRight className="h-4 w-4" />
            </span>
          </div>

          <div className="mt-6 space-y-2">
            <h2 className="text-xl font-bold text-white light:text-surface-900">
              {t.quickActionTranscribe}
            </h2>
            <p className="text-sm text-surface-400 light:text-surface-600">
              {t.quickActionTranscribeDesc}
            </p>
          </div>

          <div className="mt-6 flex flex-wrap gap-2 pt-2 border-t border-surface-800/80 light:border-surface-100">
            <span className="rounded-md bg-surface-800/70 px-2 py-1 text-[11px] font-medium text-surface-300 light:bg-surface-100 light:text-surface-700">
              WhatsApp OGG / Opus
            </span>
            <span className="rounded-md bg-surface-800/70 px-2 py-1 text-[11px] font-medium text-surface-300 light:bg-surface-100 light:text-surface-700">
              Strict Verbatim
            </span>
            <span className="rounded-md bg-surface-800/70 px-2 py-1 text-[11px] font-medium text-surface-300 light:bg-surface-100 light:text-surface-700">
              SRT & VTT Subtitles
            </span>
          </div>
        </div>

        {/* Converter Card */}
        <div
          onClick={() => setActiveTab('converter')}
          className="group relative cursor-pointer overflow-hidden rounded-2xl border border-surface-800 bg-surface-900/60 p-6 sm:p-8 transition-all duration-300 hover:border-indigo-500/50 hover:bg-surface-900/90 hover:shadow-xl hover:shadow-indigo-500/10 light:border-surface-200 light:bg-white light:hover:border-indigo-400"
        >
          <div className="flex items-start justify-between">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600/10 text-indigo-400 border border-indigo-500/20 group-hover:bg-indigo-600 group-hover:text-white transition-all duration-300">
              <Repeat className="h-7 w-7" />
            </div>
            <span className="flex items-center gap-1 text-xs font-semibold text-indigo-400 group-hover:translate-x-1 transition-transform rtl:group-hover:-translate-x-1">
              {t.quickActionConvert} <ArrowRight className="h-4 w-4" />
            </span>
          </div>

          <div className="mt-6 space-y-2">
            <h2 className="text-xl font-bold text-white light:text-surface-900">
              {t.quickActionConvert}
            </h2>
            <p className="text-sm text-surface-400 light:text-surface-600">
              {t.quickActionConvertDesc}
            </p>
          </div>

          <div className="mt-6 flex flex-wrap gap-2 pt-2 border-t border-surface-800/80 light:border-surface-100">
            <span className="rounded-md bg-surface-800/70 px-2 py-1 text-[11px] font-medium text-surface-300 light:bg-surface-100 light:text-surface-700">
              FFmpeg Engine
            </span>
            <span className="rounded-md bg-surface-800/70 px-2 py-1 text-[11px] font-medium text-surface-300 light:bg-surface-100 light:text-surface-700">
              MP3, WAV, Opus, FLAC
            </span>
            <span className="rounded-md bg-surface-800/70 px-2 py-1 text-[11px] font-medium text-surface-300 light:bg-surface-100 light:text-surface-700">
              Batch Conversion
            </span>
          </div>
        </div>
      </div>

      {/* System Status & Quick Guide Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* System & AI Readiness */}
        <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-4">
          <div className="flex items-center justify-between border-b border-surface-800/80 pb-3 light:border-surface-100">
            <h3 className="font-semibold text-white light:text-surface-900 flex items-center gap-2">
              <Zap className="h-4 w-4 text-brand-400" />
              {t.systemStatusTitle}
            </h3>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 rounded-xl bg-surface-950/60 border border-surface-800/60 light:bg-surface-50 light:border-surface-200">
              <div className="flex items-center gap-2.5">
                {hardware?.cuda_available ? (
                  <Zap className="h-4 w-4 text-amber-400 fill-amber-400" />
                ) : (
                  <Cpu className="h-4 w-4 text-blue-400" />
                )}
                <div>
                  <p className="text-xs text-surface-400 font-medium">{t.deviceLabel}</p>
                  <p className="text-sm font-semibold text-white light:text-surface-900">
                    {hardware?.gpu_name || 'CPU Safe Mode'}
                  </p>
                </div>
              </div>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                hardware?.cuda_available
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                  : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
              }`}>
                {hardware?.cuda_available ? 'CUDA ACTIVE' : 'CPU MODE'}
              </span>
            </div>

            <div className="flex items-center justify-between p-3 rounded-xl bg-surface-950/60 border border-surface-800/60 light:bg-surface-50 light:border-surface-200">
              <div className="flex items-center gap-2.5">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                <div>
                  <p className="text-xs text-surface-400 font-medium">{t.modelsReady}</p>
                  <p className="text-sm font-semibold text-white light:text-surface-900">
                    {downloadedModelsCount} / {models.length} Models Available
                  </p>
                </div>
              </div>
              <button
                onClick={() => setActiveTab('settings')}
                className="text-xs text-brand-400 hover:text-brand-300 font-semibold"
              >
                Manage
              </button>
            </div>
          </div>
        </div>

        {/* Quick Guide */}
        <div className="lg:col-span-2 rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-4">
          <h3 className="font-semibold text-white light:text-surface-900 flex items-center gap-2 border-b border-surface-800/80 pb-3 light:border-surface-100">
            <Clock className="h-4 w-4 text-brand-400" />
            {t.quickGuideTitle}
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl bg-surface-950/50 border border-surface-800/50 light:bg-surface-50 light:border-surface-200 space-y-2">
              <div className="h-7 w-7 rounded-lg bg-brand-500/20 text-brand-400 flex items-center justify-center text-xs font-bold">
                1
              </div>
              <p className="text-xs leading-relaxed text-surface-300 light:text-surface-700">
                {t.quickGuideStep1}
              </p>
            </div>

            <div className="p-4 rounded-xl bg-surface-950/50 border border-surface-800/50 light:bg-surface-50 light:border-surface-200 space-y-2">
              <div className="h-7 w-7 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center text-xs font-bold">
                2
              </div>
              <p className="text-xs leading-relaxed text-surface-300 light:text-surface-700">
                {t.quickGuideStep2}
              </p>
            </div>

            <div className="p-4 rounded-xl bg-surface-950/50 border border-surface-800/50 light:bg-surface-50 light:border-surface-200 space-y-2">
              <div className="h-7 w-7 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-xs font-bold">
                3
              </div>
              <p className="text-xs leading-relaxed text-surface-300 light:text-surface-700">
                {t.quickGuideStep3}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Activity */}
      <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-4">
        <div className="flex items-center justify-between border-b border-surface-800/80 pb-3 light:border-surface-100">
          <h3 className="font-semibold text-white light:text-surface-900 flex items-center gap-2">
            <FileText className="h-4 w-4 text-brand-400" />
            {t.recentActivityTitle}
          </h3>
          {recentJobs.length > 0 && (
            <button
              onClick={() => setActiveTab('history')}
              className="text-xs font-semibold text-brand-400 hover:text-brand-300 flex items-center gap-1"
            >
              {t.viewAllHistory} <ArrowRight className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {recentJobs.length === 0 ? (
          <div className="py-8 text-center space-y-3">
            <AlertCircle className="h-8 w-8 text-surface-500 mx-auto" />
            <p className="text-sm text-surface-400 light:text-surface-600">
              {t.noRecentActivity}
            </p>
          </div>
        ) : (
          <div className="divide-y divide-surface-800/60 light:divide-surface-100">
            {recentJobs.map(job => (
              <div
                key={job.id}
                className="py-3 flex items-center justify-between gap-4 hover:bg-surface-800/30 px-3 rounded-lg transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`p-2 rounded-lg ${
                    job.job_type === 'transcription'
                      ? 'bg-brand-500/10 text-brand-400'
                      : 'bg-indigo-500/10 text-indigo-400'
                  }`}>
                    {job.job_type === 'transcription' ? <Mic className="h-4 w-4" /> : <Repeat className="h-4 w-4" />}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-white light:text-surface-900 truncate">
                      {job.input_filename}
                    </p>
                    <p className="text-xs text-surface-400">
                      {job.job_type === 'transcription' ? 'AI Transcription' : 'Audio Conversion'} • {new Date(job.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                    job.status === 'completed'
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : job.status === 'failed'
                      ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                      : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                  }`}>
                    {job.status.toUpperCase()}
                  </span>

                  {job.job_type === 'transcription' && job.status === 'completed' && (
                    <button
                      onClick={() => onSelectJobForReview(job.id)}
                      className="text-xs font-semibold text-brand-400 hover:text-brand-300"
                    >
                      {t.reopenBtn}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
