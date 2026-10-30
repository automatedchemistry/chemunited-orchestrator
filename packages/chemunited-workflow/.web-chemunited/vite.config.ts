import { fileURLToPath, URL } from 'node:url'
import path from 'node:path'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: path.resolve(__dirname, '../chemunited_workflow/web'),
    emptyOutDir: true,
    // The lazy chunk compiling a project's .vue customizations in the browser
    // (src/extensions/loader) is ~1 MB; only projects with custom pages load it.
    chunkSizeWarningLimit: 1200,
  },
})
