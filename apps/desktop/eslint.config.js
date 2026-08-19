// Flat config (ESLint 9). Scope is deliberately the app's own source: everything
// under src/, plus the two build scripts. Generated and vendored trees are not
// linted because nothing here can act on what they say.
import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'

export default tseslint.config(
  {
    // RDKit's MinimalLib (RDKit_minimal.js/.wasm) is copied in by
    // scripts/copy-rdkit.mjs at install time. It is an Emscripten build product,
    // not source: it accounts for 152 of the 170 findings on a first run, none of
    // which anyone here can act on. Lint what we wrote.
    ignores: [
      'dist/**',
      'public/RDKit_minimal.js',
      'public/rdkit/**',
      'src-tauri/target/**',
      'node_modules/**',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    languageOptions: {
      ecmaVersion: 2022,
      globals: {
        // The renderer is a browser context (a Tauri webview).
        window: 'readonly',
        document: 'readonly',
        console: 'readonly',
        fetch: 'readonly',
        localStorage: 'readonly',
        WebSocket: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        requestAnimationFrame: 'readonly',
        AbortController: 'readonly',
        HTMLElement: 'readonly',
        HTMLInputElement: 'readonly',
        HTMLTextAreaElement: 'readonly',
        HTMLDivElement: 'readonly',
        KeyboardEvent: 'readonly',
        Event: 'readonly',
        File: 'readonly',
        FileReader: 'readonly',
        Blob: 'readonly',
        URL: 'readonly',
        TextDecoder: 'readonly',
        TextEncoder: 'readonly',
        crypto: 'readonly',
        navigator: 'readonly',
        alert: 'readonly',
      },
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // A warning, not an error, and the reason matters.
      //
      // This rule is new in eslint-plugin-react-hooks v7 (the React Compiler rule
      // set). It is a PERFORMANCE advisory about cascading renders, not a
      // correctness rule, and every one of the eleven places it fires here is the
      // same deliberate shape: an effect that clears stale state and then kicks off
      // an async load —
      //
      //     useEffect(() => { setError(null); api.load().then(setData) }, [dep])
      //
      // That is the documented way to fetch on mount without a data library, and
      // the components are covered by the vitest suite. Rewriting eleven screens to
      // silence a fresh advisory would be a real behaviour change made under lint
      // pressure, which is a bad trade. Left visible as a warning so the debt is on
      // the record instead of configured out of existence.
      'react-hooks/set-state-in-effect': 'warn',
      // An unused binding is either dead code or a typo. The underscore prefix is
      // the escape hatch for the deliberate case (an ignored callback parameter).
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
      ],
    },
  },
  {
    // Test files add the vitest/testing-library globals.
    files: ['**/*.test.{ts,tsx}', 'src/setupTests.ts'],
    languageOptions: {
      globals: {
        describe: 'readonly', it: 'readonly', test: 'readonly', expect: 'readonly',
        beforeEach: 'readonly', afterEach: 'readonly', beforeAll: 'readonly',
        afterAll: 'readonly', vi: 'readonly', global: 'readonly',
      },
    },
  },
  {
    // Node build scripts, not renderer code.
    files: ['scripts/**/*.mjs', '*.config.{ts,js}'],
    languageOptions: {
      globals: { process: 'readonly', console: 'readonly', __dirname: 'readonly' },
    },
  },
)
