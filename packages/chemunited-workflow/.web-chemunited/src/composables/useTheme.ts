import { ref } from 'vue'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'chemunited-theme'

function storedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

// Shared by the sidebar toggle and the Configurations page.
const theme = ref<Theme>(
  storedTheme() ?? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
)

function applyTheme(value: Theme) {
  document.documentElement.dataset.theme = value
  document.querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', value === 'dark' ? '#071525' : '#f3f7fb')
}

applyTheme(theme.value)

export function useTheme() {
  function setTheme(value: Theme) {
    theme.value = value
    try {
      localStorage.setItem(STORAGE_KEY, value)
    } catch {
      // Not remembered, but still applied for this visit.
    }
    applyTheme(value)
  }

  function toggleTheme() {
    setTheme(theme.value === 'dark' ? 'light' : 'dark')
  }

  return { theme, setTheme, toggleTheme }
}
