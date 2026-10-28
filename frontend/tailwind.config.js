// Colors are CSS-variable tokens (see src/index.css) so light/dark themes switch at runtime.
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        brand: { 50: '#eef3ff', 100: '#dbe6ff', 400: '#6f9bff', 500: '#3d7bff', 600: '#2c63e0', 700: '#2350b8' },
        bg: token('bg'),
        surface: token('surface'),
        raised: token('raised'),
        line: token('line'),
        fg: token('fg'),
        muted: token('muted'),
        subtle: token('subtle'),
        gain: token('gain'),
        loss: token('loss'),
        caution: token('caution'),
        // legacy names kept for existing pages
        ink: { 900: '#0f172a', 700: '#334155', 500: '#64748b' },
        ok: '#16a34a', warn: '#f59e0b', danger: '#dc2626',
      },
      boxShadow: {
        card: '0 1px 2px rgb(0 0 0 / 0.04), 0 1px 3px rgb(0 0 0 / 0.06)',
        pop: '0 12px 32px -8px rgb(0 0 0 / 0.35)',
      },
    },
  },
  plugins: [],
}
