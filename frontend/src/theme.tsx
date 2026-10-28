import React, { createContext, useContext, useEffect, useState } from 'react'

type Theme = 'dark' | 'light'

const Ctx = createContext<{ theme: Theme; toggle: () => void }>({ theme: 'dark', toggle: () => {} })

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.classList.contains('dark') ? 'dark' : 'light')
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try { localStorage.setItem('theme', theme) } catch { /* storage unavailable */ }
  }, [theme])
  return <Ctx.Provider value={{ theme, toggle: () => setTheme(t => (t === 'dark' ? 'light' : 'dark')) }}>{children}</Ctx.Provider>
}

export const useTheme = () => useContext(Ctx)

/** Chart colors per theme (Recharts needs concrete values, not CSS vars). */
export function useChartColors() {
  const { theme } = useTheme()
  const dark = theme === 'dark'
  return {
    grid: dark ? '#1c263a' : '#e8edf3',
    axis: dark ? '#68758d' : '#8491a5',
    tooltipBg: dark ? '#141c2d' : '#ffffff',
    tooltipBorder: dark ? '#26324a' : '#e2e7ef',
    text: dark ? '#e6ebf4' : '#0f172a',
    brand: '#3d7bff',
    gain: dark ? '#22c55e' : '#16a34a',
    loss: dark ? '#f85149' : '#dc2626',
    fee: '#a78bfa',
    series: ['#3d7bff', '#22c55e', '#f59e0b', '#a78bfa', '#06b6d4', '#f472b6'],
  }
}
