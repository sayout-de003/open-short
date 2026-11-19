import React, { useState, useEffect, useRef } from 'react';
import { Download, Share2, AlertCircle, Loader2, Copy, Check, Wand2, Type, Calendar, Languages, FileText, Link2, Scissors, Crosshair, TrendingUp, Sparkles, Youtube, Hash } from 'lucide-react';
import { getApiUrl } from '../config';
import { apiFetch } from '../lib/api';
import { platformOptions as buildPlatformOptions, defaultPlatformFlags, flagsFromList } from '../lib/socialPlatforms';
import { track } from '../lib/analytics';
import SubtitleModal from './SubtitleModal';
import HookModal from './HookModal';
import TranslateModal from './TranslateModal';
import Modal from './ui/Modal';
import SegmentedControl from './ui/SegmentedControl';
import WatermarkModal, { watermarkNoticeDismissed } from './WatermarkModal';
import TikTokDraftNotice from './TikTokDraftNotice';
import { useAuth } from '../contexts/AuthContext';
import { renderInBrowser } from '../lib/renderInBrowser';

const QUIET_BTN = 'group flex flex-col items-center justify-center gap-1 py-2.5 sm:py-2 px-1 rounded-input border border-rule hover:bg-paper3 text-[11px] lowercase text-ink2 whitespace-nowrap transition-colors disabled:opacity-45 disabled:cursor-not-allowed';

// Follow an async post (request_id from /api/social/post) for about a minute.
// Returns {done, failed}: done once every platform finished, failed lists
// "platform: reason" for the ones that did not. Unknown or slow = neither.
const POST_TERMINAL = new Set(['completed', 'failed', 'not_found']);
async function followPost(requestId, tries = 12, everyMs = 5000) {
    for (let i = 0; i < tries; i++) {
        await new Promise((r) => setTimeout(r, everyMs));
        let d;
        try {
            const r = await apiFetch(`/api/social/post-status/${encodeURIComponent(requestId)}`);
            if (!r.ok) continue;
            d = await r.json();
        } catch {
            continue;
        }
        if (d.status === 'unknown') return { done: false, failed: [] };
        if (!POST_TERMINAL.has(d.status)) continue;
        const failed = (d.results || [])
            .filter((x) => x.success === false)
            .map((x) => `${x.platform}${x.message ? `: ${x.message}` : ''}`);
        if (d.status !== 'completed' && !failed.length) failed.push('every platform');
        return { done: d.status === 'completed', failed };
    }
    return { done: false, failed: [] };
}

const PLATFORM_OPTIONS = buildPlatformOptions({ lower: true });

function clipDurationSeconds(clip) {
    // A recut clip's start/end are the covering source range (segments may be
    // non-contiguous or reordered); its real duration is the segment sum.
    const segments = clip.recipe?.segments;
    if (segments?.length) {
        return segments.reduce((acc, s) => acc + (s.end - s.start), 0);
    }
    return clip.end && clip.start ? clip.end - clip.start : NaN;
}

function formatDuration(clip) {
    const secs = Math.floor(clipDurationSeconds(clip));
    if (!Number.isFinite(secs) || secs < 0) return null;
    return `${String(Math.floor(secs / 60)).padStart(2, '0')}:${String(secs % 60).padStart(2, '0')}`;
}

function getDefaultScheduleTime(idx = 0) {
    const d = new Date();
    d.setMinutes(0, 0, 0);
    d.setHours(d.getHours() + 2 + (idx * 4));
    const tzOffset = d.getTimezoneOffset() * 60000;
    return new Date(d.getTime() - tzOffset).toISOString().slice(0, 16);
}

