import React from 'react';

const CAPTION_DEMO = {
  impact: {
    text: 'WAIT FOR IT',
    cls: 'font-extrabold tracking-tight text-yellow-300 drop-shadow-[0_2px_3px_rgba(0,0,0,0.95)] uppercase',
  },
  highlight: {
    text: 'THIS IS INSANE',
    cls: 'font-bold bg-yellow-300 text-black px-1.5 py-0.5 rounded-sm uppercase',
  },
  comic: {
    text: 'NO WAY!!',
    cls: 'font-black italic text-white bg-rose-600 px-1.5 py-0.5 rounded border border-white/80 uppercase',
  },
  karaoke: {
    text: 'ONE WORD NEXT',
    cls: 'font-bold text-cyan-300 drop-shadow-[0_1px_2px_rgba(0,0,0,0.95)] uppercase',
  },
  bullet_points: {
    text: '• Key takeaway',
    cls: 'font-semibold text-white bg-black/75 px-2 py-0.5 rounded border-l-2 border-emerald-400 text-left',
  },
  minimal_serif: {
    text: 'The real story',
    cls: 'font-serif italic text-zinc-100 drop-shadow-[0_1px_3px_rgba(0,0,0,0.95)]',
  },
};

function LayoutVisual({ layout, category, compact }) {
  const txt = compact ? 'text-[7px]' : 'text-[10px]';
  if (layout === 'stacked_top_cam') {
    return (
      <>
        <div className="h-[20%] bg-gradient-to-br from-indigo-900 via-slate-800 to-zinc-900 border-b border-white/60 flex items-center justify-center relative overflow-hidden">
          <div className="w-5 h-5 rounded-full bg-amber-300/25 border border-amber-200/60 flex items-center justify-center">
            <div className="w-2.5 h-2.5 rounded-full bg-amber-200/80" />
          </div>
          <span className={`absolute bottom-0.5 right-1 font-mono text-white/80 ${compact ? 'text-[6px]' : 'text-[8px]'}`}>20% CAM</span>
        </div>
        <div className="h-[80%] bg-gradient-to-br from-emerald-950 via-zinc-900 to-cyan-950 flex flex-col items-center justify-center relative overflow-hidden">
          <div className="w-10 h-6 rounded border border-emerald-400/35 bg-emerald-500/10 flex items-center justify-center">
            <div className="w-2 h-2 rounded-full bg-emerald-400/70" />
          </div>
          <span className={`mt-1 font-mono text-emerald-200/75 ${txt}`}>80% GAMEPLAY</span>
        </div>
      </>
    );
  }
  if (layout === 'gameplay_with_facecam') {
    return (
      <div className="flex-1 bg-gradient-to-br from-purple-950 via-zinc-900 to-sky-950 flex items-center justify-center relative overflow-hidden">
        <span className={`font-mono text-sky-200/75 ${txt}`}>FULL GAMEPLAY</span>
        <div className={`absolute top-1.5 right-1.5 ${compact ? 'w-6 h-4' : 'w-12 h-8'} rounded bg-slate-800 border border-white/50 flex items-center justify-center`}>
          <div className="w-2 h-2 rounded-full bg-amber-200/80" />
        </div>
      </div>
    );
  }
  if (layout === 'split_two_speaker') {
    return (
      <>
        <div className="h-1/2 bg-gradient-to-br from-slate-800 to-zinc-900 border-b border-white/40 flex flex-col items-center justify-center gap-1">
          <div className="w-4 h-4 rounded-full bg-sky-300/40 border border-sky-200/60" />
          <span className={`font-mono text-zinc-300 ${txt}`}>SPEAKER 1 (50%)</span>
        </div>
        <div className="h-1/2 bg-gradient-to-br from-zinc-900 to-stone-900 flex flex-col items-center justify-center gap-1">
          <div className="w-4 h-4 rounded-full bg-amber-300/40 border border-amber-200/60" />
          <span className={`font-mono text-zinc-300 ${txt}`}>SPEAKER 2 (50%)</span>
        </div>
      </>
    );
  }
  if (layout === 'screencast') {
    return (
      <>
        <div className="h-[62%] bg-gradient-to-br from-zinc-900 via-slate-900 to-indigo-950 border-b border-white/40 flex flex-col items-center justify-center p-1">
          <div className="w-4/5 h-3/5 rounded border border-indigo-400/40 bg-black/40 p-1 space-y-1">
            <div className="h-1 w-2/3 bg-indigo-400/50 rounded" />
            <div className="h-1 w-1/2 bg-emerald-400/40 rounded" />
            <div className="h-1 w-3/4 bg-zinc-500/40 rounded" />
          </div>
          <span className={`mt-1 font-mono text-indigo-200/80 ${txt}`}>SCREEN</span>
        </div>
        <div className="h-[38%] bg-gradient-to-br from-slate-800 to-zinc-900 flex flex-col items-center justify-center gap-0.5">
          <div className="w-3.5 h-3.5 rounded-full bg-amber-200/70" />
          <span className={`font-mono text-zinc-300 ${txt}`}>PRESENTER</span>
        </div>
      </>
    );
  }
  const isGaming = category === 'gaming' || layout === 'gameplay_center';
  return (
    <div
      className={`flex-1 flex flex-col items-center justify-center relative overflow-hidden ${
        isGaming
          ? 'bg-gradient-to-br from-emerald-950 via-zinc-900 to-blue-950'
          : 'bg-gradient-to-br from-stone-800 via-zinc-900 to-neutral-950'
      }`}
    >
      {!isGaming && <div className="w-6 h-6 rounded-full bg-amber-200/35 border border-amber-100/50 mb-1" />}
      <span className={`font-mono text-zinc-200/80 ${txt}`}>
        {isGaming ? 'CENTER GAMEPLAY' : 'CENTER SPEAKER'}
      </span>
    </div>
  );
}

/**
 * Miniature 9:16 visual demo preview for any clip template so users can see
 * the exact frame split and caption style before starting a job.
 */
export default function TemplatePreview({ template, size = 'md' }) {
  if (!template) return null;
  const compact = size === 'sm';
  const dims = size === 'lg' ? 'w-[180px] h-[320px]' : compact ? 'w-[54px] h-[96px]' : 'w-[84px] h-[149px]';
  const cap = CAPTION_DEMO[template.caption_preset] || CAPTION_DEMO.impact;
  const capSize = size === 'lg' ? 'text-[10px]' : compact ? 'text-[6px]' : 'text-[8px]';

  return (
    <div
      className={`${dims} shrink-0 bg-black rounded-md border border-rule2 relative overflow-hidden flex flex-col shadow-inner select-none`}
      title={`${template.name} (${template.layout})`}
    >
      <LayoutVisual layout={template.layout} category={template.category} compact={compact} />
      <div className={`absolute ${compact ? 'bottom-1.5' : 'bottom-4'} inset-x-1 flex justify-center pointer-events-none`}>
        <span className={`${capSize} leading-tight text-center ${cap.cls}`}>
          {cap.text}
        </span>
      </div>
    </div>
  );
}
