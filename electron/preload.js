/*
 * Renderer-side bridge to the main process.
 *
 * Exposes window.electronAPI with only the operations the renderer needs.
 * Milestone 0 surface area: getEngineUrl, getAppVersion. Future milestones
 * add folder picker, settings, dependency status, etc.
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    getEngineUrl: () => ipcRenderer.invoke('get-engine-url'),
    getAppVersion: () => ipcRenderer.invoke('get-app-version'),
});
