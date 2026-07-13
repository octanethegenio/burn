try {
  const theme = localStorage.getItem('burn-theme')
  if (theme === 'light' || theme === 'dark') {
    document.documentElement.setAttribute('data-theme', theme)
  }
} catch {
  // The default theme remains active when storage is unavailable.
}
