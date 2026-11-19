import React, { useState, useEffect, useRef } from 'react';
import { Link2, Upload, FileVideo, X, Info, Loader2, ChevronDown, ClipboardPaste, Check, Sparkles, Gamepad2, Mic, GraduationCap, MessageSquare, LayoutTemplate } from 'lucide-react';
import { track } from '../lib/analytics';
import { getApiUrl } from '../config';
import SourceCost from './SourceCost';

const SUPPORTED_PLATFORMS = [
    'YouTube', 'Vimeo', 'TikTok', 'X / Twitter', 'Twitch', 'Kick',
    'Facebook', 'Instagram', 'Dailymotion', 'Reddit', 'Streamable',
];

// Mirrors the server's MIN_SOURCE_SECONDS: shorter sources are rejected with a
// 400 after the whole file was uploaded. Checking the duration in the browser
// says so the moment the file is picked (a 27 s upload used to end in a bare
// "That run failed").
const MIN_SOURCE_SECONDS = 45;

// Duration of a local video file in seconds, or null when the browser cannot
// read it (unsupported codec): then the server stays the judge.
const readVideoDuration = (file) => new Promise((resolve) => {
    try {
        const url = URL.createObjectURL(file);
        const v = document.createElement('video');
        v.preload = 'metadata';
        const done = (d) => { URL.revokeObjectURL(url); resolve(d); };
        v.onloadedmetadata = () => done(Number.isFinite(v.duration) ? v.duration : null);
        v.onerror = () => done(null);
        setTimeout(() => done(null), 8000);
        v.src = url;
    } catch { resolve(null); }
});

const CONTENT_PROFILES = [
    { value: 'auto', label: 'Auto AI', hint: 'Smart detect', Icon: Sparkles },
    { value: 'gaming', label: 'Gameplay', hint: 'GTA, FPS & action', Icon: Gamepad2 },
    { value: 'podcast', label: 'Podcast', hint: 'Talks & interviews', Icon: Mic },
    { value: 'educational', label: 'Explainer', hint: 'Tutorials & coding', Icon: GraduationCap },
    { value: 'commentary', label: 'Vlog / Show', hint: 'Reactions & review', Icon: MessageSquare },
];

export const TEMPLATE_CATEGORIES = [
    { id: 'gaming', label: 'Gaming & Action' },
    { id: 'podcast', label: 'Podcasts & Talks' },
    { id: 'educational', label: 'Education & Code' },
    { id: 'commentary', label: 'Vlogs & Commentary' },
    { id: 'business', label: 'Business & Finance' },
    { id: 'fitness', label: 'Fitness & Sports' },
    { id: 'storytelling', label: 'Story & Cinema' },
    { id: 'travel_food', label: 'Travel & Food' },
    { id: 'music_dance', label: 'Music & Dance' },
    { id: 'news_documentary', label: 'News & Docs' },
];

