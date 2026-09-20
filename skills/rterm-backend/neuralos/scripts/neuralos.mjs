#!/usr/bin/env node
/**
 * neuralos.mjs — cross-platform lifecycle manager for the RTerm backend + CLI.
 *
 * Pure Node (>= 18) built-ins only — no npm dependencies, works on macOS, Linux,
 * and Windows. Manages install, update, setup, verify, start/stop/restart,
 * status, logs, ping, config, service install, and uninstall of:
 *   - the standalone `neuralos` (gybackend) daemon
 *   - the `rterm-cli` command client (bin: rterm / rterm-cli)
 * — together or individually.
 *
 * Usage:
 *   node neuralos.mjs <command> [flags]
 *
 * Commands:
 *   doctor                 Check Node, npm pkgs, data dir, port, gateway, CLI.
 *   install [--cli] [--backend]   npm install -g neuralos and/or rterm-cli.
 *   update  [--cli] [--backend]   update to latest from the registry (both by default).
 *   setup   [--host H] [--port N] [--data DIR] [--daemon]
 *                          install (if missing) + start + verify in one shot.
 *   verify  [--url ws://host:port]
 *                          end-to-end health: gateway ping + CLI round-trip.
 *   uninstall [--keep-cli] stop + npm uninstall -g (keep CLI with --keep-cli).
 *   start [--port N] [--host H] [--data DIR] [--daemon] [--log FILE]
 *   stop
 *   restart
 *   status
 *   logs [--lines N]
 *   ping [--url ws://host:port]
 *   config-show            Print effective env + data dir + installed versions.
 *   install-service        Print the service unit + enable command for this OS.
 *
 * Flags:
 *   --port N        gateway port (default 17888 / GYBACKEND_WS_PORT)
 *   --host H        bind host (default 0.0.0.0 / GYBACKEND_WS_HOST)
 *   --data DIR      data dir (default ./.gybackend-data / GYBACKEND_DATA_DIR)
 *   --daemon        run detached in background (nohup / Start-Process)
 *   --log FILE      daemon log file (default <data>/gybackend.log)
 *   --url URL       full ws url for ping/verify (default ws://127.0.0.1:<port>)
 */
import process from 'node:process'
import os from 'node:os'
import fs from 'node:fs'
import path from 'node:path'
import net from 'node:net'
import http from 'node:http'
import crypto from 'node:crypto'
import { spawn, spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const IS_WIN = process.platform === 'win32'
const IS_MAC = process.platform === 'darwin'
const HERE = path.dirname(fileURLToPath(import.meta.url))

// --------------------------------------------------------------------------
// args
// --------------------------------------------------------------------------
function parseArgs(argv) {
  const args = { _: [] }
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i]
    if (a.startsWith('--')) {
      const key = a.slice(2)
      const next = argv[i + 1]
      if (next === undefined || next.startsWith('--')) { args[key] = true } else { args[key] = next; i += 1 }
    } else args._.push(a)
  }
  return args
}
const argv = parseArgs(process.argv.slice(2))
const CMD = argv._[0]

const PORT = Number(argv.port || process.env.GYBACKEND_WS_PORT || 17888)
const HOST = argv.host || process.env.GYBACKEND_WS_HOST || '0.0.0.0'
const DATA_DIR = path.resolve(argv.data || process.env.GYBACKEND_DATA_DIR || './.gybackend-data')
const LOG_FILE = path.resolve(argv.log || path.join(DATA_DIR, 'gybackend.log'))
const PID_FILE = path.join(DATA_DIR, 'gybackend.pid')
const WS_URL = argv.url || `ws://127.0.0.1:${PORT}`

const c = {
  ok: (s) => console.log(`  ✔ ${s}`),
  info: (s) => console.log(`  • ${s}`),
  warn: (s) => console.log(`  ⚠ ${s}`),
  err: (s) => console.error(`  ✘ ${s}`),
  head: (s) => console.log(`\n${s}`),
}

