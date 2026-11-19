import React from 'react';
import { useI18n } from '../context/I18nContext';
import { useTheme } from '../context/ThemeContext';
import { HardwareInfo } from '../types';
import {
  FileAudio,
  Languages,
  Moon,
  Sun,
  LayoutDashboard,
  Mic,
  Repeat,
  History as HistoryIcon,
  Settings as SettingsIcon,
  BarChart3,
  Cpu,
  Zap,
} from 'lucide-react';

interface NavbarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  hardware: HardwareInfo | null;
}

export const Navbar: React.FC<NavbarProps> = ({ activeTab, setActiveTab, hardware }) => {
  const { t, language, setLanguage, isRTL } = useI18n();
  const { theme, toggleTheme } = useTheme();

  const navItems = [
    { id: 'dashboard', label: t.navDashboard, icon: LayoutDashboard },
    { id: 'transcription', label: t.navTranscription, icon: Mic },
    { id: 'benchmark', label: language === 'ar' ? 'المقارنة والدقة' : 'Benchmark', icon: BarChart3 },
    { id: 'converter', label: t.navConverter, icon: Repeat },
    { id: 'history', label: t.navHistory, icon: HistoryIcon },
    { id: 'settings', label: t.navSettings, icon: SettingsIcon },
  ];

  return (
    <header className="sticky top-0 z-40 w-full border-b border-surface-800 bg-surface-950/80 backdrop-blur-md dark:border-surface-800 dark:bg-surface-950/80 light:border-surface-200 light:bg-white/90">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Brand */}
        <div
          onClick={() => setActiveTab('dashboard')}
          className="flex cursor-pointer items-center gap-3 transition-opacity hover:opacity-90"
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-brand-600 to-indigo-500 text-white shadow-lg shadow-brand-500/20">
            <FileAudio className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold tracking-tight text-white light:text-surface-900">
                {t.appName}
              </span>
              <span className="rounded-full bg-brand-500/10 px-2 py-0.5 text-[10px] font-semibold text-brand-400 border border-brand-500/20">
                PRO
              </span>
            </div>
            <p className="text-xs text-surface-400 hidden sm:block">
              {t.tagline}
            </p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="hidden md:flex items-center gap-1 rounded-xl bg-surface-900/60 p-1 border border-surface-800 light:bg-surface-100 light:border-surface-200">
          {navItems.map(item => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all ${
                  isActive
                    ? 'bg-brand-600 text-white shadow-sm shadow-brand-600/30'
                    : 'text-surface-400 hover:text-white hover:bg-surface-800/50 light:text-surface-600 light:hover:text-surface-900 light:hover:bg-surface-200'
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Right actions: Hardware Pill, Language, Theme */}
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Hardware status badge */}
          {hardware && (
            <div className="hidden lg:flex items-center gap-1.5 rounded-lg border border-surface-800 bg-surface-900/50 px-2.5 py-1 text-xs text-surface-300 light:border-surface-200 light:bg-surface-100 light:text-surface-700">
              {hardware.cuda_available ? (
                <>
                  <Zap className="h-3.5 w-3.5 text-amber-400 fill-amber-400" />
                  <span className="truncate max-w-[130px] font-medium">{hardware.gpu_name}</span>
                </>
              ) : (
                <>
                  <Cpu className="h-3.5 w-3.5 text-blue-400" />
                  <span>CPU Safe Mode</span>
                </>
              )}
            </div>
          )}

          {/* Language Switcher */}
          <button
            onClick={() => setLanguage(language === 'en' ? 'ar' : 'en')}
            className="flex items-center gap-1 rounded-lg border border-surface-800 bg-surface-900/50 px-2.5 py-1.5 text-xs font-semibold text-surface-200 hover:border-surface-700 light:border-surface-200 light:bg-surface-100 light:text-surface-800 transition-colors"
            title="Toggle Language / تبديل اللغة"
          >
            <Languages className="h-3.5 w-3.5 text-brand-400" />
            <span>{language === 'en' ? 'العربية' : 'English'}</span>
          </button>

          {/* Theme Toggle */}
          <button
            onClick={toggleTheme}
            className="rounded-lg border border-surface-800 bg-surface-900/50 p-2 text-surface-300 hover:border-surface-700 hover:text-white light:border-surface-200 light:bg-surface-100 light:text-surface-700 light:hover:text-surface-900 transition-colors"
            title="Toggle Theme"
          >
            {theme === 'dark' ? <Sun className="h-4 w-4 text-amber-400" /> : <Moon className="h-4 w-4 text-indigo-600" />}
          </button>
        </div>
      </div>

      {/* Mobile navigation row */}
      <div className="flex md:hidden border-t border-surface-800 px-2 py-1.5 justify-around bg-surface-950 light:border-surface-200 light:bg-surface-50">
        {navItems.map(item => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`flex flex-col items-center gap-1 p-2 rounded-lg text-xs font-medium transition-all ${
                isActive ? 'text-brand-400' : 'text-surface-400 light:text-surface-600'
              }`}
            >
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>
    </header>
  );
};
