import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import TopBar from './TopBar.jsx';

const MANIFEST = {
    folder: '/cases/williams',
    files: [
        { path: '/cases/williams/exam-1.mp3', completed: true },
        { path: '/cases/williams/exam-2.mp3', completed: false },
        { path: '/cases/williams/exam-3.mp3', completed: true },
    ],
};

describe('TopBar', () => {
    it('renders the folder breadcrumb', () => {
        render(<TopBar manifest={MANIFEST} source={MANIFEST.files[0]} onBack={() => {}} onSelectSource={() => {}} />);
        expect(screen.getByText(/cases\/williams/)).toBeDefined();
    });

    it('source picker filters to completed sources only', () => {
        render(<TopBar manifest={MANIFEST} source={MANIFEST.files[0]} onBack={() => {}} onSelectSource={() => {}} />);
        const options = screen.getAllByRole('option');
        expect(options.length).toBe(2);
        expect(options[0].textContent).toMatch(/exam-1\.mp3/);
        expect(options[1].textContent).toMatch(/exam-3\.mp3/);
    });

    it('selecting a source calls onSelectSource', () => {
        const onSelectSource = vi.fn();
        render(<TopBar manifest={MANIFEST} source={MANIFEST.files[0]} onBack={() => {}} onSelectSource={onSelectSource} />);
        fireEvent.change(screen.getByRole('combobox'), { target: { value: '/cases/williams/exam-3.mp3' } });
        expect(onSelectSource).toHaveBeenCalledWith(MANIFEST.files[2]);
    });

    it('back button calls onBack', () => {
        const onBack = vi.fn();
        render(<TopBar manifest={MANIFEST} source={MANIFEST.files[0]} onBack={onBack} onSelectSource={() => {}} />);
        fireEvent.click(screen.getByRole('button', { name: /project/i }));
        expect(onBack).toHaveBeenCalled();
    });
});
