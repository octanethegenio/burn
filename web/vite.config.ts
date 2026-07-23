import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { spawn } from 'node:child_process'
import net from 'node:net'
import path from 'node:path'
import fs from 'node:fs'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const webDir = path.dirname(fileURLToPath(import.meta.url))

function probeBackend(): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: '127.0.0.1', port: 8765 })
    const done = (ok: boolean) => {
      socket.destroy()
      resolve(ok)
    }
    socket.setTimeout(300)
    socket.once('connect', () => done(true))
    socket.once('timeout', () => done(false))
    socket.once('error', () => done(false))
  })
}

function burnBackend(): Plugin {
  return {
    name: 'burn-backend',
    apply: 'serve',
    async configureServer(server) {
      const root = path.resolve(webDir, '..')

      const alreadyRunning = await probeBackend()
      if (alreadyRunning) {
        server.config.logger.info('[burn] backend already running on :8765')
        return
      }

      const python =
        process.platform === 'win32'
          ? path.join(root, '.venv', 'Scripts', 'python.exe')
          : path.join(root, '.venv', 'bin', 'python')

      if (!fs.existsSync(python)) {
        server.config.logger.warn(
          '[burn] no .venv found — run ./dev.sh once to set up the Python backend, or start it manually. Skipping backend autostart.',
        )
        return
      }

      const child = spawn(python, ['-m', 'uvicorn', 'server.main:app', '--host', '127.0.0.1', '--port', '8765'], {
        cwd: root,
        stdio: 'inherit',
      })

      let killed = false
      const stop = () => {
        if (killed) return
        killed = true
        child.kill()
      }

      // Tie the backend's lifecycle to the Node process, not the httpServer:
      // Vite closes+recreates the httpServer on every config restart, and
      // killing the child there races the next probe and can leave no backend.
      process.once('exit', stop)
      process.once('SIGINT', () => {
        stop()
        process.exit()
      })
      process.once('SIGTERM', () => {
        stop()
        process.exit()
      })

      child.on('error', (err) => server.config.logger.error('[burn] failed to start backend: ' + err.message))

      server.config.logger.info('[burn] started backend on :8765')
    },
  }
}

export default defineConfig({
  plugins: [react(), burnBackend()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8765',
    },
  },
})
