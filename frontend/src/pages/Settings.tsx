import React, { useState, useEffect } from 'react';
import { useI18n } from '../context/I18nContext';
import { useTheme } from '../context/ThemeContext';
import { HardwareInfo, ModelInfo } from '../types';
import { api } from '../services/api';
import {
  Settings as SettingsIcon,
  Zap,
  Cpu,
  HardDrive,
  Download,
  Trash2,
  CheckCircle2,
  AlertCircle,
  ShieldCheck,
  Languages,
  Moon,
  Sun,
  Sparkles,
} from 'lucide-react';

interface SettingsProps {
  hardware: HardwareInfo | null;
}

export const Settings: React.FC<SettingsProps> = ({ hardware }) => {
  const { t, language, setLanguage } = useI18n();
  const { theme, toggleTheme } = useTheme();

  const [models, setModels] = useState<ModelInfo[]>([]);
  const [systemInfo, setSystemInfo] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchModels = async () => {
    try {
      const res = await api.getModels();
      setModels(res.models);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchModels();
    api.getSystem().then(setSystemInfo).catch(console.error);
  }, []);

  const handleDownloadModel = async (modelId: string) => {
    try {
      await api.downloadModel(modelId);
      // Poll model status
      const poll = setInterval(async () => {
        const res = await api.getModels();
        setModels(res.models);
        const m = res.models.find(x => x.id === modelId);
        if (m && m.is_downloaded) {
          clearInterval(poll);
        }
      }, 1500);
    } catch (err: any) {
      alert(err.message || 'Download failed');
    }
  };

  const handleDeleteModel = async (modelId: string) => {
    if (!confirm(`Are you sure you want to delete model ${modelId} from disk?`)) return;
    try {
      await api.deleteModel(modelId);
      fetchModels();
    } catch (err: any) {
      alert(err.message || 'Delete failed');
    }
  };

  return (
    <div className="space-y-8 animate-fadeIn pb-16">
      {/* Title */}
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-black text-white light:text-surface-900">
          {t.settingsTitle}
        </h1>
        <p className="text-sm text-surface-400 light:text-surface-600">
          {t.settingsSubtitle}
        </p>
      </div>

      {/* Hardware Diagnostics */}
      <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-4 shadow-xl">
        <h2 className="font-bold text-white light:text-surface-900 flex items-center gap-2 border-b border-surface-800 pb-3 light:border-surface-100">
          <Zap className="h-5 w-5 text-amber-400" />
          {t.hardwareSectionTitle}
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
          <div className="p-4 rounded-xl bg-surface-950/60 border border-surface-800 light:bg-surface-50 light:border-surface-200 space-y-1">
            <span className="text-surface-400 font-medium">{t.gpuLabel}</span>
            <p className="text-sm font-bold text-white light:text-surface-900 truncate">
              {hardware?.gpu_name || 'CPU Only'}
            </p>
            <span className={`inline-block text-[10px] font-bold px-2 py-0.5 rounded-full ${
              hardware?.cuda_available
                ? 'bg-emerald-500/10 text-emerald-400'
                : 'bg-surface-800 text-surface-400'
            }`}>
              {hardware?.cuda_available ? 'CUDA 12+ ACCELERATION' : 'CPU FALLBACK SAFE'}
            </span>
          </div>

          <div className="p-4 rounded-xl bg-surface-950/60 border border-surface-800 light:bg-surface-50 light:border-surface-200 space-y-1">
            <span className="text-surface-400 font-medium">{t.vramLabel}</span>
            <p className="text-sm font-bold text-white light:text-surface-900">
              {hardware?.vram_total_mb ? `${hardware.vram_total_mb} MB` : 'N/A'}
            </p>
            <p className="text-[11px] text-surface-500">
              {hardware?.vram_free_mb ? `Free: ${hardware.vram_free_mb} MB` : 'System RAM used'}
            </p>
          </div>

          <div className="p-4 rounded-xl bg-surface-950/60 border border-surface-800 light:bg-surface-50 light:border-surface-200 space-y-1">
            <span className="text-surface-400 font-medium">{t.cpuCoresLabel}</span>
            <p className="text-sm font-bold text-white light:text-surface-900">
              {hardware?.cpu_cores || 4} Threads
            </p>
            <p className="text-[11px] text-surface-500">Multi-threaded CTranslate2</p>
          </div>

          <div className="p-4 rounded-xl bg-surface-950/60 border border-surface-800 light:bg-surface-50 light:border-surface-200 space-y-1">
            <span className="text-surface-400 font-medium">Recommended Setup</span>
            <p className="text-sm font-bold text-brand-400">
              {hardware?.recommended?.model?.toUpperCase() || 'MEDIUM'}
            </p>
            <p className="text-[11px] text-surface-500">
              {hardware?.recommended?.device?.toUpperCase()} • {hardware?.recommended?.compute}
            </p>
          </div>
        </div>
      </div>

      {/* Model Manager */}
      <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-5 shadow-xl">
        <h2 className="font-bold text-white light:text-surface-900 flex items-center gap-2 border-b border-surface-800 pb-3 light:border-surface-100">
          <HardDrive className="h-5 w-5 text-brand-400" />
          {t.modelsSectionTitle}
        </h2>

        <div className="space-y-4">
          {models.map(m => (
            <div
              key={m.id}
              className="p-5 rounded-2xl border border-surface-800 bg-surface-950/50 light:border-surface-200 light:bg-surface-50 flex flex-wrap items-center justify-between gap-4"
            >
              <div className="space-y-1 max-w-lg">
                <div className="flex items-center gap-2">
                  <h3 className="font-bold text-white light:text-surface-900 text-sm">
                    {m.name}
                  </h3>
                  {m.is_downloaded ? (
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      <CheckCircle2 className="h-3 w-3" />
                      READY
                    </span>
                  ) : (
                    <span className="inline-block text-[10px] font-bold px-2 py-0.5 rounded-full bg-surface-800 text-surface-400">
                      NOT DOWNLOADED
                    </span>
                  )}
                  {m.hybrid_readiness && m.hybrid_readiness.tier === 'full_tri_model' && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">
                      TRI-MODEL CONSENSUS
                    </span>
                  )}
                  {m.hybrid_readiness && m.hybrid_readiness.tier === 'dual_model_consensus' && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                      DUAL-MODEL CONSENSUS
                    </span>
                  )}
                </div>
                <p className="text-xs text-surface-400 light:text-surface-600">
                  {m.recommended_for}
                </p>
                {m.qwencleo_readiness && !m.qwencleo_readiness.ready && (
                  <p className="text-[10px] text-amber-400/90 font-medium">
                    Status: {m.qwencleo_readiness.reason}
                  </p>
                )}
                <p className="text-[11px] text-surface-500">
                  Download size: ~{m.approx_download_gb} GB • Disk size: {m.folder_size_gb > 0 ? `${m.folder_size_gb} GB` : '0 GB'}
                </p>
              </div>

              <div className="flex items-center gap-3">
                {m.is_downloaded ? (
                  <button
                    onClick={() => handleDeleteModel(m.id)}
                    className="flex items-center gap-1.5 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3.5 py-2 text-xs font-semibold text-rose-400 hover:bg-rose-500/20 transition-colors"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    <span>{t.deleteModelBtn}</span>
                  </button>
                ) : (
                  <button
                    disabled={m.is_downloading}
                    onClick={() => handleDownloadModel(m.id)}
                    className="flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-xs font-bold text-white shadow-md hover:bg-brand-500 disabled:opacity-50 transition-colors"
                  >
                    <Download className={`h-3.5 w-3.5 ${m.is_downloading ? 'animate-bounce' : ''}`} />
                    <span>{m.is_downloading ? t.downloadingModelBtn : t.downloadModelBtn}</span>
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Appearance & Language */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-4">
          <h2 className="font-bold text-white light:text-surface-900 flex items-center gap-2 border-b border-surface-800 pb-3 light:border-surface-100">
            <Sparkles className="h-4 w-4 text-brand-400" />
            {t.appearanceSectionTitle}
          </h2>

          <div className="space-y-4 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-medium text-surface-300 light:text-surface-700">{t.themeLabel}</span>
              <button
                onClick={toggleTheme}
                className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-surface-800 bg-surface-950 text-white light:border-surface-300 light:bg-surface-100 light:text-surface-900"
              >
                {theme === 'dark' ? <Moon className="h-3.5 w-3.5" /> : <Sun className="h-3.5 w-3.5 text-amber-500" />}
                <span>{theme === 'dark' ? t.themeDark : t.themeLight}</span>
              </button>
            </div>

            <div className="flex items-center justify-between">
              <span className="font-medium text-surface-300 light:text-surface-700">{t.interfaceLanguageLabel}</span>
              <div className="flex gap-2">
                <button
                  onClick={() => setLanguage('en')}
                  className={`px-3 py-1 rounded-lg font-semibold ${
                    language === 'en' ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400'
                  }`}
                >
                  English
                </button>
                <button
                  onClick={() => setLanguage('ar')}
                  className={`px-3 py-1 rounded-lg font-semibold ${
                    language === 'ar' ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400'
                  }`}
                >
                  العربية
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Local Storage & Privacy */}
        <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-4">
          <h2 className="font-bold text-white light:text-surface-900 flex items-center gap-2 border-b border-surface-800 pb-3 light:border-surface-100">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            {t.storageSectionTitle}
          </h2>

          <p className="text-xs text-surface-400 light:text-surface-600 leading-relaxed">
            {t.storageDescription}
          </p>

          <div className="pt-2 text-xs text-surface-500 space-y-1">
            <p>• FFmpeg: {systemInfo?.ffmpeg?.version?.substring(0, 40) || 'Active'}</p>
            <p>• FFprobe: {systemInfo?.ffprobe?.version?.substring(0, 40) || 'Active'}</p>
          </div>
        </div>
      </div>
    </div>
  );
};
