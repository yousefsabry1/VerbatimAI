import React, { useRef, useState, useEffect, forwardRef, useImperativeHandle } from 'react';
import { Play, Pause, RotateCcw, RotateCw, Volume2, VolumeX, Repeat, X } from 'lucide-react';
import { useI18n } from '../context/I18nContext';

export interface AudioPlayerRef {
  seekTo: (timeInSeconds: number) => void;
  play: () => void;
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
  onTimeUpdate?: (currentTime: number) => void;
  className?: string;
  autoPlay?: boolean;
}

export const AudioPlayer = forwardRef<AudioPlayerRef, AudioPlayerProps>(({
  src,
  onTimeUpdate,
  className = '',
  autoPlay = false,
}, ref) => {
  const { t } = useI18n();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [loopRange, setLoopRange] = useState<{ start: number; end: number } | null>(null);

  useImperativeHandle(ref, () => ({
    seekTo: (timeInSeconds: number) => {
      if (audioRef.current) {
        audioRef.current.currentTime = timeInSeconds;
        setCurrentTime(timeInSeconds);
        if (!isPlaying) {
          audioRef.current.play().catch(() => {});
          setIsPlaying(true);
        }
      }
    },
    play: () => {
      audioRef.current?.play().catch(() => {});
      setIsPlaying(true);
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
      if (audioRef.current) {
        audioRef.current.currentTime = start;
        setCurrentTime(start);
        audioRef.current.play().catch(() => {});
        setIsPlaying(true);
      }
    },
    clearLoop: () => {
      setLoopRange(null);
    },
    setPlaybackRate: (rate: number) => {
      changePlaybackRate(rate);
    },
    getCurrentTime: () => {
      return audioRef.current?.currentTime || 0;
    },
    getIsPlaying: () => {
      return isPlaying;
    },
  }));

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const handleLoadedMetadata = () => {
      setDuration(audio.duration || 0);
      if (autoPlay) {
        audio.play().catch(() => {});
        setIsPlaying(true);
      }
    };

    const handleTimeUpdate = () => {
      const now = audio.currentTime;
      setCurrentTime(now);

      // Check loop range
      if (loopRange) {
        if (now >= loopRange.end) {
          audio.currentTime = loopRange.start;
          audio.play().catch(() => {});
          return;
        }
      }

      if (onTimeUpdate) {
        onTimeUpdate(now);
      }
    };

    const handleEnded = () => {
      if (loopRange) {
        audio.currentTime = loopRange.start;
        audio.play().catch(() => {});
      } else {
        setIsPlaying(false);
      }
    };

    audio.addEventListener('loadedmetadata', handleLoadedMetadata);
    audio.addEventListener('timeupdate', handleTimeUpdate);
    audio.addEventListener('ended', handleEnded);

    return () => {
      audio.removeEventListener('loadedmetadata', handleLoadedMetadata);
      audio.removeEventListener('timeupdate', handleTimeUpdate);
      audio.removeEventListener('ended', handleEnded);
    };
  }, [src, autoPlay, onTimeUpdate, loopRange]);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play().catch(() => {});
      setIsPlaying(true);
    }
  };

  const seekRelative = (seconds: number) => {
    if (!audioRef.current) return;
    const target = Math.max(0, Math.min(duration, audioRef.current.currentTime + seconds));
    audioRef.current.currentTime = target;
    setCurrentTime(target);
  };

  const handleScrubberChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const target = parseFloat(e.target.value);
    if (audioRef.current) {
      audioRef.current.currentTime = target;
      setCurrentTime(target);
    }
  };

  const changePlaybackRate = (rate: number) => {
    if (!audioRef.current) return;
    audioRef.current.playbackRate = rate;
    setPlaybackRate(rate);
  };

  const toggleMute = () => {
    if (!audioRef.current) return;
    audioRef.current.muted = !isMuted;
    setIsMuted(!isMuted);
  };

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    if (!audioRef.current) return;
    audioRef.current.volume = val;
    setVolume(val);
    if (val === 0) setIsMuted(true);
    else setIsMuted(false);
  };

  const formatTime = (secs: number) => {
    const s = Math.max(0, Math.floor(secs));
    const m = Math.floor(s / 60);
    const remainder = s % 60;
    return `${m.toString().padStart(2, '0')}:${remainder.toString().padStart(2, '0')}`;
  };

  return (
    <div className={`rounded-2xl border border-surface-800 bg-surface-900/90 p-4 shadow-xl backdrop-blur-sm light:border-surface-200 light:bg-white light:shadow-sm space-y-3 ${className}`}>
      <audio ref={audioRef} src={src} preload="metadata" />

      {/* Looping indicator if active */}
      {loopRange && (
        <div className="flex items-center justify-between px-3 py-1.5 rounded-xl bg-brand-500/15 border border-brand-500/30 text-xs text-brand-300 font-semibold animate-fadeIn">
          <span className="flex items-center gap-1.5">
            <Repeat className="h-3.5 w-3.5 text-brand-400 animate-spin" style={{ animationDuration: '4s' }} />
            <span>Looping Segment: <strong className="font-mono text-white">{formatTime(loopRange.start)} - {formatTime(loopRange.end)}</strong></span>
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
        <span className="text-xs font-mono text-surface-400 min-w-[42px] text-right font-bold">
          {formatTime(currentTime)}
        </span>
        <div className="relative w-full flex items-center">
          <input
            type="range"
            min="0"
            max={duration || 100}
            step="0.1"
            value={currentTime}
            onChange={handleScrubberChange}
            className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-surface-800 accent-brand-500 light:bg-surface-200"
          />
          {/* Highlight loop segment on scrubber if active */}
          {loopRange && duration > 0 && (
            <div
              className="absolute h-2 bg-brand-400/40 rounded pointer-events-none"
              style={{
                left: `${(loopRange.start / duration) * 100}%`,
                width: `${Math.max(1, ((loopRange.end - loopRange.start) / duration) * 100)}%`,
              }}
            />
          )}
        </div>
        <span className="text-xs font-mono text-surface-400 min-w-[42px] font-bold">
          {formatTime(duration)}
        </span>
      </div>

      {/* Controls row */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
        {/* Playback rate */}
        <div className="flex items-center gap-1 bg-surface-950/60 p-1 rounded-xl border border-surface-800/80">
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

        {/* Play/Pause & Seeks */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => seekRelative(-5)}
            className="rounded-xl p-2.5 text-surface-300 hover:bg-surface-800 hover:text-white bg-surface-950/60 border border-surface-800/80 transition-colors flex items-center gap-1 text-xs font-mono"
            title="Rewind 5s (Alt+Left)"
          >
            <RotateCcw className="h-4 w-4" />
            <span>-5s</span>
          </button>

          <button
            onClick={togglePlay}
            className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-600 text-white shadow-lg shadow-brand-500/30 hover:bg-brand-500 transition-all active:scale-95"
            title={isPlaying ? "Pause (Space / Alt+Space)" : "Play (Space / Alt+Space)"}
          >
            {isPlaying ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5 ml-0.5" />}
          </button>

          <button
            onClick={() => seekRelative(5)}
            className="rounded-xl p-2.5 text-surface-300 hover:bg-surface-800 hover:text-white bg-surface-950/60 border border-surface-800/80 transition-colors flex items-center gap-1 text-xs font-mono"
            title="Forward 5s (Alt+Right)"
          >
            <span>+5s</span>
            <RotateCw className="h-4 w-4" />
          </button>
        </div>

        {/* Volume */}
        <div className="flex items-center gap-2 bg-surface-950/60 p-2 rounded-xl border border-surface-800/80">
          <button
            onClick={toggleMute}
            className="text-surface-400 hover:text-white transition-colors"
          >
            {isMuted || volume === 0 ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
          </button>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={isMuted ? 0 : volume}
            onChange={handleVolumeChange}
            className="h-1.5 w-16 cursor-pointer appearance-none rounded-lg bg-surface-800 accent-brand-500"
          />
        </div>
      </div>
    </div>
  );
});
