import React, { useState, useEffect } from 'react';
import { I18nProvider, useI18n } from './context/I18nContext';
import { ThemeProvider } from './context/ThemeContext';
import { Navbar } from './components/Navbar';
import { Dashboard } from './pages/Dashboard';
import { Transcription } from './pages/Transcription';
import { AudioConverter } from './pages/AudioConverter';
import { History } from './pages/History';
import { Settings } from './pages/Settings';
import { Benchmark } from './pages/Benchmark';
import type { HardwareInfo } from './types';
import { api } from './services/api';
import { ShieldCheck } from 'lucide-react';

const AppContent: React.FC = () => {
  // Initialize state from URL query parameters or localStorage for refresh recovery
  const getInitialState = () => {
    try {
      const params = new URLSearchParams(window.location.search);
      const tabFromUrl = params.get('tab');
      const jobFromUrl = params.get('job_id');
      const storedTab = localStorage.getItem('verbatim_active_tab');
      const storedJobId = localStorage.getItem('verbatim_active_job_id');

      const initialJob = jobFromUrl || storedJobId || null;
      let initialTab = tabFromUrl || (initialJob ? 'transcription' : storedTab) || 'dashboard';
      if (!['dashboard', 'transcription', 'benchmark', 'converter', 'history', 'settings'].includes(initialTab)) {
        initialTab = 'dashboard';
      }

      return { initialTab, initialJob };
    } catch {
      return { initialTab: 'dashboard', initialJob: null };
    }
  };

  const { initialTab, initialJob } = getInitialState();
  const [activeTab, setActiveTab] = useState<string>(initialTab);
  const [hardware, setHardware] = useState<HardwareInfo | null>(null);
  const [selectedReviewJobId, setSelectedReviewJobId] = useState<string | null>(initialJob);

  useEffect(() => {
    api.getHardware().then(setHardware).catch(console.error);
  }, []);

  // Keep URL parameters and localStorage synchronized for seamless browser refresh
  useEffect(() => {
    try {
      localStorage.setItem('verbatim_active_tab', activeTab);
      const url = new URL(window.location.href);
      url.searchParams.set('tab', activeTab);

      if (activeTab === 'transcription' && selectedReviewJobId) {
        url.searchParams.set('job_id', selectedReviewJobId);
        localStorage.setItem('verbatim_active_job_id', selectedReviewJobId);
      } else if (activeTab !== 'transcription') {
        url.searchParams.delete('job_id');
      }

      window.history.replaceState({}, '', url.toString());
    } catch (e) {
      console.warn('URL sync failed:', e);
    }
  }, [activeTab, selectedReviewJobId]);

  const handleSelectJobForReview = (jobId: string) => {
    setSelectedReviewJobId(jobId);
    setActiveTab('transcription');
    try {
      localStorage.setItem('verbatim_active_job_id', jobId);
      localStorage.setItem('verbatim_active_tab', 'transcription');
    } catch {}
  };

  const handleJobCleared = () => {
    setSelectedReviewJobId(null);
    try {
      localStorage.removeItem('verbatim_active_job_id');
      const url = new URL(window.location.href);
      url.searchParams.delete('job_id');
      window.history.replaceState({}, '', url.toString());
    } catch {}
  };

  return (
    <div className="min-h-screen flex flex-col bg-surface-950 text-surface-100 light:bg-surface-50 light:text-surface-900 transition-colors duration-200">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        hardware={hardware}
      />

      <main className="flex-1 mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'dashboard' && (
          <Dashboard
            setActiveTab={setActiveTab}
            hardware={hardware}
            onSelectJobForReview={handleSelectJobForReview}
          />
        )}

        {activeTab === 'transcription' && (
          <Transcription
            initialJobId={selectedReviewJobId}
            onJobActive={(jobId) => setSelectedReviewJobId(jobId)}
            onClearInitialJob={handleJobCleared}
            hardware={hardware}
          />
        )}

        {activeTab === 'benchmark' && <Benchmark hardware={hardware} />}

        {activeTab === 'converter' && <AudioConverter />}

        {activeTab === 'history' && (
          <History onOpenTranscript={handleSelectJobForReview} />
        )}

        {activeTab === 'settings' && <Settings hardware={hardware} />}
      </main>

      {/* Footer */}
      <footer className="border-t border-surface-800 bg-surface-950 py-6 text-xs text-surface-500 light:border-surface-200 light:bg-white">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-bold text-surface-300 light:text-surface-700">Verbatim AI</span>
            <span>—</span>
            <span>Every Word Matters.</span>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5 text-emerald-400">
              <ShieldCheck className="h-4 w-4" />
              <span>100% Local Processing</span>
            </div>
            <span>•</span>
            <span>Open Source MIT</span>
          </div>
        </div>
      </footer>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <ThemeProvider>
      <I18nProvider>
        <AppContent />
      </I18nProvider>
    </ThemeProvider>
  );
};

export default App;
