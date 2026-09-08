/**
 * Test configuration.
 *
 * Kept separate from vite.config.ts so the app build never carries test-only
 * settings. Tests run against the real FastAPI process (see src/test/setup.ts)
 * because mocked fixtures cannot catch API/UI shape drift.
 */
import path from 'node:path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'src') },
  },
  esbuild: { jsx: 'automatic' },
  test: {
    environment: 'jsdom',
    environmentOptions: {
      // Relative URLs must resolve somewhere sane inside jsdom.
      jsdom: { url: 'http://127.0.0.1:8000' },
    },
    globals: true,
    css: false,
    setupFiles: ['./src/test/setup.ts'],
    env: { VITE_API_BASE: process.env.PEHRA_API_BASE ?? 'http://127.0.0.1:8000' },
    testTimeout: 30000,
    hookTimeout: 30000,
  },
})
