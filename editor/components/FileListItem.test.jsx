import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import FileListItem from './FileListItem.jsx';

const sampleFile = {
    basename: 'officer-garcia.mp4',
    path: 'C:/case/officer-garcia.mp4',
    extension: 'mp4',
    mode: 'bwc',
    size_bytes: 12_345_678,
};

describe('FileListItem', () => {
    it('renders the basename', () => {
        render(<FileListItem file={sampleFile} selected={false} onSelect={() => {}} />);
        expect(screen.getByText('officer-garcia.mp4')).toBeDefined();
    });

    it('renders the mode badge (BWC for video)', () => {
        render(<FileListItem file={sampleFile} selected={false} onSelect={() => {}} />);
        expect(screen.getByText(/BWC/i)).toBeDefined();
    });

    it('renders DME for audio mode', () => {
        const audio = { ...sampleFile, mode: 'dme', basename: 'doctor.MP3' };
        render(<FileListItem file={audio} selected={false} onSelect={() => {}} />);
        expect(screen.getByText(/DME/i)).toBeDefined();
    });

    it('renders human-readable size', () => {
        render(<FileListItem file={sampleFile} selected={false} onSelect={() => {}} />);
        // 12,345,678 bytes ≈ 11.8 MB
        expect(screen.getByText(/11\.8 MB|12 MB|11 MB/)).toBeDefined();
    });

    it('calls onSelect when clicked', () => {
        const onSelect = vi.fn();
        render(<FileListItem file={sampleFile} selected={false} onSelect={onSelect} />);
        fireEvent.click(screen.getByText('officer-garcia.mp4'));
        expect(onSelect).toHaveBeenCalledWith(sampleFile);
    });

    it('renders selected styling when selected=true', () => {
        const { container } = render(
            <FileListItem file={sampleFile} selected={true} onSelect={() => {}} />,
        );
        const item = container.querySelector('[aria-selected]');
        expect(item).not.toBeNull();
        expect(item.getAttribute('aria-selected')).toBe('true');
    });
});

describe('FileListItem status indicator', () => {
    it('renders no status indicator when status is undefined', () => {
        const { container } = render(
            <FileListItem file={sampleFile} selected={false} onSelect={() => {}} />,
        );
        expect(container.querySelector('[data-status]')).toBeNull();
    });

    it('renders generic running label when status is just "running"', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running"
            />,
        );
        // Plain "running" without a stage suffix falls through to generic label.
        // Don't assert exact wording — implementation detail — but DO assert the
        // status-color dot is visible by aria-hidden glyph.
        expect(screen.getByText('●')).toBeDefined();
    });

    it('renders queued status', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="queued"
            />,
        );
        expect(screen.getByText(/queued/i)).toBeDefined();
    });

    it('renders completed status with checkmark', () => {
        const { container } = render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="completed"
            />,
        );
        const indicator = container.querySelector('[data-status="completed"]');
        expect(indicator).not.toBeNull();
    });

    it('renders failed status', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="failed"
            />,
        );
        expect(screen.getByText(/failed/i)).toBeDefined();
    });
});

describe('FileListItem stage-aware status', () => {
    it('renders "extracting…" for running:extract', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running:extract"
            />,
        );
        expect(screen.getByText(/extracting/i)).toBeDefined();
    });

    it('renders "normalizing…" for running:normalize', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running:normalize"
            />,
        );
        expect(screen.getByText(/normalizing/i)).toBeDefined();
    });

    it('falls back to "running" for an unknown stage suffix', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running:something-new"
            />,
        );
        expect(screen.getByText(/running/i)).toBeDefined();
    });

    it('renders "enhancing…" for running:enhance', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running:enhance"
            />,
        );
        expect(screen.getByText(/enhancing/i)).toBeDefined();
    });

    it('renders "detecting speech…" for running:vad', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running:vad"
            />,
        );
        expect(screen.getByText(/detecting speech/i)).toBeDefined();
    });
});
