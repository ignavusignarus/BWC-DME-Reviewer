import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import EmptyState from './EmptyState.jsx';

describe('EmptyState', () => {
    it('renders the open-folder button', () => {
        render(<EmptyState onOpenFolder={() => {}} />);
        expect(screen.getByRole('button', { name: /open folder/i })).toBeDefined();
    });

    it('calls onOpenFolder when the button is clicked', () => {
        const onOpenFolder = vi.fn();
        render(<EmptyState onOpenFolder={onOpenFolder} />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        expect(onOpenFolder).toHaveBeenCalledTimes(1);
    });

    it('renders an explanatory headline', () => {
        render(<EmptyState onOpenFolder={() => {}} />);
        expect(screen.getByText(/BWC Clipper/i)).toBeDefined();
    });
});
