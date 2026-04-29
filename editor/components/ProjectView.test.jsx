import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ProjectView from './ProjectView.jsx';

const sampleManifest = {
    folder: 'C:/case-folder',
    files: [
        { basename: 'a.mp4', path: 'C:/case-folder/a.mp4', extension: 'mp4', mode: 'bwc', size_bytes: 1024 },
        { basename: 'b.MP3', path: 'C:/case-folder/b.MP3', extension: 'MP3', mode: 'dme', size_bytes: 2048 },
    ],
};

describe('ProjectView', () => {
    it('renders the folder path in the header', () => {
        render(
            <ProjectView
                manifest={sampleManifest}
                selectedPath={null}
                onSelectFile={() => {}}
                onCloseProject={() => {}}
            />,
        );
        expect(screen.getByText(/C:\/case-folder/)).toBeDefined();
    });

    it('renders a row per file', () => {
        render(
            <ProjectView
                manifest={sampleManifest}
                selectedPath={null}
                onSelectFile={() => {}}
                onCloseProject={() => {}}
            />,
        );
        expect(screen.getByText('a.mp4')).toBeDefined();
        expect(screen.getByText('b.MP3')).toBeDefined();
    });

    it('marks the selected file', () => {
        const { container } = render(
            <ProjectView
                manifest={sampleManifest}
                selectedPath="C:/case-folder/a.mp4"
                onSelectFile={() => {}}
                onCloseProject={() => {}}
            />,
        );
        const selected = container.querySelector('[aria-selected="true"]');
        expect(selected).not.toBeNull();
        expect(selected.textContent).toContain('a.mp4');
    });

    it('calls onSelectFile with the file when a row is clicked', () => {
        const onSelectFile = vi.fn();
        render(
            <ProjectView
                manifest={sampleManifest}
                selectedPath={null}
                onSelectFile={onSelectFile}
                onCloseProject={() => {}}
            />,
        );
        fireEvent.click(screen.getByText('b.MP3'));
        expect(onSelectFile).toHaveBeenCalledWith(
            expect.objectContaining({ basename: 'b.MP3', mode: 'dme' }),
        );
    });

    it('shows a "no media files" message for an empty manifest', () => {
        const empty = { folder: 'C:/empty', files: [] };
        render(
            <ProjectView
                manifest={empty}
                selectedPath={null}
                onSelectFile={() => {}}
                onCloseProject={() => {}}
            />,
        );
        expect(screen.getByText(/no media files/i)).toBeDefined();
    });

    it('calls onCloseProject when the close button is clicked', () => {
        const onCloseProject = vi.fn();
        render(
            <ProjectView
                manifest={sampleManifest}
                selectedPath={null}
                onSelectFile={() => {}}
                onCloseProject={onCloseProject}
            />,
        );
        fireEvent.click(screen.getByRole('button', { name: /close/i }));
        expect(onCloseProject).toHaveBeenCalledTimes(1);
    });
});
