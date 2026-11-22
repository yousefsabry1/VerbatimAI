import React, { createContext, useContext, useState, useEffect } from 'react';

export type Language = 'en' | 'ar';

export interface Translations {
  appName: string;
  tagline: string;
  // Nav
  navDashboard: string;
  navTranscription: string;
  navConverter: string;
  navHistory: string;
  navSettings: string;
  // Dashboard
  welcomeTitle: string;
  welcomeSubtitle: string;
  quickActionTranscribe: string;
  quickActionTranscribeDesc: string;
  quickActionConvert: string;
  quickActionConvertDesc: string;
  systemStatusTitle: string;
  deviceLabel: string;
  cudaStatus: string;
  cpuStatus: string;
  modelsReady: string;
  recentActivityTitle: string;
  noRecentActivity: string;
  viewAllHistory: string;
  quickGuideTitle: string;
  quickGuideStep1: string;
  quickGuideStep2: string;
  quickGuideStep3: string;
  // Transcription
  transcriptionTitle: string;
  transcriptionSubtitle: string;
  uploadAreaTitle: string;
  uploadAreaSubtitle: string;
  dropAudioHere: string;
  browseFiles: string;
  supportedFormatsNotice: string;
  modelSelectionLabel: string;
  languageSelectionLabel: string;
  languageAuto: string;
  languageArabic: string;
  languageEnglish: string;
  modeLabel: string;
  presetSelectionLabel: string;
  presetFastTitle: string;
  presetFastDesc: string;
  presetFastBadge: string;
  presetMaxAccuracyTitle: string;
  presetMaxAccuracyDesc: string;
  presetMaxAccuracyBadge: string;
  presetCustomTitle: string;
  presetDisclaimer: string;
  modelStatusDownloaded: string;
  modelStatusDownloadNeeded: string;
  downloadNowBtn: string;
  downloadingStatus: string;
  modeStrictVerbatim: string;
  modeStrictVerbatimDesc: string;
  modeClean: string;
  modeCleanDesc: string;
  accuracyModeLabel: string;
  accuracyBalanced: string;
  accuracyMaximum: string;
  audioEnhancementLabel: string;
  audioEnhancementDesc: string;
  vadLabel: string;
  vadDesc: string;
  advancedSettings: string;
  deviceModeLabel: string;
  deviceAuto: string;
  deviceCuda: string;
  deviceCpu: string;
  startTranscriptionBtn: string;
  processingTitle: string;
  cancelBtn: string;
  saveEditsBtn: string;
  copyTranscriptBtn: string;
  copiedToast: string;
  exportBtn: string;
  tabSegments: string;
  tabCleanText: string;
  uncertainBadge: string;
  seekToSpeech: string;
  playbackSpeed: string;
  originalVsEdited: string;
  editedVersion: string;
  originalVersion: string;
  // Audio Converter
  converterTitle: string;
  converterSubtitle: string;
  targetFormatLabel: string;
  presetLabel: string;
  presetSmaller: string;
  presetSmallerDesc: string;
  presetBalanced: string;
  presetBalancedDesc: string;
  presetHigh: string;
  presetHighDesc: string;
  presetCustom: string;
  presetCustomDesc: string;
  bitrateLabel: string;
  sampleRateLabel: string;
  channelsLabel: string;
  channelMono: string;
  channelStereo: string;
  convertAudioBtn: string;
  convertingStatus: string;
  beforeAfterTitle: string;
  originalAudio: string;
  convertedAudio: string;
  sizeReduction: string;
  downloadConvertedBtn: string;
  batchQueueTitle: string;
  downloadAllZipBtn: string;
  addMoreFilesBtn: string;
  // History
  historyTitle: string;
  historySubtitle: string;
  clearHistoryBtn: string;
  confirmClearHistory: string;
  filterAll: string;
  filterTranscription: string;
  filterConversion: string;
  colFile: string;
  colType: string;
  colDuration: string;
  colModel: string;
  colStatus: string;
  colDate: string;
  colActions: string;
  reopenBtn: string;
  downloadBtn: string;
  deleteBtn: string;
  // Settings
  settingsTitle: string;
  settingsSubtitle: string;
  hardwareSectionTitle: string;
  gpuLabel: string;
  vramLabel: string;
  driverLabel: string;
  cpuCoresLabel: string;
  modelsSectionTitle: string;
  modelSizeLabel: string;
  downloadModelBtn: string;
  downloadingModelBtn: string;
  deleteModelBtn: string;
  appearanceSectionTitle: string;
  themeLabel: string;
  themeDark: string;
  themeLight: string;
  interfaceLanguageLabel: string;
  storageSectionTitle: string;
  storageDescription: string;
  clearTempFilesBtn: string;
  // Common
  loading: string;
  error: string;
  success: string;
  close: string;
  duration: string;
  fileSize: string;
}

