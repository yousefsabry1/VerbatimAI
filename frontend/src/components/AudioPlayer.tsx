import React, { useRef, useState, useEffect, forwardRef, useImperativeHandle } from 'react';
import {
  Play,
  Pause,
  RotateCcw,
  RotateCw,
  Volume2,
  VolumeX,
  Repeat,
  X,
  Loader2,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { useI18n } from '../context/I18nContext';

export interface AudioPlayerRef {
  seekTo: (timeInSeconds: number) => void;
  play: () => Promise<void>;
  pause: () => void;
  togglePlay: () => void;
  seekRelative: (seconds: number) => void;
  loopSegment: (start: number, end: number) => void;
  clearLoop: () => void;
  setPlaybackRate: (rate: number) => void;
  getCurrentTime: () => number;
  getIsPlaying: () => boolean;
}

interface AudioPlayerProps {
  src: string;
  knownDuration?: number;
  onTimeUpdate?: (currentTime: number) => void;
  className?: string;
  autoPlay?: boolean;
}

export const AudioPlayer = forwardRef<AudioPlayerRef, AudioPlayerProps>(({
  src,
  knownDuration,
  onTimeUpdate,
  className = '',
  autoPlay = false,
}, ref) => {
  const { t } = useI18n();
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Real media element playback states
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isBuffering, setIsBuffering] = useState<boolean>(false);
  const [playbackError, setPlaybackError] = useState<string | null>(null);

  const [currentTime, setCurrentTime] = useState<number>(0);
  const [duration, setDuration] = useState<number>(knownDuration || 0);
  const [playbackRate, setPlaybackRate] = useState<number>(1);
  const [volume, setVolume] = useState<number>(1);
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [loopRange, setLoopRange] = useState<{ start: number; end: number } | null>(null);

  // Keep duration in sync if knownDuration changes from parent
  useEffect(() => {
    if (knownDuration && knownDuration > 0 && (duration <= 0 || !isFinite(duration))) {
      setDuration(knownDuration);
    }
  }, [knownDuration]);

  // Imperative handle for parent component control
  useImperativeHandle(ref, () => ({
    seekTo: (timeInSeconds: number) => {
      const audio = audioRef.current;
      if (!audio) return;

      const target = Math.max(0, timeInSeconds);
      audio.currentTime = target;
      setCurrentTime(target);
      setPlaybackError(null);

      // Trigger actual playback through media element
      const p = audio.play();
      if (p !== undefined) {
        p.catch((err) => {
          console.warn('Playback prevented after seek:', err);
          setIsPlaying(false);
        });
      }
    },
    play: async () => {
      const audio = audioRef.current;
      if (!audio) return;
      setPlaybackError(null);
      try {
        await audio.play();
      } catch (err: any) {
        console.warn('Playback promise rejected:', err);
        setIsPlaying(false);
        setPlaybackError(err.message || 'Playback blocked by browser. Click Play to start.');
      }
    },
    pause: () => {
      audioRef.current?.pause();
      setIsPlaying(false);
    },
    togglePlay: () => {
      togglePlay();
    },
    seekRelative: (seconds: number) => {
      seekRelative(seconds);
    },
    loopSegment: (start: number, end: number) => {
      setLoopRange({ start, end });
      const audio = audioRef.current;
      if (audio) {
        audio.currentTime = start;
        setCurrentTime(start);
        setPlaybackError(null);
        const p = audio.play();
        if (p !== undefined) {
          p.catch((err) => {
            console.warn('Loop playback promise rejected:', err);
            setIsPlaying(false);
          });
        }
      }
    },
    clearLoop: () => {
      setLoopRange(null);
    },
    setPlaybackRate: (rate: number) => {
      changePlaybackRate(rate);
    },
    getCurrentTime: () => {
      return audioRef.current?.currentTime || currentTime || 0;
    },
    getIsPlaying: () => {
      return isPlaying;
    },
  }));

  // Bind to native HTMLAudioElement events
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    setPlaybackError(null);

    const onPlay = () => {
      setIsPlaying(true);
      setPlaybackError(null);
    };

    const onPlaying = () => {
      setIsPlaying(true);
      setIsBuffering(false);
      setPlaybackError(null);
    };

    const onPause = () => {
      setIsPlaying(false);
      setIsBuffering(false);
    };

    const onWaiting = () => {
      setIsBuffering(true);
    };

    const onCanPlay = () => {
      setIsBuffering(false);
    };

    const onLoadedMetadata = () => {
      const d = audio.duration;
      if (d && !isNaN(d) && isFinite(d) && d > 0) {
        setDuration(d);
      } else if (knownDuration && knownDuration > 0) {
        setDuration(knownDuration);
      }
      setIsBuffering(false);

      if (autoPlay) {
        audio.play().catch(console.warn);
      }
    };

    const onDurationChange = () => {
      const d = audio.duration;
      if (d && !isNaN(d) && isFinite(d) && d > 0) {
        setDuration(d);
      }
    };

    const onTimeUpdateHandler = () => {
      const now = audio.currentTime;
      setCurrentTime(now);

      // Continuous loop boundary enforcement
      if (loopRange) {
        if (now >= loopRange.end) {
          audio.currentTime = loopRange.start;
          audio.play().catch(console.warn);
          return;
        }
      }

      if (onTimeUpdate) {
        onTimeUpdate(now);
      }
    };

    const onEnded = () => {
      if (loopRange) {
        audio.currentTime = loopRange.start;
        audio.play().catch(console.warn);
      } else {
        setIsPlaying(false);
        setIsBuffering(false);
      }
    };

    const onError = () => {
      setIsPlaying(false);
      setIsBuffering(false);
      const mediaErr = audio.error;
      let errMsg = 'Audio playback error occurred.';
      if (mediaErr) {
        switch (mediaErr.code) {
          case MediaError.MEDIA_ERR_ABORTED:
            errMsg = 'Audio playback aborted.';
            break;
          case MediaError.MEDIA_ERR_NETWORK:
            errMsg = 'Network error while loading audio.';
            break;
          case MediaError.MEDIA_ERR_DECODE:
            errMsg = 'Audio decoding failed.';
            break;
          case MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED:
            errMsg = 'Audio stream not supported or not found (404).';
            break;
        }
      }
      setPlaybackError(errMsg);
    };

    audio.addEventListener('play', onPlay);
    audio.addEventListener('playing', onPlaying);
    audio.addEventListener('pause', onPause);
    audio.addEventListener('waiting', onWaiting);
    audio.addEventListener('canplay', onCanPlay);
    audio.addEventListener('loadedmetadata', onLoadedMetadata);
    audio.addEventListener('durationchange', onDurationChange);
    audio.addEventListener('timeupdate', onTimeUpdateHandler);
    audio.addEventListener('ended', onEnded);
    audio.addEventListener('error', onError);

    return () => {
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('playing', onPlaying);
      audio.removeEventListener('pause', onPause);
      audio.removeEventListener('waiting', onWaiting);
      audio.removeEventListener('canplay', onCanPlay);
      audio.removeEventListener('loadedmetadata', onLoadedMetadata);
      audio.removeEventListener('durationchange', onDurationChange);
      audio.removeEventListener('timeupdate', onTimeUpdateHandler);
      audio.removeEventListener('ended', onEnded);
      audio.removeEventListener('error', onError);
    };
  }, [src, autoPlay, onTimeUpdate, loopRange, knownDuration]);

  const togglePlay = () => {
    const audio = audioRef.current;
    if (!audio) return;

    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
    } else {
      setPlaybackError(null);
      const p = audio.play();
      if (p !== undefined) {
        p.catch((err) => {
          console.warn('Playback error on togglePlay:', err);
          setIsPlaying(false);
          setPlaybackError('Could not start playback. Please click Play again.');
        });
      }
    }
  };

  const seekRelative = (seconds: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    const effectiveDuration = duration > 0 ? duration : (knownDuration || 600);
    const target = Math.max(0, Math.min(effectiveDuration, audio.currentTime + seconds));
    audio.currentTime = target;
    setCurrentTime(target);
  };

  const handleScrubberChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const target = parseFloat(e.target.value);
    const audio = audioRef.current;
    if (audio) {
      audio.currentTime = target;
      setCurrentTime(target);
    }
  };

  const changePlaybackRate = (rate: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.playbackRate = rate;
    setPlaybackRate(rate);
  };

  const toggleMute = () => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.muted = !isMuted;
    setIsMuted(!isMuted);
  };

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    const audio = audioRef.current;
    if (!audio) return;
    audio.volume = val;
    setVolume(val);
    setIsMuted(val === 0);
  };

  const formatTime = (secs: number) => {
    if (isNaN(secs) || !isFinite(secs) || secs < 0) return '00:00';
    const s = Math.floor(secs);
    const m = Math.floor(s / 60);
    const remainder = s % 60;
    return `${m.toString().padStart(2, '0')}:${remainder.toString().padStart(2, '0')}`;
  };

  const effectiveDuration = (duration > 0 && isFinite(duration))
    ? duration
    : (knownDuration && knownDuration > 0 ? knownDuration : 0);

  return (
    <div className={`rounded-2xl border border-surface-800 bg-surface-900/90 p-4 shadow-xl backdrop-blur-sm light:border-surface-200 light:bg-white light:shadow-sm space-y-3 ${className}`}>
      {/* Hidden native audio element */}
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        playsInline
      />

      {/* Error alert banner if playback failed */}
      {playbackError && (
        <div className="flex items-center justify-between p-2.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs animate-fadeIn">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
            <span>{playbackError}</span>
          </div>
          <button
            type="button"
            onClick={() => {
              setPlaybackError(null);
              if (audioRef.current) {
                audioRef.current.load();
                audioRef.current.play().catch(console.warn);
              }
            }}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-semibold text-[11px] transition-colors shrink-0"
          >
            <RefreshCw className="h-3 w-3" />
            <span>Retry Audio</span>
          </button>
        </div>
      )}

      {/* Looping indicator if active */}
      {loopRange && (
        <div className="flex items-center justify-between px-3 py-1.5 rounded-xl bg-brand-500/15 border border-brand-500/30 text-xs text-brand-300 font-semibold animate-fadeIn">
          <span className="flex items-center gap-1.5">
            <Repeat className="h-3.5 w-3.5 text-brand-400 animate-spin" style={{ animationDuration: '4s' }} />
            <span>Looping Segment: <strong className="font-mono text-white">{formatTime(loopRange.start)} — {formatTime(loopRange.end)}</strong></span>
          </span>
          <button
            type="button"
            onClick={() => setLoopRange(null)}
            className="flex items-center gap-1 px-2 py-0.5 rounded-lg bg-surface-800 text-surface-300 hover:text-white hover:bg-surface-700 transition-colors text-[11px]"
          >
            <X className="h-3 w-3" />
            <span>Stop Loop</span>
          </button>
        </div>
      )}

      {/* Scrubber timeline */}
      <div className="flex items-center gap-3">
        <span className="text-xs font-mono text-surface-300 light:text-surface-700 min-w-[44px] text-right font-bold">
          {formatTime(currentTime)}
        </span>
        <div className="relative w-full flex items-center">
          <input
            type="range"
            min="0"
            max={effectiveDuration > 0 ? effectiveDuration : 100}
            step="0.1"
            value={currentTime}
            onChange={handleScrubberChange}
            className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-surface-800 accent-brand-500 light:bg-surface-200"
          />
          {/* Highlight loop segment on scrubber if active */}
          {loopRange && effectiveDuration > 0 && (
            <div
              className="absolute h-2 bg-brand-400/40 rounded pointer-events-none"
              style={{
                left: `${(loopRange.start / effectiveDuration) * 100}%`,
                width: `${Math.max(1, ((loopRange.end - loopRange.start) / effectiveDuration) * 100)}%`,
              }}
            />
          )}
        </div>
        <span className="text-xs font-mono text-surface-400 light:text-surface-600 min-w-[44px] font-bold">
          {formatTime(effectiveDuration)}
        </span>
      </div>

      {/* Controls row */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
        {/* Playback rate presets */}
        <div className="flex items-center gap-1 bg-surface-950/60 p-1 rounded-xl border border-surface-800/80 light:bg-surface-100 light:border-surface-200">
          <span className="text-[10px] font-bold text-surface-500 uppercase px-1">Speed</span>
          {[0.5, 0.75, 1, 1.25, 1.5].map(rate => (
            <button
              key={rate}
              onClick={() => changePlaybackRate(rate)}
              className={`rounded-lg px-2 py-1 text-xs font-mono font-bold transition-colors ${
                playbackRate === rate
                  ? 'bg-brand-600 text-white shadow-sm'
                  : 'text-surface-400 hover:text-white hover:bg-surface-800 light:text-surface-600'
              }`}
            >
              {rate}x
            </button>
          ))}
        </div>

        {/* Center: Rewind, Play/Pause, Forward */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => seekRelative(-5)}
            className="rounded-xl p-2.5 text-surface-300 hover:bg-surface-800 hover:text-white bg-surface-950/60 border border-surface-800/80 light:bg-surface-100 light:border-surface-200 light:text-surface-700 transition-colors flex items-center gap-1 text-xs font-mono"
            title="Rewind 5s (Shift+Left)"
          >
            <RotateCcw className="h-4 w-4" />
            <span>-5s</span>
          </button>

          <button
            onClick={togglePlay}
            disabled={isBuffering && !isPlaying}
            className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-600 text-white shadow-lg shadow-brand-500/30 hover:bg-brand-500 transition-all active:scale-95 disabled:opacity-70"
            title={isPlaying ? 'Pause (Space / Alt+Space)' : 'Play (Space / Alt+Space)'}
          >
            {isBuffering ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : isPlaying ? (
              <Pause className="h-5 w-5" />
            ) : (
              <Play className="h-5 w-5 ml-0.5" />
            )}
          </button>

          <button
            onClick={() => seekRelative(5)}
            className="rounded-xl p-2.5 text-surface-300 hover:bg-surface-800 hover:text-white bg-surface-950/60 border border-surface-800/80 light:bg-surface-100 light:border-surface-200 light:text-surface-700 transition-colors flex items-center gap-1 text-xs font-mono"
            title="Forward 5s (Shift+Right)"
          >
            <span>+5s</span>
            <RotateCw className="h-4 w-4" />
          </button>
        </div>

        {/* Volume controls */}
        <div className="flex items-center gap-2 bg-surface-950/60 p-2 rounded-xl border border-surface-800/80 light:bg-surface-100 light:border-surface-200">
          <button
            onClick={toggleMute}
            className="text-surface-400 hover:text-white light:hover:text-surface-900 transition-colors"
            title={isMuted ? 'Unmute' : 'Mute'}
          >
            {isMuted || volume === 0 ? <VolumeX className="h-4 w-4 text-rose-400" /> : <Volume2 className="h-4 w-4" />}
          </button>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={isMuted ? 0 : volume}
            onChange={handleVolumeChange}
            className="h-1.5 w-16 cursor-pointer appearance-none rounded-lg bg-surface-800 accent-brand-500 light:bg-surface-300"
          />
        </div>
      </div>
    </div>
  );
});
