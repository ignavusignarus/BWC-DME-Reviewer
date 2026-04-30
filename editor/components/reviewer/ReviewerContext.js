import { createContext, useContext } from 'react';

export const ReviewerContext = createContext(null);

export function useReviewer() {
    const ctx = useContext(ReviewerContext);
    if (!ctx) throw new Error('useReviewer must be used inside <ReviewerView>');
    return ctx;
}