export const DEFAULT_TEMPLATES = [
    { id: 'streamer_stacked_top', name: 'Streamer Top Cam (Stacked)', category: 'gaming', layout: 'stacked_top_cam', caption_preset: 'impact', duration_range: [15, 60] },
    { id: 'gaming_cinematic', name: 'Gaming Cinematic', category: 'gaming', layout: 'gameplay_center', caption_preset: 'impact', duration_range: [15, 60] },
    { id: 'streamer_reaction', name: 'Streamer Reaction', category: 'gaming', layout: 'gameplay_with_facecam', caption_preset: 'highlight', duration_range: [15, 60] },
    { id: 'gta_story', name: 'GTA Story', category: 'gaming', layout: 'gameplay_center', caption_preset: 'comic', duration_range: [20, 60] },
    { id: 'esports_highlights', name: 'Esports Highlights', category: 'gaming', layout: 'gameplay_center', caption_preset: 'impact', duration_range: [15, 45] },
    { id: 'gaming_fails', name: 'Gaming Fails', category: 'gaming', layout: 'gameplay_center', caption_preset: 'comic', duration_range: [10, 35] },
    { id: 'gaming_meme', name: 'Gaming Meme', category: 'gaming', layout: 'gameplay_center', caption_preset: 'impact', duration_range: [10, 30] },
    { id: 'podcast_split', name: 'Podcast Split Screen', category: 'podcast', layout: 'split_two_speaker', caption_preset: 'highlight', duration_range: [20, 60] },
    { id: 'podcast_cinematic', name: 'Podcast Cinematic', category: 'podcast', layout: 'talking_head_center', caption_preset: 'minimal_serif', duration_range: [30, 90] },
    { id: 'podcast_kinetic', name: 'Podcast Kinetic', category: 'podcast', layout: 'talking_head_center', caption_preset: 'karaoke', duration_range: [15, 45] },
    { id: 'podcast_reaction', name: 'Podcast Reaction', category: 'podcast', layout: 'split_two_speaker', caption_preset: 'highlight', duration_range: [15, 50] },
    { id: 'controversial_opinion', name: 'Controversial Opinion', category: 'podcast', layout: 'talking_head_center', caption_preset: 'impact', duration_range: [15, 45] },
    { id: 'educational_insight', name: 'Educational Insight', category: 'podcast', layout: 'talking_head_center', caption_preset: 'highlight', duration_range: [25, 75] },
    { id: 'edu_explainer', name: 'Explainer', category: 'educational', layout: 'screencast', caption_preset: 'bullet_points', duration_range: [20, 60] },
    { id: 'code_tutorial', name: 'Code Tutorial', category: 'educational', layout: 'screencast', caption_preset: 'highlight', duration_range: [30, 90] },
    { id: 'step_by_step', name: 'Step by Step', category: 'educational', layout: 'screencast', caption_preset: 'bullet_points', duration_range: [25, 75] },
    { id: 'whiteboard', name: 'Whiteboard', category: 'educational', layout: 'screencast', caption_preset: 'minimal_serif', duration_range: [20, 60] },
    { id: 'reaction_punch', name: 'Reaction Punch', category: 'commentary', layout: 'gameplay_with_facecam', caption_preset: 'highlight', duration_range: [15, 45] },
    { id: 'commentary_news', name: 'Commentary News', category: 'commentary', layout: 'talking_head_center', caption_preset: 'impact', duration_range: [20, 60] },
    { id: 'story_vlog', name: 'Story Vlog', category: 'commentary', layout: 'talking_head_center', caption_preset: 'minimal_serif', duration_range: [20, 60] },
    { id: 'lifestyle_minimal', name: 'Lifestyle Minimal', category: 'commentary', layout: 'talking_head_center', caption_preset: 'minimal_serif', duration_range: [15, 50] },
    { id: 'business_explainer', name: 'Business Explainer', category: 'business', layout: 'screencast', caption_preset: 'bullet_points', duration_range: [25, 60] },
    { id: 'business_premium', name: 'Business Premium', category: 'business', layout: 'talking_head_center', caption_preset: 'minimal_serif', duration_range: [20, 60] },
    { id: 'fitness_intense', name: 'Fitness Intense', category: 'fitness', layout: 'talking_head_center', caption_preset: 'impact', duration_range: [15, 45] },
    { id: 'sports_highlight', name: 'Sports Highlight', category: 'fitness', layout: 'gameplay_center', caption_preset: 'impact', duration_range: [15, 45] },
    { id: 'cinematic_story', name: 'Cinematic Story', category: 'storytelling', layout: 'talking_head_center', caption_preset: 'minimal_serif', duration_range: [25, 90] },
    { id: 'mystery_suspense', name: 'Mystery Suspense', category: 'storytelling', layout: 'talking_head_center', caption_preset: 'minimal_serif', duration_range: [20, 60] },
    { id: 'travel_cinematic', name: 'Travel Cinematic', category: 'travel_food', layout: 'gameplay_center', caption_preset: 'minimal_serif', duration_range: [20, 60] },
    { id: 'food_recipe', name: 'Food Recipe', category: 'travel_food', layout: 'gameplay_center', caption_preset: 'highlight', duration_range: [15, 50] },
    { id: 'dance_beat_sync', name: 'Dance Beat Sync', category: 'music_dance', layout: 'gameplay_center', caption_preset: 'karaoke', duration_range: [15, 45] },
    { id: 'music_visualizer', name: 'Music Visualizer', category: 'music_dance', layout: 'gameplay_center', caption_preset: 'karaoke', duration_range: [20, 60] },
    { id: 'mini_documentary', name: 'Mini Documentary', category: 'news_documentary', layout: 'talking_head_center', caption_preset: 'minimal_serif', duration_range: [30, 90] },
    { id: 'news_bulletin', name: 'News Bulletin', category: 'news_documentary', layout: 'talking_head_center', caption_preset: 'impact', duration_range: [15, 45] },
];

