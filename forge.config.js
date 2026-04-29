module.exports = {
    packagerConfig: {
        name: 'BWC Clipper',
        executableName: 'bwc-clipper',
        appBundleId: 'law.panish.bwcclipper',
        asar: true,
        ignore: [
            /^\/\.venv($|\/)/,
            /^\/node_modules\/electron\/dist\//,
            /^\/tests($|\/)/,
            /^\/docs($|\/)/,
            /^\/\.bwcclipper($|\/)/,
            /^\/Samples($|\/)/,
            /^\/clips($|\/)/,
            /^\/\.git($|\/)/,
            /^\/\.gitignore$/,
        ],
    },
    rebuildConfig: {},
    makers: [
        { name: '@electron-forge/maker-zip', platforms: ['darwin', 'linux', 'win32'] },
    ],
    plugins: [],
};
