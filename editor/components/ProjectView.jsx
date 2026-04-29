import React from 'react';
import FileListItem from './FileListItem.jsx';

export default function ProjectView({ manifest, selectedPath, onSelectFile, onCloseProject }) {
    return (
        <div
            style={{
                display: 'flex',
                flexDirection: 'column',
                width: '100%',
                height: '100%',
                padding: '1rem',
                boxSizing: 'border-box',
            }}
        >
            <div
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    paddingBottom: '0.75rem',
                    borderBottom: '1px solid #21262d',
                    marginBottom: '0.75rem',
                }}
            >
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '0.8rem', color: '#6e7681' }}>Project folder</div>
                    <div
                        style={{
                            fontFamily: 'ui-monospace, monospace',
                            fontSize: '0.9rem',
                            color: '#c9d1d9',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                        }}
                        title={manifest.folder}
                    >
                        {manifest.folder}
                    </div>
                </div>
                <button
                    onClick={onCloseProject}
                    style={{
                        background: 'transparent',
                        color: '#8b949e',
                        border: '1px solid #30363d',
                        borderRadius: 4,
                        padding: '0.4rem 0.8rem',
                        cursor: 'pointer',
                    }}
                >
                    Close
                </button>
            </div>

            {manifest.files.length === 0 ? (
                <div style={{ color: '#6e7681', textAlign: 'center', padding: '2rem' }}>
                    No media files in this folder. Drop in some `.mp4` / `.mp3` files and reopen.
                </div>
            ) : (
                <div role="listbox" style={{ overflowY: 'auto', flex: 1 }}>
                    {manifest.files.map((file) => (
                        <FileListItem
                            key={file.path}
                            file={file}
                            selected={file.path === selectedPath}
                            onSelect={onSelectFile}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}
