import React, { useRef, useState, useEffect, forwardRef, useImperativeHandle } from 'react';
import { Play, Pause, RotateCcw, RotateCw, Volume2, VolumeX } from 'lucide-react';
import { useI18n } from '../context/I18nContext';

export interface AudioPlayerRef {
  seekTo: (timeInSeconds: number) => void;
  play: () => void;
  pause: () => void;
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
      setCurrentTime(audio.currentTime);
      if (onTimeUpdate) {
        onTimeUpdate(audio.currentTime);
      }
    };

    const handleEnded = () => {
      setIsPlaying(false);
    };

    audio.addEventListener('loadedmetadata', handleLoadedMetadata);
    audio.addEventListener('timeupdate', handleTimeUpdate);
    audio.addEventListener('ended', handleEnded);

    return () => {
      audio.removeEventListener('loadedmetadata', handleLoadedMetadata);
      audio.removeEventListener('timeupdate', handleTimeUpdate);
      audio.removeEventListener('ended', handleEnded);
    };
  }, [src, autoPlay, onTimeUpdate]);

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
    <div className={`rounded-xl border border-surface-800 bg-surface-900/90 p-4 shadow-xl backdrop-blur-sm light:border-surface-200 light:bg-white light:shadow-sm ${className}`}>
      <audio ref={audioRef} src={src} preload="metadata" />

      {/* Scrubber timeline */}
      <div className="flex items-center gap-3 mb-3">
        <span className="text-xs font-mono text-surface-400 min-w-[42px] text-right">
          {formatTime(currentTime)}
        </span>
        <input
          type="range"
          min="0"
          max={duration || 100}
          step="0.1"
          value={currentTime}
          onChange={handleScrubberChange}
          className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-surface-800 accent-brand-500 light:bg-surface-200"
        />
        <span className="text-xs font-mono text-surface-400 min-w-[42px]">
          {formatTime(duration)}
        </span>
      </div>

      {/* Controls row */}
      <div className="flex items-center justify-between">
        {/* Playback rate */}
        <div className="flex items-center gap-1">
          {[0.75, 1, 1.25, 1.5, 2].map(rate => (
            <button
              key={rate}
              onClick={() => changePlaybackRate(rate)}
              className={`rounded px-1.5 py-0.5 text-[11px] font-semibold transition-colors ${
                playbackRate === rate
                  ? 'bg-brand-600 text-white'
                  : 'text-surface-400 hover:text-white light:text-surface-600 light:hover:text-surface-900'
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
            className="rounded-lg p-2 text-surface-400 hover:bg-surface-800 hover:text-white light:hover:bg-surface-100 light:text-surface-600 transition-colors"
            title="Rewind 5s"
          >
            <RotateCcw className="h-4 w-4" />
          </button>

          <button
            onClick={togglePlay}
            className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-600 text-white shadow-md shadow-brand-500/25 hover:bg-brand-500 transition-all active:scale-95"
            title={isPlaying ? "Pause" : "Play"}
          >
            {isPlaying ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5 ml-0.5" />}
          </button>

          <button
            onClick={() => seekRelative(5)}
            className="rounded-lg p-2 text-surface-400 hover:bg-surface-800 hover:text-white light:hover:bg-surface-100 light:text-surface-600 transition-colors"
            title="Forward 5s"
          >
            <RotateCw className="h-4 w-4" />
          </button>
        </div>

        {/* Volume */}
        <div className="flex items-center gap-2">
          <button
            onClick={toggleMute}
            className="text-surface-400 hover:text-white light:text-surface-600 transition-colors"
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
            className="h-1.5 w-16 cursor-pointer appearance-none rounded-lg bg-surface-800 accent-brand-500 light:bg-surface-200"
          />
        </div>
      </div>
    </div>
  );
});
