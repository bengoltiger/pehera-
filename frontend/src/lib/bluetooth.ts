/**
 * Bluetooth capability + peer-relay primitives for the citizen mobile app.
 *
 * Three real transport levels, resolved at runtime:
 *   1. `native`   — inside the PEHRA Android APK (Capacitor +
 *                   @capacitor-community/bluetooth-le). Calling through the
 *                   runtime bridge (no import needed) so the web bundle stays
 *                   free of the plugin.
 *   2. `web`      — Web Bluetooth (Chrome/Android). Works for the "enable
 *                   Bluetooth" prompt; peer discovery is limited on purpose.
 *   3. `simulated`— any other browser. The app still runs, clearly labelled.
 *
 * IMPORTANT: the demo never guarantees real phone-to-phone BLE pairing.
 * Peer relay between the Person 1/2/3 personas is therefore SIMULATED at the
 * server (the client reports "relayed via Person X"). This file only performs
 * the real permission request so the user experience matches the real app.
 */
export type BtMode = 'native' | 'web' | 'simulated' | 'off'

export interface BtState {
  mode: BtMode
  enabled: boolean
  permission: 'granted' | 'denied' | 'unsupported' | 'n/a'
  label: string
  note: string
}

const BT_MODE_KEY = 'pehra.bt_mode'

function nativeLePlugin(): any | null {
  try {
    const w = window as any
    if (w.Capacitor?.isNativePlatform?.() && w.Capacitor?.Plugins?.BluetoothLE) {
      return w.Capacitor.Plugins.BluetoothLE
    }
  } catch {
    /* bridge unavailable */
  }
  return null
}

export function detectBt(): { mode: BtMode; supported: boolean; label: string } {
  if (nativeLePlugin()) return { mode: 'native', supported: true, label: 'Native Bluetooth (APK)' }
  if (typeof navigator !== 'undefined' && 'bluetooth' in navigator) {
    return { mode: 'web', supported: true, label: 'Web Bluetooth' }
  }
  return { mode: 'simulated', supported: false, label: 'No Bluetooth API — SIMULATED' }
}

export function getStoredBtMode(): BtMode {
  try {
    const v = localStorage.getItem(BT_MODE_KEY)
    if (v === 'native' || v === 'web' || v === 'simulated' || v === 'off') return v
  } catch {
    /* storage disabled */
  }
  return 'off'
}

function storeBtMode(mode: BtMode) {
  try {
    localStorage.setItem(BT_MODE_KEY, mode)
  } catch {
    /* ignore */
  }
}

/** Request the OS Bluetooth permission (real), or fall back to simulation. */
export async function requestBluetoothEnable(): Promise<BtState> {
  const det = detectBt()

  // 1) Native APK — real Android permission prompt via the Capacitor bridge.
  if (det.mode === 'native') {
    const plugin = nativeLePlugin()
    try {
      await plugin.initialize()
      const perms = await plugin.requestPermissions()
      const ok = perms && (perms.permissions?.ble === 'granted' || perms.permissions?.location === 'granted' || perms.granted === true)
      const state: BtState = ok
        ? { mode: 'native', enabled: true, permission: 'granted', label: 'Bluetooth ON', note: 'Real Bluetooth permissions granted on this device.' }
        : { mode: 'native', enabled: false, permission: 'denied', label: 'Bluetooth denied', note: 'Permission was not granted. The demo can continue in simulated relay mode.' }
      if (ok) storeBtMode('native')
      return state
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'unknown'
      storeBtMode('simulated')
      return {
        mode: 'simulated',
        enabled: true,
        permission: 'unsupported',
        label: 'Bluetooth unavailable — SIMULATED relay',
        note: `Native BLE failed (${msg}). Continuing with SIMULATED peer relay for the demo.`,
      }
    }
  }

  // 2) Web Bluetooth — browser prompt.
  if (det.mode === 'web') {
    try {
      const nav = navigator as any
      const available = typeof nav.bluetooth.getAvailability === 'function' ? await nav.bluetooth.getAvailability() : true
      if (available === false) throw new Error('Bluetooth hardware not available')
      await nav.bluetooth.requestDevice({ acceptAllDevices: true })
      storeBtMode('web')
      return {
        mode: 'web',
        enabled: true,
        permission: 'granted',
        label: 'Bluetooth ON',
        note: 'Web Bluetooth session allowed. Peer relay between personas is simulated server-side.',
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'unknown'
      // Permission cancel / no hardware → continue as simulation, never break the app.
      storeBtMode('simulated')
      return {
        mode: 'simulated',
        enabled: true,
        permission: 'unsupported',
        label: 'Bluetooth unavailable — SIMULATED relay',
        note: `Web Bluetooth could not be used (${msg}). Continuing with SIMULATED peer relay for the demo.`,
      }
    }
  }

  // 3) Simulated — no API at all.
  storeBtMode('simulated')
  return {
    mode: 'simulated',
    enabled: true,
    permission: 'n/a',
    label: 'Bluetooth SIMULATED',
    note: 'This browser has no Bluetooth API. Peer relay is driven by the demo server (labelled SIMULATED).',
  }
}

export function turnBluetoothOff(): BtState {
  storeBtMode('off')
  return {
    mode: 'off',
    enabled: false,
    permission: 'n/a',
    label: 'Bluetooth off',
    note: 'Bluetooth relay is switched off in this demo session.',
  }
}

/** Simulated peer list for the demo's relay flow (always clearly labelled). */
export function simulatedPeers(activePersona: string, otherPersonas: string[]): { id: string; rssi_dbm: number; distance_m: number }[] {
  return otherPersonas.map((name, i) => ({
    id: name,
    rssi_dbm: -46 - (i % 3) * 14 - Math.floor(Math.abs(activePersona.charCodeAt(1)) % 3) * 5,
    distance_m: 4 + i * 9,
  }))
}