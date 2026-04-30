import React from 'react';

export default function SearchHighlight({ text, query }) {
    if (!query) return text;
    const lower = text.toLowerCase();
    const q = query.toLowerCase();
    const out = [];
    let cursor = 0;
    while (cursor < text.length) {
        const i = lower.indexOf(q, cursor);
        if (i === -1) {
            out.push(text.slice(cursor));
            break;
        }
        if (i > cursor) out.push(text.slice(cursor, i));
        out.push(<mark key={i}>{text.slice(i, i + q.length)}</mark>);
        cursor = i + q.length;
    }
    return out.map((part, idx) => (typeof part === 'string' ? <React.Fragment key={idx}>{part}</React.Fragment> : part));
}