function getClipCaption(clip) {
    if (clip.caption && clip.caption.trim()) return clip.caption.trim();
    const desc = clip.video_description_for_tiktok || clip.video_description_for_instagram || "";
    // Remove hashtags from description to isolate the clean caption
    const clean = desc.replace(/#[a-zA-Z0-9_\u00c0-\u024f]+/g, "").trim();
    return clean || desc || clip.video_title_for_youtube_short || "Watch till the end! 🔥";
}

function getClipHashtags(clip) {
    if (Array.isArray(clip.hashtags) && clip.hashtags.length > 0) {
        return clip.hashtags.map(t => t.startsWith('#') ? t : `#${t}`);
    }
    const combined = [
        clip.video_description_for_tiktok,
        clip.video_description_for_instagram,
        clip.video_title_for_youtube_short,
        clip.caption,
    ].filter(Boolean).join(" ");
    const matches = combined.match(/#[a-zA-Z0-9_\u00c0-\u024f]+/g);
    if (matches && matches.length > 0) {
        return Array.from(new Set(matches));
    }
    return ["#shorts", "#viral", "#trending", "#fyp", "#foryou"];
}

export default function ResultCard({ clip, index, jobId, durable, uploadPostKey, uploadUserId, geminiApiKey, elevenLabsKey, isManaged, onPlay, onPause, onBulkSubtitle, clipCount = 1, bulkProgress, initialState = null, onStateChange, connectedPlatforms = null, onConnectSocials, onEditClip = null, onReframeClip = null, onModeChanged = null, onUpgrade = null }) {
    const [showModal, setShowModal] = useState(false);
    // The "why" line is clamped to two lines so cards in a row stay level;
    // when it overflows, a hover (desktop) or tap (touch) shows the whole
    // sentence in a popover that floats over the card instead of growing it.
    const whyRef = useRef(null);
    const [whyOpen, setWhyOpen] = useState(false);
    const [whyClamped, setWhyClamped] = useState(false);
    useEffect(() => {
        const el = whyRef.current;
        if (!el) return;
        const check = () => setWhyClamped(el.scrollHeight > el.clientHeight + 1);
        check();
        window.addEventListener('resize', check);
        return () => window.removeEventListener('resize', check);
    }, [clip.why]);
    const [showDescModal, setShowDescModal] = useState(false);
    const [showSubtitleModal, setShowSubtitleModal] = useState(false);
    const [showWatermarkModal, setShowWatermarkModal] = useState(false);
    const { plan } = useAuth();
    const videoRef = React.useRef(null);
    // Pristine base clip (no burned subtitles/hook), stable regardless of how
    // clip.video_url mutates after server edits. Used as the compositing base
    // for the Remotion preview so it never stacks subtitles over an already-
    // subtitled file (double-subtitle bug).
    const stripBurns = (filename) => {
        let f = filename || '', prev;
        do { prev = f; f = f.replace(/^subtitled_\d+_/, '').replace(/^hooked_\d+_/, '').replace(/^hook_/, ''); } while (f !== prev);
        return f;
    };
    const originalVideoUrl = getApiUrl((clip.video_url || '').replace(/[^/]+$/, stripBurns((clip.video_url || '').split('/').pop())));
    const [currentVideoUrl, setCurrentVideoUrl] = useState(getApiUrl(clip.video_url));
    // Where the <video> element pulls its bytes from. The clips are archived to
    // R2 anyway, and R2 egress is free and edge-served, while /videos is served
    // by the same single-worker API process that is running the renders. So play
    // from R2 when possible.
    //
    // ONLY when R2 holds exactly the file the server considers current for this
    // clip (durable.filename === serverVideoFile). Every server-side edit sends
    // input_filename: serverVideoFile and rewrites clip.video_url, but the R2
    // re-archive behind it is fire-and-forget, so for a few seconds the durable
    // copy is the PRE-edit clip. Preferring it blindly would silently show the
    // clip without the subtitles/hook the user just burned.
    //
    // This is display-only: currentVideoUrl remains the source of truth for the
    // download button and for every server operation, so no edit can be routed
    // to the wrong file by this.
    const [durableSrc, setDurableSrc] = useState(null);
    const [durableFailed, setDurableFailed] = useState(false);
    // Switching src reloads the element and restarts playback, so the durable copy
    // is only ever adopted before the user has touched this player. After an edit
    // the chase in App.jsx can land while they are watching the result, and losing
    // their position to save a few seconds of buffering is a bad trade.
    const [hasPlayed, setHasPlayed] = useState(false);

    // A delivered clip is tens of MB, and on a slow link the old silent
    // fetch-then-save took minutes with nothing on screen, which reads as a dead
    // button. Stream it instead and report progress.
    const [downloadPct, setDownloadPct] = useState(null);

    const downloadClip = async () => {
        try {
            setDownloadPct(0);
            const response = await fetch(currentVideoUrl);
            if (!response.ok) throw new Error('Download failed');
            const total = Number(response.headers.get('content-length')) || 0;
            let blob;
            // No body reader (old browser) or no length to measure against: fall
            // back to the plain path rather than lose the download.
            if (!response.body || !total) {
                blob = await response.blob();
            } else {
                const reader = response.body.getReader();
                const chunks = [];
                let received = 0;
                for (;;) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    chunks.push(value);
                    received += value.length;
                    setDownloadPct(Math.min(99, Math.round((received / total) * 100)));
                }
                blob = new Blob(chunks, { type: 'video/mp4' });
            }
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = `clip-${index + 1}.mp4`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (err) {
            console.error('Download error:', err);
            window.open(currentVideoUrl, '_blank');
        } finally {
            setDownloadPct(null);
        }
    };
    // Latest file that exists ON THE SERVER (blob: previews don't count).
    // All server-side operations must chain from this, so burned-in edits
    // (subtitles, hooks, effects) never get silently dropped.
    // A reopened project seeds it from the persisted project state.
    const [serverVideoFile, setServerVideoFile] = useState(initialState?.server_file || (clip.video_url || '').split('/').pop());
    const [videoErrored, setVideoErrored] = useState(false);
    const [resolution, setResolution] = useState(null);

    // Adopt the durable copy only while it matches the current server file, and
    // pin the first signed URL seen for that file: /api/history mints a fresh
    // signature on every call, and swapping src mid-playback restarts the video.
    useEffect(() => {
        if (durable?.url && durable.filename && durable.filename === serverVideoFile && !hasPlayed) {
            setDurableSrc((prev) => prev || durable.url);
        } else {
            setDurableSrc(null);
        }
    }, [durable?.url, durable?.filename, serverVideoFile, hasPlayed]);

    // If the local video failed and a durable R2 URL is (now) available, use it.
    // Handles the race where the video errors before the durable URL has loaded.
    // Deliberately NOT version-gated: reaching here means the local file is gone
    // (retention sweep after a reload), so an older durable copy still beats a
    // broken player.
    useEffect(() => {
        if (videoErrored && durable?.url && currentVideoUrl !== durable.url) {
            setCurrentVideoUrl(durable.url);
            setVideoErrored(false);
        }
    }, [videoErrored, durable, currentVideoUrl]);

    // When an external refresh changes this clip's server file (e.g. bulk
    // subtitles applied from another card), adopt it so the card shows the
    // freshly subtitled video instead of a stale one.
    useEffect(() => {
        const serverUrl = getApiUrl(clip.video_url);
        const serverName = (clip.video_url || '').split('/').pop();
        if (serverName && serverName !== serverVideoFile) {
            setServerVideoFile(serverName);
            setCurrentVideoUrl(serverUrl);
            setDurableFailed(false);
            setHasPlayed(false);
            if (videoRef.current) videoRef.current.load();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [clip.video_url]);

    const [platforms, setPlatforms] = useState(defaultPlatformFlags);
    const [postTitle, setPostTitle] = useState("");
    const [postDescription, setPostDescription] = useState("");
    const [isScheduling, setIsScheduling] = useState(true); // Default ON per user requirement
    const [scheduleDate, setScheduleDate] = useState(() => getDefaultScheduleTime(index));
    const [scheduledInfo, setScheduledInfo] = useState(null);
    const [showManualAuth, setShowManualAuth] = useState(false);
    const [manualCode, setManualCode] = useState("");
    const [exchangingAuth, setExchangingAuth] = useState(false);
    const [ytDirectConfigured, setYtDirectConfigured] = useState(false);
    const [ytPrivacy, setYtPrivacy] = useState("public");
    const [bufferConfigured, setBufferConfigured] = useState(false);
    const [bufferAccount, setBufferAccount] = useState(null);
    const [bufferChannels, setBufferChannels] = useState([]);
    const [selectedProvider, setSelectedProvider] = useState('buffer');

    useEffect(() => {
        let ytOk = false;
        let bufOk = false;
        apiFetch('/api/youtube/config')
            .then(r => r.json())
            .then(data => {
                if (data && data.configured) {
                    setYtDirectConfigured(true);
                    ytOk = true;
                    if (data.default_privacy) setYtPrivacy(data.default_privacy);
                    if (!bufOk) setSelectedProvider('youtube');
                }
            })
            .catch(() => {});

        apiFetch('/api/buffer/status')
            .then(r => r.json())
            .then(data => {
                if (data && data.configured) {
                    setBufferConfigured(true);
                    bufOk = true;
                    setBufferAccount(data.account);
                    setBufferChannels(data.channels || []);
                    setSelectedProvider('buffer');
                }
            })
            .catch(() => {});
    }, []);

    useEffect(() => {
        if (!jobId) return;
        apiFetch(`/api/schedule/list?job_id=${encodeURIComponent(jobId)}`)
            .then(r => r.json())
            .then(data => {
                const existing = (data?.schedules || []).find(s => s.clip_index === index && s.status === 'pending');
                if (existing) setScheduledInfo(existing);
            })
            .catch(() => {});
    }, [jobId, index]);

    const handleCancelSchedule = async () => {
        if (!scheduledInfo?.id) return;
        try {
            await apiFetch(`/api/schedule/${scheduledInfo.id}`, { method: 'DELETE' });
            setScheduledInfo(null);
        } catch (e) {
            alert('Failed to cancel schedule: ' + e.message);
        }
    };

    const handleManualExchange = async () => {
        if (!manualCode.trim()) return;
        setExchangingAuth(true);
        try {
            const isRefreshToken = manualCode.trim().startsWith('1//') || manualCode.trim().length > 60;
            const payload = isRefreshToken
                ? { refresh_token: manualCode.trim() }
                : { code: manualCode.trim() };
            const res = await apiFetch('/api/youtube/auth/exchange', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!res.ok) {
                const err = await res.text();
                throw new Error(err);
            }
            setYtDirectConfigured(true);
            setShowManualAuth(false);
            setManualCode("");
            setPostResult({ success: true, msg: "YouTube channel connected successfully!" });
        } catch (e) {
            alert('Connection failed: ' + e.message);
        } finally {
            setExchangingAuth(false);
        }
    };

    const [posting, setPosting] = useState(false);
    const [postResult, setPostResult] = useState(null);
    const [copied, setCopied] = useState(null);

    const handleCopy = async (field, text) => {
        try {
            await navigator.clipboard.writeText(text || '');
            setCopied(field);
            setTimeout(() => setCopied(null), 2000);
        } catch {
            // clipboard unavailable — silent
        }
    };

    const [isEditing, setIsEditing] = useState(false);
    const [isSubtitling, setIsSubtitling] = useState(false);
    const [isHooking, setIsHooking] = useState(false);
    const [isTranslating, setIsTranslating] = useState(false);
    const [showHookModal, setShowHookModal] = useState(false);
    const [showTranslateModal, setShowTranslateModal] = useState(false);
    const [editError, setEditError] = useState(null);

    // Pro mode: the talking-head re-edit (tighter frame on the face, dead air
    // cut, graded picture). The server renders a new file both ways, so the
    // card remounts from it exactly like after a recut.
    const isPro = clip.mode === 'pro';
    const [isSwitchingMode, setIsSwitchingMode] = useState(false);
    // Pro mode frames a face in a vertical clip: on a horizontal or square
    // one the server refuses, so the switch is not offered there. Unknown
    // until the video's metadata loads, and offered meanwhile.
    const [isUpright, setIsUpright] = useState(true);
    const canSwitchMode = Boolean(onModeChanged) && (isUpright || isPro);
    const handleMode = async () => {
        setIsSwitchingMode(true);
        setEditError(null);
        try {
            const res = await apiFetch('/api/clip/mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    job_id: jobId,
                    clip_index: index,
                    mode: isPro ? 'normal' : 'pro',
                    input_filename: serverVideoFile,
                }),
            });
            if (!res.ok) {
                let detail = '';
                try { detail = (await res.json()).detail; } catch { /* not JSON */ }
                throw new Error(typeof detail === 'string' && detail ? detail : 'Could not switch the clip mode.');
            }
            const data = await res.json();
            track('ClipModeSwitched', { props: { mode: data.mode } });
            if (onModeChanged && data.new_video_url) onModeChanged(index, data);
        } catch (e) {
            setEditError(e.message);
            setTimeout(() => setEditError(null), 6000);
        } finally {
            setIsSwitchingMode(false);
        }
    };

    const [clipDuration, setClipDuration] = useState(() => {
        const secs = clipDurationSeconds(clip);
        return Number.isFinite(secs) ? secs : 30;
    });

    // Accumulate Remotion layers across operations. A reopened project restores
    // the layers persisted in its project state, so the next edit composes over
    // them instead of silently dropping previous browser-side work.
    const [activeLayers, setActiveLayers] = useState(initialState?.active_layers || { subtitles: null, hook: null, effects: null });

    // Report edit state upward (debounced sync to the project record). Skip the
    // mount run: only user-driven changes are worth persisting.
    const stateReported = React.useRef(false);
    useEffect(() => {
        if (!stateReported.current) { stateReported.current = true; return; }
        onStateChange?.(index, { activeLayers, serverVideoFile });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeLayers, serverVideoFile]);

    // True when the current server file already carries burned-in content.
    // Browser (Remotion) renders compose over the ORIGINAL clip, so using them
    // here would silently drop those burns — chain via server FFmpeg instead.
    const hasServerBurns = /(^|_)(subtitled|hook|hooked)_/.test(serverVideoFile || '');

    // The hook currently burned into the server file (auto-hook or a manual
    // one). /api/hook REPLACES it; tracked locally so the modal stays honest
    // after edits without refetching the job.
    const [burnedHook, setBurnedHook] = useState(clip.auto_hook?.text || null);

    // Fetch clip duration from transcript endpoint
    useEffect(() => {
        if (!jobId || index === undefined) return;
        apiFetch(`/api/clip/${jobId}/${index}/transcript`)
            .then(res => res.ok ? res.json() : null)
            .then(data => {
                if (data && data.durationSec) setClipDuration(data.durationSec);
            })
            .catch(() => {});
    }, [jobId, index]);

    // Which platforms the selected profile actually has linked. `null` means
    // unknown (profile list not loaded) — in that case nothing is gated.
    const knownConnections = Array.isArray(connectedPlatforms);
    const noAccountsConnected = knownConnections && connectedPlatforms.length === 0 && !ytDirectConfigured && !bufferConfigured;
    const platformOptions = knownConnections
        ? PLATFORM_OPTIONS.map((o) => {
            if (o.value === 'youtube' && ytDirectConfigured) return o;
            if (bufferChannels.some(c => c.service?.toLowerCase() === o.value)) return o;
            if (connectedPlatforms.includes(o.value)) return o;
            if (bufferConfigured) return o;
            return { ...o, disabled: true, hint: 'not connected' };
          })
        : PLATFORM_OPTIONS;

    const handleConnectAccounts = () => {
        setShowModal(false);
        if (onConnectSocials) onConnectSocials();
        else window.open('https://app.upload-post.com', '_blank', 'noopener');
    };

    // Initialize/Reset form when modal opens
    useEffect(() => {
        if (showModal) {
            setPostTitle(clip.video_title_for_youtube_short || "Viral Short");
            setPostDescription(clip.video_description_for_instagram || clip.video_description_for_tiktok || "");
            setIsScheduling(true);
            setScheduleDate(getDefaultScheduleTime(index));
            setPostResult(null);
            // Only preselect platforms the profile can actually publish to.
            if (knownConnections) {
                const initialPlatforms = flagsFromList(connectedPlatforms);
                if (ytDirectConfigured && connectedPlatforms.length === 0) {
                    initialPlatforms.youtube = true;
                }
                setPlatforms(initialPlatforms);
            }
        }
        // Reset only when the modal opens for a clip; connection changes while
        // it is open must not wipe the user's selection.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [showModal, clip, ytDirectConfigured]);

    const handleAutoEdit = async () => {
        setIsEditing(true);
        setEditError(null);
        try {
            const apiKey = geminiApiKey || localStorage.getItem('gemini_key');

            // Managed (paid) users get the Gemini key resolved server-side;
            // only BYOK/self-host needs a local key.
            if (!apiKey && !isManaged) {
                throw new Error("Gemini API Key is missing. Please set it in Settings.");
            }
            const geminiHeaders = apiKey ? { 'X-Gemini-Key': apiKey } : {};

            // Try Remotion effects endpoint first
            const effectsRes = hasServerBurns ? null : await apiFetch('/api/effects/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...geminiHeaders
                },
                body: JSON.stringify({
                    job_id: jobId,
                    clip_index: index,
                    input_filename: serverVideoFile
                })
            });

            if (effectsRes && effectsRes.ok) {
                const data = await effectsRes.json();
                if (data.effects && data.effects.segments) {
                    const newLayers = { ...activeLayers, effects: data.effects };
                    setActiveLayers(newLayers);
                    const blobUrl = await renderInBrowser({
                        videoUrl: originalVideoUrl,
                        durationInSeconds: clipDuration,
                        subtitles: newLayers.subtitles,
                        hook: newLayers.hook,
                        effects: newLayers.effects,
                    });
                    setCurrentVideoUrl(blobUrl);
                    if (videoRef.current) videoRef.current.load();
                    return;
                }
            }

            // Fallback: legacy FFmpeg edit endpoint
            const res = await apiFetch('/api/edit', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...geminiHeaders
                },
                body: JSON.stringify({
                    job_id: jobId,
                    clip_index: index,
                    input_filename: serverVideoFile
                })
            });

            if (!res.ok) {
                const errText = await res.text();
                try {
                    const jsonErr = JSON.parse(errText);
                    throw new Error(jsonErr.detail || errText);
                } catch (e) {
                    throw new Error(errText);
                }
            }

            const data = await res.json();
            if (data.new_video_url) {
                setCurrentVideoUrl(getApiUrl(data.new_video_url));
                setServerVideoFile(data.new_video_url.split('/').pop());
                if (videoRef.current) {
                    videoRef.current.load();
                }
            }

        } catch (e) {
            setEditError(e.message);
            setTimeout(() => setEditError(null), 5000);
        } finally {
            setIsEditing(false);
        }
    };

    // Clips are captioned by default, so "no captions" has to be reachable.
    // Nothing is re-encoded: the server still holds the clean file next to the
    // captioned one and just points this clip back at it.
    const handleRemoveSubtitles = async () => {
        setIsSubtitling(true);
        setEditError(null);
        try {
            const res = await apiFetch('/api/subtitle/remove', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    job_id: jobId, clip_index: index, input_filename: serverVideoFile,
                }),
            });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            if (data.new_video_url) {
                const serverUrl = getApiUrl(data.new_video_url);
                setServerVideoFile(data.new_video_url.split('/').pop());
                const remaining = { ...activeLayers, subtitles: null };
                setActiveLayers(remaining);
                if (remaining.hook || remaining.effects) {
                    setCurrentVideoUrl(await renderInBrowser({
                        videoUrl: serverUrl,
                        durationInSeconds: clipDuration,
                        subtitles: null,
                        hook: remaining.hook,
                        effects: remaining.effects,
                    }));
                } else {
                    setCurrentVideoUrl(serverUrl);
                }
                if (videoRef.current) videoRef.current.load();
                setShowSubtitleModal(false);
            }
        } catch (e) {
            setEditError(e.message);
            setTimeout(() => setEditError(null), 5000);
        } finally {
            setIsSubtitling(false);
        }
    };

    const handleSubtitle = async (options) => {
        setIsSubtitling(true);
        setEditError(null);
        try {
            // Karaoke styles are burned server-side (ASS word-highlight render);
            // the in-browser Remotion path only handles classic styles, and only
            // when the server file has no burned-in content to preserve.
            if (options.remotion && options.style !== 'karaoke' && !hasServerBurns) {
                // Accumulate layer and render all layers together
                const newLayers = { ...activeLayers, subtitles: options.remotion };
                setActiveLayers(newLayers);
                const blobUrl = await renderInBrowser({
                    videoUrl: originalVideoUrl,
                    durationInSeconds: clipDuration,
                    subtitles: newLayers.subtitles,
                    hook: newLayers.hook,
                    effects: newLayers.effects,
                });
                setCurrentVideoUrl(blobUrl);
                if (videoRef.current) videoRef.current.load();
                setShowSubtitleModal(false);
                return;
            }

            // Fallback: legacy FFmpeg
            const res = await apiFetch('/api/subtitle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    job_id: jobId,
                    clip_index: index,
                    position: options.position,
                    font_size: options.fontSize,
                    font_name: options.fontName,
                    font_color: options.fontColor,
                    border_color: options.borderColor,
                    border_width: options.borderWidth,
                    bg_color: options.bgColor,
                    bg_opacity: options.bgOpacity,
                    style: options.style || 'classic',
                    highlight_color: options.highlightColor || '#FFD700',
                    effect: options.effect || 'none',
                    base_opacity: options.baseOpacity ?? 1.0,
                    uppercase: options.uppercase || false,
                    reveal: options.reveal || false,
                    shadow: options.shadow || 0,
                    max_chars: options.maxChars ?? null,
                    max_duration: options.maxDuration ?? null,
                    input_filename: serverVideoFile,
                    // Edited caption text (clip-relative ms); null = server
                    // regenerates from the transcript as before.
                    words: options.captions || null
                })
            });

            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            if (data.new_video_url) {
                const serverUrl = getApiUrl(data.new_video_url);
                setServerVideoFile(data.new_video_url.split('/').pop());
                // Subtitles are burned into the server file now — drop the
                // browser subtitle layer and re-compose any remaining browser
                // layers (hook/effects) over the new file so they aren't lost.
                const remaining = { ...activeLayers, subtitles: null };
                setActiveLayers(remaining);
                if (remaining.hook || remaining.effects) {
                    const blobUrl = await renderInBrowser({
                        videoUrl: serverUrl,
                        durationInSeconds: clipDuration,
                        subtitles: null,
                        hook: remaining.hook,
                        effects: remaining.effects,
                    });
                    setCurrentVideoUrl(blobUrl);
                } else {
                    setCurrentVideoUrl(serverUrl);
                }
                if (videoRef.current) videoRef.current.load();
                setShowSubtitleModal(false);
            }
        } catch (e) {
            setEditError(e.message);
            setTimeout(() => setEditError(null), 5000);
        } finally {
            setIsSubtitling(false);
        }
    };

    const handleHook = async (hookData) => {
        setIsHooking(true);
        setEditError(null);
        try {
            if (hookData.remotion && !hasServerBurns) {
                // Accumulate layer and render all layers together
                const newLayers = { ...activeLayers, hook: hookData.remotion };
                setActiveLayers(newLayers);
                const blobUrl = await renderInBrowser({
                    videoUrl: originalVideoUrl,
                    durationInSeconds: clipDuration,
                    subtitles: newLayers.subtitles,
                    hook: newLayers.hook,
                    effects: newLayers.effects,
                });
                setCurrentVideoUrl(blobUrl);
                if (videoRef.current) videoRef.current.load();
                setShowHookModal(false);
                return;
            }

            // Fallback: legacy FFmpeg
            const payload = typeof hookData === 'string'
                ? { text: hookData, position: 'top', size: 'M' }
                : hookData;

            const res = await apiFetch('/api/hook', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    job_id: jobId,
                    clip_index: index,
                    text: payload.text,
                    position: payload.position,
                    size: payload.size,
                    style: payload.style || 'pill',
                    font: payload.font || null,
                    duration_seconds: payload.remotion?.displayDurationSec ?? null,
                    input_filename: serverVideoFile
                })
            });

            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            if (data.new_video_url) {
                setCurrentVideoUrl(getApiUrl(data.new_video_url));
                setServerVideoFile(data.new_video_url.split('/').pop());
                setBurnedHook(data.burned_hook?.text ?? payload.text ?? null);
                if (videoRef.current) videoRef.current.load();
                setShowHookModal(false);
            }
        } catch (e) {
            setEditError(e.message);
            setTimeout(() => setEditError(null), 5000);
        } finally {
            setIsHooking(false);
        }
    };

    // Strip the burned hook (auto-hook or manual) off the server file.
    const handleRemoveHook = async () => {
        setIsHooking(true);
        setEditError(null);
        try {
            const res = await apiFetch('/api/hook', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    job_id: jobId,
                    clip_index: index,
                    remove: true,
                    input_filename: serverVideoFile,
                }),
            });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            if (data.new_video_url) {
                setCurrentVideoUrl(getApiUrl(data.new_video_url));
                setServerVideoFile(data.new_video_url.split('/').pop());
                setBurnedHook(null);
                if (videoRef.current) videoRef.current.load();
                setShowHookModal(false);
            }
        } catch (e) {
            setEditError(e.message);
            setTimeout(() => setEditError(null), 5000);
        } finally {
            setIsHooking(false);
        }
    };

    const handleTranslate = async (options) => {
        console.log('[Translate] Starting translation with options:', options);
        setIsTranslating(true);
        setEditError(null);
        try {
            const apiKey = elevenLabsKey;
            console.log('[Translate] API Key available:', !!apiKey);

            if (!apiKey) {
                throw new Error("ElevenLabs API Key is missing. Please set it in Settings.");
            }

            const requestBody = {
                job_id: jobId,
                clip_index: index,
                target_language: options.targetLanguage,
                input_filename: serverVideoFile
            };
            console.log('[Translate] Request body:', requestBody);
            console.log('[Translate] Sending request to /api/translate');

            const res = await apiFetch('/api/translate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-ElevenLabs-Key': apiKey
                },
                body: JSON.stringify(requestBody)
            });

            console.log('[Translate] Response status:', res.status);

            if (!res.ok) {
                const errText = await res.text();
                console.error('[Translate] Error response:', errText);
                try {
                    const jsonErr = JSON.parse(errText);
                    throw new Error(jsonErr.detail || errText);
                } catch (e) {
                    if (e.message !== errText) throw e;
                    throw new Error(errText);
                }
            }

            const data = await res.json();
            console.log('[Translate] Success response:', data);
            if (data.new_video_url) {
                setCurrentVideoUrl(getApiUrl(data.new_video_url));
                setServerVideoFile(data.new_video_url.split('/').pop());
                if (videoRef.current) {
                    videoRef.current.load();
                }
                setShowTranslateModal(false);
            }

        } catch (e) {
            console.error('[Translate] Exception:', e);
            setEditError(e.message);
            setTimeout(() => setEditError(null), 5000);
        } finally {
            setIsTranslating(false);
        }
    };

    // Managed users, BYOK upload-post, direct YouTube, or Buffer integration
    const canPost = isManaged ||
        (uploadPostKey && uploadUserId) ||
        (selectedProvider === 'buffer' && bufferConfigured) ||
        (selectedProvider === 'youtube' && ytDirectConfigured) ||
        (selectedProvider === 'both' && (bufferConfigured || ytDirectConfigured));

    const handlePost = async () => {
        if (!canPost) {
            setPostResult({ success: false, msg: "Please connect Buffer or YouTube Direct to publish/schedule." });
            return;
        }

        if (noAccountsConnected && !bufferConfigured && !ytDirectConfigured) {
            setPostResult({ success: false, msg: "Connect a social account first." });
            return;
        }

        const selectedPlatforms = Object.keys(platforms).filter(k => platforms[k]);
        if (selectedPlatforms.length === 0) {
            setPostResult({ success: false, msg: "Select at least one platform." });
            return;
        }

        if (isScheduling && !scheduleDate) {
            setPostResult({ success: false, msg: "Please select a date and time." });
            return;
        }

        setPosting(true);
        setPostResult(null);

        // If scheduling is enabled, route to our persistent auto-post scheduler
        if (isScheduling && scheduleDate) {
            try {
                const schedRes = await apiFetch('/api/schedule/clip', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        job_id: jobId,
                        clip_index: index,
                        scheduled_at: new Date(scheduleDate).toISOString(),
                        platforms: selectedPlatforms,
                        provider: selectedProvider,
                        title: postTitle,
                        description: postDescription,
                        privacy_status: ytPrivacy,
                    })
                });
                if (!schedRes.ok) {
                    const errText = await schedRes.text();
                    let detail = errText;
                    try { detail = JSON.parse(errText).detail || errText; } catch {}
                    throw new Error(detail);
                }
                const schedData = await schedRes.json();
                setScheduledInfo(schedData.schedule);
                setPostResult({
                    success: true,
                    msg: `Auto-Post scheduled for ${new Date(scheduleDate).toLocaleString()}!`,
                });
                setTimeout(() => {
                    setShowModal(false);
                    setPostResult(null);
                }, 3000);
                return;
            } catch (e) {
                setPostResult({ success: false, msg: `Scheduling Failed: ${e.message}` });
                return;
            } finally {
                setPosting(false);
            }
        }

        // Direct Buffer publishing immediately
        if (!isScheduling && (selectedProvider === 'buffer' || (selectedProvider === 'both' && bufferConfigured))) {
            try {
                const res = await apiFetch('/api/buffer/publish', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        job_id: jobId,
                        clip_index: index,
                        title: postTitle,
                        text: postDescription,
                    })
                });
                if (!res.ok) {
                    const errText = await res.text();
                    let detail = errText;
                    try { detail = JSON.parse(errText).detail || errText; } catch {}
                    throw new Error(detail);
                }
                const sent = await res.json();
                if (selectedProvider === 'buffer') {
                    setPostResult({
                        success: true,
                        msg: `Published to ${sent.results?.length || 1} Buffer channels!`,
                    });
                    setTimeout(() => {
                        setShowModal(false);
                        setPostResult(null);
                    }, 3000);
                    return;
                }
            } catch (e) {
                if (selectedProvider === 'buffer') {
                    setPostResult({ success: false, msg: `Buffer Publish Failed: ${e.message}` });
                    setPosting(false);
                    return;
                }
            }
        }

        // Direct YouTube upload immediately
        const isDirectYt = ytDirectConfigured && (selectedProvider === 'youtube' || selectedProvider === 'both');
        if (isDirectYt && !isScheduling) {
            try {
                const res = await apiFetch('/api/youtube/publish', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        job_id: jobId,
                        clip_index: index,
                        title: postTitle,
                        description: postDescription,
                        privacy_status: ytPrivacy,
                    })
                });
                if (!res.ok) {
                    const errText = await res.text();
                    let detail = errText;
                    try { detail = JSON.parse(errText).detail || errText; } catch {}
                    throw new Error(detail);
                }
                const sent = await res.json();
                const link = sent.shorts_url || sent.url;
                setPostResult({
                    success: true,
                    msg: "Published directly to YouTube Shorts!",
                    url: link,
                });
                return;
            } catch (e) {
                setPostResult({ success: false, msg: `YouTube Upload Failed: ${e.message}` });
                return;
            } finally {
                setPosting(false);
            }
        }

        try {
            const payload = {
                job_id: jobId,
                clip_index: index,
                api_key: uploadPostKey,
                user_id: uploadUserId,
                platforms: selectedPlatforms,
                title: postTitle,
                description: postDescription
            };

            if (isScheduling && scheduleDate) {
                // Convert to ISO-8601
                payload.scheduled_date = new Date(scheduleDate).toISOString();
                // Optional: pass timezone if needed, backend defaults to UTC or we can send user's timezone
                payload.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
            }

            const res = await apiFetch('/api/social/post', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const errText = await res.text();
                let detail = errText;
                try { detail = JSON.parse(errText).detail || errText; } catch { /* not JSON */ }
                throw new Error(detail);
            }

            const sent = await res.json().catch(() => ({}));
            if (sent?.shorts_url || sent?.url) {
                setPostResult({
                    success: true,
                    msg: "Published to YouTube!",
                    url: sent.shorts_url || sent.url,
                });
                return;
            }
            if (isScheduling || !sent?.request_id) {
                setPostResult({ success: true, msg: isScheduling ? "Scheduled successfully!" : "Sent for publishing." });
                setTimeout(() => {
                    setShowModal(false);
                    setPostResult(null);
                }, 3000);
                return;
            }
            // A 200 only means Upload-Post took the file: follow the post to
            // its real end, so a platform that fails says so here.
            setPostResult({ success: true, msg: "Publishing…" });
            const outcome = await followPost(sent.request_id);
            if (outcome.failed.length) {
                setPostResult({ success: false, msg: `Failed on ${outcome.failed.join('; ')}` });
                track('SocialPostFailed', { props: { platforms: selectedPlatforms.join(',') } });
            } else {
                setPostResult({ success: true, msg: outcome.done ? "Posted successfully!" : "Still publishing: check your accounts in a few minutes." });
                setTimeout(() => {
                    setShowModal(false);
                    setPostResult(null);
                }, 3000);
            }

        } catch (e) {
            setPostResult({ success: false, msg: `Failed: ${e.message}` });
        } finally {
            setPosting(false);
        }
    };

    // Browser-rendered previews (Remotion) live in a blob: URL that exists only
    // in this tab, so they always win over the durable copy.
    const playbackUrl = (durableSrc && !durableFailed && !String(currentVideoUrl || '').startsWith('blob:'))
        ? durableSrc
        : currentVideoUrl;

    const durationReadout = formatDuration(clip);

    return (
        <div className="card overflow-hidden flex flex-col md:flex-row group hover:border-rule2 transition-colors animate-fade md:min-h-[420px]" style={{ animationDelay: `${index * 0.1}s` }}>
            {/* Left: Video Preview — 9:16 column matching the fixed card height */}
            {/* A full-width 9:16 preview on a phone is ~640px tall on its own,
                which pushed the title, captions and every action off-screen.
                Capping the height and centring keeps the whole card scannable
                without letterboxing the clip. */}
            <div className="w-full max-w-[calc(64vh*0.5625)] md:max-w-none mx-auto md:mx-0 md:w-[236px] bg-black relative shrink-0 aspect-[9/16] md:aspect-auto group/video">
                <video
                    ref={videoRef}
                    src={playbackUrl}
                    controls
                    className="w-full h-full object-contain"
                    playsInline
                    onLoadedMetadata={(e) => {
                        if (e.target.videoWidth) {
                            setResolution(`${e.target.videoWidth}×${e.target.videoHeight}`);
                            setIsUpright(e.target.videoHeight > e.target.videoWidth);
                        }
                    }}
                    onError={() => {
                        // The durable copy is unreachable (signature expired after an
                        // hour on an idle tab, object purged) → serve from the API for
                        // the rest of this card's life.
                        if (playbackUrl === durableSrc) {
                            setDurableFailed(true);
                            return;
                        }
                        // Local /videos/ file gone (e.g. cleaned up after a reload) →
                        // fall back to the durable R2 copy for managed users. If the
                        // durable URL hasn't loaded yet, the effect above retries.
                        if (durable?.url && currentVideoUrl !== durable.url) setCurrentVideoUrl(durable.url);
                        else setVideoErrored(true);
                    }}
                    onPlay={() => {
                        setHasPlayed(true);
                        const currentTime = videoRef.current ? videoRef.current.currentTime : 0;
                        onPlay && onPlay(clip.start + currentTime);
                    }}
                    onPause={() => onPause && onPause()}
                    onEnded={() => {
                        if (videoRef.current) {
                            videoRef.current.currentTime = 0;
                            videoRef.current.play();
                        }
                    }}
                />
                <div className="absolute top-3 left-3 flex gap-2">
                    {/* Stays the clip's own number, not its rank: the cards are
                        ordered by score, but this is what the downloaded file
                        is called (clip-N.mp4) and what every api call indexes. */}
                    <span className="bg-black/70 text-ink font-mono text-micro uppercase px-2 py-1 rounded-full">
                        Clip {index + 1}
                    </span>
                    {/* A bare number on a thumbnail reads as a duration, a
                        position, anything — it has to name itself and carry
                        its scale, or it is decoration. */}
                    {Number.isFinite(clip.predicted_score) && (
                        <span
                            className="bg-black/70 font-mono text-micro uppercase px-2 py-1 rounded-full flex items-center gap-1"
                            title="openshorts' prediction of how well this clip will perform, from 0 to 100"
                        >
                            <TrendingUp size={11} className="shrink-0 text-muted" />
                            <span className="text-muted">viral</span>
                            <b className={
                                clip.predicted_score >= 80 ? 'text-ok'
                                    : clip.predicted_score >= 65 ? 'text-brass'
                                        : 'text-ink2'
                            }>
                                {clip.predicted_score}
                            </b>
                            <span className="text-muted">/100</span>
                        </span>
                    )}
                </div>

                {/* Auto Edit Overlay if Processing */}
                {isEditing && (
                    <div className="absolute inset-0 bg-black/70 flex flex-col items-center justify-center z-10 p-4 text-center">
                        <Loader2 size={28} className="text-brass animate-spin mb-3" />
                        <span className="text-xs text-ink lowercase">ai magic in progress…</span>
                        <span className="readout mt-1.5">APPLYING VIRAL EDITS · ZOOMS</span>
                    </div>
                )}
            </div>

            {/* Right: Content & Details */}
            <div className="flex-1 p-4 md:p-5 flex flex-col overflow-hidden min-w-0">
                <div className="mb-4">
                    <h3 className="text-base font-medium text-ink leading-tight line-clamp-2 mb-2 break-words" title={clip.video_title_for_youtube_short}>
                        {clip.video_title_for_youtube_short || "Viral Clip Generated"}
                    </h3>
                    {/* The score alone says how much, not why. One line from
                        the selection pass on what this moment has going for it. */}
                    {clip.why && (
                        <div
                            className="relative mb-2"
                            onMouseEnter={() => setWhyOpen(true)}
                            onMouseLeave={() => setWhyOpen(false)}
                        >
                            <p
                                ref={whyRef}
                                className={`text-xs text-muted leading-snug line-clamp-2 break-words ${whyClamped ? 'cursor-pointer' : ''}`}
                                onClick={() => whyClamped && setWhyOpen(v => !v)}
                                aria-label="why openshorts picked this moment"
                            >
                                {clip.why}
                            </p>
                            {whyClamped && whyOpen && (
                                <div
                                    role="tooltip"
                                    className="absolute left-0 right-0 top-full mt-1 z-20 bg-paper border border-rule rounded-input px-3 py-2 text-xs text-ink leading-snug shadow-lg"
                                >
                                    {clip.why}
                                </div>
                            )}
                        </div>
                    )}
                    <div className="flex flex-wrap gap-1.5">
                        {durationReadout && <span className="readout bg-paper3 px-2 py-0.5 rounded-full shrink-0">{durationReadout}</span>}
                        {resolution && <span className="readout bg-paper3 px-2 py-0.5 rounded-full shrink-0">{resolution}</span>}
                        {isPro && <span className="readout bg-paper3 px-2 py-0.5 rounded-full shrink-0 text-brass">pro mode</span>}
                        {!isPro && clip.pro_suggested && <span className="readout bg-paper3 px-2 py-0.5 rounded-full shrink-0 text-brass">pro recommended</span>}
                        {getClipHashtags(clip).slice(0, 4).map((tag, tagIdx) => (
                            <button
                                key={tagIdx}
                                type="button"
                                onClick={() => handleCopy(`tag-${tag}`, tag)}
                                title={`Click to copy ${tag}`}
                                className="readout bg-paper3 hover:bg-brass/20 text-ink2 hover:text-brass px-2 py-0.5 rounded-full shrink-0 transition-colors flex items-center gap-1 cursor-pointer"
                            >
                                {copied === `tag-${tag}` ? <Check size={10} className="text-ok" /> : <Hash size={10} />}
                                {tag.replace(/^#/, '')}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Caption & Metadata with 1-Click Copy */}
                <div className="flex-1 min-h-0 space-y-2 mb-4">
                    {/* Caption Row */}
                    <div className="bg-paper rounded-input px-3 py-2 border border-rule flex items-start gap-2 min-w-0">
                        <span className="eyebrow shrink-0 mt-0.5">CAPTION</span>
                        <p className="text-xs text-ink2 line-clamp-2 flex-1 min-w-0 leading-relaxed">
                            {getClipCaption(clip)}
                        </p>
                        <button
                            onClick={() => handleCopy('caption', getClipCaption(clip))}
                            aria-label="copy caption"
                            className="p-1 rounded-full text-muted hover:text-brass transition-colors shrink-0"
                            title="Copy clean caption"
                        >
                            {copied === 'caption' ? <Check size={14} className="text-ok" /> : <Copy size={14} />}
                        </button>
                    </div>

                    {/* Hashtags Row */}
                    <div className="bg-paper rounded-input px-3 py-2 border border-rule flex items-center gap-2 min-w-0 overflow-hidden">
                        <span className="eyebrow shrink-0">HASHTAGS</span>
                        <p className="text-xs text-brass font-mono truncate flex-1 min-w-0">
                            {getClipHashtags(clip).join(' ')}
                        </p>
                        <button
                            onClick={() => handleCopy('hashtags', getClipHashtags(clip).join(' '))}
                            aria-label="copy all hashtags"
                            className="p-1 rounded-full text-muted hover:text-brass transition-colors shrink-0"
                            title="Copy all hashtags"
                        >
                            {copied === 'hashtags' ? <Check size={14} className="text-ok" /> : <Copy size={14} />}
                        </button>
                    </div>

                    {/* YouTube Title Row */}
                    <div className="bg-paper rounded-input px-3 py-2 border border-rule flex items-center gap-2 min-w-0 overflow-hidden">
                        <span className="eyebrow shrink-0">TITLE</span>
                        <p className="text-xs text-ink2 truncate flex-1 min-w-0">
                            {clip.video_title_for_youtube_short || "Viral Short Video"}
                        </p>
                        <button
                            onClick={() => handleCopy('youtube', clip.video_title_for_youtube_short || "Viral Short Video")}
                            aria-label="copy title"
                            className="p-1 rounded-full text-muted hover:text-brass transition-colors shrink-0"
                            title="Copy YouTube Short title"
                        >
                            {copied === 'youtube' ? <Check size={14} className="text-ok" /> : <Copy size={14} />}
                        </button>
                    </div>

                    <button
                        onClick={() => setShowDescModal(true)}
                        className="w-full flex items-center justify-center gap-2 py-2 rounded-input border border-dashed border-rule text-xs lowercase text-muted hover:text-brass hover:border-rule2 transition-colors"
                    >
                        <FileText size={14} /> view all copy & hashtags
                    </button>
                </div>

                {/* Error Message */}
                {editError && (
                    <div className="mb-3 px-3 py-2 rounded-input text-xs text-danger bg-[color-mix(in_oklab,var(--color-danger)_10%,transparent)] flex items-center gap-2">
                        <AlertCircle size={14} className="shrink-0" />
                        {editError}
                    </div>
                )}

                {canSwitchMode && !isPro && clip.pro_suggested && (
                    <button
                        onClick={handleMode}
                        disabled={isSwitchingMode}
                        className="mb-3 w-full flex items-center gap-3 px-3 py-2.5 rounded-input border border-brass bg-brass/10 hover:bg-brass/20 text-left transition-colors disabled:opacity-70"
                    >
                        {isSwitchingMode
                            ? <Loader2 size={20} className="animate-spin text-brass shrink-0" />
                            : <Sparkles size={20} className="text-brass shrink-0" />}
                        <span className="min-w-0">
                            <span className="block text-sm font-semibold text-ink">
                                {isSwitchingMode ? 'Rendering pro mode…' : 'Try pro mode on this clip'}
                            </span>
                            <span className="block text-[11px] leading-snug text-ink2">
                                One person talking: tighter frame on the face, pauses cut, cinematic look. One click back to normal.
                            </span>
                        </span>
                    </button>
                )}
                {canSwitchMode && (isPro || !clip.pro_suggested) && (
                    <p className="mb-2 text-[11px] leading-snug text-muted">
                        {isPro
                            ? 'Pro mode is on: tighter frame on the face, pauses cut, cinematic look. You can switch back to normal any time.'
                            : 'Pro mode is recommended only for podcasts and talking-head clips, where the picture is one person speaking.'}
                    </p>
                )}

                {scheduledInfo && (
                    <div className="mb-3 px-3 py-2 rounded-input bg-brass/10 border border-brass/40 flex items-center justify-between gap-2 text-xs animate-fade">
                        <span className="flex items-center gap-1.5 text-ink font-medium">
                            <Calendar size={14} className="text-brass shrink-0" />
                            <span>Auto-Post: {new Date(scheduledInfo.scheduled_at).toLocaleDateString()} at {new Date(scheduledInfo.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                        </span>
                        <button
                            type="button"
                            onClick={handleCancelSchedule}
                            className="text-[11px] text-danger hover:underline font-semibold shrink-0"
                        >
                            cancel
                        </button>
                    </div>
                )}

                {/* Actions Footer */}
                <div className="grid grid-cols-[repeat(auto-fill,minmax(104px,1fr))] gap-2 mt-auto pt-4 border-t border-rule">
                    {onEditClip && (
                        <button
                            onClick={() => onEditClip(index)}
                            className={QUIET_BTN}
                        >
                            <Scissors size={16} className="text-muted group-hover:text-brass transition-colors shrink-0" />
                            edit clip
                        </button>
                    )}

                    {onReframeClip && (
                        <button
                            onClick={() => onReframeClip(index)}
                            className={QUIET_BTN}
                        >
                            <Crosshair size={16} className="text-muted group-hover:text-brass transition-colors shrink-0" />
                            reframing
                        </button>
                    )}

                    {canSwitchMode && (
                        <button
                            onClick={handleMode}
                            disabled={isSwitchingMode}
                            title="Pro mode: tighter frame on the face, pauses cut, cinematic look. Recommended for podcasts and talking-head clips."
                            className={!isPro && clip.pro_suggested
                                ? 'btn-primary flex-col gap-1 py-2.5 sm:py-2 px-1 text-[11px] leading-none rounded-input whitespace-nowrap'
                                : QUIET_BTN}
                        >
                            {isSwitchingMode
                                ? <Loader2 size={16} className={`animate-spin shrink-0 ${!isPro && clip.pro_suggested ? '' : 'text-brass'}`} />
                                : <Sparkles size={16} className={!isPro && clip.pro_suggested ? 'shrink-0' : `${isPro ? 'text-brass' : 'text-muted'} group-hover:text-brass transition-colors shrink-0`} />}
                            {isSwitchingMode ? 'rendering…' : isPro ? 'normal mode' : 'pro mode'}
                        </button>
                    )}

                    <button
                        onClick={handleAutoEdit}
                        disabled={isEditing}
                        className={QUIET_BTN}
                    >
                        {isEditing ? <Loader2 size={16} className="animate-spin text-brass shrink-0" /> : <Wand2 size={16} className="text-muted group-hover:text-brass transition-colors shrink-0" />}
                        {isEditing ? 'editing…' : 'auto edit'}
                    </button>

                    <button
                        onClick={() => setShowSubtitleModal(true)}
                        disabled={isSubtitling}
                        className={QUIET_BTN}
                    >
                        {isSubtitling ? <Loader2 size={16} className="animate-spin text-brass shrink-0" /> : <Type size={16} className="text-muted group-hover:text-brass transition-colors shrink-0" />}
                        {isSubtitling ? 'adding…' : 'subtitles'}
                    </button>

                    <button
                        onClick={() => setShowHookModal(true)}
                        disabled={isHooking}
                        className={QUIET_BTN}
                    >
                        {isHooking ? <Loader2 size={16} className="animate-spin text-brass shrink-0" /> : <Wand2 size={16} className="text-muted group-hover:text-brass transition-colors shrink-0" />}
                        {isHooking ? 'saving…' : 'edit hook'}
                    </button>

                    <button
                        onClick={() => setShowTranslateModal(true)}
                        disabled={isTranslating}
                        className={QUIET_BTN}
                    >
                        {isTranslating ? <Loader2 size={16} className="animate-spin text-brass shrink-0" /> : <Languages size={16} className="text-muted group-hover:text-brass transition-colors shrink-0" />}
                        {isTranslating ? 'translating…' : 'dub voice'}
                    </button>

                    <button
                        onClick={() => {
                            setIsScheduling(false);
                            setShowModal(true);
                        }}
                        className="btn-primary flex-col gap-1 py-2.5 sm:py-2 px-1 text-[11px] leading-none rounded-input whitespace-nowrap"
                        title="Publish this clip now"
                    >
                        <Share2 size={16} className="shrink-0" /> publish
                    </button>
                    <button
                        onClick={() => {
                            setIsScheduling(true);
                            setShowModal(true);
                        }}
                        className="btn-primary flex-col gap-1 py-2.5 sm:py-2 px-1 text-[11px] leading-none rounded-input whitespace-nowrap bg-brass/20 text-brass hover:bg-brass hover:text-paper border border-brass/40"
                        title="Schedule this clip to auto-post at a specific date & time"
                    >
                        <Calendar size={16} className="shrink-0" /> schedule
                    </button>
                    <button
                        onClick={(e) => {
                            e.preventDefault();
                            // Free clips are watermarked — surface the upsell once
                            // before the first download, then get out of the way.
                            if (plan === 'free' && !watermarkNoticeDismissed(jobId)) {
                                setShowWatermarkModal(true);
                                return;
                            }
                            downloadClip();
                        }}
                        className={`${QUIET_BTN}${onEditClip ? ' col-span-2' : ''}`}
                    >
                        <Download size={16} className="text-muted group-hover:text-brass transition-colors shrink-0" />
                        {downloadPct === null ? 'download' : `downloading ${downloadPct}%`}
                    </button>
                </div>
            </div>

            {/* Descriptions & Hashtags Studio Modal */}
            <Modal
                isOpen={showDescModal}
                onClose={() => setShowDescModal(false)}
                eyebrow="CAPTION & HASHTAGS STUDIO"
                title="copy & tags"
                size="md"
            >
                <div className="space-y-4">
                    {/* Clean Caption */}
                    <div>
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                            <label className="eyebrow flex items-center gap-1.5 text-brass">
                                <Sparkles size={13} /> PUNCHY CAPTION
                            </label>
                            <button
                                onClick={() => handleCopy('caption-clean', getClipCaption(clip))}
                                aria-label="copy caption"
                                className="p-1 rounded-full text-muted hover:text-brass transition-colors shrink-0 flex items-center gap-1 text-xs"
                            >
                                {copied === 'caption-clean' ? <><Check size={14} className="text-ok" /><span className="text-ok text-[11px]">copied!</span></> : <><Copy size={14} /><span className="text-[11px]">copy</span></>}
                            </button>
                        </div>
                        <p className="text-sm text-ink2 select-all break-words bg-paper rounded-input p-3 border border-rule leading-relaxed">
                            {getClipCaption(clip)}
                        </p>
                    </div>

                    {/* Viral Hashtags */}
                    <div>
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                            <label className="eyebrow flex items-center gap-1.5 text-brass">
                                <Hash size={13} /> VIRAL HASHTAGS
                            </label>
                            <button
                                onClick={() => handleCopy('hashtags-all', getClipHashtags(clip).join(' '))}
                                aria-label="copy all hashtags"
                                className="p-1 rounded-full text-muted hover:text-brass transition-colors shrink-0 flex items-center gap-1 text-xs"
                            >
                                {copied === 'hashtags-all' ? <><Check size={14} className="text-ok" /><span className="text-ok text-[11px]">copied!</span></> : <><Copy size={14} /><span className="text-[11px]">copy all</span></>}
                            </button>
                        </div>
                        <div className="bg-paper rounded-input p-3 border border-rule space-y-2">
                            <div className="flex flex-wrap gap-1.5">
                                {getClipHashtags(clip).map((tag, idx) => (
                                    <button
                                        key={idx}
                                        type="button"
                                        onClick={() => handleCopy(`modal-tag-${tag}`, tag)}
                                        title={`Click to copy ${tag}`}
                                        className="text-xs bg-paper3 hover:bg-brass/20 text-brass hover:text-ink px-2.5 py-1 rounded-full font-mono transition-colors flex items-center gap-1 cursor-pointer"
                                    >
                                        {copied === `modal-tag-${tag}` ? <Check size={11} className="text-ok" /> : <Hash size={11} />}
                                        {tag.replace(/^#/, '')}
                                    </button>
                                ))}
                            </div>
                            <p className="text-[11px] text-muted font-mono select-all pt-1 border-t border-rule/50">
                                {getClipHashtags(clip).join(' ')}
                            </p>
                        </div>
                    </div>

                    {/* YouTube Shorts Title */}
                    <div>
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                            <label className="eyebrow flex items-center gap-1.5">
                                <Youtube size={13} className="text-red-500" /> YOUTUBE TITLE
                            </label>
                            <button
                                onClick={() => handleCopy('youtube', clip.video_title_for_youtube_short || "Viral Short Video")}
                                aria-label="copy youtube title"
                                className="p-1 rounded-full text-muted hover:text-brass transition-colors shrink-0 flex items-center gap-1 text-xs"
                            >
                                {copied === 'youtube' ? <><Check size={14} className="text-ok" /><span className="text-ok text-[11px]">copied!</span></> : <><Copy size={14} /><span className="text-[11px]">copy</span></>}
                            </button>
                        </div>
                        <p className="text-sm text-ink2 select-all break-words bg-paper rounded-input p-3 border border-rule">
                            {clip.video_title_for_youtube_short || "Viral Short Video"}
                        </p>
                    </div>

                    {/* Full All-In-One Copy */}
                    <div>
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                            <label className="eyebrow">READY-TO-POST (CAPTION + HASHTAGS)</label>
                            <button
                                onClick={() => handleCopy('caption-full', `${getClipCaption(clip)}\n\n${getClipHashtags(clip).join(' ')}`)}
                                aria-label="copy full description"
                                className="p-1 rounded-full text-muted hover:text-brass transition-colors shrink-0 flex items-center gap-1 text-xs"
                            >
                                {copied === 'caption-full' ? <><Check size={14} className="text-ok" /><span className="text-ok text-[11px]">copied!</span></> : <><Copy size={14} /><span className="text-[11px]">copy all</span></>}
                            </button>
                        </div>
                        <p className="text-xs text-ink2 select-all break-words bg-paper rounded-input p-3 border border-rule whitespace-pre-wrap leading-relaxed">
                            {`${getClipCaption(clip)}\n\n${getClipHashtags(clip).join(' ')}`}
                        </p>
                    </div>
                </div>
            </Modal>

            {/* Post Modal */}
            <Modal
                isOpen={showModal}
                onClose={() => setShowModal(false)}
                eyebrow="PUBLISH"
                title="post clip"
                size="md"
                footer={
                    (selectedProvider === 'youtube' && !ytDirectConfigured && !uploadPostKey) ? (
                        <a
                            href="/api/youtube/auth/login"
                            className="btn-primary w-full flex items-center justify-center gap-2 py-2.5 text-xs text-center font-medium"
                        >
                            <Youtube size={16} /> 1-Click Connect YouTube Channel
                        </a>
                    ) : (noAccountsConnected && !platforms.youtube && !bufferConfigured) ? (
                        <button onClick={handleConnectAccounts} className="btn-primary w-full">
                            <Link2 size={16} /> connect accounts
                        </button>
                    ) : (
                        <button
                            onClick={handlePost}
                            disabled={posting || !canPost}
                            className="btn-primary w-full"
                        >
                            {posting ? <><Loader2 size={16} className="animate-spin" /> {isScheduling ? 'scheduling…' : 'publishing…'}</> : <><Share2 size={16} /> {isScheduling ? 'schedule post' : 'publish now'}</>}
                        </button>
                    )
                }
            >
                {/* Publishing Service Selector */}
                <div className="mb-4 p-3 rounded-input bg-paper border border-rule space-y-2">
                    <div className="flex items-center justify-between">
                        <label className="eyebrow block">PUBLISHING SERVICE</label>
                        <span className="text-[11px] text-muted">
                            {selectedProvider === 'buffer' ? (bufferConfigured ? `${bufferChannels.length} Buffer channels ready` : 'Buffer not configured') :
                             selectedProvider === 'youtube' ? (ytDirectConfigured ? 'YouTube Direct ready' : 'YouTube OAuth required') :
                             'Both services'}
                        </span>
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                        <button
                            type="button"
                            onClick={() => setSelectedProvider('buffer')}
                            className={`py-2 px-2 text-xs rounded-input font-medium flex items-center justify-center gap-1.5 border transition-all ${
                                selectedProvider === 'buffer'
                                    ? 'bg-brass/10 border-brass text-brass'
                                    : 'bg-paper hover:bg-hover border-rule text-muted hover:text-ink'
                            }`}
                        >
                            <Share2 size={13} /> Buffer {bufferConfigured ? '✓' : ''}
                        </button>
                        <button
                            type="button"
                            onClick={() => setSelectedProvider('youtube')}
                            className={`py-2 px-2 text-xs rounded-input font-medium flex items-center justify-center gap-1.5 border transition-all ${
                                selectedProvider === 'youtube'
                                    ? 'bg-red-500/10 border-red-500 text-red-500'
                                    : 'bg-paper hover:bg-hover border-rule text-muted hover:text-ink'
                            }`}
                        >
                            <Youtube size={13} /> YouTube Direct {ytDirectConfigured ? '✓' : ''}
                        </button>
                        <button
                            type="button"
                            onClick={() => setSelectedProvider('both')}
                            className={`py-2 px-2 text-xs rounded-input font-medium flex items-center justify-center gap-1.5 border transition-all ${
                                selectedProvider === 'both'
                                    ? 'bg-ink/10 border-ink text-ink font-semibold'
                                    : 'bg-paper hover:bg-hover border-rule text-muted hover:text-ink'
                            }`}
                        >
                            Both / All
                        </button>
                    </div>
                </div>

                {selectedProvider !== 'buffer' && platforms.youtube && !ytDirectConfigured && (
                    <div className="mb-4 p-3 rounded-input text-xs bg-paper border border-brass/50 space-y-2.5 animate-fade">
                        <div className="flex items-center justify-between">
                            <span className="font-semibold text-ink flex items-center gap-1.5">
                                <Youtube size={16} className="text-red-500" /> YouTube Direct Publishing
                            </span>
                            <span className="badge-quiet text-[10px] text-warn">1-Click OAuth</span>
                        </div>
                        <p className="text-xs text-muted leading-relaxed">
                            Authorize your YouTube channel in 1 click to upload and auto-schedule this clip directly to YouTube Shorts.
                        </p>
                        <a
                            href="/api/youtube/auth/login"
                            className="btn-primary w-full flex items-center justify-center gap-2 py-2 text-xs font-medium"
                        >
                            <Youtube size={14} /> 1-Click Connect YouTube Channel
                        </a>

                        <div className="pt-1 border-t border-rule/50">
                            <button
                                type="button"
                                onClick={() => setShowManualAuth(!showManualAuth)}
                                className="text-[11px] text-brass hover:underline flex items-center gap-1 font-medium"
                            >
                                {showManualAuth ? '▾ Hide manual code entry' : '▸ OAuth blocked or redirect error? Enter Auth Code / Token'}
                            </button>
                            {showManualAuth && (
                                <div className="mt-2 space-y-2 animate-fade">
                                    <p className="text-[10px] text-muted">
                                        Paste authorization code or refresh token to connect without redirect issues:
                                    </p>
                                    <div className="flex gap-2">
                                        <input
                                            type="text"
                                            value={manualCode}
                                            onChange={(e) => setManualCode(e.target.value)}
                                            placeholder="Paste code (4/...) or token (1//...)"
                                            className="input-field text-xs py-1.5 flex-1"
                                        />
                                        <button
                                            type="button"
                                            disabled={exchangingAuth || !manualCode.trim()}
                                            onClick={handleManualExchange}
                                            className="btn-primary px-3 py-1.5 text-xs shrink-0"
                                        >
                                            {exchangingAuth ? 'saving…' : 'connect'}
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {selectedProvider !== 'youtube' && bufferConfigured && (
                    <div className="mb-4 p-3 rounded-input text-xs bg-paper border border-brass/40 space-y-2 animate-fade">
                        <div className="flex items-center justify-between">
                            <span className="font-semibold text-ink flex items-center gap-1.5">
                                <Share2 size={15} className="text-brass" /> Buffer Publishing
                            </span>
                            <span className="badge-ok text-[10px]">
                                {bufferChannels.length} {bufferChannels.length === 1 ? 'channel' : 'channels'} active
                            </span>
                        </div>
                        {bufferChannels.length === 0 ? (
                            <p className="text-[11px] text-muted leading-relaxed">
                                Buffer account connected ({bufferAccount?.email || 'authenticated'}). You can link social channels on <a href="https://publish.buffer.com/channels" target="_blank" rel="noopener noreferrer" className="text-brass underline">buffer.com</a> to publish across networks.
                            </p>
                        ) : (
                            <div className="flex flex-wrap gap-1.5 pt-1">
                                {bufferChannels.map(ch => (
                                    <span key={ch.id} className="badge-quiet text-[10px] px-1.5 py-0.5">
                                        {ch.service} ({ch.name || ch.type})
                                    </span>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {!canPost && (
                    <div className="mb-4 px-3 py-2 rounded-input text-xs text-warn bg-[color-mix(in_oklab,var(--color-warn)_10%,transparent)] flex items-start gap-2">
                        <AlertCircle size={14} className="mt-0.5 shrink-0" />
                        <div className="lowercase">configure api key in settings or youtube credentials in .env first.</div>
                    </div>
                )}

                {noAccountsConnected && !platforms.youtube && (
                    <div className="mb-4 px-3 py-2 rounded-input text-xs text-warn bg-[color-mix(in_oklab,var(--color-warn)_10%,transparent)] flex items-start gap-2">
                        <AlertCircle size={14} className="mt-0.5 shrink-0" />
                        <div className="lowercase">no social accounts connected yet — link tiktok, instagram, youtube, facebook, linkedin, threads or bluesky to publish this clip.</div>
                    </div>
                )}

                {/* Both the title/description fields below and the schedule
                    button are downstream of this: on a tiktok draft neither
                    travels. See TikTokDraftNotice. */}
                {platforms.tiktok && <TikTokDraftNotice />}

                <div className="space-y-4">
                    {/* Title & Description */}
                    <div>
                        <label className="eyebrow block mb-1.5">TITLE</label>
                        <input
                            type="text"
                            value={postTitle}
                            onChange={(e) => setPostTitle(e.target.value)}
                            className="input-field"
                            placeholder="enter a catchy title…"
                        />
                    </div>

                    <div>
                        <label className="eyebrow block mb-1.5">CAPTION</label>
                        <textarea
                            value={postDescription}
                            onChange={(e) => setPostDescription(e.target.value)}
                            rows={4}
                            className="input-field resize-none"
                            placeholder="write a caption for your post…"
                        />
                    </div>

                    {/* Scheduling */}
                    <div className="p-3 bg-paper rounded-input border border-rule">
                        <label className="flex items-center justify-between cursor-pointer">
                            <span className="flex items-center gap-2 text-sm text-ink2 lowercase">
                                <Calendar size={16} className={isScheduling ? 'text-brass' : 'text-muted'} /> schedule post
                            </span>
                            <input
                                type="checkbox"
                                checked={isScheduling}
                                onChange={(e) => setIsScheduling(e.target.checked)}
                                className="w-4 h-4 accent-brass cursor-pointer"
                            />
                        </label>

                        {isScheduling && (
                            <div className="mt-3 animate-fade">
                                <label className="eyebrow block mb-1.5">DATE · TIME</label>
                                <input
                                    type="datetime-local"
                                    value={scheduleDate}
                                    onChange={(e) => setScheduleDate(e.target.value)}
                                    className="input-field [color-scheme:dark]"
                                />
                            </div>
                        )}
                    </div>

                    {/* Platforms */}
                    <div>
                        <label className="eyebrow block mb-2">PLATFORMS</label>
                        <SegmentedControl
                            multi
                            columns={4}
                            options={platformOptions}
                            value={Object.keys(platforms).filter(k => platforms[k])}
                            onChange={(arr) => setPlatforms(flagsFromList(arr))}
                        />
                    </div>

                    {platforms.youtube && (
                        <div className="p-3 bg-paper rounded-input border border-rule space-y-2 animate-fade">
                            <div className="flex items-center justify-between text-xs text-ink2">
                                <span className="eyebrow flex items-center gap-1.5"><Youtube size={14} className="text-red-500" /> YOUTUBE PRIVACY</span>
                                {ytDirectConfigured ? (
                                    <span className="badge-quiet text-[10px] text-ok border border-ok/30 px-1.5 py-0.5 rounded flex items-center gap-1">
                                        <Check size={10} /> Direct API Connected
                                    </span>
                                ) : (
                                    <a href="/api/youtube/auth/login" className="text-[10px] text-brass hover:underline flex items-center gap-1 font-medium">
                                        <Youtube size={12} /> 1-Click Connect →
                                    </a>
                                )}
                            </div>
                            <div className="flex gap-2">
                                {['public', 'unlisted', 'private'].map((p) => (
                                    <button
                                        key={p}
                                        type="button"
                                        onClick={() => setYtPrivacy(p)}
                                        className={`px-3 py-1 text-xs rounded capitalize transition-colors ${ytPrivacy === p ? 'bg-brass text-paper font-semibold' : 'bg-surface2 text-ink2 hover:bg-surface3'}`}
                                    >
                                        {p}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {postResult && (
                        <div className={`space-y-1.5 p-3 rounded-input text-xs ${postResult.success ? 'badge-ok' : 'badge-danger'}`}>
                            <div className="flex items-center gap-1.5">
                                {postResult.success ? <Check size={14} className="shrink-0 text-ok" /> : <AlertCircle size={14} className="shrink-0 text-danger" />}
                                <span className="font-medium">{postResult.msg}</span>
                            </div>
                            {postResult.url && (
                                <div className="pt-1">
                                    <a
                                        href={postResult.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-xs text-brass hover:underline break-all font-mono"
                                    >
                                        {postResult.url} ↗
                                    </a>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </Modal>

            <SubtitleModal
                isOpen={showSubtitleModal}
                onClose={() => setShowSubtitleModal(false)}
                onGenerate={handleSubtitle}
                onApplyAll={onBulkSubtitle ? async (options) => {
                    await onBulkSubtitle(options);
                    setShowSubtitleModal(false);
                } : undefined}
                onRemove={handleRemoveSubtitles}
                bulkCount={clipCount}
                bulkProgress={bulkProgress}
                isProcessing={isSubtitling || (bulkProgress?.running ?? false)}
                videoUrl={originalVideoUrl}
                jobId={jobId}
                clipIndex={index}
                existingHook={activeLayers.hook}
            />

            <HookModal
                isOpen={showHookModal}
                onClose={() => setShowHookModal(false)}
                onGenerate={handleHook}
                isProcessing={isHooking}
                videoUrl={originalVideoUrl}
                initialText={clip.viral_hook_text}
                durationInSeconds={clip.end && clip.start ? clip.end - clip.start : 30}
                existingSubtitles={activeLayers.subtitles}
                hasCaptions={!!activeLayers.subtitles || /(^|_)subtitled_/.test(serverVideoFile || '')}
                serverRender={hasServerBurns}
                burnedHook={burnedHook}
                onRemove={burnedHook ? handleRemoveHook : null}
            />

            <TranslateModal
                isOpen={showTranslateModal}
                onClose={() => setShowTranslateModal(false)}
                onTranslate={handleTranslate}
                isProcessing={isTranslating}
                videoUrl={currentVideoUrl}
                hasApiKey={!!elevenLabsKey}
            />

            {showWatermarkModal && (
                <WatermarkModal
                    source="download"
                    jobId={jobId}
                    onUpgrade={onUpgrade}
                    onClose={() => setShowWatermarkModal(false)}
                    onContinue={downloadClip}
                />
            )}

        </div>
    );
}
