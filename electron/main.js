/*
 * BWC Clipper Electron main process.
 *
 * Milestone 0 responsibilities:
 *   - Open splash window on startup.
 *   - Spawn the Python engine subprocess (added in Task 17).
 *   - When the engine signals "ready," dismiss splash and open main window
 *     pointing at index.html (added in Task 17).
 *   - Handle 'get-engine-url' and 'get-app-version' IPC requests.
 *
 * For Task 16, only the main-window-open logic is here; engine spawn arrives
 * next. We open the main window directly so we can verify the renderer loads
 * the editor bundle before adding subprocess complexity.
 */
const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');

let mainWindow = null;

// Placeholder until Task 17 — main window will fetch this URL via electronAPI.
let _engineUrl = 'http://127.0.0.1:0';

function createMainWindow() {
    mainWindow = new BrowserWindow({
        width: 1280,
        height: 800,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
        },
    });
    mainWindow.loadFile(path.join(__dirname, '..', 'index.html'));
    mainWindow.on('closed', () => { mainWindow = null; });
}

ipcMain.handle('get-engine-url', () => _engineUrl);
ipcMain.handle('get-app-version', () => app.getVersion());

app.whenReady().then(() => {
    createMainWindow();
    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
