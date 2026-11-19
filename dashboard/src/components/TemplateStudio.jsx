import React, { useState, useEffect, useMemo } from 'react';
import { 
    LayoutTemplate, Sparkles, Gamepad2, Mic, GraduationCap, MessageSquare, 
    Dumbbell, Briefcase, Film, Compass, Music, Newspaper, Check, Play, 
    Sliders, RefreshCw, Save, Trash2, ArrowUpRight, ShieldCheck, Eye, X
} from 'lucide-react';
import { getApiUrl } from '../config';

const CATEGORY_ITEMS = [
    { id: 'all', label: 'All Templates', Icon: LayoutTemplate },
    { id: 'gaming', label: 'Gaming & Streams', Icon: Gamepad2 },
    { id: 'podcast', label: 'Podcasts & Talk', Icon: Mic },
    { id: 'educational', label: 'Education & Code', Icon: GraduationCap },
    { id: 'commentary', label: 'Vlog & Reactions', Icon: MessageSquare },
    { id: 'fitness', label: 'Fitness & Sports', Icon: Dumbbell },
    { id: 'business', label: 'Business & Finance', Icon: Briefcase },
    { id: 'storytelling', label: 'Story & Cinema', Icon: Film },
    { id: 'travel_food', label: 'Travel & Food', Icon: Compass },
    { id: 'music_dance', label: 'Music & Dance', Icon: Music },
    { id: 'news_documentary', label: 'News & Docs', Icon: Newspaper },
];

