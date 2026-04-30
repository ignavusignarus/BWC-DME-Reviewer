/*
 * dev-shim.js — installs window.electronAPI when running the editor in plain
 * Chrome (no Electron). Production uses electron/preload.js; this file is
 * loaded only from dev-chrome.html and never bundled into the desktop app.
 *
 * Configuration sources (in priority order):
 *   1. URL query params: ?engine=8765&folder=C:%2Fcase
 *   2. window._devFolder / window._devEngine (set by harness JS injection)
 *   3. window.prompt() fallback for pickFolder
 */
(function installDevShim() {
    const params = new URLSearchParams(window.location.search);

    function getEnginePort() {
        const fromQuery = params.get('engine');
        if (fromQuery) return parseInt(fromQuery, 10);
        if (window._devEngine) return parseInt(window._devEngine, 10);
        return null;
    }

    function getEngineUrl() {
        // When the dev page is served by dev_server.py (the static + reverse
        // proxy), prefer same-origin so /api/* requests stay on the same host
        // and avoid CORS preflight. Production Electron always uses the
        // hardcoded engine port via the real preload bridge, so this fallback
        // path doesn't affect production.
        if (params.get('proxy') !== '0') {
            return ''; // empty string -> apiPost('/api/foo') hits same origin
        }
        const port = getEnginePort();
        if (!port) {
            console.error('[dev-shim] no engine port set — pass ?engine=PORT or set window._devEngine');
            return 'http://127.0.0.1:0';
        }
        return `http://127.0.0.1:${port}`;
    }

    function currentFolder() {
        return params.get('folder') || window._devFolder || null;
    }

    async function pickFolder() {
        // 1) URL param wins (one-shot — clear after first use so the React
        //    "Choose Folder" button isn't sticky if the user clicks again).
        const fromQuery = params.get('folder');
        if (fromQuery) {
            params.delete('folder');
            const newSearch = params.toString();
            const newUrl = window.location.pathname + (newSearch ? '?' + newSearch : '');
            window.history.replaceState(null, '', newUrl);
            window._devFolder = fromQuery;
            updateBanner();
            return fromQuery;
        }
        // 2) Harness-injected value (one-shot).
        if (window._devFolder) {
            const v = window._devFolder;
            window._devFolder = null;
            updateBanner();
            return v;
        }
        // 3) Last resort: prompt the user.
        const entered = window.prompt('Enter project folder path:');
        return entered && entered.trim() ? entered.trim() : null;
    }

    function getAppVersion() {
        return Promise.resolve('dev');
    }

    window.electronAPI = {
        getEngineUrl: () => Promise.resolve(getEngineUrl()),
        getAppVersion,
        pickFolder,
    };

    function updateBanner() {
        const engineEl = document.getElementById('dev-engine');
        const folderEl = document.getElementById('dev-folder');
        const warnEl = document.getElementById('dev-warn');
        if (!engineEl) return; // banner not in this page
        const port = getEnginePort();
        engineEl.textContent = port ? `127.0.0.1:${port}` : '(no port — set ?engine=)';
        const folder = currentFolder();
        folderEl.textContent = folder || '(unset)';
        if (warnEl) {
            warnEl.className = port ? '' : 'warn';
            warnEl.textContent = port ? '' : 'engine port missing';
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', updateBanner);
    } else {
        updateBanner();
    }

    // Expose helpers for the harness so I can drive the app via JS injection.
    window._dev = {
        setFolder: (path) => { window._devFolder = path; updateBanner(); },
        setEngine: (port) => { window._devEngine = String(port); updateBanner(); },
        getEngineUrl,
        currentFolder,
    };

    console.log('[dev-shim] electronAPI installed; engine =', getEnginePort(), 'folder =', currentFolder());
})();