// --------------------------------------------------------------------------
// helpers
// --------------------------------------------------------------------------
function sh(cmd, args, opts = {}) {
  // Node >= 18.20 spawn-security fix: spawning .cmd/.bat without shell throws
  // EINVAL (status null → our `?? 0` masked it as success). Wrap those.
  const needsShell = IS_WIN && /\.(cmd|bat)$/i.test(cmd)
  const r = spawnSync(cmd, args, { encoding: 'utf8', stdio: 'pipe', shell: needsShell, windowsVerbatimArguments: needsShell, ...opts })
  return { code: r.status ?? (r.error ? 1 : 0), stdout: (r.stdout || '').trim(), stderr: (r.stderr || (r.error ? r.error.message : '')).trim() }
}
function which(bin) {
  const cmd = IS_WIN ? 'where' : 'which'
  const r = spawnSync(cmd, [bin], { encoding: 'utf8' })
  return r.status === 0 ? (r.stdout || '').split('\n')[0].trim() : null
}
function nodeMajor() {
  return Number(String(process.versions.node).split('.')[0])
}
function npmBin() {
  if (IS_WIN) {
    // `where npm` lists npm (bash shim), npm.cmd, npm.ps1 — only npm.cmd is
    // spawnable from Node (the bash shim ENOENTs, npm.ps1 needs a PS host).
    const r = spawnSync('where', ['npm'], { encoding: 'utf8' })
    if (r.status === 0) {
      const lines = (r.stdout || '').split('\n').map((l) => l.trim()).filter(Boolean)
      const cmd = lines.find((l) => l.toLowerCase().endsWith('npm.cmd'))
      if (cmd) return cmd
    }
    return 'npm.cmd'
  }
  const nb = which('npm')
  return nb || 'npm'
}

/**
 * Full spawn spec for an npm invocation. On Windows we run
 * `node <npm-cli.js>` directly — .cmd shims need shell:true (Node >= 18.20
 * spawn policy) and shell:true breaks on spaces in "C:\Program Files\...".
 * node + npm-cli.js sidesteps both.
 */
function npmSpawn(args) {
  if (IS_WIN) {
    const npmCli = path.join(path.dirname(process.execPath), 'node_modules', 'npm', 'bin', 'npm-cli.js')
    if (fs.existsSync(npmCli)) return { cmd: process.execPath, args: [npmCli, ...args] }
    return { cmd: 'npm.cmd', args }
  }
  return { cmd: npmBin(), args }
}
function nodeBin() {
  return process.execPath
}

/** Installed global version of an npm package (null when absent). */
function globalVersion(pkg) {
  const spec = npmSpawn(['ls', '-g', pkg, '--depth=0'])
  const r = sh(spec.cmd, spec.args)
  if (r.code !== 0) return null
  const m = r.stdout.match(new RegExp(`${pkg}@(\\S+)`))
  return m ? m[1] : null
}

/** Latest version on the npm registry (null when unreachable). */
function registryVersion(pkg) {
  const spec = npmSpawn(['view', pkg, 'version'])
  const r = sh(spec.cmd, spec.args)
  return r.code === 0 && r.stdout ? r.stdout : null
}

/**
 * npm install -g with one retry on EACCES using a fresh temp cache.
 * Root-owned files in the user cache (from past `sudo npm`) are a common
 * real-world failure; a clean cache dir sidesteps them without sudo.
 */
function npmInstallG(args) {
  const spec = npmSpawn(args)
  let r = sh(spec.cmd, spec.args)
  if (r.code === 0) return r
  if (/EACCES/i.test(r.stderr) || /cache folder contains root-owned/i.test(r.stderr)) {
    const fresh = path.join(os.tmpdir(), `npm-cache-neuralos-${process.pid}`)
    fs.rmSync(fresh, { recursive: true, force: true })
    c.warn('npm cache has root-owned files (EACCES) — retrying with a fresh temp cache')
    r = sh(spec.cmd, [...spec.args, '--cache', fresh])
    try { fs.rmSync(fresh, { recursive: true, force: true }) } catch {}
  }
  return r
}

/** Semver-ish compare — enough for update checks (ignores prerelease nuance). */
function isNewer(candidate, current) {
  if (!candidate || !current) return false
  const a = candidate.split('.').map((x) => Number(x) || 0)
  const b = current.split('.').map((x) => Number(x) || 0)
  for (let i = 0; i < 3; i++) {
    if ((a[i] || 0) > (b[i] || 0)) return true
    if ((a[i] || 0) < (b[i] || 0)) return false
  }
  return false
}

