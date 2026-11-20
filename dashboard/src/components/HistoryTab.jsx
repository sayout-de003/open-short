import React, { useState, useEffect, useMemo } from 'react';
import { Loader2, Download, Film, Folder, FolderOpen, Trash2, Play, ExternalLink, RefreshCw, Check, AlertCircle, Clock, CheckSquare, Square as SquareIcon } from 'lucide-react';
import { apiJson, apiFetch } from '../lib/api';

export default function HistoryTab({ onReopenProject }) {
  const [projects, setProjects] = useState(null);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);
  const [selectedJobIds, setSelectedJobIds] = useState(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [expandedFolders, setExpandedFolders] = useState({});
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [error, setError] = useState('');

  const loadProjects = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiJson('/api/projects');
      setProjects(data.projects || []);
      setSelectedJobIds(new Set());
    } catch (e) {
      console.error("Failed to load projects:", e);
      setError("Could not load projects from local storage.");
      setProjects([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const toggleFolder = (jobId) => {
    setExpandedFolders(prev => ({
      ...prev,
      [jobId]: !prev[jobId]
    }));
  };

  const toggleSelect = (jobId, e) => {
    if (e) e.stopPropagation();
    setSelectedJobIds(prev => {
      const next = new Set(prev);
      if (next.has(jobId)) next.delete(jobId);
      else next.add(jobId);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedJobIds.size === filteredProjects.length && filteredProjects.length > 0) {
      setSelectedJobIds(new Set());
    } else {
      setSelectedJobIds(new Set(filteredProjects.map(p => p.job_id)));
    }
  };

  const handleBatchDelete = async () => {
    const count = selectedJobIds.size;
    if (count === 0) return;
    if (!window.confirm(`Permanently delete ${count} selected project folder(s) and all their video clips? This will immediately free up disk space.`)) {
      return;
    }
    setBatchDeleting(true);
    try {
      const res = await apiFetch('/api/projects/batch-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_ids: Array.from(selectedJobIds) })
      });
      if (!res.ok) throw new Error(await res.text());
      const toRemove = new Set(selectedJobIds);
      setProjects(prev => (prev || []).filter(p => !toRemove.has(p.job_id)));
      setSelectedJobIds(new Set());
    } catch (err) {
      alert(`Batch delete failed: ${err.message || 'Unknown error'}`);
    } finally {
      setBatchDeleting(false);
    }
  };

  const handleDelete = async (jobId, title) => {
    if (!window.confirm(`Are you sure you want to delete project "${title || jobId}"? This will permanently delete its video clips and free up disk space.`)) {
      return;
    }
    setDeletingId(jobId);
    try {
      const res = await apiFetch(`/api/projects/${jobId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(await res.text());
      setProjects(prev => (prev || []).filter(p => p.job_id !== jobId));
      setSelectedJobIds(prev => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
    } catch (err) {
      alert(`Delete failed: ${err.message || 'Unknown error'}`);
    } finally {
      setDeletingId(null);
    }
  };

  const handleOpenProject = (jobId) => {
    const proj = (projects || []).find(p => p.job_id === jobId);
    if (onReopenProject) {
      onReopenProject(jobId, proj);
    } else {
      window.location.hash = `#app?tab=dashboard&job=${jobId}`;
    }
  };

  const filteredProjects = useMemo(() => {
    if (!projects) return [];
    return projects.filter(p => {
      const matchSearch = (p.title || p.job_id).toLowerCase().includes(searchTerm.toLowerCase());
      const matchStatus = statusFilter === 'all' || p.status === statusFilter;
      return matchSearch && matchStatus;
    });
  }, [projects, searchTerm, statusFilter]);

  const getStatusBadge = (status) => {
    switch (status) {
      case 'completed':
        return (
          <span className="badge-ok text-[11px] py-0.5 px-2 flex items-center gap-1">
            <Check size={11} /> Completed
          </span>
        );
      case 'queued':
        return (
          <span className="bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[11px] py-0.5 px-2 rounded-full flex items-center gap-1 animate-pulse">
            <Clock size={11} /> Queued
          </span>
        );
      case 'processing':
        return (
          <span className="bg-sky-500/10 text-sky-400 border border-sky-500/20 text-[11px] py-0.5 px-2 rounded-full flex items-center gap-1 animate-pulse">
            <Loader2 size={11} className="animate-spin" /> Processing
          </span>
        );
      case 'failed':
        return (
          <span className="badge-warn text-[11px] py-0.5 px-2 flex items-center gap-1">
            <AlertCircle size={11} /> Failed
          </span>
        );
      default:
        return (
          <span className="badge-quiet text-[11px] py-0.5 px-2">
            {status || 'Draft'}
          </span>
        );
    }
  };

  if (loading && !projects) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3">
        <Loader2 className="animate-spin text-brass" size={28} />
        <p className="text-muted text-xs">Loading local project repository...</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-8 max-w-6xl mx-auto animate-fade">
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <p className="eyebrow mb-1">LOCAL STUDIO STORAGE</p>
          <h1 className="font-display lowercase text-2xl text-ink">Project Directory & History</h1>
          <p className="text-muted text-xs mt-1">
            All your video clipping projects, clips, and renders stored on this machine.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadProjects}
            className="btn-quiet py-1.5 px-3 text-xs flex items-center gap-1.5"
            title="Refresh project list"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* Filter, Search, and Batch Selection Bar */}
      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Search by project name or Job ID..."
          className="input-field text-xs sm:flex-1 py-2"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="input-field text-xs sm:w-44 py-2"
        >
          <option value="all">All Statuses</option>
          <option value="completed">Completed</option>
          <option value="processing">Processing</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {/* Batch Action Toolbar */}
      {filteredProjects.length > 0 && (
        <div className="flex items-center justify-between gap-3 p-2.5 mb-4 bg-paper2 rounded-input border border-rule text-xs">
          <div className="flex items-center gap-2">
            <button
              onClick={toggleSelectAll}
              className="flex items-center gap-1.5 text-ink hover:text-brass transition-colors font-medium select-none"
            >
              {selectedJobIds.size === filteredProjects.length && filteredProjects.length > 0 ? (
                <CheckSquare size={16} className="text-brass fill-brass/10" />
              ) : (
                <SquareIcon size={16} className="text-muted" />
              )}
              <span>Select All ({filteredProjects.length})</span>
            </button>
            {selectedJobIds.size > 0 && (
              <span className="text-muted text-[11px] font-mono">
                · {selectedJobIds.size} selected
              </span>
            )}
          </div>
          {selectedJobIds.size > 0 && (
            <button
              onClick={handleBatchDelete}
              disabled={batchDeleting}
              className="py-1 px-3 rounded bg-red-600 hover:bg-red-700 text-white font-medium flex items-center gap-1.5 transition-colors shadow-xs"
              title="Delete all selected project folders and free up disk space"
            >
              {batchDeleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              Delete Selected ({selectedJobIds.size})
            </button>
          )}
        </div>
      )}

      {error && (
        <div className="p-3 mb-6 bg-red-500/10 border border-red-500/20 rounded-input text-danger text-xs">
          {error}
        </div>
      )}

      {filteredProjects.length === 0 ? (
        <div className="card p-12 text-center text-muted">
          <Film size={36} className="mx-auto mb-3 text-muted/60" />
          <p className="font-medium text-sm text-ink mb-1">No Projects Found</p>
          <p className="text-xs text-muted max-w-md mx-auto">
            {searchTerm || statusFilter !== 'all'
              ? 'No projects match your current search filters.'
              : 'You have not processed any videos yet. Go to the Generator tab to clip your first video!'}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredProjects.map((project) => {
            const isExpanded = !!expandedFolders[project.job_id];
            const isDeleting = deletingId === project.job_id;
            const hasClips = project.clip_count > 0;
            const isSelected = selectedJobIds.has(project.job_id);

            return (
              <div
                key={project.job_id}
                className={`card p-4 sm:p-5 border transition-all ${isSelected ? 'border-brass bg-brass/5 shadow-xs' : 'border-rule hover:border-rule2'}`}
              >
                {/* Folder Header */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-start gap-2.5 min-w-0 flex-1">
                    <button
                      type="button"
                      onClick={(e) => toggleSelect(project.job_id, e)}
                      className={`p-1 mt-1 rounded transition-colors ${isSelected ? 'text-brass' : 'text-muted/60 hover:text-muted'}`}
                      title={isSelected ? "Deselect folder" : "Select folder for batch deletion"}
                    >
                      {isSelected ? <CheckSquare size={18} className="text-brass fill-brass/10" /> : <SquareIcon size={18} />}
                    </button>
                    <div
                      onClick={() => handleOpenProject(project.job_id)}
                      className="flex items-start gap-3 min-w-0 cursor-pointer select-none flex-1 group"
                      title="Click to open this project's view"
                    >
                      <div className="p-2.5 bg-paper3 rounded-input text-brass shrink-0 mt-0.5 sm:mt-0 group-hover:scale-105 transition-transform">
                        {isExpanded ? <FolderOpen size={20} /> : <Folder size={20} />}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-sm text-ink group-hover:text-brass transition-colors truncate max-w-lg">
                            {project.title || `Job: ${project.job_id}`}
                          </span>
                          {getStatusBadge(project.status)}
                        </div>
                        <div className="flex items-center gap-3 text-[11px] text-muted mt-1 flex-wrap">
                          <span className="flex items-center gap-1 font-mono">
                            <Clock size={11} /> {project.created_at}
                          </span>
                          <span>·</span>
                          <span className="text-brass font-medium">
                            {project.clip_count} {project.clip_count === 1 ? 'clip' : 'clips'}
                          </span>
                          <span>·</span>
                          <span className="font-mono text-muted/70">
                            ID: {project.job_id.slice(0, 8)}...
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-rule">
                    {(project.status === 'processing' || project.status === 'queued') ? (
                      <button
                        onClick={() => handleOpenProject(project.job_id)}
                        className="btn-primary py-1.5 px-3 text-xs flex items-center gap-1.5 bg-sky-500 hover:bg-sky-600 border-sky-400 text-white animate-pulse shadow-sm"
                        title="Open live clipping monitor, video preview & system logs"
                      >
                        <Loader2 size={12} className="animate-spin" /> Live Clipping
                      </button>
                    ) : hasClips ? (
                      <button
                        onClick={() => handleOpenProject(project.job_id)}
                        className="btn-primary py-1.5 px-3 text-xs flex items-center gap-1.5"
                        title="Open this project in the Clip Generator & Editor"
                      >
                        <Play size={12} /> View Clips
                      </button>
                    ) : (
                      <button
                        onClick={() => handleOpenProject(project.job_id)}
                        className="btn-quiet py-1.5 px-2.5 text-xs flex items-center gap-1 text-muted hover:text-ink"
                        title="Open project studio"
                      >
                        <Play size={11} /> Open Studio
                      </button>
                    )}
                    {hasClips && (
                      <a
                        href={`/api/jobs/${project.job_id}/download-all`}
                        download
                        className="btn-quiet py-1.5 px-3 text-xs flex items-center gap-1.5"
                        title="Download all clips as a single ZIP archive"
                      >
                        <Download size={12} /> ZIP
                      </a>
                    )}
                    <button
                      onClick={() => handleDelete(project.job_id, project.title)}
                      disabled={isDeleting}
                      className="p-1.5 text-muted hover:text-danger hover:bg-paper3 rounded-input transition-colors"
                      title="Permanently delete project and free disk space"
                    >
                      {isDeleting ? <Loader2 size={15} className="animate-spin text-danger" /> : <Trash2 size={15} />}
                    </button>
                  </div>
                </div>

                {/* Expanded Clips View (Folder Contents) */}
                {isExpanded && (
                  <div className="mt-4 pt-4 border-t border-rule space-y-2">
                    <p className="text-[11px] font-medium text-muted uppercase tracking-wider">
                      Folder Files ({project.clips?.length || 0} clips rendered)
                    </p>
                    {(!project.clips || project.clips.length === 0) ? (
                      <p className="text-xs text-muted italic">No rendered clips inside this project folder.</p>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 pt-1">
                        {project.clips.map((clip, idx) => (
                          <div
                            key={clip.filename}
                            className="p-3 bg-paper2 rounded-input border border-rule flex flex-col justify-between gap-2"
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <Film size={14} className="text-brass shrink-0" />
                              <span className="text-xs text-ink truncate font-mono" title={clip.filename}>
                                {clip.filename}
                              </span>
                            </div>
                            <div className="flex items-center justify-between text-[11px] text-muted">
                              <span>{clip.size_mb} MB</span>
                              <div className="flex items-center gap-1.5">
                                <a
                                  href={clip.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-brass hover:underline flex items-center gap-1"
                                >
                                  <ExternalLink size={11} /> Play
                                </a>
                                <a
                                  href={clip.url}
                                  download={clip.filename}
                                  className="p-1 hover:text-ink text-muted transition-colors"
                                  title="Download MP4"
                                >
                                  <Download size={13} />
                                </a>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}