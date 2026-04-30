import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import Waveform from './Waveform.jsx';

beforeEach(() => {
    globalThis.fetch = vi.fn(() => Promise.resolve({
        ok: true,
        arrayBuffer: () => Promise.resolve(new ArrayBuffer(1024)),
    }));
    globalThis.AudioContext = class {
        decodeAudioData(buf) {
            // Synthetic audio: 48000 samples, single channel.
            const channelLength = 48000;
            return Promise.resolve({
                length: channelLength,
                numberOfChannels: 1,
                getChannelData: () => Float32Array.from({ length: channelLength }, (_, i) => Math.sin(i / 100)),
            });
        }
    };
});

describe('Waveform', () => {
    it('renders a canvas after decoding audio', async () => {
        const { container } = render(<Waveform url="/api/source/audio?x=y" />);
        await waitFor(() => expect(container.querySelector('canvas')).toBeTruthy());
    });

    it('shows loading state before decode resolves', () => {
        const { container } = render(<Waveform url="/api/source/audio?x=y" />);
        // Before any await, loading text should be visible
        expect(container.textContent.toLowerCase()).toContain('loading');
    });
});