export default function MediaInput({
    onProcess,
    isProcessing,
    selectedTemplate = '',
    onSelectTemplate = null,
    onOpenTemplates = null,
}) {
    const [youtubeUrlEnabled, setYoutubeUrlEnabled] = useState(true);
    // File upload is the primary path; the link is secondary.
    const [mode, setMode] = useState('file'); // 'file' | 'url'
    const [url, setUrl] = useState('');
    const [file, setFile] = useState(null);
    const [fileSeconds, setFileSeconds] = useState(null);
    const fileTooShort = fileSeconds != null && fileSeconds < MIN_SOURCE_SECONDS;
    const [acknowledged, setAcknowledged] = useState(false);
    // {start, end} in seconds when the user picked a stretch under the cost line.
    const [range, setRange] = useState(null);
    const [outputFormat, setOutputFormat] = useState('vertical'); // vertical | horizontal | square
    const [showInfo, setShowInfo] = useState(false);
    // Advanced generation controls — empty string means "let the AI decide",
    // which keeps the default pipeline behavior untouched.
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [targetClips, setTargetClips] = useState('');
    const [clipMinSeconds, setClipMinSeconds] = useState('');
    const [clipMaxSeconds, setClipMaxSeconds] = useState('');
    // Auto-hook: burn the AI hook text into every clip. On by default; the
    // choice persists so turning it off sticks across sessions.
    const [autoHook, setAutoHook] = useState(() => {
        try { return localStorage.getItem('os_auto_hook') !== '0'; } catch { return true; }
    });
    const [autoHookStyle, setAutoHookStyle] = useState(() => {
        // v2 key: the default became 'pill'; an old saved 'classic' was just the old default.
        try { return localStorage.getItem('os_auto_hook_style_v2') || 'pill'; } catch { return 'pill'; }
    });
    // Layout: 'auto' lets the AI pick per video (server default); the others
    // force one on so a podcast host who knows what they uploaded doesn't
    // depend on the detector, and 'none' keeps the plain single crop.
    const [layout, setLayout] = useState(() => {
        try { return localStorage.getItem('os_layout') || 'auto'; } catch { return 'auto'; }
    });
    const [clippingProfile, setClippingProfile] = useState(() => {
        try { return localStorage.getItem('os_clipping_profile') || 'auto'; } catch { return 'auto'; }
    });
    const [templateId, setTemplateId] = useState(() => {
        return selectedTemplate || (() => {
            try { return localStorage.getItem('os_template_id') || ''; } catch { return ''; }
        })();
    });
    const [templates, setTemplates] = useState(DEFAULT_TEMPLATES);

    // Sync when prop changes
    useEffect(() => {
        if (selectedTemplate !== undefined && selectedTemplate !== null) {
            setTemplateId(selectedTemplate);
        }
    }, [selectedTemplate]);

    // Fetch live templates from backend database to include custom ones
    useEffect(() => {
        let active = true;
        fetch(`${getApiUrl()}/api/templates`)
            .then((r) => r.ok ? r.json() : null)
            .then((data) => {
                if (active && Array.isArray(data?.templates) && data.templates.length > 0) {
                    setTemplates(data.templates);
                }
            })
            .catch(() => {});
        return () => { active = false; };
    }, []);

    const currentTemplate = templates.find((t) => t.id === templateId) || null;

    const handleTemplateChange = (newId) => {
        setTemplateId(newId);
        if (onSelectTemplate) onSelectTemplate(newId);
        try { localStorage.setItem('os_template_id', newId); } catch {}
        if (!newId) return;
        const tmpl = templates.find((t) => t.id === newId);
        if (tmpl) {
            if (tmpl.category) {
                const profileMatch = CONTENT_PROFILES.find((p) => p.value === tmpl.category);
                if (profileMatch) {
                    setClippingProfile(tmpl.category);
                }
            }
            if (tmpl.layout === 'stacked_top_cam') {
                setLayout('stacked_top_cam');
            } else if (tmpl.layout === 'split_two_speaker' || tmpl.layout === 'split') {
                setLayout('split');
            } else if (tmpl.layout === 'screencast') {
                setLayout('screencast');
            }
            if (tmpl.duration_range && Array.isArray(tmpl.duration_range)) {
                if (!clipMinSeconds && !clipMaxSeconds) {
                    setClipMinSeconds(tmpl.duration_range[0]);
                    setClipMaxSeconds(tmpl.duration_range[1]);
                }
            }
        }
    };

    const [pasteFeedback, setPasteFeedback] = useState(false);
    const infoRef = useRef(null);

    const handlePaste = async () => {
        try {
            const text = await navigator.clipboard.readText();
            if (text && text.trim()) {
                setUrl(text.trim());
                setPasteFeedback(true);
                setTimeout(() => setPasteFeedback(false), 1800);
            }
        } catch (_) {
            /* clipboard API blocked or denied: silently let user type/paste */
        }
    };

    // Close the compatibility popover on any outside click.
    useEffect(() => {
        if (!showInfo) return;
        const onClick = (e) => {
            if (infoRef.current && !infoRef.current.contains(e.target)) setShowInfo(false);
        };
        document.addEventListener('mousedown', onClick);
        return () => document.removeEventListener('mousedown', onClick);
    }, [showInfo]);

    useEffect(() => {
        let cancelled = false;
        setFileSeconds(null);
        if (!file) return undefined;
        readVideoDuration(file).then((d) => {
            if (cancelled) return;
            setFileSeconds(d);
            if (d != null && d < MIN_SOURCE_SECONDS) {
                track('SourceTooShort', { props: { seconds: String(Math.round(d)) } });
            }
        });
        return () => { cancelled = true; };
    }, [file]);

    useEffect(() => {
        fetch(getApiUrl('/api/config'))
            .then((r) => r.ok ? r.json() : null)
            .then((cfg) => {
                if (cfg && cfg.youtubeUrlEnabled === false) {
                    setYoutubeUrlEnabled(false);
                    setMode('file');
                }
            })
            .catch(() => {});
    }, []);

    // A link pasted in the landing hero: preload it here so the user picks up
    // where they left off. Not auto-submitted — the rights attestation below
    // has to be ticked by the user.
    useEffect(() => {
        let pending = null;
        try {
            pending = localStorage.getItem('os_pending_url');
            if (pending) localStorage.removeItem('os_pending_url');
        } catch { /* ignore */ }
        if (pending) {
            setMode('url');
            setUrl(pending);
        }
    }, []);

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!acknowledged) return;
        const advanced = {
            targetClips: targetClips || null,
            clipMinSeconds: clipMinSeconds || null,
            clipMaxSeconds: clipMaxSeconds || null,
            autoHook,
            autoHookStyle,
            layout,
            templateId: templateId || null,
            clipping_profile: clippingProfile,
            sourceStart: range ? Math.round(range.start) : null,
            sourceEnd: range ? Math.round(range.end) : null,
        };
        try {
            localStorage.setItem('os_auto_hook', autoHook ? '1' : '0');
            localStorage.setItem('os_auto_hook_style_v2', autoHookStyle);
            localStorage.setItem('os_layout', layout);
            localStorage.setItem('os_clipping_profile', clippingProfile);
            localStorage.setItem('os_template_id', templateId || '');
        } catch { /* ignore */ }
        if (mode === 'url' && url) {
            onProcess({ type: 'url', payload: url, acknowledged: true, outputFormat, ...advanced });
        } else if (mode === 'file' && file && !fileTooShort) {
            onProcess({ type: 'file', payload: file, acknowledged: true, outputFormat, ...advanced });
        }
    };

    const handleDrop = (e) => {
        e.preventDefault();
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            setFile(e.dataTransfer.files[0]);
            setMode('file');
        }
    };

    const hasMedia = mode === 'url' ? Boolean(url) : Boolean(file && !fileTooShort);
    const canSubmit = hasMedia && acknowledged && !isProcessing;

    return (
        <div className="card p-4 sm:p-6 animate-fade">
            {/* Tactile Source Selector */}
            <div className="grid grid-cols-2 p-1 bg-paper border border-rule rounded-input mb-5" data-tutorial="source-tabs">
                <button
                    type="button"
                    onClick={() => setMode('file')}
                    className={`flex items-center justify-center gap-2 py-2.5 px-3 rounded-[6px] text-xs lowercase font-medium transition-all ${
                        mode === 'file'
                            ? 'bg-paper3 text-ink border border-rule2 shadow-sm text-brass'
                            : 'text-muted hover:text-ink2 hover:bg-paper3/30'
                    }`}
                >
                    <Upload size={15} className={mode === 'file' ? 'text-brass' : ''} />
                    <span>Upload File</span>
                </button>
                {youtubeUrlEnabled && (
                    <button
                        type="button"
                        onClick={() => setMode('url')}
                        className={`flex items-center justify-center gap-2 py-2.5 px-3 rounded-[6px] text-xs lowercase font-medium transition-all ${
                            mode === 'url'
                                ? 'bg-paper3 text-ink border border-rule2 shadow-sm text-brass'
                                : 'text-muted hover:text-ink2 hover:bg-paper3/30'
                        }`}
                    >
                        <Link2 size={15} className={mode === 'url' ? 'text-brass' : ''} />
                        <span>Video URL</span>
                    </button>
                )}
            </div>

            <form onSubmit={handleSubmit}>
                {mode === 'url' ? (
                    <div className="space-y-4" data-tutorial="drop-zone">
                        <div className="relative flex items-center">
                            <input
                                type="url"
                                value={url}
                                onChange={(e) => setUrl(e.target.value)}
                                placeholder="https://... paste YouTube, Vimeo, TikTok link"
                                className="input-field pr-24 py-3 text-sm"
                                required
                            />
                            <div className="absolute right-1.5 flex items-center gap-1" ref={infoRef}>
                                <button
                                    type="button"
                                    onClick={handlePaste}
                                    className="px-2 py-1 rounded-[6px] text-[11px] font-mono lowercase bg-paper3 border border-rule text-ink2 hover:text-brass hover:border-brass/40 transition-colors flex items-center gap-1 shrink-0"
                                    title="Paste link from clipboard"
                                >
                                    {pasteFeedback ? (
                                        <>
                                            <Check size={12} className="text-ok" />
                                            <span className="text-ok">pasted</span>
                                        </>
                                    ) : (
                                        <>
                                            <ClipboardPaste size={12} className="text-brass" />
                                            <span>paste</span>
                                        </>
                                    )}
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setShowInfo((v) => !v)}
                                    aria-label="Supported platforms"
                                    className="p-1.5 text-muted hover:text-brass transition-colors"
                                >
                                    <Info size={16} />
                                </button>
                                {showInfo && (
                                    <div className="absolute right-0 top-full mt-2 w-64 z-20 card p-4 text-left animate-fade shadow-xl">
                                        <p className="eyebrow mb-2">Supported Platforms</p>
                                        <div className="flex flex-wrap gap-1.5">
                                            {SUPPORTED_PLATFORMS.map((p) => (
                                                <span key={p} className="text-xs px-2 py-0.5 rounded-full bg-paper3 text-ink2">
                                                    {p}
                                                </span>
                                            ))}
                                        </div>
                                        <p className="text-xs text-muted mt-2.5 leading-relaxed">
                                            …and 1,000+ more sites. If a link has a public video, we can usually fetch it.
                                        </p>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                ) : (
                    <div
                        data-tutorial="drop-zone"
                        className={`border-2 border-dashed rounded-card p-6 sm:p-8 text-center transition-colors min-h-[140px] flex flex-col items-center justify-center ${
                            file ? 'border-brass bg-brass/5' : 'border-rule2 hover:border-brass/70 bg-paper/50'
                        }`}
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={handleDrop}
                    >
                        {file ? (
                            <div className="flex flex-col sm:flex-row items-center justify-center gap-2 sm:gap-3 text-ok min-w-0 max-w-full">
                                <div className="flex items-center gap-2 min-w-0 truncate">
                                    <FileVideo size={20} className="shrink-0 text-brass" />
                                    <span className="font-medium text-ink truncate text-sm">{file.name}</span>
                                </div>
                                <div className="flex items-center gap-2 shrink-0">
                                    {fileSeconds && (
                                        <span className="readout bg-paper3 px-2 py-0.5 rounded-full">
                                            {Math.round(fileSeconds)}s
                                        </span>
                                    )}
                                    <button
                                        type="button"
                                        onClick={() => setFile(null)}
                                        className="p-1.5 text-muted hover:text-ink hover:bg-paper3 rounded-full transition-colors"
                                        aria-label="Remove file"
                                    >
                                        <X size={16} />
                                    </button>
                                </div>
                            </div>
                        ) : null}
                        {file && fileTooShort ? (
                            <p className="text-danger text-xs sm:text-sm mt-3" role="alert">
                                This video is {Math.round(fileSeconds)}s long. Clip generation needs at least {MIN_SOURCE_SECONDS}s
                                of footage to cut from: it already is a short. Pick a longer video.
                            </p>
                        ) : null}
                        {!file && (
                            <label className="cursor-pointer block w-full py-2">
                                <input
                                    type="file"
                                    accept="video/*"
                                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                                    className="hidden"
                                />
                                <div className="w-10 h-10 rounded-full bg-paper3 border border-rule mx-auto mb-3 flex items-center justify-center text-muted group-hover:text-brass">
                                    <Upload size={18} />
                                </div>
                                <p className="text-ink2 lowercase text-sm font-medium">Click to upload or drag &amp; drop video</p>
                                <p className="readout mt-1.5 text-[11px]">MP4, MOV up to 500MB · at least {MIN_SOURCE_SECONDS}s long</p>
                            </label>
                        )}
                    </div>
                )}

                <SourceCost
                    mode={mode}
                    url={url}
                    fileSeconds={fileSeconds}
                    range={range}
                    onRangeChange={setRange}
                />

                {/* Content type / Style selector */}
                <div className="mt-5" data-tutorial="content-type">
                    <div className="flex items-center justify-between mb-2">
                        <p className="eyebrow">Content Type</p>
                        <span className="text-[11px] text-muted">
                            {clippingProfile === 'auto' ? 'AI automatically detects genre' : `Optimized for ${clippingProfile}`}
                        </span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                        {CONTENT_PROFILES.map(({ value, label, hint, Icon }) => {
                            const active = clippingProfile === value;
                            return (
                                <button
                                    key={value}
                                    type="button"
                                    onClick={() => setClippingProfile(value)}
                                    className={`py-2.5 px-2 rounded-input border flex flex-col items-center justify-center gap-1.5 transition-all text-center
                                        ${active ? 'border-brass bg-brass/10 text-ink shadow-sm ring-1 ring-brass/30' : 'border-rule bg-paper text-muted hover:border-rule2 hover:text-ink2'}`}
                                >
                                    <Icon size={17} className={active ? 'text-brass' : 'text-muted'} />
                                    <span className="block text-xs font-medium leading-none">{label}</span>
                                    <span className="block text-[10px] text-muted truncate max-w-full">{hint}</span>
                                </button>
                            );
                        })}
                    </div>
                </div>

                {/* Output format selector */}
                <div className="mt-5" data-tutorial="output-format">
                    <p className="eyebrow mb-2">Output format</p>
                    <div className="grid grid-cols-3 gap-2">
                        {[
                            { value: 'vertical', label: '9:16', hint: 'Shorts · Reels · TikTok', w: 16, h: 28 },
                            { value: 'square', label: '1:1', hint: 'Feed posts', w: 22, h: 22 },
                            { value: 'horizontal', label: '16:9', hint: 'Landscape · YouTube', w: 28, h: 16 },
                        ].map((f) => {
                            const active = outputFormat === f.value;
                            return (
                                <button
                                    key={f.value}
                                    type="button"
                                    onClick={() => setOutputFormat(f.value)}
                                    className={`py-3 px-2 rounded-input border flex flex-col items-center justify-center gap-1.5 transition-all
                                        ${active ? 'border-brass bg-brass/10 text-ink shadow-sm' : 'border-rule bg-paper text-muted hover:border-rule2 hover:text-ink2'}`}
                                >
                                    {/* Aspect-ratio glyph */}
                                    <span
                                        className="rounded-[3px] border-2 transition-colors flex-shrink-0"
                                        style={{
                                            width: `${f.w}px`,
                                            height: `${f.h}px`,
                                            borderColor: active ? 'var(--color-accent)' : 'var(--color-rule-2)',
                                            backgroundColor: active ? 'color-mix(in srgb, var(--color-accent) 25%, transparent)' : 'transparent',
                                        }}
                                    />
                                    <span className="block font-mono text-xs sm:text-sm font-semibold leading-none">{f.label}</span>
                                    <span className="block text-[10px] leading-tight text-center text-muted truncate max-w-full">{f.hint}</span>
                                </button>
                            );
                        })}
                    </div>
                </div>

                {/* Advanced generation controls — collapsed by default */}
                <div className="mt-4">
                    <button
                        type="button"
                        onClick={() => setShowAdvanced((v) => !v)}
                        className="flex items-center gap-1.5 text-xs text-muted hover:text-ink2 lowercase transition-colors py-1"
                    >
                        <ChevronDown size={14} className={`transition-transform duration-200 ${showAdvanced ? 'rotate-180' : ''}`} />
                        <span>advanced options</span>
                        {(targetClips || clipMinSeconds || clipMaxSeconds || !autoHook || templateId) && (
                            <span className="text-brass font-bold">· modified</span>
                        )}
                    </button>
                    {showAdvanced && (
                        <div className="mt-3 p-3.5 bg-paper/60 border border-rule rounded-input grid grid-cols-1 sm:grid-cols-3 gap-3 animate-fade">
                            <div>
                                <p className="eyebrow mb-1.5">clips to aim for</p>
                                <input
                                    type="number" min="1" max="15" step="1"
                                    value={targetClips}
                                    onChange={(e) => setTargetClips(e.target.value)}
                                    placeholder="auto"
                                    className="input-field"
                                />
                            </div>
                            <div>
                                <p className="eyebrow mb-1.5">min length (s)</p>
                                <input
                                    type="number" min="5" max="175" step="1"
                                    value={clipMinSeconds}
                                    onChange={(e) => setClipMinSeconds(e.target.value)}
                                    placeholder="15"
                                    className="input-field"
                                />
                            </div>
                            <div>
                                <p className="eyebrow mb-1.5">max length (s)</p>
                                <input
                                    type="number" min="10" max="180" step="1"
                                    value={clipMaxSeconds}
                                    onChange={(e) => setClipMaxSeconds(e.target.value)}
                                    placeholder="60"
                                    className="input-field"
                                />
                            </div>
                            <p className="col-span-1 sm:col-span-3 text-[11px] leading-relaxed text-muted">
                                Targets, not guarantees: the AI returns fewer clips when the
                                material doesn&apos;t hold them. Leave blank to let it decide.
                            </p>
                            <div className="col-span-1 sm:col-span-3 flex flex-wrap items-center justify-between gap-2 pt-2.5 border-t border-rule">
                                <div className="flex items-center gap-1.5">
                                    <LayoutTemplate size={14} className="text-brass" />
                                    <span className="text-xs text-ink2">template preset</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <select
                                        value={templateId}
                                        onChange={(e) => handleTemplateChange(e.target.value)}
                                        className="input-field !w-auto text-xs py-1.5 max-w-[260px] sm:max-w-xs font-sans"
                                        aria-label="template preset"
                                    >
                                        <option value="">Auto AI (Smart Match)</option>
                                        {TEMPLATE_CATEGORIES.map((cat) => {
                                            const catTemplates = templates.filter((t) => t.category === cat.id);
                                            if (!catTemplates.length) return null;
                                            return (
                                                <optgroup key={cat.id} label={cat.label}>
                                                    {catTemplates.map((t) => (
                                                        <option key={t.id} value={t.id}>
                                                            {t.name}
                                                        </option>
                                                    ))}
                                                </optgroup>
                                            );
                                        })}
                                    </select>
                                    {onOpenTemplates && (
                                        <button
                                            type="button"
                                            onClick={onOpenTemplates}
                                            className="text-xs text-muted hover:text-brass transition-colors underline whitespace-nowrap"
                                            title="Browse templates in Template Studio"
                                        >
                                            studio →
                                        </button>
                                    )}
                                </div>
                            </div>
                            {currentTemplate && (
                                <div className="col-span-1 sm:col-span-3 bg-paper3/60 rounded px-3 py-2 text-[11px] text-muted flex items-center justify-between gap-2 border border-rule/50 animate-fade">
                                    <div className="flex items-center gap-2 truncate">
                                        <span className="w-1.5 h-1.5 rounded-full bg-brass shrink-0" />
                                        <span className="truncate">
                                            <strong className="text-ink">{currentTemplate.name}</strong> · Layout: <span className="font-mono text-ink2">{currentTemplate.layout}</span> · Captions: <span className="font-mono text-ink2">{currentTemplate.caption_preset}</span> · Range: <span className="font-mono text-ink2">{currentTemplate.duration_range?.[0]}–{currentTemplate.duration_range?.[1]}s</span>
                                        </span>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => handleTemplateChange('')}
                                        className="text-[10px] text-muted hover:text-ink shrink-0 underline"
                                    >
                                        clear
                                    </button>
                                </div>
                            )}
                            <div className="col-span-1 sm:col-span-3 flex flex-wrap items-center justify-between gap-2 pt-2.5 border-t border-rule">
                                <span className="text-xs text-ink2">clipping mode</span>
                                <select
                                    value={clippingProfile}
                                    onChange={(e) => setClippingProfile(e.target.value)}
                                    className="input-field !w-auto text-xs py-1.5"
                                    aria-label="clipping mode"
                                >
                                    <option value="auto">Auto AI (Smart Detection)</option>
                                    <option value="gaming">Gaming &amp; Action (GTA, FPS, etc.)</option>
                                    <option value="podcast">Podcast (conversations &amp; interviews)</option>
                                    <option value="educational">Educational (tutorials &amp; explainers)</option>
                                    <option value="commentary">Commentary / Vlog / YouTube</option>
                                </select>
                            </div>
                            <div className="col-span-1 sm:col-span-3 flex flex-wrap items-center justify-between gap-2 pt-2.5 border-t border-rule">
                                <span className="text-xs text-ink2">vertical layout</span>
                                <select
                                    value={layout}
                                    onChange={(e) => setLayout(e.target.value)}
                                    className="input-field !w-auto text-xs py-1.5"
                                    aria-label="vertical layout"
                                >
                                    <option value="auto">Auto (AI picks per video)</option>
                                    <option value="stacked_top_cam">Streamer cam on top (stacked)</option>
                                    <option value="split">Two speakers stacked</option>
                                    <option value="screencast">Screen over presenter</option>
                                    <option value="none">Single crop only</option>
                                </select>
                            </div>
                            <div className="col-span-1 sm:col-span-3 flex flex-wrap items-center justify-between gap-2 pt-2.5 border-t border-rule">
                                <label className="flex items-center gap-2 text-xs text-ink2 cursor-pointer select-none">
                                    <input
                                        type="checkbox"
                                        checked={autoHook}
                                        onChange={(e) => setAutoHook(e.target.checked)}
                                        className="w-4 h-4 shrink-0 accent-[var(--color-accent)] cursor-pointer"
                                    />
                                    <span>auto hook titles on clips</span>
                                </label>
                                {autoHook && (
                                    <select
                                        value={autoHookStyle}
                                        onChange={(e) => setAutoHookStyle(e.target.value)}
                                        className="input-field !w-auto text-xs py-1.5"
                                    >
                                        <option value="pill">Pills</option>
                                        <option value="classic">Classic</option>
                                        <option value="dark">Dark</option>
                                        <option value="yellow">Yellow</option>
                                        <option value="red">Red</option>
                                        <option value="outline">Outline</option>
                                        <option value="outline_yellow">Outline+</option>
                                    </select>
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {/* Rights confirmation - Interactive Card */}
                <label className={`flex items-start gap-3 mt-5 p-3.5 rounded-input border transition-all cursor-pointer select-none text-left ${
                    acknowledged ? 'bg-paper3/40 border-brass/50' : 'bg-paper border-rule hover:border-rule2'
                }`}>
                    <input
                        type="checkbox"
                        checked={acknowledged}
                        onChange={(e) => setAcknowledged(e.target.checked)}
                        className="mt-0.5 w-4 h-4 shrink-0 accent-[var(--color-accent)] cursor-pointer rounded"
                    />
                    <span className="text-[12px] sm:text-xs leading-relaxed text-muted">
                        I confirm I own this content or have the rights to process it. I am responsible for any content I submit. See our <a href="/terms" target="_blank" rel="noopener noreferrer" className="text-ink2 underline underline-offset-2 hover:text-brass transition-colors" onClick={(e) => e.stopPropagation()}>Terms</a> and <a href="/privacy" target="_blank" rel="noopener noreferrer" className="text-ink2 underline underline-offset-2 hover:text-brass transition-colors" onClick={(e) => e.stopPropagation()}>Privacy Policy</a>.
                    </span>
                </label>

                {/* Primary Action Button */}
                <button
                    type="submit"
                    data-tutorial="generate"
                    disabled={!canSubmit}
                    className="w-full btn-primary mt-4 py-3 sm:py-3.5 text-sm font-medium flex items-center justify-center gap-2 shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {isProcessing ? (
                        <>
                            <Loader2 size={16} className="animate-spin text-brassink" />
                            <span>Processing Video...</span>
                        </>
                    ) : (
                        <>
                            <Sparkles size={16} className="text-brassink" />
                            <span>Generate Viral Shorts</span>
                        </>
                    )}
                </button>

                {/* Helper hint for disabled state */}
                {!isProcessing && !canSubmit && (
                    <p className="text-[11px] text-center text-muted mt-2">
                        {!hasMedia
                            ? 'Please provide a video file or link to continue'
                            : !acknowledged
                            ? 'Please confirm content rights above to generate clips'
                            : ''}
                    </p>
                )}
            </form>
        </div>
    );
}