export default function TemplateStudio() {
    const [templates, setTemplates] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedCategory, setSelectedCategory] = useState('all');
    const [activeTemplate, setActiveTemplate] = useState(null);
    const [editMode, setEditMode] = useState(false);
    const [saveStatus, setSaveStatus] = useState(null);
    const [searchQuery, setSearchQuery] = useState('');

    // Fetch templates from backend database
    const loadTemplates = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${getApiUrl()}/api/templates`);
            if (res.ok) {
                const data = await res.json();
                setTemplates(data.templates || []);
            }
        } catch (err) {
            console.error('Failed to load templates:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadTemplates();
    }, []);

    // Filtered templates
    const filteredTemplates = useMemo(() => {
        return templates.filter((t) => {
            const matchesCat = selectedCategory === 'all' || t.category === selectedCategory;
            const matchesQuery = !searchQuery || 
                t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                t.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
                (t.layout && t.layout.toLowerCase().includes(searchQuery.toLowerCase()));
            return matchesCat && matchesQuery;
        });
    }, [templates, selectedCategory, searchQuery]);

    // Handle template selection & draft loading from localStorage
    const handleSelectTemplate = (template) => {
        const draftKey = `os_template_draft_${template.id}`;
        const savedDraft = localStorage.getItem(draftKey);
        if (savedDraft) {
            try {
                setActiveTemplate(JSON.parse(savedDraft));
            } catch {
                setActiveTemplate({ ...template });
            }
        } else {
            setActiveTemplate({ ...template });
        }
        setEditMode(false);
        setSaveStatus(null);
    };

    // Save changes to backend database
    const handleSaveToBackend = async () => {
        if (!activeTemplate) return;
        setSaveStatus('saving');
        try {
            const res = await fetch(`${getApiUrl()}/api/templates`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(activeTemplate),
            });
            if (res.ok) {
                setSaveStatus('saved');
                localStorage.removeItem(`os_template_draft_${activeTemplate.id}`);
                await loadTemplates();
                setTimeout(() => setSaveStatus(null), 2500);
            } else {
                setSaveStatus('error');
            }
        } catch (e) {
            console.error(e);
            setSaveStatus('error');
        }
    };

    // Update draft in state and localStorage
    const updateActiveField = (field, value) => {
        setActiveTemplate((prev) => {
            const updated = { ...prev, [field]: value };
            localStorage.setItem(`os_template_draft_${prev.id}`, JSON.stringify(updated));
            return updated;
        });
    };

    return (
        <div className="max-w-7xl mx-auto space-y-6 animate-fade">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-rule">
                <div>
                    <div className="flex items-center gap-2">
                        <Sparkles size={20} className="text-brass" />
                        <h1 className="text-xl font-semibold text-ink">Template Studio</h1>
                    </div>
                    <p className="text-xs text-muted mt-1">
                        Select and customize 30+ niche-specific video editing templates across 10 categories.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        type="button"
                        onClick={loadTemplates}
                        className="btn-secondary !text-xs !py-1.5 flex items-center gap-1.5"
                    >
                        <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
                        Refresh Presets
                    </button>
                </div>
            </div>

            {/* Category Navigation Pills */}
            <div className="flex items-center gap-1.5 overflow-x-auto pb-2 scrollbar-none">
                {CATEGORY_ITEMS.map(({ id, label, Icon }) => {
                    const active = selectedCategory === id;
                    return (
                        <button
                            key={id}
                            type="button"
                            onClick={() => setSelectedCategory(id)}
                            className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap flex items-center gap-1.5 transition-all ${
                                active
                                    ? 'bg-brass text-ink font-semibold shadow-sm'
                                    : 'bg-paper border border-rule text-muted hover:text-ink hover:border-rule2'
                            }`}
                        >
                            <Icon size={14} className={active ? 'text-ink' : 'text-muted'} />
                            <span>{label}</span>
                        </button>
                    );
                })}
            </div>

            {/* Grid of Templates */}
            {loading ? (
                <div className="p-12 text-center text-muted text-xs">
                    <RefreshCw size={24} className="animate-spin mx-auto text-brass mb-3" />
                    Loading template library from database...
                </div>
            ) : filteredTemplates.length === 0 ? (
                <div className="p-12 text-center card text-muted text-xs">
                    No templates found matching this category.
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {filteredTemplates.map((template) => {
                        const isSelected = activeTemplate?.id === template.id;
                        return (
                            <div
                                key={template.id}
                                className={`card p-4 flex flex-col justify-between transition-all hover:border-brass/40 ${
                                    isSelected ? 'border-brass shadow-md ring-1 ring-brass/30' : ''
                                }`}
                            >
                                <div>
                                    <div className="flex items-center justify-between gap-2 mb-2">
                                        <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-paper3 border border-rule text-muted">
                                            {template.category}
                                        </span>
                                        {template.is_builtin ? (
                                            <span className="text-[10px] text-muted flex items-center gap-1">
                                                <ShieldCheck size={12} className="text-ok" /> Built-in
                                            </span>
                                        ) : (
                                            <span className="text-[10px] text-brass">Custom Preset</span>
                                        )}
                                    </div>
                                    <h3 className="text-sm font-semibold text-ink">{template.name}</h3>
                                    <p className="text-xs text-muted font-mono mt-0.5">Layout: {template.layout}</p>

                                    <div className="mt-3 space-y-1.5 text-xs text-ink2">
                                        <div className="flex items-center justify-between">
                                            <span className="text-muted text-[11px]">Duration:</span>
                                            <span className="font-mono text-[11px]">{template.duration_range[0]}s – {template.duration_range[1]}s</span>
                                        </div>
                                        <div className="flex items-center justify-between">
                                            <span className="text-muted text-[11px]">Captions:</span>
                                            <span className="font-mono text-[11px] capitalize">{template.caption_preset}</span>
                                        </div>
                                        <div className="flex items-center justify-between">
                                            <span className="text-muted text-[11px]">Audio Mix:</span>
                                            <span className="font-mono text-[11px] capitalize">{template.audio_preset}</span>
                                        </div>
                                    </div>

                                    {/* Effects Chips */}
                                    <div className="flex flex-wrap gap-1 mt-3">
                                        {template.effects.map((ef) => (
                                            <span
                                                key={ef}
                                                className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-paper2 border border-rule text-muted"
                                            >
                                                {ef}
                                            </span>
                                        ))}
                                    </div>
                                </div>

                                <div className="mt-4 pt-3 border-t border-rule flex items-center justify-between gap-2">
                                    <button
                                        type="button"
                                        onClick={() => handleSelectTemplate(template)}
                                        className="btn-primary !text-xs !py-1 flex-1 flex items-center justify-center gap-1.5"
                                    >
                                        <Eye size={13} />
                                        <span>Preview &amp; Customize</span>
                                    </button>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* Template Preview & Customizer Modal / Panel */}
            {activeTemplate && (
                <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
                    <div className="bg-paper border border-rule rounded-card max-w-3xl w-full p-6 shadow-2xl space-y-5 animate-scaleUp max-h-[90vh] overflow-y-auto">
                        <div className="flex items-center justify-between border-b border-rule pb-3">
                            <div>
                                <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-paper3 text-muted">
                                    {activeTemplate.category}
                                </span>
                                <h2 className="text-lg font-semibold text-ink mt-1">{activeTemplate.name}</h2>
                            </div>
                            <button
                                type="button"
                                onClick={() => setActiveTemplate(null)}
                                className="p-1.5 text-muted hover:text-ink rounded"
                            >
                                <X size={18} />
                            </button>
                        </div>

                        {/* Visual Layout Mockup */}
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 items-center">
                            {/* Layout Simulation Container */}
                            <div className="flex justify-center">
                                <div className="w-[180px] h-[320px] bg-black rounded-lg border-2 border-rule2 relative overflow-hidden flex flex-col shadow-inner">
                                    {activeTemplate.layout === 'stacked_top_cam' ? (
                                        <>
                                            <div className="h-[30%] bg-zinc-800 border-b border-white/40 flex items-center justify-center text-[11px] font-mono text-zinc-300">
                                                Streamer Cam (Top)
                                            </div>
                                            <div className="flex-1 bg-zinc-900 flex items-center justify-center text-[11px] font-mono text-zinc-400">
                                                Gameplay Stream
                                            </div>
                                        </>
                                    ) : activeTemplate.layout === 'split_two_speaker' ? (
                                        <>
                                            <div className="h-[50%] bg-zinc-800 border-b border-rule flex items-center justify-center text-[11px] font-mono text-zinc-300">
                                                Speaker 1 (Top)
                                            </div>
                                            <div className="h-[50%] bg-zinc-900 flex items-center justify-center text-[11px] font-mono text-zinc-300">
                                                Speaker 2 (Bottom)
                                            </div>
                                        </>
                                    ) : (
                                        <div className="flex-1 bg-zinc-900 flex items-center justify-center text-[11px] font-mono text-zinc-400">
                                            {activeTemplate.name}
                                        </div>
                                    )}

                                    {/* Simulated Dynamic Subtitles */}
                                    <div className="absolute bottom-6 inset-x-2 text-center bg-black/60 py-1 px-1.5 rounded text-[10px] text-yellow-300 font-bold tracking-wide">
                                        CAPTION: {activeTemplate.caption_preset.toUpperCase()}
                                    </div>
                                </div>
                            </div>

                            {/* Configuration Options */}
                            <div className="space-y-4 text-xs">
                                <div>
                                    <label className="block text-muted mb-1 font-medium">Template Name</label>
                                    <input
                                        type="text"
                                        value={activeTemplate.name}
                                        onChange={(e) => updateActiveField('name', e.target.value)}
                                        className="input-field py-1.5 text-xs"
                                    />
                                </div>

                                <div>
                                    <label className="block text-muted mb-1 font-medium">Layout Strategy</label>
                                    <select
                                        value={activeTemplate.layout}
                                        onChange={(e) => updateActiveField('layout', e.target.value)}
                                        className="input-field py-1.5 text-xs"
                                    >
                                        <option value="gameplay_center">gameplay_center (Centered viewport)</option>
                                        <option value="stacked_top_cam">stacked_top_cam (Top streamer cam + bottom stream)</option>
                                        <option value="gameplay_with_facecam">gameplay_with_facecam (Bottom cam inset)</option>
                                        <option value="split_two_speaker">split_two_speaker (Dual speaker split)</option>
                                        <option value="talking_head_center">talking_head_center (Podcast / Talk)</option>
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-muted mb-1 font-medium">Caption Style</label>
                                    <select
                                        value={activeTemplate.caption_preset}
                                        onChange={(e) => updateActiveField('caption_preset', e.target.value)}
                                        className="input-field py-1.5 text-xs"
                                    >
                                        <option value="impact">impact (Bold uppercase impact font)</option>
                                        <option value="highlight">highlight (Word-level pop highlight)</option>
                                        <option value="karaoke">karaoke (Animated word-by-word highlight)</option>
                                        <option value="comic">comic (Vibrant yellow/red comic font)</option>
                                        <option value="minimal_serif">minimal_serif (Subtle editorial serif)</option>
                                        <option value="bullet_points">bullet_points (Structured bullet callouts)</option>
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-muted mb-1 font-medium">Target Duration Range</label>
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="number"
                                            value={activeTemplate.duration_range[0]}
                                            onChange={(e) => updateActiveField('duration_range', [Number(e.target.value), activeTemplate.duration_range[1]])}
                                            className="input-field py-1 text-xs w-20 text-center"
                                        />
                                        <span className="text-muted">to</span>
                                        <input
                                            type="number"
                                            value={activeTemplate.duration_range[1]}
                                            onChange={(e) => updateActiveField('duration_range', [activeTemplate.duration_range[0], Number(e.target.value)])}
                                            className="input-field py-1 text-xs w-20 text-center"
                                        />
                                        <span className="text-muted">seconds</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Actions Footer */}
                        <div className="pt-4 border-t border-rule flex items-center justify-between">
                            <span className="text-[11px] text-muted">
                                {saveStatus === 'saving' && 'Saving preset to backend database...'}
                                {saveStatus === 'saved' && '✅ Preset successfully saved to database!'}
                                {saveStatus === 'error' && '❌ Failed to save preset.'}
                            </span>
                            <div className="flex items-center gap-2">
                                <button
                                    type="button"
                                    onClick={() => setActiveTemplate(null)}
                                    className="btn-secondary !text-xs !py-1.5"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="button"
                                    onClick={handleSaveToBackend}
                                    className="btn-primary !text-xs !py-1.5 flex items-center gap-1.5"
                                >
                                    <Save size={13} />
                                    <span>Save Preset to Database</span>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
