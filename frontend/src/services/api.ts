import type { AudioMetadata, HardwareInfo, Job, ModelInfo, Segment, TranscriptResult } from '../types';

const API_BASE = '/api';

export const api = {
  // Health & System
  async getHealth() {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error('Failed to fetch health');
    return res.json();
  },

  async getSystem() {
    const res = await fetch(`${API_BASE}/system`);
    if (!res.ok) throw new Error('Failed to fetch system info');
    return res.json();
  },

  // Hardware
  async getHardware(): Promise<HardwareInfo> {
    const res = await fetch(`${API_BASE}/hardware`);
    if (!res.ok) throw new Error('Failed to fetch hardware status');
    return res.json();
  },

  // Models
  async getModels(): Promise<{ models: ModelInfo[] }> {
    const res = await fetch(`${API_BASE}/models`);
    if (!res.ok) throw new Error('Failed to fetch models');
    return res.json();
  },

  async downloadModel(modelId: string) {
    const res = await fetch(`${API_BASE}/models/${modelId}/download`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to trigger model download');
    return res.json();
  },

  async deleteModel(modelId: string) {
    const res = await fetch(`${API_BASE}/models/${modelId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete model');
    return res.json();
  },

  // Audio Upload & Stream
  async uploadAudio(file: File): Promise<{ file_id: string; filename: string; metadata: AudioMetadata }> {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/audio/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(err.detail || 'Upload failed');
    }
    return res.json();
  },

  getAudioStreamUrl(fileId: string): string {
    return `${API_BASE}/audio/stream/${fileId}`;
  },

  // Transcription
  async submitTranscription(payload: {
    file_id: string;
    model_id: string;
    language?: string | null;
    device_mode: string;
    compute_mode: string;
    accuracy_mode: string;
    verbatim_mode: string;
    enhance_audio: boolean;
    vad_filter: boolean;
    vocabulary_hints?: string | null;
  }): Promise<{ job_id: string; status: string }> {
    const res = await fetch(`${API_BASE}/transcription/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Submission failed' }));
      throw new Error(err.detail || 'Failed to submit transcription job');
    }
    return res.json();
  },

  async getTranscriptionStatus(jobId: string): Promise<Job> {
    const res = await fetch(`${API_BASE}/transcription/${jobId}`);
    if (!res.ok) throw new Error('Failed to get job status');
    return res.json();
  },

  async getTranscriptionResult(jobId: string): Promise<TranscriptResult> {
    const res = await fetch(`${API_BASE}/transcription/${jobId}/result`);
    if (!res.ok) throw new Error('Failed to get transcription result');
    return res.json();
  },

  async updateTranscriptSegments(jobId: string, cleanText: string, segments: Segment[]) {
    const res = await fetch(`${API_BASE}/transcription/${jobId}/segments`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clean_text: cleanText, segments }),
    });
    if (!res.ok) throw new Error('Failed to save transcript edits');
    return res.json();
  },

  async cancelJob(jobId: string) {
    const res = await fetch(`${API_BASE}/transcription/${jobId}/cancel`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to cancel job');
    return res.json();
  },

  // Conversion
  async getConversionFormats() {
    const res = await fetch(`${API_BASE}/conversion/formats`);
    if (!res.ok) throw new Error('Failed to get formats');
    return res.json();
  },

  async submitConversion(payload: {
    file_id: string;
    target_format: string;
    preset: string;
    bitrate?: string | null;
    sample_rate?: number | null;
    channels?: number | null;
  }): Promise<{ job_id: string; status: string }> {
    const res = await fetch(`${API_BASE}/conversion/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Conversion submission failed' }));
      throw new Error(err.detail || 'Failed to submit conversion');
    }
    return res.json();
  },

  getConvertedDownloadUrl(jobId: string): string {
    return `${API_BASE}/conversion/${jobId}/download`;
  },

  async downloadBatchZip(jobIds: string[]) {
    const res = await fetch(`${API_BASE}/conversion/download-zip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_ids: jobIds }),
    });
    if (!res.ok) throw new Error('Failed to download ZIP');
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'verbatim_converted_audio.zip';
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  },

  // History
  async getHistory(limit: number = 50, type?: string): Promise<{ jobs: Job[] }> {
    const url = type ? `${API_BASE}/history?limit=${limit}&type=${type}` : `${API_BASE}/history?limit=${limit}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to fetch history');
    return res.json();
  },

  async deleteHistoryItem(jobId: string) {
    const res = await fetch(`${API_BASE}/history/${jobId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete history item');
    return res.json();
  },

  async clearAllHistory() {
    const res = await fetch(`${API_BASE}/history`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to clear history');
    return res.json();
  },

  // Exports
  getExportUrl(jobId: string, format: string, version: string = 'edited'): string {
    return `${API_BASE}/exports/${jobId}/${format}?version=${version}`;
  },

  // Benchmarking
  async getBenchmarkSamples(): Promise<any> {
    const res = await fetch(`${API_BASE}/benchmark/samples`);
    if (!res.ok) throw new Error('Failed to fetch benchmark samples');
    return res.json();
  },

  getBenchmarkAudioUrl(sampleId: string): string {
    return `${API_BASE}/benchmark/audio/${sampleId}`;
  },

  async getBenchmarkReference(sampleId: string = 'dev_0_103'): Promise<any> {
    const res = await fetch(`${API_BASE}/benchmark/reference?sample_id=${encodeURIComponent(sampleId)}`);
    if (!res.ok) throw new Error('Failed to fetch benchmark reference');
    return res.json();
  },

  async saveBenchmarkReference(params: {
    sample_id?: string;
    reference_text: string;
    start_time: number;
    end_time: number;
    is_human_verified?: boolean;
    verification_statement?: string;
  }): Promise<any> {
    const res = await fetch(`${API_BASE}/benchmark/reference`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error('Failed to save benchmark reference');
    return res.json();
  },

  async getBenchmarkResults(sampleId: string = 'dev_0_103'): Promise<{ has_results: boolean; sample_id?: string; results: any[] }> {
    const res = await fetch(`${API_BASE}/benchmark/results?sample_id=${encodeURIComponent(sampleId)}`);
    if (!res.ok) throw new Error('Failed to fetch benchmark results');
    return res.json();
  },

  async runBenchmark(params: {
    sample_id?: string;
    start_time: number;
    end_time: number;
    model_ids: string[];
    device_mode: string;
    use_hints: boolean;
    custom_hints?: string | null;
    eval_mode: string;
    vad_filter?: boolean;
  }): Promise<any> {
    const res = await fetch(`${API_BASE}/benchmark/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Benchmark execution failed' }));
      throw new Error(err.detail || 'Benchmark execution failed');
    }
    return res.json();
  },

  async liveAlign(reference_text: string, hypothesis_text: string, eval_mode: string = 'normalized'): Promise<any> {
    const res = await fetch(`${API_BASE}/benchmark/align`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reference_text, hypothesis_text, eval_mode }),
    });
    if (!res.ok) throw new Error('Failed to recalculate alignment');
    return res.json();
  },
};