// Resolve how to launch gybackend: prefer the on-PATH shim, else resolve
// node + the globally-installed package script via `npm root -g`.
function gybackendLaunch() {
  if (IS_WIN) {
    // .cmd shims need shell (blocked by Node >= 18.20 policy); launch the
    // real JS entry via node instead. Try npm root -g first.
    try {
      const spec = npmSpawn(['root', '-g'])
      const root = sh(spec.cmd, spec.args).stdout
      for (const rel of [
        path.join('neuralos', 'bin', 'gybackend.js'),
        path.join('neuralos', 'bin', 'gybackend.cjs'),
      ]) {
        const script = path.join(root, rel)
        if (fs.existsSync(script)) return { cmd: nodeBin(), args: [script] }
      }
    } catch {}
    const shim = which('gybackend')
    if (shim) return { cmd: 'cmd.exe', args: ['/c', shim] }
    return null
  }
  const shim = which('gybackend') || 'gybackend'
  if (shim && fs.existsSync(shim)) {
    return { cmd: shim, args: [] }
  }
  try {
    const spec = npmSpawn(['root', '-g'])
    const root = sh(spec.cmd, spec.args).stdout
    const script = path.join(root, 'neuralos', 'bin', 'gybackend.js')
    if (fs.existsSync(script)) {
      return { cmd: nodeBin(), args: [script] }
    }
  } catch {}
  return null
}

function portInUse(port, host = '127.0.0.1') {
  return new Promise((resolve) => {
    const s = net.connect({ port, host })
    s.once('connect', () => { s.end(); resolve(true) })
    s.once('error', () => resolve(false))
    s.setTimeout(1200, () => { s.destroy(); resolve(false) })
  })
}
function readPid() {
  try { return Number(fs.readFileSync(PID_FILE, 'utf8').trim()) || null } catch { return null }
}
function pidAlive(pid) {
  if (!pid) return false
  try { process.kill(pid, 0); return true } catch { return false }
}

// Minimal WS client (RFC6455, no deps) for ping.
function wsPing(url, timeoutMs = 4000) {
  return new Promise((resolve, reject) => {
    let u
    try { u = new URL(url) } catch { return reject(new Error('bad url')) }
    const key = crypto.randomBytes(16).toString('base64')
    const req = http.request({
      hostname: u.hostname,
      port: u.port || 80,
      path: u.pathname || '/',
      headers: {
        Connection: 'Upgrade', Upgrade: 'websocket',
        'Sec-WebSocket-Key': key, 'Sec-WebSocket-Version': '13',
      },
      timeout: timeoutMs,
    })
    req.on('upgrade', (res, socket) => {
      // send a masked text frame containing the gateway:ping RPC
      const payload = Buffer.from(JSON.stringify({ id: '1', method: 'gateway:ping' }))
      const mask = crypto.randomBytes(4)
      const masked = Buffer.from(payload.map((b, i) => b ^ mask[i % 4]))
      const header = Buffer.from([0x81, 0x80 | masked.length])
      socket.write(Buffer.concat([header, mask, masked]))
      const chunks = []
      socket.on('data', (d) => {
        chunks.push(d)
        const buf = Buffer.concat(chunks)
        if (buf.includes('pong')) {
          socket.destroy()
          resolve(true)
        }
      })
      socket.setTimeout(timeoutMs, () => { socket.destroy(); reject(new Error('ws timeout')) })
      socket.on('error', reject)
    })
    req.on('error', reject)
    req.on('timeout', () => { req.destroy(); reject(new Error('http timeout')) })
    req.end()
  })
}

/** Run an rterm-cli one-shot command against WS_URL; returns stdout or throws. */
function cliCall(args, timeoutMs = 30000) {
  const shim = which('rterm-cli') || which('rterm')
  if (!shim) throw new Error('rterm-cli not installed (npm i -g rterm-cli)')
  const r = spawnSync(shim, args, {
    encoding: 'utf8',
    timeout: timeoutMs,
    env: { ...process.env, RTERM_URL: WS_URL },
  })
  if (r.status !== 0) {
    throw new Error((r.stderr || r.stdout || `exit ${r.status}`).trim().slice(0, 300))
  }
  return (r.stdout || '').trim()
}

