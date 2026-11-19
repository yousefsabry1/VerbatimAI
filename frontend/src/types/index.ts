export interface AudioMetadata {
  is_valid_audio: boolean;
  format: string;
  codec: string;
  duration: number;
  duration_formatted: string;
  sample_rate: number;
  channels: number;
  channel_layout: string;
  bitrate: number;
  bitrate_kbps: number | null;
  size: number;
  size_formatted: string;
  has_video: boolean;
  error?: string;
}

export interface Word {
  word: string;
  start: number;
  end: number;
  probability: number;
}

export interface Segment {
  id: number;
  start: number;
  end: number;
  text: string;
  confidence: 'high' | 'medium' | 'low';
  uncertain: boolean;
  words?: Word[];
}

export interface Job {
  id: string;
  job_type: 'transcription' | 'conversion';
  status: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  stage: string;
  error_message?: string | null;
  input_filename: string;
  input_path: string;
  input_duration?: number;
  input_size?: number;
  input_format?: string;
  model_used?: string;
  device_used?: string;
  compute_used?: string;
  language?: string;
  output_files: Record<string, string>;
  metadata: Record<string, any>;
  created_at: string;
  completed_at?: string | null;
}

export interface TranscriptResult {
  job_id: string;
  is_complete: boolean;
  job: Job;
  original_text: string;
  clean_text: string;
  srt_content: string;
  vtt_content: string;
  segments: Segment[];
  is_edited: boolean;
  updated_at?: string;
}

export interface HardwareInfo {
  cuda_available: boolean;
  cuda_device_count: number;
  gpu_name: string;
  vram_total_mb: number | null;
  vram_used_mb: number | null;
  vram_free_mb: number | null;
  driver_version: string | null;
  cpu_cores: number;
  recommended: {
    model: string;
    device: string;
    compute: string;
  };
}

export interface ModelInfo {
  id: string;
  name: string;
  repo: string;
  approx_vram_gb: number;
  approx_download_gb: number;
  recommended_for: string;
  is_downloaded: boolean;
  folder_size_gb: number;
  is_downloading: boolean;
  download_progress: number;
  status_message: string;
}

export interface ConversionPreset {
  id: 'smaller' | 'balanced' | 'high' | 'custom';
  name: string;
  description: string;
}
