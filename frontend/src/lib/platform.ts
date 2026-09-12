/** True when running inside the native Android APK (Capacitor WebView). */
export function isNativeApk(): boolean {
  try {
    const w = window as unknown as { Capacitor?: { isNativePlatform?: () => boolean } }
    if (typeof w.Capacitor !== 'undefined' && typeof w.Capacitor.isNativePlatform === 'function') {
      return w.Capacitor.isNativePlatform()
    }
  } catch {
    /* ignore */
  }
  // Capacitor serves the bundled app from https://localhost inside the Android WebView.
  return /Android/i.test(navigator.userAgent) && location.protocol === 'https:' && location.hostname === 'localhost'
}

/** The APK ships citizen-only: no authority login, authority routes are unreachable. */
export function isCitizenKiosk(): boolean {
  return isNativeApk()
}