const translations: Record<Language, Translations> = {
  en: {
    appName: "Verbatim AI",
    tagline: "Every Word Matters.",
    navDashboard: "Dashboard",
    navTranscription: "Transcription",
    navConverter: "Audio Converter",
    navHistory: "History",
    navSettings: "Settings",
    welcomeTitle: "Local AI Audio Studio",
    welcomeSubtitle: "High-accuracy local Whisper transcription and zero-cloud audio conversion.",
    quickActionTranscribe: "New Transcription",
    quickActionTranscribeDesc: "Transcribe WhatsApp voice notes, lectures, and meetings with verbatim precision.",
    quickActionConvert: "Convert Audio",
    quickActionConvertDesc: "Convert between MP3, WAV, OGG, Opus, FLAC, and M4A locally with FFmpeg.",
    systemStatusTitle: "System & AI Readiness",
    deviceLabel: "Active Processor",
    cudaStatus: "NVIDIA CUDA Hardware Acceleration Ready",
    cpuStatus: "CPU Processing Safe Mode",
    modelsReady: "Downloaded Models Ready",
    recentActivityTitle: "Recent Jobs",
    noRecentActivity: "No jobs processed yet. Drop an audio file to get started.",
    viewAllHistory: "View All History",
    quickGuideTitle: "How It Works",
    quickGuideStep1: "1. Drop any audio or video file (WhatsApp OGG, MP3, WAV, MP4, etc.).",
    quickGuideStep2: "2. Select your language and model (Egyptian Arabic & English optimized).",
    quickGuideStep3: "3. Review the synchronized transcript, click timestamps to listen, and export.",
    transcriptionTitle: "AI Transcription Workspace",
    transcriptionSubtitle: "Extract every word, repetition, and hesitation with millisecond-accurate timestamps.",
    uploadAreaTitle: "Drop your audio recording here",
    uploadAreaSubtitle: "or click to browse from your computer",
    dropAudioHere: "Release file to upload",
    browseFiles: "Browse Files",
    supportedFormatsNotice: "Supports OGG (WhatsApp), Opus, MP3, WAV, M4A, AAC, FLAC, and MP4 video extraction",
    modelSelectionLabel: "AI Whisper Model",
    languageSelectionLabel: "Spoken Language",
    languageAuto: "Auto Detection (Recommended)",
    languageArabic: "Arabic (Egyptian & Dialects)",
    languageEnglish: "English",
    modeLabel: "Transcription Fidelity",
    presetSelectionLabel: "Transcription Mode Presets",
    presetFastTitle: "Fast Transcription",
    presetFastDesc: "Optimized for speed using Egyptian Arabic & English Specialized Whisper. Accuracy may vary, particularly with challenging audio or noise.",
    presetFastBadge: "Fast & Lightweight (~0.04x RTF)",
    presetMaxAccuracyTitle: "Maximum Accuracy — Experimental",
    presetMaxAccuracyDesc: "Prioritizes verbatim accuracy using Hybrid ASR V3 multi-model consensus (Specialized + Turbo + QwenCleo). May require more processing time. Experimental architecture.",
    presetMaxAccuracyBadge: "Multi-Model Consensus (~30.4% Benchmark WER)",
    presetCustomTitle: "Custom Model (Advanced)",
    presetDisclaimer: "Notice: No speech recognition system is universally accurate or error-free. Fast mode optimizes turnaround speed, while Maximum Accuracy applies multi-model consensus to minimize errors. Please review and edit transcripts before publishing.",
    modelStatusDownloaded: "Model Ready (Local)",
    modelStatusDownloadNeeded: "Download Required",
    downloadNowBtn: "Download Model",
    downloadingStatus: "Downloading...",
    modeStrictVerbatim: "Strict Verbatim",
    modeStrictVerbatimDesc: "Preserves filler words, hesitations, informal Egyptian expressions, and mixed English terms.",
    modeClean: "Clean Transcript",
    modeCleanDesc: "Polished paragraphs with clean punctuation while keeping audio segments intact.",
    accuracyModeLabel: "Accuracy Pipeline",
    accuracyBalanced: "Balanced (Fast & Reliable)",
    accuracyMaximum: "Maximum Accuracy (Deep Verification)",
    audioEnhancementLabel: "Gentle Audio Normalization",
    audioEnhancementDesc: "Balances quiet speakers without distorting soft consonants.",
    vadLabel: "Voice Activity Filter (VAD)",
    vadDesc: "Skips long silent intervals and improves segment boundaries.",
    advancedSettings: "Advanced Pipeline Settings",
    deviceModeLabel: "Processing Device",
    deviceAuto: "Auto: GPU CUDA with CPU Fallback",
    deviceCuda: "GPU CUDA Only",
    deviceCpu: "CPU Only Safe Mode",
    startTranscriptionBtn: "Start Transcription",
    processingTitle: "AI Processing in Progress...",
    cancelBtn: "Cancel Processing",
    saveEditsBtn: "Save Edits",
    copyTranscriptBtn: "Copy Text",
    copiedToast: "Transcript copied to clipboard!",
    exportBtn: "Export Transcript",
    tabSegments: "Timestamped Segments",
    tabCleanText: "Full Clean Text",
    uncertainBadge: "Uncertain Segment",
    seekToSpeech: "Click timestamp to jump audio",
    playbackSpeed: "Speed",
    originalVsEdited: "Version",
    editedVersion: "Edited Version",
    originalVersion: "Original AI Output",
    converterTitle: "Local Audio Converter",
    converterSubtitle: "Fast, genuine FFmpeg format conversion without cloud uploads or size limits.",
    targetFormatLabel: "Target Format",
    presetLabel: "Quality Preset",
    presetSmaller: "Smaller File",
    presetSmallerDesc: "Higher compression, optimized for voice notes & sharing",
    presetBalanced: "Balanced (Recommended)",
    presetBalancedDesc: "Optimal balance between audio fidelity and file size",
    presetHigh: "High Quality",
    presetHighDesc: "Maximum bitrate / lossless audio preservation",
    presetCustom: "Custom Settings",
    presetCustomDesc: "Configure custom bitrate, sample rate, and channels",
    bitrateLabel: "Bitrate",
    sampleRateLabel: "Sample Rate",
    channelsLabel: "Audio Channels",
    channelMono: "Mono (1 Channel)",
    channelStereo: "Stereo (2 Channels)",
    convertAudioBtn: "Convert Audio",
    convertingStatus: "Converting Audio with FFmpeg...",
    beforeAfterTitle: "Audio Preview & Comparison",
    originalAudio: "Original File",
    convertedAudio: "Converted Output",
    sizeReduction: "Storage Savings",
    downloadConvertedBtn: "Download Converted File",
    batchQueueTitle: "Batch Conversion Queue",
    downloadAllZipBtn: "Download All as ZIP",
    addMoreFilesBtn: "Add More Files",
    historyTitle: "Processing History",
    historySubtitle: "Local database of your past transcriptions and audio conversions.",
    clearHistoryBtn: "Clear All History",
    confirmClearHistory: "Are you sure you want to delete all history entries and generated files?",
    filterAll: "All Jobs",
    filterTranscription: "Transcriptions",
    filterConversion: "Conversions",
    colFile: "File Name",
    colType: "Type",
    colDuration: "Duration",
    colModel: "Model / Format",
    colStatus: "Status",
    colDate: "Created",
    colActions: "Actions",
    reopenBtn: "Open in Editor",
    downloadBtn: "Download",
    deleteBtn: "Delete",
    settingsTitle: "Application Settings",
    settingsSubtitle: "Hardware diagnostics, local AI models, and preferences.",
    hardwareSectionTitle: "Hardware Acceleration Diagnostics",
    gpuLabel: "Graphics Card (GPU)",
    vramLabel: "Video Memory (VRAM)",
    driverLabel: "NVIDIA Driver",
    cpuCoresLabel: "CPU Cores",
    modelsSectionTitle: "Local AI Models Manager",
    modelSizeLabel: "Disk Size",
    downloadModelBtn: "Download Model",
    downloadingModelBtn: "Downloading...",
    deleteModelBtn: "Delete from Disk",
    appearanceSectionTitle: "Appearance & Language",
    themeLabel: "Theme Mode",
    themeDark: "Dark Mode",
    themeLight: "Light Mode",
    interfaceLanguageLabel: "Interface Language",
    storageSectionTitle: "Local Storage & Data",
    storageDescription: "All files remain on your local machine. No telemetry or external cloud storage is used.",
    clearTempFilesBtn: "Clear Temporary Cache",
    loading: "Loading...",
    error: "Error",
    success: "Success",
    close: "Close",
    duration: "Duration",
    fileSize: "File Size",
  },
  ar: {
    appName: "فيرباتم للذكاء الاصطناعي",
    tagline: "كل كلمة لها قيمتها.",
    navDashboard: "لوحة التحكم",
    navTranscription: "التفريغ الصوتي",
    navConverter: "محول الصوتيات",
    navHistory: "السجل",
    navSettings: "الإعدادات",
    welcomeTitle: "استوديو الصوتيات المحلي بالذكاء الاصطناعي",
    welcomeSubtitle: "تفريغ صوتي محلي فائق الدقة بنموذج ويسبر وتحويل فوري للصوتيات بدون أي رفع للسحاب.",
    quickActionTranscribe: "تفريغ صوتي جديد",
    quickActionTranscribeDesc: "تفريغ تسجيلات واتساب، المحاضرات، والاجتماعات بدقة حرفية متناهية.",
    quickActionConvert: "تحويل ملف صوتي",
    quickActionConvertDesc: "تحويل فوري بين MP3, WAV, OGG, Opus, FLAC, M4A محلياً عبر FFmpeg.",
    systemStatusTitle: "حالة النظام وجاهزية الذكاء الاصطناعي",
    deviceLabel: "المعالج النشط",
    cudaStatus: "تسريع العتاد NVIDIA CUDA جاهز للعمل",
    cpuStatus: "وضع الأمان للمعالجة عبر المعالج المركزي (CPU)",
    modelsReady: "النماذج الجاهزة على الجهاز",
    recentActivityTitle: "العمليات الأخيرة",
    noRecentActivity: "لا توجد عمليات سابقة بعد. اسحب ملف صوتي للبدء فوراً.",
    viewAllHistory: "عرض السجل بالكامل",
    quickGuideTitle: "كيف يعمل التطبيق",
    quickGuideStep1: "1. اسحب أي تسجيل صوتي أو فيديو (رسائل واتساب OGG, MP3, WAV, إلخ).",
    quickGuideStep2: "2. حدد اللغة والنموذج (محسّن للمصطلحات الإنجليزية والعامية المصرية).",
    quickGuideStep3: "3. استعرض النص المتزامن، اضغط على التوقيت للاستماع، وقم بالتصدير.",
    transcriptionTitle: "مساحة التفريغ الصوتي الذكي",
    transcriptionSubtitle: "التقاط كل كلمة وتكرار وتردد مع توقيتات زمنية دقيقة بالمللي ثانية.",
    uploadAreaTitle: "اسحب وأفلت التسجيل الصوتي هنا",
    uploadAreaSubtitle: "أو اضغط لاختيار ملف من جهازك",
    dropAudioHere: "أفلت الملف للرفع",
    browseFiles: "تصفح الملفات",
    supportedFormatsNotice: "يدعم تسجيلات واتساب OGG, Opus, MP3, WAV, M4A, AAC, FLAC، واستخراج الصوت من MP4",
    modelSelectionLabel: "نموذج الذكاء الاصطناعي (ويدسبر)",
    languageSelectionLabel: "لغة التسجيل",
    languageAuto: "اكتشاف تلقائي للغة (مستحسن)",
    languageArabic: "العربية (المصرية واللهجات)",
    languageEnglish: "الإنجليزية",
    modeLabel: "طبيعة التفريغ النصي",
    presetSelectionLabel: "أوضاع التفريغ الصوتي الموصى بها",
    presetFastTitle: "تفريغ سريع (Fast Transcription)",
    presetFastDesc: "محسّن لتحقيق أقصى سرعة باستخدام ويسبر المخصص للعامية والمصطلحات. قد تتفاوت الدقة في التسجيلات ذات الضوضاء العالية أو اللهجات المعقدة.",
    presetFastBadge: "سريع وخفيف (~0.04x RTF)",
    presetMaxAccuracyTitle: "أقصى دقة — تجريبي (Maximum Accuracy)",
    presetMaxAccuracyDesc: "يعطي الأولوية القصوى للدقة الحرفية عبر دمج ثلاثة نماذج متزامنة (Hybrid V3: Specialized + Turbo + QwenCleo). قد يستغرق وقتاً أطول. معمارية تجريبية.",
    presetMaxAccuracyBadge: "توافق النماذج المتعددة (30.4% معدل خطأ قياسي)",
    presetCustomTitle: "نموذج مخصص (إعدادات متقدمة)",
    presetDisclaimer: "تنبيه: لا يوجد نظام تفريغ صوتي آلي دقيق أو خالٍ من الأخطاء بشكل مطلق. يوفر الوضع السريع سرعة إنجاز فائقة، بينما يطبق وضع أقصى دقة تصويتاً ثلاثياً لتقليل الهلاوس. يُرجى دائماً مراجعة النص وتدقيقه.",
    modelStatusDownloaded: "النموذج جاهز محلياً",
    modelStatusDownloadNeeded: "يتطلب تنزيل النموذج",
    downloadNowBtn: "تنزيل النموذج الآن",
    downloadingStatus: "جاري التنزيل...",
    modeStrictVerbatim: "تفريغ حرفي دقيق (Strict Verbatim)",
    modeStrictVerbatimDesc: "يحافظ على كلمات الحشو، التردد، العبارات المصرية، والمصطلحات التقنية الإنجليزية.",
    modeClean: "نص منقح ومقروء (Clean Transcript)",
    modeCleanDesc: "فقرات منسقة بعلامات ترقيم أنيقة مع الاحتفاظ بتوقيت المقاطع الأصلية.",
    accuracyModeLabel: "مسار الدقة",
    accuracyBalanced: "متوازن (سريع وموثوق)",
    accuracyMaximum: "أقصى دقة (تحقق متقدم وفحص الشك)",
    audioEnhancementLabel: "تنقية وموازنة ديناميكية للصوت",
    audioEnhancementDesc: "موازنة الأصوات الخافتة دون تشويه مخارج الحروف الهامسة.",
    vadLabel: "فلتر كشف النشاط الصوتي (VAD)",
    vadDesc: "تخطي فترات الصمت الطويلة وتحديد حدود الجمل بدقة.",
    advancedSettings: "إعدادات المعالجة المتقدمة",
    deviceModeLabel: "معالج التشغيل",
    deviceAuto: "تلقائي: تجربة كارت الشاشة GPU مع الرجوع التلقائي للـ CPU",
    deviceCuda: "كارت الشاشة NVIDIA CUDA فقط",
    deviceCpu: "المعالج المركزي CPU فقط (الوضع الآمن)",
    startTranscriptionBtn: "بدء التفريغ الصوتي",
    processingTitle: "جارٍ التفريغ بالذكاء الاصطناعي...",
    cancelBtn: "إلغاء المعالجة",
    saveEditsBtn: "حفظ التعديلات",
    copyTranscriptBtn: "نسخ النص",
    copiedToast: "تم نسخ النص إلى الحافظة بنجاح!",
    exportBtn: "تصدير النص",
    tabSegments: "المقاطع الزمنية بالتوقيت",
    tabCleanText: "النص الكامل المنقح",
    uncertainBadge: "مقطع غير مؤكد",
    seekToSpeech: "اضغط على التوقيت للقفز في الصوت",
    playbackSpeed: "السرعة",
    originalVsEdited: "النسخة",
    editedVersion: "النسخة المعدلة",
    originalVersion: "مخرج الذكاء الاصطناعي الأصلي",
    converterTitle: "محول الصوتيات المحلي",
    converterSubtitle: "تحويل فوري وسريع بين الصيغ عبر FFmpeg دون رفع ملفاتك وبدون حدود للحجم.",
    targetFormatLabel: "الصيغة المطلوبة",
    presetLabel: "نمط الجودة",
    presetSmaller: "ملف أصغر حجماً",
    presetSmallerDesc: "ضغط أعلى، مناسب للمشاركة والرسائل الصوتية",
    presetBalanced: "متوازن (مستحسن)",
    presetBalancedDesc: "توازن مثالي بين جودة الصوت وحجم الملف",
    presetHigh: "أعلى جودة",
    presetHighDesc: "أعلى معدل بت / حفظ الصوت بجودة أصلية",
    presetCustom: "إعدادات مخصصة",
    presetCustomDesc: "تحديد معدل البت، التردد، والقنوات يدوياً",
    bitrateLabel: "معدل البت",
    sampleRateLabel: "معدل العينات (Hz)",
    channelsLabel: "قنوات الصوت",
    channelMono: "أحادي (Mono)",
    channelStereo: "ستيريو (Stereo)",
    convertAudioBtn: "تحويل الملف الصوتي",
    convertingStatus: "جارٍ التحويل باستخدام FFmpeg...",
    beforeAfterTitle: "المعاينة والمقارنة الصوتية",
    originalAudio: "الملف الأصلي",
    convertedAudio: "الملف المحول",
    sizeReduction: "نسبة توفير المساحة",
    downloadConvertedBtn: "تحميل الملف المحول",
    batchQueueTitle: "طابور التحويل الجماعي",
    downloadAllZipBtn: "تحميل الكل في ملف ZIP",
    addMoreFilesBtn: "إضافة ملفات أخرى",
    historyTitle: "سجل العمليات",
    historySubtitle: "قاعدة بيانات محلية لجميع عمليات التفريغ وتحويل الصوت السابقة.",
    clearHistoryBtn: "مسح السجل بالكامل",
    confirmClearHistory: "هل أنت متأكد من مسح جميع عناصر السجل والملفات المنشأة؟",
    filterAll: "الكل",
    filterTranscription: "التفريغ الصوتي",
    filterConversion: "تحويل الصوتيات",
    colFile: "اسم الملف",
    colType: "النوع",
    colDuration: "المدة",
    colModel: "النموذج / الصيغة",
    colStatus: "الحالة",
    colDate: "التاريخ",
    colActions: "الإجراءات",
    reopenBtn: "فتح في المحرر",
    downloadBtn: "تحميل",
    deleteBtn: "حذف",
    settingsTitle: "إعدادات التطبيق",
    settingsSubtitle: "فحص العتاد، نماذج الذكاء الاصطناعي المحلية، والتفضيلات.",
    hardwareSectionTitle: "تشخيص تسريع العتاد (Hardware)",
    gpuLabel: "كارت الشاشة (GPU)",
    vramLabel: "ذاكرة الفيديو (VRAM)",
    driverLabel: "تعريف كارت الشاشة",
    cpuCoresLabel: "أنوية المعالج (CPU Cores)",
    modelsSectionTitle: "إدارة نماذج الذكاء الاصطناعي المحلية",
    modelSizeLabel: "الحجم على القرص",
    downloadModelBtn: "تحميل النموذج",
    downloadingModelBtn: "جارٍ التحميل...",
    deleteModelBtn: "حذف من القرص",
    appearanceSectionTitle: "المظهر واللغة",
    themeLabel: "وضع المظهر",
    themeDark: "الوضع الداكن",
    themeLight: "الوضع الفاتح",
    interfaceLanguageLabel: "لغة الواجهة",
    storageSectionTitle: "التخزين والخصوصية المحلية",
    storageDescription: "جميع بياناتك وملفاتك الصوتية تبقى على جهازك بالكامل ولا يتم إرسال أي بيانات خارجياً.",
    clearTempFilesBtn: "مسح الملفات المؤقتة",
    loading: "جارٍ التحميل...",
    error: "خطأ",
    success: "تم بنجاح",
    close: "إغلاق",
    duration: "المدة",
    fileSize: "حجم الملف",
  }
};

interface I18nContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: Translations;
  isRTL: boolean;
}

const I18nContext = createContext<I18nContextType | null>(null);

export const I18nProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [language, setLanguageState] = useState<Language>(() => {
    return (localStorage.getItem('verbatim_lang') as Language) || 'en';
  });

  const setLanguage = (lang: Language) => {
    setLanguageState(lang);
    localStorage.setItem('verbatim_lang', lang);
  };

  useEffect(() => {
    const isRtl = language === 'ar';
    document.documentElement.dir = isRtl ? 'rtl' : 'ltr';
    document.documentElement.lang = language;
  }, [language]);

  const value = {
    language,
    setLanguage,
    t: translations[language],
    isRTL: language === 'ar',
  };

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
};

export const useI18n = () => {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n must be used within I18nProvider');
  return ctx;
};
