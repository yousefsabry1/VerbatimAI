import React, { useState, useEffect } from 'react';
import { useI18n } from '../context/I18nContext';
import { AudioMetadata, Job } from '../types';
import { api } from '../services/api';
import { AudioPlayer } from '../components/AudioPlayer';
import {
  Repeat,
  UploadCloud,
  FileAudio,
  CheckCircle2,
  Download,
  Archive,
  ArrowRight,
  Sliders,
  Sparkles,
  Play,
  RotateCcw,
  Plus,
  Trash2,
} from 'lucide-react';

interface BatchItem {
  id: string;
  file: File;
  fileId?: string;
  metadata?: AudioMetadata;
  targetFormat: string;
  preset: string;
  status: 'pending' | 'uploading' | 'converting' | 'completed' | 'failed';
  jobId?: string;
  convertedMetadata?: AudioMetadata;
  outputFilename?: string;
  error?: string;
}

export const AudioConverter: React.FC = () => {
  const { t, isRTL } = useI18n();

  // Single file conversion state
  const [singleFile, setSingleFile] = useState<File | null>(null);
  const [singleFileId, setSingleFileId] = useState<string | null>(null);
  const [singleMeta, setSingleMeta] = useState<AudioMetadata | null>(null);
  const [targetFormat, setTargetFormat] = useState<string>('mp3');
  const [preset, setPreset] = useState<'smaller' | 'balanced' | 'high' | 'custom'>('balanced');
  const [bitrate, setBitrate] = useState<string>('192k');
  const [sampleRate, setSampleRate] = useState<number>(44100);
  const [channels, setChannels] = useState<number>(2);

  const [isConverting, setIsConverting] = useState(false);
  const [conversionResult, setConversionResult] = useState<any | null>(null);

  // Batch conversion state
  const [batchItems, setBatchItems] = useState<BatchItem[]>([]);
  const [isBatchRunning, setIsBatchRunning] = useState(false);

  const formats = ['mp3', 'wav', 'ogg', 'opus', 'm4a', 'aac', 'flac', 'aiff', 'webm'];

  const handleSingleFileUpload = async (file: File) => {
    setSingleFile(file);
    setConversionResult(null);
    try {
      const res = await api.uploadAudio(file);
      setSingleFileId(res.file_id);
      setSingleMeta(res.metadata);
    } catch (err: any) {
      alert(err.message || 'File upload failed');
      setSingleFile(null);
    }
  };

  const handleStartConversion = async () => {
    if (!singleFileId) return;
    setIsConverting(true);
    setConversionResult(null);

    try {
      const res = await api.submitConversion({
        file_id: singleFileId,
        target_format: targetFormat,
        preset: preset,
        bitrate: preset === 'custom' ? bitrate : null,
        sample_rate: preset === 'custom' ? sampleRate : null,
        channels: preset === 'custom' ? channels : null,
      });

      // Poll completion
      const interval = setInterval(async () => {
        try {
          const job = await api.getTranscriptionStatus(res.job_id);
          if (job.status === 'completed') {
            clearInterval(interval);
            setIsConverting(false);
            setConversionResult({
              jobId: res.job_id,
              ...job.metadata,
              output_files: job.output_files,
            });
          } else if (job.status === 'failed') {
            clearInterval(interval);
            setIsConverting(false);
            alert(job.error_message || 'Conversion failed');
          }
        } catch (err) {
          console.error(err);
        }
      }, 1000);
    } catch (err: any) {
      alert(err.message || 'Conversion failed');
      setIsConverting(false);
    }
  };

  // Add multiple files to batch
  const handleBatchUpload = async (files: FileList) => {
    const newItems: BatchItem[] = Array.from(files).map(f => ({
      id: Math.random().toString(36).substring(2, 9),
      file: f,
      targetFormat: 'mp3',
      preset: 'balanced',
      status: 'pending',
    }));

    setBatchItems(prev => [...prev, ...newItems]);

    // Upload each
    for (const item of newItems) {
      try {
        const res = await api.uploadAudio(item.file);
        setBatchItems(prev =>
          prev.map(i => (i.id === item.id ? { ...i, fileId: res.file_id, metadata: res.metadata } : i))
        );
      } catch (err: any) {
        setBatchItems(prev =>
          prev.map(i => (i.id === item.id ? { ...i, status: 'failed', error: err.message } : i))
        );
      }
    }
  };

  const runBatchConversion = async () => {
    setIsBatchRunning(true);
    for (const item of batchItems) {
      if (item.status === 'completed' || !item.fileId) continue;

      setBatchItems(prev => prev.map(i => (i.id === item.id ? { ...i, status: 'converting' } : i)));

      try {
        const res = await api.submitConversion({
          file_id: item.fileId,
          target_format: item.targetFormat,
          preset: item.preset,
        });

        // Wait for completion
        let finished = false;
        while (!finished) {
          await new Promise(r => setTimeout(r, 1000));
          const job = await api.getTranscriptionStatus(res.job_id);
          if (job.status === 'completed') {
            finished = true;
            setBatchItems(prev =>
              prev.map(i =>
                i.id === item.id
                  ? {
                      ...i,
                      status: 'completed',
                      jobId: res.job_id,
                      convertedMetadata: job.metadata?.converted_metadata,
                      outputFilename: job.metadata?.output_filename,
                    }
                  : i
              )
            );
          } else if (job.status === 'failed') {
            finished = true;
            setBatchItems(prev =>
              prev.map(i => (i.id === item.id ? { ...i, status: 'failed', error: job.error_message || 'Failed' } : i))
            );
          }
        }
      } catch (err: any) {
        setBatchItems(prev =>
          prev.map(i => (i.id === item.id ? { ...i, status: 'failed', error: err.message } : i))
        );
      }
    }
    setIsBatchRunning(false);
  };

  const handleDownloadZip = () => {
    const completedJobIds = batchItems.filter(i => i.status === 'completed' && i.jobId).map(i => i.jobId!);
    if (completedJobIds.length === 0) return;
    api.downloadBatchZip(completedJobIds);
  };

  return (
    <div className="space-y-8 animate-fadeIn pb-16">
      {/* Title */}
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-black text-white light:text-surface-900">
          {t.converterTitle}
        </h1>
        <p className="text-sm text-surface-400 light:text-surface-600">
          {t.converterSubtitle}
        </p>
      </div>

      {/* Main Single File Conversion Card */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Upload Zone */}
        <div className="lg:col-span-2 space-y-4">
          <div
            onDragOver={e => e.preventDefault()}
            onDrop={e => {
              e.preventDefault();
              if (e.dataTransfer.files?.[0]) handleSingleFileUpload(e.dataTransfer.files[0]);
            }}
            className={`relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 text-center transition-all ${
              singleFile
                ? 'border-indigo-500/80 bg-indigo-500/5'
                : 'border-surface-800 bg-surface-900/40 hover:border-surface-700 light:border-surface-300 light:bg-white'
            }`}
          >
            <input
              type="file"
              id="converter-file"
              accept="audio/*,video/*"
              onChange={e => e.target.files?.[0] && handleSingleFileUpload(e.target.files[0])}
              className="hidden"
            />

            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-3">
              <Repeat className="h-7 w-7" />
            </div>

            <h3 className="text-base font-bold text-white light:text-surface-900 mb-1">
              {singleFile ? singleFile.name : 'Drop audio to convert'}
            </h3>

            <p className="text-xs text-surface-400 max-w-sm mb-4">
              {singleFile
                ? `${singleMeta?.size_formatted || ''} • ${singleMeta?.duration_formatted || ''} • ${singleMeta?.format?.toUpperCase() || ''}`
                : 'Supports WhatsApp voice notes (OGG/Opus), MP3, WAV, M4A, FLAC, and video'}
            </p>

            <label
              htmlFor="converter-file"
              className="cursor-pointer rounded-xl bg-surface-800 px-4 py-2 text-xs font-semibold text-white hover:bg-surface-700 light:bg-surface-100 light:text-surface-800 transition-colors"
            >
              {singleFile ? 'Change File' : t.browseFiles}
            </label>
          </div>

          {/* Original file metadata summary */}
          {singleMeta && (
            <div className="rounded-xl border border-surface-800 bg-surface-900/60 p-4 light:border-surface-200 light:bg-white grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div>
                <span className="text-surface-400">Duration:</span>
                <p className="font-semibold text-white light:text-surface-900">{singleMeta.duration_formatted}</p>
              </div>
              <div>
                <span className="text-surface-400">Codec:</span>
                <p className="font-semibold text-white light:text-surface-900">{singleMeta.codec} ({singleMeta.format})</p>
              </div>
              <div>
                <span className="text-surface-400">Sample Rate:</span>
                <p className="font-semibold text-white light:text-surface-900">{singleMeta.sample_rate} Hz</p>
              </div>
              <div>
                <span className="text-surface-400">Original Size:</span>
                <p className="font-semibold text-white light:text-surface-900">{singleMeta.size_formatted}</p>
              </div>
            </div>
          )}
        </div>

        {/* Conversion Controls Panel */}
        <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-5">
          <h3 className="font-bold text-white light:text-surface-900 flex items-center gap-2 border-b border-surface-800/80 pb-3 light:border-surface-100">
            <Sliders className="h-4 w-4 text-indigo-400" />
            Conversion Options
          </h3>

          {/* Target Format */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-surface-300 light:text-surface-700">
              {t.targetFormatLabel}
            </label>
            <div className="grid grid-cols-3 gap-1.5">
              {formats.map(fmt => (
                <button
                  key={fmt}
                  type="button"
                  onClick={() => setTargetFormat(fmt)}
                  className={`rounded-lg py-2 text-xs font-bold uppercase transition-all ${
                    targetFormat === fmt
                      ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/30'
                      : 'border border-surface-800 bg-surface-950/60 text-surface-400 hover:text-white light:border-surface-200 light:bg-surface-50'
                  }`}
                >
                  {fmt}
                </button>
              ))}
            </div>
          </div>

          {/* Quality Presets */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-surface-300 light:text-surface-700">
              {t.presetLabel}
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setPreset('smaller')}
                className={`rounded-xl p-2.5 text-xs font-semibold border transition-all text-left rtl:text-right ${
                  preset === 'smaller'
                    ? 'border-indigo-500 bg-indigo-500/10 text-indigo-400'
                    : 'border-surface-800 bg-surface-950/60 text-surface-400 light:border-surface-200 light:bg-surface-50'
                }`}
              >
                <p className="font-bold">{t.presetSmaller}</p>
                <p className="text-[10px] text-surface-500 font-normal">Voice & sharing</p>
              </button>

              <button
                type="button"
                onClick={() => setPreset('balanced')}
                className={`rounded-xl p-2.5 text-xs font-semibold border transition-all text-left rtl:text-right ${
                  preset === 'balanced'
                    ? 'border-indigo-500 bg-indigo-500/10 text-indigo-400'
                    : 'border-surface-800 bg-surface-950/60 text-surface-400 light:border-surface-200 light:bg-surface-50'
                }`}
              >
                <p className="font-bold">{t.presetBalanced}</p>
                <p className="text-[10px] text-surface-500 font-normal">Balanced size</p>
              </button>

              <button
                type="button"
                onClick={() => setPreset('high')}
                className={`rounded-xl p-2.5 text-xs font-semibold border transition-all text-left rtl:text-right ${
                  preset === 'high'
                    ? 'border-indigo-500 bg-indigo-500/10 text-indigo-400'
                    : 'border-surface-800 bg-surface-950/60 text-surface-400 light:border-surface-200 light:bg-surface-50'
                }`}
              >
                <p className="font-bold">{t.presetHigh}</p>
                <p className="text-[10px] text-surface-500 font-normal">Highest bitrate</p>
              </button>

              <button
                type="button"
                onClick={() => setPreset('custom')}
                className={`rounded-xl p-2.5 text-xs font-semibold border transition-all text-left rtl:text-right ${
                  preset === 'custom'
                    ? 'border-indigo-500 bg-indigo-500/10 text-indigo-400'
                    : 'border-surface-800 bg-surface-950/60 text-surface-400 light:border-surface-200 light:bg-surface-50'
                }`}
              >
                <p className="font-bold">{t.presetCustom}</p>
                <p className="text-[10px] text-surface-500 font-normal">Manual options</p>
              </button>
            </div>
          </div>

          {/* Custom Settings fields */}
          {preset === 'custom' && (
            <div className="space-y-3 p-3 rounded-xl bg-surface-950/80 border border-surface-800 text-xs">
              <div>
                <label className="text-surface-400 font-medium">Bitrate</label>
                <select
                  value={bitrate}
                  onChange={e => setBitrate(e.target.value)}
                  className="w-full mt-1 rounded-lg border border-surface-800 bg-surface-900 px-2 py-1 text-xs text-white"
                >
                  <option value="96k">96 kbps</option>
                  <option value="128k">128 kbps</option>
                  <option value="192k">192 kbps</option>
                  <option value="256k">256 kbps</option>
                  <option value="320k">320 kbps</option>
                </select>
              </div>

              <div>
                <label className="text-surface-400 font-medium">Sample Rate</label>
                <select
                  value={sampleRate}
                  onChange={e => setSampleRate(parseInt(e.target.value))}
                  className="w-full mt-1 rounded-lg border border-surface-800 bg-surface-900 px-2 py-1 text-xs text-white"
                >
                  <option value={16000}>16,000 Hz</option>
                  <option value={22050}>22,050 Hz</option>
                  <option value={44100}>44,100 Hz</option>
                  <option value={48000}>48,000 Hz</option>
                </select>
              </div>

              <div>
                <label className="text-surface-400 font-medium">Channels</label>
                <select
                  value={channels}
                  onChange={e => setChannels(parseInt(e.target.value))}
                  className="w-full mt-1 rounded-lg border border-surface-800 bg-surface-900 px-2 py-1 text-xs text-white"
                >
                  <option value={1}>{t.channelMono}</option>
                  <option value={2}>{t.channelStereo}</option>
                </select>
              </div>
            </div>
          )}

          {/* Convert Button */}
          <button
            type="button"
            disabled={!singleFileId || isConverting}
            onClick={handleStartConversion}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-indigo-600 py-3 text-sm font-bold text-white shadow-lg shadow-indigo-500/25 hover:bg-indigo-500 disabled:opacity-50 disabled:pointer-events-none transition-all active:scale-[0.98]"
          >
            <Repeat className={`h-4 w-4 ${isConverting ? 'animate-spin' : ''}`} />
            <span>{isConverting ? t.convertingStatus : t.convertAudioBtn}</span>
          </button>
        </div>
      </div>

      {/* Before / After Preview & Result Card */}
      {conversionResult && (
        <div className="rounded-2xl border border-surface-800 bg-surface-900/70 p-6 light:border-surface-200 light:bg-white space-y-6 animate-fadeIn">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-surface-800 pb-4 light:border-surface-100">
            <div>
              <h3 className="text-lg font-bold text-white light:text-surface-900 flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                {t.beforeAfterTitle}
              </h3>
              <p className="text-xs text-surface-400">
                Converted to {targetFormat.toUpperCase()} ({conversionResult.output_filename})
              </p>
            </div>

            {/* Download Button */}
            <a
              href={api.getConvertedDownloadUrl(conversionResult.jobId)}
              download
              className="flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-xs font-bold text-white shadow-lg shadow-emerald-600/20 hover:bg-emerald-500 transition-colors"
            >
              <Download className="h-4 w-4" />
              <span>{t.downloadConvertedBtn}</span>
            </a>
          </div>

          {/* Size comparison pill */}
          <div className="flex items-center gap-4 p-4 rounded-xl bg-surface-950/60 border border-surface-800 light:bg-surface-50 light:border-surface-200 text-xs">
            <div>
              <span className="text-surface-400">Original Size:</span>
              <p className="text-sm font-bold text-white light:text-surface-900">{conversionResult.source_metadata?.size_formatted}</p>
            </div>
            <ArrowRight className="h-4 w-4 text-surface-600" />
            <div>
              <span className="text-surface-400">Converted Size:</span>
              <p className="text-sm font-bold text-white light:text-surface-900">{conversionResult.converted_metadata?.size_formatted}</p>
            </div>
            <div className="ml-auto rtl:mr-auto rtl:ml-0">
              <span className={`px-2.5 py-1 rounded-full font-bold text-xs ${
                conversionResult.size_change_bytes > 0
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                  : 'bg-surface-800 text-surface-300'
              }`}>
                {conversionResult.size_change_bytes > 0
                  ? `Saved ${conversionResult.size_change_percent}%`
                  : 'High Fidelity Output'}
              </span>
            </div>
          </div>

          {/* Dual Audio Players */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <span className="text-xs font-semibold text-surface-400">{t.originalAudio}</span>
              <AudioPlayer src={api.getAudioStreamUrl(singleFileId!)} />
            </div>
            <div className="space-y-2">
              <span className="text-xs font-semibold text-surface-400">{t.convertedAudio}</span>
              <AudioPlayer src={api.getConvertedDownloadUrl(conversionResult.jobId)} />
            </div>
          </div>
        </div>
      )}

      {/* Batch Conversion Section */}
      <div className="rounded-2xl border border-surface-800 bg-surface-900/50 p-6 light:border-surface-200 light:bg-white space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-surface-800 pb-3 light:border-surface-100">
          <div>
            <h3 className="font-bold text-white light:text-surface-900 flex items-center gap-2">
              <Archive className="h-4 w-4 text-indigo-400" />
              {t.batchQueueTitle}
            </h3>
            <p className="text-xs text-surface-400">
              Convert multiple files simultaneously with controlled background concurrency.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="file"
              id="batch-files"
              multiple
              accept="audio/*,video/*"
              onChange={e => e.target.files && handleBatchUpload(e.target.files)}
              className="hidden"
            />
            <label
              htmlFor="batch-files"
              className="cursor-pointer flex items-center gap-1.5 rounded-xl border border-surface-800 bg-surface-900 px-3 py-1.5 text-xs font-semibold text-surface-200 hover:bg-surface-800 light:border-surface-200 light:bg-surface-100 light:text-surface-800 transition-colors"
            >
              <Plus className="h-4 w-4" />
              <span>{t.addMoreFilesBtn}</span>
            </label>

            {batchItems.some(i => i.status === 'completed') && (
              <button
                onClick={handleDownloadZip}
                className="flex items-center gap-1.5 rounded-xl bg-indigo-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-indigo-500 shadow-md transition-colors"
              >
                <Download className="h-4 w-4" />
                <span>{t.downloadAllZipBtn}</span>
              </button>
            )}
          </div>
        </div>

        {batchItems.length === 0 ? (
          <div className="py-6 text-center text-xs text-surface-400">
            No files in batch queue. Click "{t.addMoreFilesBtn}" to add multiple recordings.
          </div>
        ) : (
          <div className="space-y-3">
            <div className="divide-y divide-surface-800/60 light:divide-surface-100">
              {batchItems.map(item => (
                <div key={item.id} className="py-3 flex flex-wrap items-center justify-between gap-3 text-xs">
                  <div className="flex items-center gap-2 min-w-0 max-w-xs">
                    <FileAudio className="h-4 w-4 text-indigo-400 flex-shrink-0" />
                    <span className="truncate font-medium text-white light:text-surface-900">{item.file.name}</span>
                  </div>

                  <div className="flex items-center gap-2">
                    <select
                      value={item.targetFormat}
                      disabled={item.status !== 'pending'}
                      onChange={e =>
                        setBatchItems(prev =>
                          prev.map(i => (i.id === item.id ? { ...i, targetFormat: e.target.value } : i))
                        )
                      }
                      className="rounded border border-surface-800 bg-surface-950 px-2 py-1 text-xs text-white"
                    >
                      {formats.map(f => (
                        <option key={f} value={f}>{f.toUpperCase()}</option>
                      ))}
                    </select>

                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      item.status === 'completed'
                        ? 'bg-emerald-500/10 text-emerald-400'
                        : item.status === 'converting'
                        ? 'bg-amber-500/10 text-amber-400 animate-pulse'
                        : 'bg-surface-800 text-surface-400'
                    }`}>
                      {item.status.toUpperCase()}
                    </span>

                    {item.status === 'completed' && item.jobId && (
                      <a
                        href={api.getConvertedDownloadUrl(item.jobId)}
                        download
                        className="text-indigo-400 hover:text-indigo-300 font-semibold"
                      >
                        Download
                      </a>
                    )}

                    <button
                      onClick={() => setBatchItems(prev => prev.filter(i => i.id !== item.id))}
                      className="text-surface-500 hover:text-rose-400 p-1"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <button
              onClick={runBatchConversion}
              disabled={isBatchRunning || batchItems.length === 0}
              className="w-full py-2.5 rounded-xl bg-indigo-600 font-bold text-xs text-white shadow-md hover:bg-indigo-500 disabled:opacity-50 transition-colors"
            >
              {isBatchRunning ? 'Processing Batch...' : 'Start Batch Conversion'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
