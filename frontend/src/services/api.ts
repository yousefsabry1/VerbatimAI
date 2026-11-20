import type {
  AudioMetadata,
  HardwareInfo,
  Job,
  ModelInfo,
  Segment,
  TranscriptResult,
  AlternativeHypothesis,
  JobReviewsResponse,
  VerifySegmentResponse,
} from '../types';

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

  getAudioStreamUrl(fileId: string, preview: boolean = true): string {
    return `${API_BASE}/audio/stream/${fileId}?preview=${preview}`;
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

  async suggestAlternativeSegment(params: {
    job_id: string;
    start: number;
    end: number;
    model_id: string;
    device_mode?: string;
  }): Promise<{
    status: string;
    job_id: string;
    start: number;
    end: number;
    model_id: string;
    model_name: string;
    suggested_text: string;
    device_used?: string;
    compute_used?: string;
    elapsed_seconds: number;
  }> {
    const res = await fetch(`${API_BASE}/transcription/suggest-alternative`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to generate alternative suggestion' }));
      throw new Error(err.detail || 'Failed to generate alternative suggestion');
    }
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
    action?: 'save_draft' | 'save_and_verify';
    start_time?: number;
    end_time?: number;
    is_human_verified?: boolean;
    verification_statement?: string;
  }): Promise<any> {
    const res = await fetch(`${API_BASE}/benchmark/reference`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to save benchmark reference' }));
      throw new Error(err.detail || 'Failed to save benchmark reference');
    }
    return res.json();
  },

  async calculateBenchmarkAccuracy(params: {
    sample_id: string;
    eval_mode?: 'normalized' | 'raw';
  }): Promise<{ status: string; sample_id: string; sample_name?: string; is_human_verified: boolean; eval_mode: string; evaluated_models: number; results: any[] }> {
    const res = await fetch(`${API_BASE}/benchmark/calculate-accuracy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to calculate accuracy' }));
      throw new Error(err.detail || 'Failed to calculate accuracy metrics');
    }
    return res.json();
  },

  async getBenchmarkResults(sampleId: string = 'dev_0_103'): Promise<{ has_results: boolean; sample_id?: string; sample_name?: string; is_human_verified?: boolean; results: any[] }> {
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
    audio_filter?: 'none' | 'highpass_gain';
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

  // Second-Pass & Review Workspace Endpoints
  async verifySegment(
    jobId: string,
    segmentId: number,
    params: {
      model_id?: string;
      context_padding?: number;
      device_mode?: string;
      force_recompute?: boolean;
    } = {}
  ): Promise<VerifySegmentResponse> {
    const res = await fetch(`${API_BASE}/review/${encodeURIComponent(jobId)}/segment/${segmentId}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Verification failed' }));
      throw new Error(err.detail || 'Verification request failed');
    }
    return res.json();
  },

  async getSegmentAlternatives(
    jobId: string,
    segmentId: number
  ): Promise<{ job_id: string; segment_id: number; count: number; hypotheses: AlternativeHypothesis[] }> {
    const res = await fetch(`${API_BASE}/review/${encodeURIComponent(jobId)}/segment/${segmentId}/alternatives`);
    if (!res.ok) throw new Error('Failed to fetch segment alternatives');
    return res.json();
  },

  async getJobReviews(jobId: string): Promise<JobReviewsResponse> {
    const res = await fetch(`${API_BASE}/review/${encodeURIComponent(jobId)}/reviews`);
    if (!res.ok) throw new Error('Failed to fetch job reviews');
    return res.json();
  },

  async updateReviewStatus(
    jobId: string,
    segmentId: number,
    params: {
      review_status: string;
      selected_alternative_id?: string | null;
      human_notes?: string | null;
      flag_reasons?: string[];
    }
  ): Promise<any> {
    const res = await fetch(`${API_BASE}/review/${encodeURIComponent(jobId)}/segment/${segmentId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error('Failed to update review status');
    return res.json();
  },

  getSegmentAudioUrl(jobId: string, segmentId: number, padding: number = 1.0): string {
    return `${API_BASE}/review/${encodeURIComponent(jobId)}/segment/${segmentId}/audio?padding=${padding}`;
  },

  // Evidence-Grounded Speech Understanding & Actionable Briefs
  async generateUnderstandingBrief(
    jobId: string,
    preferHumanCorrected: boolean = true
  ): Promise<{ status: string; job_id: string; brief: any }> {
    const res = await fetch(`${API_BASE}/understanding/${encodeURIComponent(jobId)}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prefer_human_corrected: preferHumanCorrected }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to generate understanding brief' }));
      throw new Error(err.detail || 'Failed to generate understanding brief');
    }
    return res.json();
  },

  async getUnderstandingBrief(
    jobId: string
  ): Promise<{ status: string; job_id: string; title: string; topic_overview: string; brief: any; created_at: string }> {
    const res = await fetch(`${API_BASE}/understanding/${encodeURIComponent(jobId)}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to fetch understanding brief' }));
      throw new Error(err.detail || 'Failed to fetch understanding brief');
    }
    return res.json();
  },

  getUnderstandingMarkdownUrl(jobId: string): string {
    return `${API_BASE}/understanding/${encodeURIComponent(jobId)}/export/markdown`;
  },

  getUnderstandingJsonUrl(jobId: string): string {
    return `${API_BASE}/understanding/${encodeURIComponent(jobId)}/export/json`;
  },
};
