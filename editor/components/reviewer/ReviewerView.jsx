import React from 'react';

export default function ReviewerView({ folder, source, onBack, manifest }) {
    return (
        <div data-testid="reviewer-placeholder" style={{ padding: 24 }}>
            <button onClick={onBack}>← Project</button>
            <p>Reviewer placeholder for: {source?.path}</p>
        </div>
    );
}
