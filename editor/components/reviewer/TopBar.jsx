import React from 'react';

function progressLabel(status) {
    if (status === 'queued') return 'Re-transcribing — queued';
    if (status === 'running:transcribe') return 'Re-transcribing — Stage 5 of 6';
    if (status === 'running:align') return 'Re-transcribing — Stage 6 of 6';
    return null;
}

function basename(path) {
    return path.replace(/\\/g, '/').split('/').pop();
}

export default function TopBar({ manifest, source, onBack, onSelectSource, retranscribeStatus }) {
    const completedFiles = manifest.files.filter(f => f.completed);
    const label = progressLabel(retranscribeStatus);

    return (
        <div role="banner" data-testid="topbar" style={{ display: 'flex', gap: 14, alignItems: 'center', padding: '8px 14px', background: '#161b22', borderBottom: '1px solid #21262d' }}>
            <button onClick={onBack} style={{ background: 'transparent', color: '#8b949e', border: '1px solid #30363d', borderRadius: 3, padding: '3px 9px', cursor: 'pointer' }}>
                ← Project
            </button>
            <span style={{ fontFamily: 'ui-monospace, monospace', color: '#6e7681', fontSize: '0.72rem', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={manifest.folder}>
                {manifest.folder}
            </span>
            <select
                value={source?.path || ''}
                onChange={(e) => {
                    const next = manifest.files.find(f => f.path === e.target.value);
                    if (next) onSelectSource(next);
                }}
                style={{ background: '#0d1117', color: '#c9d1d9', border: '1px solid #30363d', borderRadius: 3, padding: '4px 9px', fontSize: '0.78rem', fontFamily: 'ui-monospace, monospace' }}
            >
                {completedFiles.map(f => (
                    <option key={f.path} value={f.path}>{basename(f.path)}</option>
                ))}
            </select>
            {label && (
                <span style={{ background: '#161b22', border: '1px solid #d29922', color: '#d29922', borderRadius: 10, padding: '2px 9px', fontSize: '0.7rem' }}>
                    ⟳ {label}…
                </span>
            )}
            <span style={{ flex: 1 }} />
        </div>
    );
}
