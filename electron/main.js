/*
 * BWC Clipper Electron main process.
 */
const { app, BrowserWindow, ipcMain } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

let mainWindow = null;
let splashWindow = null;
let pythonProcess = null;
let serverPort = null;
let isShuttingDown = false;

const REPO_ROOT = path.resolve(__dirname, '..');

function pythonExecutable() {
    const candidates = [
        path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe'),  // Windows venv
        path.join(REPO_ROOT, '.venv', 'bin', 'python'),          // POSIX venv
    ];
    for (const c of candidates) {
        if (fs.existsSync(c)) return c;
    }
    // Fall back to system python on PATH; will surface as a clear startup
    // failure if neither venv is present.
    return process.platform === 'win32' ? 'python.exe' : 'python3';
}

function createSplashWindow() {
    splashWindow = new BrowserWindow({
        width: 480,
        height: 320,
        frame: false,
        resizable: false,
        center: true,
        webPreferences: {
            preload: path.join(__dirname, 'splash-preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
        },
    });
    splashWindow.loadFile(path.join(__dirname, 'splash.html'));
    splashWindow.on('closed', () => { splashWindow = null; });
}

function setSplashStatus(message) {
    if (splashWindow && !splashWindow.isDestroyed()) {
        splashWindow.webContents.send('splash-status', message);
    }
}

function spawnEngine() {
    return new Promise((resolve, reject) => {
        const py = pythonExecutable();
        const servePy = path.join(REPO_ROOT, 'serve.py');
        if (!fs.existsSync(servePy)) {
            reject(new Error(`serve.py not found at ${servePy}`));
            return;
        }
        console.log(`[main] spawning engine: ${py} ${servePy}`);
        const proc = spawn(py, [servePy], {
            cwd: REPO_ROOT,
            env: { ...process.env, PYTHONUNBUFFERED: '1' },
            stdio: ['ignore', 'pipe', 'pipe'],
        });

        let portResolved = false;
        const PORT_TIMEOUT_MS = 15000;
        const timeoutHandle = setTimeout(() => {
            if (!portResolved) {
                portResolved = true;
                proc.kill();
                reject(new Error(`engine did not print BWC_CLIPPER_PORT= within ${PORT_TIMEOUT_MS}ms`));
            }
        }, PORT_TIMEOUT_MS);

        let stdoutBuffer = '';
        proc.stdout.on('data', (chunk) => {
            stdoutBuffer += chunk.toString('utf8');
            const lines = stdoutBuffer.split('\n');
            stdoutBuffer = lines.pop();  // keep partial trailing line
            for (const line of lines) {
                const trimmed = line.trim();
                if (trimmed.startsWith('BWC_CLIPPER_PORT=')) {
                    if (!portResolved) {
                        portResolved = true;
                        clearTimeout(timeoutHandle);
                        const port = parseInt(trimmed.slice('BWC_CLIPPER_PORT='.length), 10);
                        resolve({ proc, port });
                        return;
                    }
                } else if (trimmed) {
                    console.log('[engine stdout]', trimmed);
                }
            }
        });

        proc.stderr.on('data', (chunk) => {
            const text = chunk.toString('utf8');
            for (const line of text.split('\n')) {
                if (line.trim()) console.log('[engine stderr]', line.trim());
            }
        });

        proc.on('error', (err) => {
            if (!portResolved) {
                portResolved = true;
                clearTimeout(timeoutHandle);
                reject(err);
            }
        });

        proc.on('exit', (code, signal) => {
            console.log(`[main] engine exited code=${code} signal=${signal}`);
            if (!isShuttingDown) {
                if (mainWindow && !mainWindow.isDestroyed()) {
                    mainWindow.webContents.send('engine-exited', { code, signal });
                }
            }
        });
    });
}

function createMainWindow() {
    mainWindow = new BrowserWindow({
        width: 1280,
        height: 800,
        show: false,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
        },
    });
    mainWindow.loadFile(path.join(REPO_ROOT, 'index.html'));
    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
        if (splashWindow && !splashWindow.isDestroyed()) splashWindow.close();
    });
    mainWindow.on('closed', () => { mainWindow = null; });
}

ipcMain.handle('get-engine-url', () => {
    if (!serverPort) throw new Error('engine not yet started');
    return `http://127.0.0.1:${serverPort}`;
});
ipcMain.handle('get-app-version', () => app.getVersion());

app.whenReady().then(async () => {
    createSplashWindow();
    setSplashStatus('Starting engine…');
    try {
        const { proc, port } = await spawnEngine();
        pythonProcess = proc;
        serverPort = port;
        setSplashStatus('Engine started. Loading editor…');
        createMainWindow();
    } catch (err) {
        console.error('[main] engine startup failed:', err);
        setSplashStatus(`Failed to start engine: ${err.message}`);
        // Leave splash visible so the user sees the error. They can close it manually.
    }
    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createSplashWindow();
    });
});

app.on('before-quit', () => {
    isShuttingDown = true;
    if (pythonProcess) {
        try { pythonProcess.kill(); } catch (_) {}
        pythonProcess = null;
    }
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
