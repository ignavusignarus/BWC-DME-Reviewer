/*
 * Tiny fetch wrapper around the engine HTTP server.
 *
 * The engine URL is injected at runtime via window.electronAPI.getEngineUrl().
 * In dev / test environments without electronAPI, defaults to a static
 * environment variable so the editor can be unit-tested in jsdom.
 */

let _cachedBase = null;

async function getBaseUrl() {
    if (_cachedBase) return _cachedBase;
    if (typeof window !== 'undefined' && window.electronAPI?.getEngineUrl) {
        _cachedBase = await window.electronAPI.getEngineUrl();
        return _cachedBase;
    }
    // Test/dev fallback — overridable for unit tests.
    _cachedBase = 'http://127.0.0.1:0';
    return _cachedBase;
}

export function _resetCachedBaseForTests() {
    _cachedBase = null;
}

export async function apiGet(path) {
    const base = await getBaseUrl();
    const response = await fetch(`${base}${path}`);
    if (!response.ok) {
        throw new Error(`API ${path} returned ${response.status}`);
    }
    return response.json();
}
