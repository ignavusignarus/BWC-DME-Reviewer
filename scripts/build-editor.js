/*
 * esbuild driver for the React editor bundle.
 *
 * Usage:
 *   node scripts/build-editor.js          # one-shot build
 *   node scripts/build-editor.js --watch  # rebuild on change
 *
 * Produces: editor-bundle.js at the repo root, referenced by index.html.
 */

const path = require('path');
const esbuild = require('esbuild');

const watch = process.argv.includes('--watch');
const isProduction = process.env.NODE_ENV === 'production';

const buildOptions = {
    entryPoints: [path.join(__dirname, '..', 'editor', 'main.jsx')],
    bundle: true,
    outfile: path.join(__dirname, '..', 'editor-bundle.js'),
    jsx: 'automatic',
    loader: { '.jsx': 'jsx' },
    define: {
        'process.env.NODE_ENV': JSON.stringify(isProduction ? 'production' : 'development'),
    },
    sourcemap: !isProduction,
    minify: isProduction,
    logLevel: 'info',
};

async function main() {
    if (watch) {
        const ctx = await esbuild.context(buildOptions);
        await ctx.watch();
        console.log('[build-editor] watching for changes…');
    } else {
        await esbuild.build(buildOptions);
        console.log('[build-editor] built editor-bundle.js');
    }
}

main().catch((err) => {
    console.error('[build-editor] failed:', err);
    process.exit(1);
});
