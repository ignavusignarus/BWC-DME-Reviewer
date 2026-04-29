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