// --------------------------------------------------------------------------
// commands
// --------------------------------------------------------------------------
async function doctor() {
  c.head('neuralos doctor')
  const nm = nodeMajor()
  nm >= 18 ? c.ok(`Node ${process.versions.node}`) : c.err(`Node ${process.versions.node} — need >= 18`)
  const npm = npmBin(); npm ? c.ok(`npm: ${npm}`) : c.err('npm not found')
  const vBackend = globalVersion('neuralos')
  const vCli = globalVersion('rterm-cli')
  vBackend ? c.ok(`neuralos ${vBackend} (gybackend)`) : c.warn('neuralos not installed — run: install')
  vCli ? c.ok(`rterm-cli ${vCli}`) : c.warn('rterm-cli not installed (optional) — run: install --cli')
  const gyb = (gybackendLaunch() || {}).cmd; gyb ? c.ok(`gybackend: ${gyb}`) : c.warn('gybackend not on PATH')
  c.info(`platform: ${process.platform} ${process.arch}`)
  c.info(`data dir: ${DATA_DIR} ${fs.existsSync(DATA_DIR) ? '(exists)' : '(will be created)'}`)
  const busy = await portInUse(PORT)
  c.info(`port ${PORT}: ${busy ? 'in use (running?)' : 'free'}`)
  try { await wsPing(WS_URL); c.ok(`gateway ping OK (${WS_URL})`) }
  catch { c.warn(`gateway not answering at ${WS_URL}`) }
  if (vCli) {
    try { cliCall(['ping']); c.ok('rterm-cli round-trip OK') }
    catch (e) { c.warn(`rterm-cli round-trip failed: ${e.message}`) }
  }
}

async function installPkgs({ backend, cli }) {
  const npm = npmBin()
  const targets = []
  if (backend) targets.push('neuralos')
  if (cli) targets.push('rterm-cli')
  if (targets.length === 0) targets.push('neuralos', 'rterm-cli')
  c.head(`Installing: ${targets.join(' + ')}`)
  const r = npmInstallG(targets)
  if (r.code !== 0) { c.err(`npm install failed: ${r.stderr.slice(0, 300)}`); process.exit(r.code) }
  for (const t of targets) {
    const v = globalVersion(t)
    if (v) c.ok(`${t}@${v} installed`)
    else { c.err(`${t} still not resolvable after install`); process.exit(1) }
  }
}

async function updatePkgs({ backend, cli }) {
  const npm = npmBin()
  const targets = []
  if (backend) targets.push('neuralos')
  if (cli) targets.push('rterm-cli')
  if (targets.length === 0) targets.push('neuralos', 'rterm-cli')
  c.head('Checking for updates')
  let updated = 0
  for (const pkg of targets) {
    const cur = globalVersion(pkg)
    const latest = registryVersion(pkg)
    if (!latest) { c.warn(`${pkg}: registry unreachable — skipping`); continue }
    if (!cur) { c.info(`${pkg}: not installed — skipping (use install)`); continue }
    if (!isNewer(latest, cur)) {
      c.ok(`${pkg} ${cur} — already latest (registry ${latest})`)
      continue
    }
    c.info(`${pkg} ${cur} → ${latest} — updating…`)
    const r = npmInstallG([`${pkg}@latest`])
    if (r.code !== 0) { c.err(`${pkg} update failed: ${r.stderr.slice(0, 200)}`); continue }
    const now = globalVersion(pkg)
    if (now === latest) { c.ok(`${pkg} updated to ${now}`); updated += 1 }
    else c.warn(`${pkg} reports ${now} (expected ${latest})`)
  }
  if (updated > 0) {
    c.info('note: restart the daemon to run the new version (restart)')
  }
}

async function uninstallPkgs({ keepCli }) {
  await stop()
  const npm = npmBin()
  c.head('Uninstalling')
  if (!keepCli) {
    sh(npm, ['uninstall', '-g', 'rterm-cli'])
    c.ok('rterm-cli uninstalled')
  }
  sh(npm, ['uninstall', '-g', 'neuralos'])
  c.ok('neuralos uninstalled')
}

