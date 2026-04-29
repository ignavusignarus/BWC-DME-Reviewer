/*
 * ffmpeg + ffprobe downloader for Windows.
 *
 * On first launch, downloads a release-essentials zip from the first
 * working source in ffmpeg-hashes.json, verifies the SHA-256 if pinned,
 * extracts ffmpeg.exe and ffprobe.exe into:
 *
 *     %LOCALAPPDATA%\BWCClipper\ffmpeg\
 *
 * Subsequent launches find the binaries already present and skip the
 * download. Reports progress via an optional onProgress(fraction)
 * callback so the splash window can show a progress indicator.
 *
 * macOS support arrives in the packaging milestone; this file is
 * Windows-only for V1.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const https = require('https');
const crypto = require('crypto');
const { spawnSync } = require('child_process');
const { app } = require('electron');

const HASHES = require('./ffmpeg-hashes.json');

function getFFmpegDir() {
    // %LOCALAPPDATA%\BWCClipper\ffmpeg on Windows; equivalent on other platforms.
    return path.join(app.getPath('userData'), 'ffmpeg');
}

function ffmpegBinaryName() {
    return process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg';
}

function ffprobeBinaryName() {
    return process.platform === 'win32' ? 'ffprobe.exe' : 'ffprobe';
}

function isInstalled() {
    const dir = getFFmpegDir();
    return fs.existsSync(path.join(dir, ffmpegBinaryName())) &&
           fs.existsSync(path.join(dir, ffprobeBinaryName()));
}

function downloadBuffer(url, onProgress) {
    return new Promise((resolve, reject) => {
        const fetch = (currentUrl, redirectsLeft) => {
            https.get(currentUrl, { headers: { 'User-Agent': 'BWCClipper/0.0.1' } }, (res) => {
                if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                    if (redirectsLeft <= 0) return reject(new Error('too many redirects'));
                    return fetch(res.headers.location, redirectsLeft - 1);
                }
                if (res.statusCode !== 200) {
                    return reject(new Error(`download failed: HTTP ${res.statusCode}`));
                }
                const total = parseInt(res.headers['content-length'] || '0', 10);
                const chunks = [];
                let downloaded = 0;
                res.on('data', (chunk) => {
                    chunks.push(chunk);
                    downloaded += chunk.length;
                    if (onProgress && total > 0) onProgress(downloaded / total);
                });
                res.on('end', () => resolve(Buffer.concat(chunks)));
                res.on('error', reject);
            }).on('error', reject);
        };
        fetch(url, 5);
    });
}

function verifySha256(buffer, expected) {
    if (!expected) return; // unpinned
    const actual = crypto.createHash('sha256').update(buffer).digest('hex');
    if (actual !== expected) {
        throw new Error(`SHA-256 mismatch: expected ${expected}, got ${actual}`);
    }
}

function extractBinariesFromZip(zipPath, outDir) {
    // Use PowerShell's built-in Expand-Archive (every Win10+ has it),
    // then walk the extract dir to find ffmpeg.exe and ffprobe.exe.
    const tmpExtract = path.join(outDir, '_extract');
    fs.rmSync(tmpExtract, { recursive: true, force: true });
    fs.mkdirSync(tmpExtract, { recursive: true });

    const result = spawnSync(
        'powershell',
        ['-NoProfile', '-Command', `Expand-Archive -LiteralPath '${zipPath}' -DestinationPath '${tmpExtract}' -Force`],
        { stdio: 'pipe', encoding: 'utf8' }
    );
    if (result.status !== 0) {
        throw new Error(`Expand-Archive failed: ${result.stderr || result.stdout}`);
    }

    // Recursively find ffmpeg.exe and ffprobe.exe and copy them to outDir.
    const findAndCopy = (dir, target) => {
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
            const full = path.join(dir, entry.name);
            if (entry.isDirectory()) {
                const found = findAndCopy(full, target);
                if (found) return found;
            } else if (entry.name === target) {
                fs.copyFileSync(full, path.join(outDir, target));
                return full;
            }
        }
        return null;
    };
    if (!findAndCopy(tmpExtract, ffmpegBinaryName())) {
        throw new Error('ffmpeg.exe not found in zip');
    }
    if (!findAndCopy(tmpExtract, ffprobeBinaryName())) {
        throw new Error('ffprobe.exe not found in zip');
    }

    fs.rmSync(tmpExtract, { recursive: true, force: true });
}

async function ensureInstalled(onProgress) {
    if (isInstalled()) return getFFmpegDir();

    const dir = getFFmpegDir();
    fs.mkdirSync(dir, { recursive: true });

    if (process.platform !== 'win32') {
        throw new Error('ffmpeg auto-download is Windows-only in V1');
    }

    const platformKey = 'win64';
    const sources = (HASHES[platformKey] && HASHES[platformKey].sources) || [];
    if (sources.length === 0) throw new Error(`no sources configured for ${platformKey}`);

    let lastError = null;
    for (const source of sources) {
        try {
            if (onProgress) onProgress({ phase: 'downloading', source: source.label, fraction: 0 });
            const buffer = await downloadBuffer(source.url, (f) => {
                if (onProgress) onProgress({ phase: 'downloading', source: source.label, fraction: f });
            });
            verifySha256(buffer, source.sha256);

            if (onProgress) onProgress({ phase: 'extracting', source: source.label, fraction: 1 });
            const tmpZip = path.join(dir, '_download.zip');
            fs.writeFileSync(tmpZip, buffer);
            try {
                extractBinariesFromZip(tmpZip, dir);
            } finally {
                fs.rmSync(tmpZip, { force: true });
            }

            if (onProgress) onProgress({ phase: 'ready', source: source.label, fraction: 1 });
            return dir;
        } catch (err) {
            console.warn(`[ffmpeg-downloader] source "${source.label}" failed: ${err.message}`);
            lastError = err;
        }
    }
    throw new Error(`all ffmpeg sources failed; last: ${lastError && lastError.message}`);
}

module.exports = {
    getFFmpegDir,
    ffmpegBinaryName,
    ffprobeBinaryName,
    isInstalled,
    ensureInstalled,
};
