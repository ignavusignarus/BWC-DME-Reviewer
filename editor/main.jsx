import React from 'react';
import { createRoot } from 'react-dom/client';
import EditorApp from './EditorApp.jsx';

const container = document.getElementById('root');
if (!container) {
    throw new Error('#root element missing from index.html');
}
createRoot(container).render(<EditorApp />);
