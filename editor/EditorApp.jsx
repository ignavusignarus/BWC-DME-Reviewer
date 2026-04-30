import React, { useEffect, useRef, useState } from 'react';
import { apiPost, apiGet } from './api.js';
import EmptyState from './components/EmptyState.jsx';
import ProjectView from './components/ProjectView.jsx';
import ReviewerView from './components/reviewer/ReviewerView.jsx';

const POLL_INTERVAL_MS = 1000;
function isActiveStatus(s) {
    return s === 'queued' || (typeof s === 'string' && s.startsWith('running'));
}

export default function EditorApp() {
    const [manifest, setManifest] = useState(null);
    const [selectedPath, setSelectedPath] = useState(null);
    const [statuses, setStatuses] = useState({});
    const [error, setError] = useState(null);
    const [view, setView] = useState('empty');
    const [reviewSource, setReviewSource] = useState(null);
    const pollHandle = useRef(null);

    async function openFolder() {
        setError(null);
        const folderPath = await window.electronAPI.pickFolder();
        if (!folderPath) return;
        try {
            const result = await apiPost('/api/project/open', { path: folderPath });
            setManifest(result);
            setSelectedPath(null);
            setStatuses({});
            setView('project');
        } catch (err) {
            setError(err.message);
        }
    }

    function closeProject() {
        setManifest(null);
        setSelectedPath(null);
        setStatuses({});
        setReviewSource(null);
        setView('empty');
        setError(null);
        stopPolling();
    }

    async function selectFile(file) {
        setSelectedPath(file.path);
        // If this source has already completed processing, route to reviewer view.
        const cachedStatus = statuses[file.path];
        if (cachedStatus === 'completed' || file.completed) {
            setReviewSource(file);
            setView('reviewer');
            try {
                await apiPost('/api/project/reviewer-state', {
                    folder: manifest.folder,
                    last_source: file.path,
                });
            } catch (err) {
                console.warn('[reviewer-state] save failed:', err);
            }
            return;
        }
        // Otherwise, kick off processing as before.
        setStatuses((s) => ({ ...s, [file.path]: 'queued' }));
        try {
            const resp = await apiPost('/api/source/process', {
                folder: manifest.folder,
                source: file.path,
            });
            setStatuses((s) => ({ ...s, [file.path]: resp.status }));
            if (isActiveStatus(resp.status)) {
                startPolling(file.path);
            } else if (resp.status === 'completed') {
                // If processing was a no-op (already completed), allow routing to reviewer next click.
                setStatuses((s) => ({ ...s, [file.path]: 'completed' }));
            }
        } catch (err) {
            setStatuses((s) => ({ ...s, [file.path]: 'failed' }));
            setError(err.message);
        }
    }

    function backToProject() {
        setView('project');
        setReviewSource(null);
    }

    function startPolling(path) {
        stopPolling();
        pollHandle.current = setInterval(async () => {
            try {
                const params = new URLSearchParams({ folder: manifest.folder, source: path });
                const resp = await apiGet(`/api/source/state?${params.toString()}`);
                setStatuses((s) => ({ ...s, [path]: resp.status }));
                if (!isActiveStatus(resp.status)) {
                    stopPolling();
                }
            } catch (err) {
                console.warn('[poll] state fetch failed:', err);
            }
        }, POLL_INTERVAL_MS);
    }

    function stopPolling() {
        if (pollHandle.current) {
            clearInterval(pollHandle.current);
            pollHandle.current = null;
        }
    }

    useEffect(() => () => stopPolling(), []);

    return (
        <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {view === 'empty' && (
                <div>
                    <EmptyState onOpenFolder={openFolder} />
                    {error && (
                        <p style={{ marginTop: '1rem', color: '#f87171', textAlign: 'center' }}>{error}</p>
                    )}
                </div>
            )}
            {view === 'project' && manifest !== null && (
                <ProjectView
                    manifest={manifest}
                    selectedPath={selectedPath}
                    onSelectFile={selectFile}
                    onCloseProject={closeProject}
                    statuses={statuses}
                />
            )}
            {view === 'reviewer' && manifest !== null && reviewSource !== null && (
                <ReviewerView
                    folder={manifest.folder}
                    source={reviewSource}
                    onBack={backToProject}
                    manifest={manifest}
                />
            )}
        </div>
    );
}
