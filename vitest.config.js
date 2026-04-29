import { defineConfig } from 'vitest/config';

export default defineConfig({
    test: {
        environment: 'jsdom',
        globals: true,
        include: ['editor/**/*.test.{js,jsx,ts,tsx}'],
    },
    esbuild: {
        jsx: 'automatic',
        loader: 'jsx',
    },
});
