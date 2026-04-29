import React from 'react';

const MODE_LABELS = { bwc: 'BWC', dme: 'DME' };
const MODE_COLORS = {
    bwc: { bg: '#0e3a4a', fg: '#5eead4' },
    dme: { bg: '#3a2d0e', fg: '#fbbf24' },
};

const STATUS_LABELS = {
    queued: 'queued',
    running: 'extracting…',
    completed: '',
    failed: 'failed',
};

const STATUS_COLORS = {
    queued: '#6e7681',
    running: '#fbbf24',
    completed: '#22c55e',
    failed: '#f87171',
};

function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function StatusIndicator({ status }) {
    if (!status) return null;
    const color = STATUS_COLORS[status] ?? '#6e7681';
    const label = STATUS_LABELS[status] ?? status;
    const glyph = status === 'completed' ? '✓' : status === 'failed' ? '✗' : '●';
    return (
        <span
            data-status={status}
            style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                color,
                fontSize: '0.75rem',
                marginLeft: '0.75rem',
                minWidth: 80,
                justifyContent: 'flex-end',
            }}
        >
            <span aria-hidden="true">{glyph}</span>
            {label && <span>{label}</span>}
        </span>
    );
}

export default function FileListItem({ file, selected, onSelect, status }) {
    const modeStyle = MODE_COLORS[file.mode] || { bg: '#21262d', fg: '#8b949e' };
    return (
        <div
            role="option"
            aria-selected={selected ? 'true' : 'false'}
            onClick={() => onSelect(file)}
            style={{
                display: 'flex',
                alignItems: 'center',
                padding: '0.5rem 0.75rem',
                borderRadius: 4,
                cursor: 'pointer',
                background: selected ? '#1c2733' : 'transparent',
                borderLeft: selected ? '3px solid #5eead4' : '3px solid transparent',
                marginBottom: 2,
            }}
        >
            <span
                style={{
                    background: modeStyle.bg,
                    color: modeStyle.fg,
                    fontSize: '0.7rem',
                    fontWeight: 600,
                    padding: '2px 6px',
                    borderRadius: 3,
                    marginRight: '0.75rem',
                    minWidth: 36,
                    textAlign: 'center',
                }}
            >
                {MODE_LABELS[file.mode] ?? file.mode}
            </span>
            <span style={{ flex: 1, color: '#c9d1d9', fontFamily: 'system-ui, sans-serif' }}>
                {file.basename}
            </span>
            <span style={{ color: '#6e7681', fontSize: '0.85rem' }}>
                {formatSize(file.size_bytes)}
            </span>
            <StatusIndicator status={status} />
        </div>
    );
}
