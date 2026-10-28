export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: { 50: '#eef6ff', 500: '#2563eb', 700: '#1d4ed8' },
        surface: { 0: '#ffffff', 1: '#f8fafc', 2: '#f1f5f9' },
        ink: { 900: '#0f172a', 700: '#334155', 500: '#64748b' },
        ok: '#16a34a', warn: '#f59e0b', danger: '#dc2626',
      },
    },
  },
  plugins: [],
}
