import React, { useState } from 'react';
import { apiPost } from './api.js';
import EmptyState from './components/EmptyState.jsx';
import ProjectView from './components/ProjectView.jsx';

export default function EditorApp() {
    const [manifest, setManifest] = useState(null);
    const [selectedPath, setSelectedPath] = useState(null);
    const [error, setError] = useState(null);

    async function openFolder() {
        setError(null);
        const folderPath = await window.electronAPI.pickFolder();
        if (!folderPath) return; // user cancelled
        try {
            const result = await apiPost('/api/project/open', { path: folderPath });
            setManifest(result);
            setSelectedPath(null);
        } catch (err) {
            setError(err.message);
        }
    }

    function closeProject() {
        setManifest(null);
        setSelectedPath(null);
        setError(null);
    }

    function selectFile(file) {
        setSelectedPath(file.path);
    }

    return (
        <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {manifest === null ? (
                <div>
                    <EmptyState onOpenFolder={openFolder} />
                    {error && (
                        <p style={{ marginTop: '1rem', color: '#f87171', textAlign: 'center' }}>{error}</p>
                    )}
                </div>
            ) : (
                <ProjectView
                    manifest={manifest}
                    selectedPath={selectedPath}
                    onSelectFile={selectFile}
                    onCloseProject={closeProject}
                />
            )}
        </div>
    );
}
