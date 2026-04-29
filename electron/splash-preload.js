/*
 * Splash window preload. Listens for status messages from the main process
 * and updates the visible "Starting engine…" line.
 */
const { ipcRenderer } = require('electron');

ipcRenderer.on('splash-status', (_event, message) => {
    const el = document.getElementById('status');
    if (el) el.textContent = message;
});
