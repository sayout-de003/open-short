import React, { useState, useEffect, useMemo } from 'react';
import { Loader2, Download, Film, Folder, FolderOpen, Trash2, Play, ExternalLink, RefreshCw, Check, AlertCircle, Clock } from 'lucide-react';
import { apiJson, apiFetch } from '../lib/api';

export default function HistoryTab({ onReopenProject }) {
  const [projects, setProjects] = useState(null);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);
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

  const handleDelete = async (jobId, title) => {
    if (!window.confirm(`Are you sure you want to delete project "${title || jobId}"? This will permanently delete its video clips and free up disk space.`)) {
      return;
    }
    setDeletingId(jobId);
    try {
      const res = await apiFetch(`/api/projects/${jobId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(await res.text());
      setProjects(prev => (prev || []).filter(p => p.job_id !== jobId));
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

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
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

            return (
              <div
                key={project.job_id}
                className="card p-4 sm:p-5 border border-rule transition-all hover:border-rule2"
              >
                {/* Folder Header */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div
                    onClick={() => toggleFolder(project.job_id)}
                    className="flex items-start gap-3 min-w-0 cursor-pointer select-none flex-1"
                  >
                    <div className="p-2.5 bg-paper3 rounded-input text-brass shrink-0 mt-0.5 sm:mt-0">
                      {isExpanded ? <FolderOpen size={20} /> : <Folder size={20} />}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-sm text-ink hover:text-brass transition-colors truncate max-w-lg">
                          {project.title || `Job: ${project.job_id}`}
                        </span>
                        {getStatusBadge(project.status)}
                      </div>
                      <div className="flex items-center gap-3 text-[11px] text-muted mt-1 flex-wrap">
                        <span className="flex items-center gap-1 font-mono">
                          <Clock size={11} /> {project.created_at}
                        </span>
                        <span>·</span>
                        <span>
                          {project.clip_count} {project.clip_count === 1 ? 'clip' : 'clips'}
                        </span>
                        <span>·</span>
                        <span className="font-mono text-muted/70">
                          ID: {project.job_id.slice(0, 8)}...
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-rule">
                    {hasClips && (
                      <button
                        onClick={() => handleOpenProject(project.job_id)}
                        className="btn-primary py-1.5 px-3 text-xs flex items-center gap-1.5"
                        title="Open this project in the Clip Generator & Editor"
                      >
                        <Play size={12} /> View Clips
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