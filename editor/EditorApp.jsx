import React, { useEffect, useState } from 'react';
import { apiGet } from './api.js';

export default function EditorApp() {
    const [version, setVersion] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        let cancelled = false;
        apiGet('/api/version')
            .then((data) => {
                if (!cancelled) setVersion(data.version);
            })
            .catch((err) => {
                if (!cancelled) setError(err.message);
            });
        return () => { cancelled = true; };
    }, []);

    return (
        <div style={{ textAlign: 'center' }}>
            <h1 style={{ fontSize: '2.5rem', margin: 0, color: '#5eead4' }}>BWC Clipper</h1>
            <p style={{ marginTop: '0.5rem', color: '#8b949e' }}>
                {error
                    ? `engine error: ${error}`
                    : version
                    ? `engine v${version}`
                    : 'connecting to engine…'}
            </p>
        </div>
    );
}
