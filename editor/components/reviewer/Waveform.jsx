import React, { useEffect, useRef, useState } from 'react';

const PEAK_COUNT = 2000;

export default function Waveform({ url }) {
    const canvasRef = useRef(null);
    const [peaks, setPeaks] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        async function load() {
            setLoading(true);
            try {
                const buf = await fetch(url).then(r => r.arrayBuffer());
                if (cancelled) return;
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const decoded = await ctx.decodeAudioData(buf);
                if (cancelled) return;
                const channel = decoded.getChannelData(0);
                const samplesPerPeak = Math.max(1, Math.ceil(channel.length / PEAK_COUNT));
                const out = new Float32Array(PEAK_COUNT);
                for (let i = 0; i < PEAK_COUNT; i++) {
                    let max = 0;
                    const start = i * samplesPerPeak;
                    const end = Math.min(start + samplesPerPeak, channel.length);
                    for (let j = start; j < end; j++) {
                        const v = Math.abs(channel[j]);
                        if (v > max) max = v;
                    }
                    out[i] = max;
                }
                setPeaks(out);
            } catch (err) {
                console.warn('[Waveform] decode failed:', err);
            } finally {
                if (!cancelled) setLoading(false);
            }
        }
        load();
        return () => { cancelled = true; };
    }, [url]);

    useEffect(() => {
        if (!peaks || !canvasRef.current) return;
        const canvas = canvasRef.current;
        const dpr = window.devicePixelRatio || 1;
        const w = canvas.clientWidth || 800;
        const h = canvas.clientHeight || 110;
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        const c = canvas.getContext('2d');
        if (!c) return;
        c.scale(dpr, dpr);
        c.clearRect(0, 0, w, h);
        c.fillStyle = '#2ea3a3';
        const barWidth = Math.max(1, w / peaks.length);
        for (let i = 0; i < peaks.length; i++) {
            const barHeight = peaks[i] * h;
            c.fillRect(i * barWidth, (h - barHeight) / 2, Math.max(1, barWidth - 0.5), barHeight);
        }
    }, [peaks]);

    return (
        <div data-testid="waveform-container" style={{ position: 'relative', width: '100%', height: 110 }}>
            <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block' }} />
            {loading && (
                <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6e7681', pointerEvents: 'none', fontSize: '0.78rem' }}>
                    Loading waveform…
                </div>
            )}
        </div>
    );
}
