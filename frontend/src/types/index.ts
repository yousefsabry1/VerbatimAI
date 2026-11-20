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
  original_text?: string;
  confidence: 'high' | 'medium' | 'low';
  uncertain: boolean;
  uncertain_reason?: string | null;
  avg_logprob?: number;
  no_speech_prob?: number;
  compression_ratio?: number;
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
  is_experimental?: boolean;
  benchmark_only?: boolean;
}

export interface ConversionPreset {
  id: 'smaller' | 'balanced' | 'high' | 'custom';
  name: string;
  description: string;
}

export interface WordAlignmentOp {
  type: 'equal' | 'substitute' | 'delete' | 'insert';
  ref: string | null;
  hyp: string | null;
}

export interface BenchmarkRunResult {
  sample_id?: string;
  sample_name?: string;
  audio_filter?: string;
  model_id: string;
  name: string;
  status: 'success' | 'failed' | 'skipped';
  error?: string;
  device?: string;
  compute?: string;
  cuda_fallback?: boolean;
  elapsed_seconds?: number;
  speedup?: number;
  is_verified?: boolean;
  verification_notice?: string;
  reference_revision?: string;
  norm_wer?: number | null;
  norm_cer?: number | null;
  norm_sub?: number | null;
  norm_del?: number | null;
  norm_ins?: number | null;
  norm_hits?: number | null;
  raw_wer?: number | null;
  raw_cer?: number | null;
  raw_sub?: number | null;
  raw_del?: number | null;
  raw_ins?: number | null;
  predicted_text?: string;
  word_alignment?: WordAlignmentOp[];
}

export interface BenchmarkSample {
  sample_id: string;
  name: string;
  start_time: number;
  end_time: number;
  duration: number;
  audio_url: string;
  status: 'VERIFIED' | 'UNVERIFIED';
  verification_badge: string;
  has_human_reference: boolean;
  is_human_verified?: boolean;
  word_count: number;
  description: string;
}

export interface BenchmarkReference {
  sample_id?: string;
  sample_name?: string;
  has_reference: boolean;
  is_human_verified?: boolean;
  verification_status?: string;
  verification_badge?: string;
  verification_statement?: string;
  verification_method?: string;
  verification_timestamp?: number;
  reference_revision?: string;
  raw_text: string;
  normalized_text: string;
  start_time: number;
  end_time: number;
  duration?: number;
  word_count_raw?: number;
  word_count_norm?: number;
  updated_at?: number;
}

export interface DiffChunk {
  type: 'equal' | 'substitute' | 'insert' | 'delete';
  primary: string | null;
  alternative: string | null;
}

export interface AlternativeHypothesis {
  id: string;
  job_id: string;
  segment_id: number;
  model_id: string;
  model_name: string;
  start_time: number;
  end_time: number;
  extracted_start: number;
  extracted_end: number;
  context_padding: number;
  hypothesis_text: string;
  primary_text: string;
  diff: DiffChunk[];
  disagreement_score: number;
  device_used?: string;
  compute_used?: string;
  elapsed_seconds?: number;
  is_cached?: boolean;
  created_at?: string;
}

export interface SegmentReviewItem {
  segment_id: number;
  start: number;
  end: number;
  text: string;
  original_text: string;
  review_status: 'unreviewed' | 'review_suggested' | 'alternative_available' | 'human_reviewed';
  is_flagged: boolean;
  flag_label: string;
  flag_reasons: string[];
  severity: 'high' | 'medium' | 'low' | 'none';
  alternatives_count: number;
  latest_alternative?: AlternativeHypothesis | null;
  human_notes?: string | null;
  reviewed_at?: string | null;
}

export interface JobReviewsResponse {
  job_id: string;
  total_segments: number;
  flagged_count: number;
  reviewed_count: number;
  items: SegmentReviewItem[];
}

export interface VerifySegmentResponse {
  status: string;
  is_cached: boolean;
  hypothesis_id: string;
  job_id: string;
  segment_id: number;
  model_id: string;
  model_name: string;
  start_time: number;
  end_time: number;
  extracted_start: number;
  extracted_end: number;
  context_padding: number;
  hypothesis_text: string;
  primary_text: string;
  diff: DiffChunk[];
  disagreement_score: number;
  device_used?: string;
  compute_used?: string;
  elapsed_seconds?: number;
  peak_vram_mb?: number;
}

export interface EvidenceSpan {
  segment_id: number;
  start: number;
  end: number;
  time_formatted: string;
  quote: string;
}

export interface InstructionItem {
  id: string;
  category: string;
  title: string;
  description: string;
  provenance: 'explicitly_spoken' | 'interpreted_from_context' | 'needs_human_verification';
  evidence: EvidenceSpan;
  confidence: number;
  negation_detected: boolean;
  reversal_detected: boolean;
  reversal_details?: string | null;
}

export interface UnderstandingBrief {
  job_id: string;
  title: string;
  topic_overview: string;
  summary_counts: Record<string, number>;
  categories: Record<string, InstructionItem[]>;
  created_at?: string;
}
