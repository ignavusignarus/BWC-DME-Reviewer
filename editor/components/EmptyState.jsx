import React from 'react';

export default function EmptyState({ onOpenFolder }) {
    return (
        <div style={{ textAlign: 'center', maxWidth: 540, padding: 24 }}>
            <h1 style={{ fontSize: '2rem', margin: 0, color: '#5eead4' }}>BWC Clipper</h1>
            <p style={{ marginTop: '0.75rem', color: '#8b949e', lineHeight: 1.5 }}>
                Open a folder containing body-worn camera video or defense medical exam audio
                to begin reviewing.
            </p>
            <button
                onClick={onOpenFolder}
                style={{
                    marginTop: '1.5rem',
                    padding: '0.75rem 1.5rem',
                    fontSize: '1rem',
                    background: '#1f6feb',
                    color: '#fff',
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'pointer',
                }}
            >
                Open folder
            </button>
        </div>
    );
}
