import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Rocket, Youtube, Twitch, Loader2, RefreshCw, Play, CheckCircle2, AlertTriangle,
  Clock, Scissors, Send, ExternalLink, FolderOpen, Lock, Radio, Gamepad2, Search,
  Download, Sparkles, Check, ChevronRight, Eye, ShieldCheck, Flame, ArrowUpRight
} from 'lucide-react';
import { apiJson, openQuotaWall } from '../lib/api';
import { getApiUrl } from '../config';
import { PLATFORM_VALUES, platformLabel } from '../lib/socialPlatforms';
import { track } from '../lib/analytics';
import { connectNotice } from '../lib/connectReturn';

const POPULAR_GAMES = [
  'GTA 5', 'Valorant', 'Minecraft', 'Call of Duty', 'Fortnite', 'League of Legends', 'Apex Legends', 'Counter-Strike 2'
];

export default function AutopilotTab({ onOpenProject, onUpgrade, justConnected }) {
  const [activeSubTab, setActiveSubTab] = useState('radar'); // 'radar' | 'channel'
  
  // Radar state (Discover top streams across YouTube & Twitch)
  const [searchQuery, setSearchQuery] = useState('GTA 5');
  const [discovering, setDiscovering] = useState(false);
  const [discoveredSources, setDiscoveredSources] = useState([]);
  const [discoveryError, setDiscoveryError] = useState(null);
  
  // Clips state (Right panel: generated reels & auto-post status)
  const [clips, setClips] = useState([]);
  const [loadingClips, setLoadingClips] = useState(false);
  const [publishingClipId, setPublishingClipId] = useState(null);
  const [publishFeedback, setPublishFeedback] = useState({});
  const [clippingSourceId, setClippingSourceId] = useState(null);
  const [clipFeedback, setClipFeedback] = useState(null);
  const [activeJobs, setActiveJobs] = useState([]);

  // Status & channel config
  const [overview, setOverview] = useState(null);
  const [ytConfig, setYtConfig] = useState(null);
  const [loadError, setLoadError] = useState('');

  // Fetch YouTube configuration (Direct 10k/day OAuth)
  const fetchYtConfig = useCallback(async () => {
    try {
      const cfg = await apiJson('/api/youtube/config');
      setYtConfig(cfg);
    } catch (_) {}
  }, []);

  // Fetch rendered clips & auto-post status
  const fetchClips = useCallback(async () => {
    setLoadingClips(true);
    try {
      const res = await apiJson('/api/autopilot/clips?limit=50');
      setClips(res.clips || []);
    } catch (_) {}
    finally {
      setLoadingClips(false);
    }
  }, []);

  // Fetch active/recent autopilot jobs
  const fetchJobs = useCallback(async () => {
    try {
      const res = await apiJson('/api/autopilot/jobs?limit=20');
      setActiveJobs(res.jobs || []);
    } catch (_) {}
  }, []);

  // Discover top live streams across YouTube & Twitch
  const discoverStreams = useCallback(async (queryToUse) => {
    const q = queryToUse !== undefined ? queryToUse : searchQuery;
    setDiscovering(true);
    setDiscoveryError(null);
    try {
      const res = await apiJson(`/api/autopilot/discover?query=${encodeURIComponent(q)}`);
      setDiscoveredSources(res.sources || []);
    } catch (e) {
      setDiscoveryError('Discovery failed. Verify your YouTube API key or Twitch credentials in settings.');
    } finally {
      setDiscovering(false);
    }
  }, [searchQuery]);

  // Initial load
  useEffect(() => {
    fetchYtConfig();
    fetchClips();
    fetchJobs();
    discoverStreams('GTA 5');
    
    // Auto-poll clips & jobs every 8s to update status when background workers finish
    const interval = setInterval(() => {
      fetchClips();
      fetchJobs();
    }, 8000);
    return () => clearInterval(interval);
  }, [fetchYtConfig, fetchClips, fetchJobs, discoverStreams]);

  // Trigger cutting reels from a discovered live stream or VOD
  const handleCutReels = async (source) => {
    setClippingSourceId(source.source_id);
    setClipFeedback(null);
    try {
      const res = await apiJson('/api/autopilot/clip-source', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: source.url,
          title: source.title,
          platform: source.platform,
          source_id: source.source_id,
          source_type: source.source_type,
          channel_id: source.channel_id,
          channel_name: source.channel_name,
          game_name: source.game_name || searchQuery,
        }),
      });

      // Instantly show in active jobs UI
      setActiveJobs(prev => [
        {
          id: res.job_id || `job_${Date.now()}`,
          title: source.title,
          platform: source.platform,
          status: 'processing',
          created_at: new Date().toLocaleTimeString(),
        },
        ...prev
      ]);

      setClipFeedback({
        id: source.source_id,
        type: 'success',
        text: `⚡ Clipping started for "${source.title.slice(0, 45)}...". Visible in running jobs & Projects!`,
      });
      // Refresh clips and jobs list after brief pause
      setTimeout(() => {
        fetchJobs();
        fetchClips();
      }, 2500);
    } catch (e) {
      setClipFeedback({
        id: source.source_id,
        type: 'error',
        text: 'Failed to start clipping. Please check the backend connection.',
      });
    } finally {
      setClippingSourceId(null);
    }
  };

  // Publish a reel to YouTube Shorts manually / on demand
  const handlePublishClip = async (clipId) => {
    setPublishingClipId(clipId);
    try {
      const res = await apiJson(`/api/autopilot/publish-clip/${clipId}`, { method: 'POST' });
      if (res.success) {
        setPublishFeedback((prev) => ({
          ...prev,
          [clipId]: { type: 'success', text: '🎉 Published directly to YouTube Shorts!' },
        }));
        fetchClips();
      } else if (res.quota_exceeded) {
        setPublishFeedback((prev) => ({
          ...prev,
          [clipId]: { type: 'warning', text: '⚠️ Daily YouTube API quota (10,000 units) reached. Clip is preserved on your server—click Download to post manually.' },
        }));
        fetchClips();
      } else {
        setPublishFeedback((prev) => ({
          ...prev,
          [clipId]: { type: 'error', text: res.error || 'Upload error. Ensure YouTube OAuth is connected.' },
        }));
      }
    } catch (e) {
      setPublishFeedback((prev) => ({
        ...prev,
        [clipId]: { type: 'error', text: 'Publishing failed. Please connect YouTube account first.' },
      }));
    } finally {
      setPublishingClipId(null);
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-2 sm:p-4 animate-fade">
      {/* Top Banner / Auto-Mode Badges */}
      <div className="mb-6 bg-paper2 border border-rule rounded-card p-4 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
              <p className="eyebrow !text-emerald-400">Zero-Touch Auto-Mode Active</p>
            </div>
            <h1 className="font-display lowercase text-2xl sm:text-3xl text-ink">
              Live Stream Radar &amp; Autonomous Clipping
            </h1>
            <p className="text-muted text-xs sm:text-sm mt-1 max-w-2xl leading-relaxed">
              OpenShorts automatically scans top live gaming streams on YouTube &amp; Twitch, tracks sentiment spikes in real-time, stacks streamer webcams in full-bleed 20/80 vertical layout, and publishes directly to YouTube Shorts.
            </p>
          </div>

          {/* YouTube Connection status & 10k quota notice */}
          <div className="shrink-0 flex flex-col sm:flex-row md:flex-col items-start md:items-end gap-2 bg-paper/60 p-3.5 rounded-card border border-rule">
            <div className="flex items-center gap-2">
              <Youtube size={16} className={ytConfig?.configured ? "text-emerald-400" : "text-red-500"} />
              <span className="text-xs font-medium text-ink">
                {ytConfig?.configured ? "Direct YouTube Auto-Post: Connected" : "Direct YouTube Auto-Post"}
              </span>
              {ytConfig?.configured ? (
                <span className="badge-ok text-[10px]">10k/day Active</span>
              ) : (
                <span className="badge-quiet text-[10px] text-amber-400">1 Step Needed</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <a
                href="/api/youtube/auth/login"
                className="btn-primary text-xs py-1.5 px-3 flex items-center gap-1.5"
                title="1-Click Connect YouTube using Google OAuth (10,000 units/day)"
              >
                <Youtube size={13} />
                {ytConfig?.configured ? "Reconnect / Change Channel" : "1-Click Connect YouTube (10k/day)"}
              </a>
            </div>
          </div>
        </div>

        {/* Feature Pills */}
        <div className="mt-4 pt-3 border-t border-rule flex flex-wrap items-center gap-2 sm:gap-4 text-xs text-muted">
          <span className="flex items-center gap-1.5 bg-paper px-2.5 py-1 rounded-full border border-rule">
            <Check size={12} className="text-emerald-400" /> Watchdog &amp; Auto-Healing (5m)
          </span>
          <span className="flex items-center gap-1.5 bg-paper px-2.5 py-1 rounded-full border border-rule">
            <Check size={12} className="text-emerald-400" /> 20/80 Streamer Cam + Gameplay Stacking
          </span>
          <span className="flex items-center gap-1.5 bg-paper px-2.5 py-1 rounded-full border border-rule">
            <Check size={12} className="text-emerald-400" /> Live Chat Hype Clipping (Zero API Quota)
          </span>
          <span className="flex items-center gap-1.5 bg-paper px-2.5 py-1 rounded-full border border-rule">
            <Check size={12} className="text-emerald-400" /> 10,000 YouTube Units/Day Direct Upload
          </span>
        </div>
      </div>

      {/* Main Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* LEFT COLUMN: Live Stream Radar (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          <div className="card p-4 sm:p-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
              <div className="flex items-center gap-2">
                <Radio size={16} className="text-brass animate-pulse" />
                <h2 className="text-sm font-semibold uppercase tracking-wider text-ink">
                  Live Stream Scanner &amp; Discovery
                </h2>
              </div>
              <button
                onClick={() => discoverStreams()}
                disabled={discovering}
                className="btn-ghost text-xs py-1.5 px-3 flex items-center gap-1.5 self-start sm:self-auto"
              >
                <RefreshCw size={13} className={discovering ? "animate-spin text-brass" : ""} />
                {discovering ? "Scanning Streams..." : "Refresh Scanner"}
              </button>
            </div>

            {/* Quick Game Chips */}
            <div className="flex flex-wrap items-center gap-1.5 mb-3">
              {POPULAR_GAMES.map((game) => (
                <button
                  key={game}
                  onClick={() => {
                    setSearchQuery(game);
                    discoverStreams(game);
                  }}
                  className={`text-[11px] py-1 px-2.5 rounded-full border transition-all ${
                    searchQuery === game
                      ? 'bg-brass text-black border-brass font-medium'
                      : 'bg-paper text-muted border-rule hover:text-ink hover:border-rule2'
                  }`}
                >
                  {game}
                </button>
              ))}
            </div>

            {/* Search Input Bar */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                discoverStreams();
              }}
              className="flex gap-2 mb-4"
            >
              <div className="relative flex-1">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search stream, game or creator (e.g. GTA 5, IShowSpeed, Shroud)..."
                  className="input-field !pl-9 text-xs"
                />
              </div>
              <button
                type="submit"
                disabled={discovering}
                className="btn-primary text-xs px-4 flex items-center gap-1.5 shrink-0"
              >
                {discovering ? <Loader2 size={13} className="animate-spin" /> : <Flame size={13} />}
                Scan
              </button>
            </form>

            {/* Global Clip Feedback */}
            {clipFeedback && (
              <div
                className={`p-3 rounded-card text-xs mb-4 flex items-center justify-between gap-2 animate-fade ${
                  clipFeedback.type === 'success'
                    ? 'bg-emerald-950/40 border border-emerald-500/40 text-emerald-300'
                    : 'bg-red-950/40 border border-red-500/40 text-red-300'
                }`}
              >
                <span>{clipFeedback.text}</span>
                <button onClick={() => setClipFeedback(null)} className="text-muted hover:text-ink">✕</button>
              </div>
            )}

            {/* Discovered Stream Cards */}
            {discovering ? (
              <div className="py-16 flex flex-col items-center justify-center text-muted space-y-3">
                <Loader2 size={24} className="animate-spin text-brass" />
                <p className="text-xs">Scanning YouTube Live and Twitch for top {searchQuery} streams...</p>
              </div>
            ) : discoveryError ? (
              <div className="p-4 bg-paper rounded border border-rule text-xs text-warn">
                {discoveryError}
              </div>
            ) : discoveredSources.length === 0 ? (
              <div className="py-12 text-center text-muted text-xs bg-paper/40 rounded border border-rule/50">
                No active streams found for &quot;{searchQuery}&quot;. Try selecting another game chip above.
              </div>
            ) : (
              <div className="space-y-3 max-h-[640px] overflow-y-auto custom-scrollbar pr-1">
                {discoveredSources.map((src, i) => (
                  <div
                    key={`${src.platform}-${src.source_id}-${i}`}
                    className="p-3.5 bg-paper/60 hover:bg-paper border border-rule hover:border-brass/40 rounded-card transition-all flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 group"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span
                          className={`text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded flex items-center gap-1 ${
                            src.platform === 'twitch' ? 'bg-purple-900/60 text-purple-300 border border-purple-700/50' : 'bg-red-900/60 text-red-300 border border-red-700/50'
                          }`}
                        >
                          {src.platform === 'twitch' ? <Twitch size={10} /> : <Youtube size={10} />}
                          {src.platform}
                        </span>
                        {src.source_type === 'live' && (
                          <span className="badge-danger text-[9px] px-1.5 py-0.2 animate-pulse">LIVE</span>
                        )}
                        {src.concurrent_viewers > 0 && (
                          <span className="text-[11px] text-muted flex items-center gap-1">
                            <Eye size={11} /> {src.concurrent_viewers.toLocaleString()} watching
                          </span>
                        )}
                        {src.score > 0 && (
                          <span className="text-[10px] font-mono text-brass font-bold ml-auto sm:ml-0">
                            ★ {Math.round(src.score)} Virality
                          </span>
                        )}
                      </div>

                      <h3 className="text-xs font-medium text-ink line-clamp-1 group-hover:text-brass transition-colors">
                        {src.title}
                      </h3>
                      <p className="text-[11px] text-muted truncate mt-0.5">
                        <strong className="text-ink2">{src.channel_name}</strong> · {src.game_name || searchQuery}
                      </p>
                    </div>

                    <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                      <a
                        href={src.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn-ghost p-2 text-xs"
                        title="View stream in new tab"
                      >
                        <ArrowUpRight size={14} />
                      </a>
                      <button
                        onClick={() => handleCutReels(src)}
                        disabled={clippingSourceId === src.source_id}
                        className="btn-primary text-xs py-2 px-3.5 flex items-center gap-1.5 font-medium shadow-sm hover:shadow-brass/20"
                        title="Cut 9:16 Shorts with 20/80 layout & live sentiment highlights"
                      >
                        {clippingSourceId === src.source_id ? (
                          <>
                            <Loader2 size={13} className="animate-spin" /> Clipping…
                          </>
                        ) : (
                          <>
                            <Scissors size={13} /> Cut Reels Now
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT COLUMN: Generated Reels & Auto-Post Monitor (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          <div className="card p-4 sm:p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Sparkles size={16} className="text-brass" />
                <h2 className="text-sm font-semibold uppercase tracking-wider text-ink">
                  Generated Reels &amp; Auto-Posting
                </h2>
              </div>
              <button
                onClick={fetchClips}
                disabled={loadingClips}
                className="btn-quiet p-1.5 text-xs text-muted hover:text-ink"
                title="Refresh clips"
              >
                <RefreshCw size={13} className={loadingClips ? "animate-spin text-brass" : ""} />
              </button>
            </div>

            {/* Active Running/Queued Jobs Card */}
            {activeJobs.filter(j => ['queued', 'claimed', 'processing', 'running'].includes(j.status)).length > 0 && (
              <div className="p-3.5 bg-paper2/90 border border-sky-500/30 rounded-card space-y-2.5 mb-4 animate-fade shadow-sm">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-sky-400 flex items-center gap-1.5">
                    <Loader2 size={12} className="animate-spin text-sky-400" />
                    Clipping In Progress ({activeJobs.filter(j => ['queued', 'claimed', 'processing', 'running'].includes(j.status)).length})
                  </span>
                  <a
                    href="#app?tab=history"
                    className="text-[11px] text-brass hover:underline flex items-center gap-1 font-medium"
                    title="Open Projects & Library tab"
                  >
                    View in Projects <ArrowUpRight size={11} />
                  </a>
                </div>
                <div className="space-y-2 max-h-48 overflow-y-auto custom-scrollbar">
                  {activeJobs.filter(j => ['queued', 'claimed', 'processing', 'running'].includes(j.status)).map(j => (
                    <div key={j.id} className="p-2.5 rounded bg-paper border border-rule flex items-center justify-between gap-3 text-xs">
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-ink truncate">{j.title || j.source_id || j.id}</p>
                        <p className="text-[10px] text-muted flex items-center gap-1 mt-0.5">
                          <span className="capitalize">{j.platform}</span> · 
                          <span className="text-sky-400 font-medium">20/80 Stack Active</span> · 
                          <span>{j.created_at}</span>
                        </p>
                      </div>
                      <span className="shrink-0 bg-sky-500/10 text-sky-400 border border-sky-500/20 text-[10px] py-0.5 px-2 rounded-full flex items-center gap-1">
                        <Loader2 size={9} className="animate-spin" /> {j.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {loadingClips && clips.length === 0 ? (
              <div className="py-16 flex flex-col items-center justify-center text-muted space-y-2">
                <Loader2 size={24} className="animate-spin text-brass" />
                <p className="text-xs">Loading cut reels...</p>
              </div>
            ) : clips.length === 0 ? (
              <div className="py-14 text-center text-muted space-y-3 bg-paper/40 rounded border border-rule/50 p-4">
                <Scissors size={28} className="mx-auto text-muted/60" />
                <p className="text-xs text-ink font-medium">No reels cut yet</p>
                <p className="text-[11px] leading-relaxed max-w-xs mx-auto text-muted">
                  Click <strong>&quot;Cut Reels Now&quot;</strong> on any stream on the left. The AI will extract viral moments, apply the 20/80 layout, and list them here ready to post.
                </p>
              </div>
            ) : (
              <div className="space-y-4 max-h-[640px] overflow-y-auto custom-scrollbar pr-1">
                {clips.map((clip) => {
                  const isPosted = clip.posted || clip.publication_status === 'sent';
                  const isPublishing = publishingClipId === clip.id;
                  const feedback = publishFeedback[clip.id];

                  return (
                    <div
                      key={clip.id}
                      className="p-3 bg-paper/80 border border-rule rounded-card flex flex-col gap-2.5 transition-all hover:border-rule2"
                    >
                      {/* Video Player Preview */}
                      <div className="relative aspect-[9/16] w-full max-h-[260px] bg-black rounded overflow-hidden border border-rule/80 group">
                        <video
                          src={clip.video_url ? getApiUrl(clip.video_url) : ''}
                          controls
                          playsInline
                          preload="metadata"
                          className="w-full h-full object-contain"
                        />
                        <div className="absolute top-2 left-2 pointer-events-none">
                          <span className="bg-black/80 backdrop-blur-sm text-[10px] text-white px-2 py-0.5 rounded font-mono">
                            {clip.duration_sec ? `${Math.round(clip.duration_sec)}s` : '9:16'}
                          </span>
                        </div>
                      </div>

                      {/* Clip Info */}
                      <div>
                        <h4 className="text-xs font-medium text-ink line-clamp-1">
                          {clip.source_title || 'Gaming Reel'}
                        </h4>
                        <p className="text-[11px] text-muted truncate mt-0.5">
                          {clip.channel_name ? `${clip.channel_name} · ` : ''}
                          {clip.created_at ? new Date(clip.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Ready'}
                        </p>
                      </div>

                      {/* Auto-Post Status Badge & Feedback */}
                      <div className="flex items-center justify-between gap-2 pt-2 border-t border-rule/60">
                        <div className="flex items-center gap-1.5">
                          {isPosted ? (
                            <span className="badge-ok text-[10px] flex items-center gap-1 font-medium">
                              <CheckCircle2 size={12} className="text-emerald-400" /> Posted to YouTube Shorts
                            </span>
                          ) : clip.publication_status === 'quota_exhausted' ? (
                            <span className="bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[10px] py-0.5 px-2 rounded flex items-center gap-1 font-medium" title="YouTube Data API daily limit reached. Clip preserved locally.">
                              <Clock size={11} /> 10k Quota Reached — Ready to Download
                            </span>
                          ) : (
                            <span className="badge-quiet text-[10px] text-amber-400 flex items-center gap-1 font-medium">
                              <Clock size={11} /> Ready to Post
                            </span>
                          )}
                        </div>

                        {/* Action Buttons */}
                        <div className="flex items-center gap-2">
                          <a
                            href={clip.video_url ? `${getApiUrl(clip.video_url)}?download=1` : '#'}
                            download={`short_${clip.id}.mp4`}
                            className="btn-ghost py-1 px-2.5 text-xs text-ink hover:text-brass flex items-center gap-1 border border-rule/70 rounded hover:border-brass/40 transition-colors"
                            title="Download MP4 Reel directly to your computer"
                          >
                            <Download size={13} />
                            <span>Download</span>
                          </a>

                          {!isPosted && (
                            <button
                              onClick={() => handlePublishClip(clip.id)}
                              disabled={isPublishing}
                              className="btn-primary text-xs py-1.5 px-3 flex items-center gap-1 font-medium"
                              title="Post immediately to YouTube Shorts via Direct YouTube API"
                            >
                              {isPublishing ? (
                                <>
                                  <Loader2 size={12} className="animate-spin" /> Uploading…
                                </>
                              ) : (
                                <>
                                  <Send size={12} /> Post to YouTube
                                </>
                              )}
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Publish Feedback Message */}
                      {feedback && (
                        <p
                          className={`text-[11px] mt-1 ${
                            feedback.type === 'success' ? 'text-emerald-400' : feedback.type === 'warning' ? 'text-amber-400' : 'text-danger'
                          }`}
                        >
                          {feedback.text}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
