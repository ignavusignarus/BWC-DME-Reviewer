import React, { useState } from 'react';

export default function ContextNamesPanel({ folder, sourcePath, onRetranscribeStarted, disabled }) {
    const [names, setNames] = useState('');
    const [locations, setLocations] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);

    const apply = async () => {
        setBusy(true);
        setError(null);
        try {
            const ctxResp = await fetch('/api/source/context', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    folder, source: sourcePath,
                    names: names.split('\n').map(s => s.trim()).filter(Boolean),
                    locations: locations.split('\n').map(s => s.trim()).filter(Boolean),
                }),
            });
            if (!ctxResp.ok) throw new Error(`context save failed (${ctxResp.status})`);
            const rerunResp = await fetch('/api/source/retranscribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder, source: sourcePath }),
            });
            if (!rerunResp.ok) throw new Error(`retranscribe failed (${rerunResp.status})`);
            onRetranscribeStarted();
        } catch (e) {
            setError(e.message);
        } finally {
            setBusy(false);
        }
    };

    return (
        <details open data-testid="context-names-panel" style={{ borderTop: '1px solid #21262d', background: '#0d1117', padding: '10px 12px', fontSize: '0.74rem', color: '#8b949e' }}>
            <summary style={{ cursor: 'pointer', color: '#c9d1d9' }}>Context names &amp; locations</summary>
            <label style={{ marginTop: 8, display: 'block', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: '0.65rem', color: '#6e7681' }}>
                Names you expect to hear
                <textarea aria-label="names" value={names} onChange={(e) => setNames(e.target.value)} style={{ width: '100%', height: 36, marginTop: 5, background: '#010409', border: '1px solid #30363d', borderRadius: 3, color: '#c9d1d9', padding: '5px 8px', fontSize: '0.78rem', fontFamily: 'inherit' }} />
            </label>
            <label style={{ marginTop: 8, display: 'block', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: '0.65rem', color: '#6e7681' }}>
                Locations
                <textarea aria-label="locations" value={locations} onChange={(e) => setLocations(e.target.value)} style={{ width: '100%', height: 36, marginTop: 5, background: '#010409', border: '1px solid #30363d', borderRadius: 3, color: '#c9d1d9', padding: '5px 8px', fontSize: '0.78rem', fontFamily: 'inherit' }} />
            </label>
            <button
                onClick={apply}
                disabled={disabled || busy}
                style={{ marginTop: 9, background: '#2ea3a3', color: '#010409', border: 0, borderRadius: 3, padding: '4px 11px', fontSize: '0.74rem', fontWeight: 600, cursor: (disabled || busy) ? 'not-allowed' : 'pointer', opacity: (disabled || busy) ? 0.6 : 1 }}>
                {busy ? 'Applying…' : 'Apply & re-transcribe'}
            </button>
            {error && <span style={{ marginLeft: 8, color: '#f87171' }}>{error}</span>}
        </details>
    );
}