async function start() {
  c.head('Starting neuralos')
  const launch = gybackendLaunch()
  if (!launch) { c.err('gybackend not installed. Run: node neuralos.mjs install'); process.exit(1) }
  const busy = await portInUse(PORT)
  if (busy) { c.warn(`port ${PORT} already in use — is it already running? (status)`); return }
  fs.mkdirSync(DATA_DIR, { recursive: true })
  const env = {
    ...process.env,
    GYBACKEND_WS_ENABLE: '1',
    GYBACKEND_WS_HOST: HOST,
    GYBACKEND_WS_PORT: String(PORT),
    GYBACKEND_DATA_DIR: DATA_DIR,
  }
  if (argv.daemon) {
    fs.mkdirSync(path.dirname(LOG_FILE), { recursive: true })
    const out = fs.openSync(LOG_FILE, 'a')
    const err = fs.openSync(LOG_FILE, 'a')
    const child = spawn(launch.cmd, launch.args, { env, detached: true, stdio: ['ignore', out, err] })
    child.on('error', (e) => c.err(`daemon spawn error: ${e.message}`))
    child.unref()
    fs.writeFileSync(PID_FILE, String(child.pid))
    c.ok(`daemon started (pid ${child.pid})`)
    c.info(`log: ${LOG_FILE}`)
    await new Promise((r) => setTimeout(r, 2500))
    try { await wsPing(WS_URL); c.ok(`gateway answering at ${WS_URL}`) }
    catch { c.warn(`gateway not answering yet — check: node neuralos.mjs logs`) }
  } else {
    c.info('foreground mode (Ctrl+C to stop)')
    const child = spawn(launch.cmd, launch.args, { env, stdio: 'inherit' })
    child.on('exit', (code) => process.exit(code ?? 0))
  }
}

async function stop() {
  c.head('Stopping neuralos')
  const pid = readPid()
  if (pidAlive(pid)) {
    try {
      if (IS_WIN) sh('taskkill', ['/PID', String(pid), '/T', '/F'], { quiet: true })
      else process.kill(pid, 'SIGTERM')
      c.ok(`stopped pid ${pid}`)
    } catch (e) { c.err(`could not stop ${pid}: ${e.message}`) }
  } else {
    // best-effort: find by name
    if (IS_WIN) sh('taskkill', ['/IM', 'gybackend.cmd', '/F'], { quiet: true })
    else sh('pkill', ['-f', 'gybackend'], { quiet: true })
    c.info('no pidfile; attempted name-based stop')
  }
  try { fs.unlinkSync(PID_FILE) } catch {}
}

async function restart() { await stop(); await new Promise((r) => setTimeout(r, 1200)); await start() }

async function status() {
  c.head('neuralos status')
  const pid = readPid()
  const alive = pidAlive(pid)
  c.info(`pid: ${pid || 'none'} ${alive ? '(running)' : ''}`)
  const busy = await portInUse(PORT)
  c.info(`port ${PORT}: ${busy ? 'LISTENING' : 'not listening'}`)
  try { await wsPing(WS_URL); c.ok(`gateway OK at ${WS_URL}`) }
  catch { c.warn(`gateway not answering at ${WS_URL}`) }
  if (fs.existsSync(LOG_FILE)) c.info(`log: ${LOG_FILE}`)
}

async function logs() {
  const n = Number(argv.lines || 40)
  if (!fs.existsSync(LOG_FILE)) { c.warn(`no log at ${LOG_FILE}`); return }
  const lines = fs.readFileSync(LOG_FILE, 'utf8').split('\n')
  console.log(lines.slice(-n).join('\n'))
}

async function ping() {
  try { await wsPing(WS_URL); c.ok(`pong from ${WS_URL}`) }
  catch (e) { c.err(`no response from ${WS_URL}: ${e.message}`); process.exit(1) }
}

function configShow() {
  c.head('effective configuration')
  const vBackend = globalVersion('neuralos')
  const vCli = globalVersion('rterm-cli')
  const rows = [
    ['neuralos (installed)', vBackend || '(not installed)'],
    ['rterm-cli (installed)', vCli || '(not installed)'],
    ['GYBACKEND_WS_ENABLE', '1'],
    ['GYBACKEND_WS_HOST', HOST],
    ['GYBACKEND_WS_PORT', String(PORT)],
    ['GYBACKEND_DATA_DIR', DATA_DIR],
    ['log file', LOG_FILE],
    ['pid file', PID_FILE],
    ['platform', `${process.platform} ${process.arch}`],
    ['node', process.versions.node],
  ]
  for (const [k, v] of rows) console.log(`  ${k.padEnd(34)} ${v}`)
  c.info(`settings: ${path.join(DATA_DIR, 'settings.json')}`)
}

function installService() {
  c.head(`install-service (${process.platform})`)
  const gyb = (gybackendLaunch() || {}).cmd || 'gybackend'
  if (IS_MAC) {
    const plist = path.join(HERE, '..', 'service', 'ng.hyperspace.neuralos.plist')
    console.log(`  1. cp "${plist}" ~/Library/LaunchAgents/`)
    console.log(`  2. edit GYBACKEND_DATA_DIR in the plist (currently a placeholder)`)
    console.log(`  3. launchctl load ~/Library/LaunchAgents/ng.hyperspace.neuralos.plist`)
    console.log(`  gybackend resolves to: ${gyb}`)
  } else if (IS_WIN) {
    const ps1 = path.join(HERE, '..', 'service', 'install-windows-service.ps1')
    console.log(`  Run in an elevated PowerShell:`)
    console.log(`  powershell -ExecutionPolicy Bypass -File "${ps1}"`)
  } else {
    const unit = path.join(HERE, '..', 'service', 'neuralos.service')
    console.log(`  1. sudo cp "${unit}" /etc/systemd/system/`)
    console.log(`  2. sudo systemctl daemon-reload`)
    console.log(`  3. sudo systemctl enable --now neuralos`)
    console.log(`  gybackend resolves to: ${gyb}`)
  }
}

/**
 * One-shot: install what's missing, start (daemon by default), verify.
 * Idempotent — safe to re-run; an already-running healthy daemon is left alone.
 */
async function setup() {
  c.head('neuralos setup')
  const steps = []
  const daemon = argv.daemon !== false // default true for setup

  // 1. install what's missing
  const needBackend = !globalVersion('neuralos')
  const needCli = !globalVersion('rterm-cli')
  if (needBackend || needCli) {
    await installPkgs({ backend: needBackend, cli: needCli })
  } else {
    c.ok('neuralos + rterm-cli already installed')
  }

  // 2. start if not already running
  const busy = await portInUse(PORT)
  if (busy) {
    try { await wsPing(WS_URL); c.ok(`gateway already running at ${WS_URL}`) }
    catch {
      c.warn(`port ${PORT} busy but gateway not answering — another service?`)
      c.info('continuing to verify (it may still fail)')
    }
  } else {
    const prevDaemon = argv.daemon
    argv.daemon = daemon
    await start()
    argv.daemon = prevDaemon
  }

  // 3. verify
  await verify()
}

/**
 * End-to-end health check: gateway ping over raw WS + rterm-cli round-trip
 * (the CLI is the primary programmatic client, so it must work).
 */
async function verify() {
  c.head('verify')
  let failures = 0

  // 1. raw gateway ping
  try { await wsPing(WS_URL); c.ok(`gateway ping (${WS_URL})`) }
  catch (e) { c.err(`gateway ping failed: ${e.message}`); failures += 1 }

  // 2. rterm-cli installed?
  const vCli = globalVersion('rterm-cli')
  if (!vCli) {
    c.warn('rterm-cli not installed — skipping CLI round-trip (install with: install --cli)')
  } else {
    c.ok(`rterm-cli ${vCli} present`)
    // 3. CLI → gateway version round-trip
    try {
      const out = cliCall(['version'])
      const v = JSON.parse(out)
      c.ok(`CLI→gateway round-trip: backend ${v.version}, ${v.methodCount} RPC methods`)
    } catch (e) { c.err(`CLI round-trip failed: ${e.message}`); failures += 1 }
    // 4. CLI → terminals (exercises the terminal subsystem)
    try {
      const out = cliCall(['terminals'])
      const t = JSON.parse(out)
      const n = Array.isArray(t.terminals) ? t.terminals.length : 0
      c.ok(`CLI terminals listing: ${n} tab(s)`)
    } catch (e) { c.warn(`CLI terminals listing failed: ${e.message}`) }
  }

  console.log('')
  if (failures > 0) { c.err(`verify FAILED (${failures} failure(s))`); process.exit(1) }
  c.ok('verify PASSED')
}

async function main() {
  switch (CMD) {
    case 'doctor': return doctor()
    case 'install': return installPkgs({ backend: argv.backend === true, cli: argv.cli === true })
    case 'update': return updatePkgs({ backend: argv.backend === true, cli: argv.cli === true })
    case 'setup': return setup()
    case 'verify': return verify()
    case 'uninstall': return uninstallPkgs({ keepCli: argv['keep-cli'] === true })
    case 'start': return start()
    case 'stop': return stop()
    case 'restart': return restart()
    case 'status': return status()
    case 'logs': return logs()
    case 'ping': return ping()
    case 'config-show': return configShow()
    case 'install-service': return installService()
    default:
      console.error(`unknown command: ${CMD || '(none)'}\n`)
      console.error('commands: doctor | install | update | setup | verify | uninstall | start | stop | restart | status | logs | ping | config-show | install-service')
      process.exit(2)
  }
}

main().catch((e) => { c.err(e.message); process.exit(1) })
