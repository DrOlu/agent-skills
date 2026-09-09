#!/usr/bin/env node
/**
 * ensure-rterm.mjs — detect / install neuralos (gybackend) + rterm-cli, optionally start daemon.
 * Cross-platform: Windows, macOS, Linux. Node >= 18. No secrets in argv.
 * Exit 0 = gateway ready, 1 = failed, 2 = Node too old.
 */
import { spawnSync, spawn } from 'node:child_process'
import { mkdirSync, appendFileSync, writeFileSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { join } from 'node:path'

const IS_WIN = process.platform === 'win32'
const PORT = String(process.env.GYBACKEND_WS_PORT || process.env.RTERM_PORT || '17888')
const HOST = process.env.RTERM_HOST || '127.0.0.1'
const URL = process.env.RTERM_URL || `ws://${HOST}:${PORT}`
const DATA_DIR = process.env.GYBACKEND_DATA_DIR || join(homedir(), '.gybackend-data')
const START = process.env.ENSURE_RTERM_START !== '0'
const log = (s) => console.error(s)

function which(bin) {
  const cmd = IS_WIN ? 'where' : 'which'
  const r = spawnSync(cmd, [bin], { encoding: 'utf8', shell: IS_WIN })
  if (r.status !== 0) return null
  const line = (r.stdout || '').split(/\r?\n/).map((x) => x.trim()).filter(Boolean)[0]
  return line || null
}

function nodeMajor() {
  return Number(String(process.versions.node).split('.')[0])
}

function npmBin() {
  return which('npm') || (IS_WIN ? 'npm.cmd' : 'npm')
}

function npmInstallG(pkg) {
  const npm = npmBin()
  log(`Installing ${pkg}@latest …`)
  let r = spawnSync(npm, ['install', '-g', pkg, '--prefer-online'], { encoding: 'utf8', shell: IS_WIN })
  if (r.status === 0) return
  const err = `${r.stderr || ''} ${r.stdout || ''}`
  if (/EACCES|root-owned/i.test(err)) {
    const cache = join(tmpdir(), `npm-cache-rterm-${process.pid}`)
    log('npm EACCES — retrying with a fresh temp cache')
    r = spawnSync(npm, ['install', '-g', pkg, '--prefer-online', '--cache', cache], {
      encoding: 'utf8',
      shell: IS_WIN,
    })
  }
  if (r.status !== 0) {
    log((r.stderr || r.stdout || 'npm install failed').slice(0, 800))
    process.exit(1)
  }
}

function rtermBin() {
  return which('rterm-cli') || which('rterm') || (IS_WIN ? which('rterm-cli.cmd') : null)
}

function gyBin() {
  return which('gybackend') || (IS_WIN ? which('gybackend.cmd') : null)
}

function gatewayUp() {
  const bin = rtermBin()
  if (!bin) return false
  const r = spawnSync(bin, ['ping'], {
    encoding: 'utf8',
    env: { ...process.env, RTERM_URL: URL },
    timeout: 8000,
    shell: IS_WIN,
  })
  return r.status === 0 && /pong/i.test(r.stdout || '')
}

if (nodeMajor() < 18) {
  log(`Node ${process.versions.node} is too old (need >= 18).`)
  process.exit(2)
}

if (!rtermBin()) npmInstallG('rterm-cli')
if (!gyBin()) npmInstallG('neuralos')

if (START && !gatewayUp()) {
  log(`Gateway not answering at ${URL} — starting gybackend …`)
  mkdirSync(DATA_DIR, { recursive: true })
  const logFile = join(DATA_DIR, 'gybackend.log')
  const pidFile = join(DATA_DIR, 'gybackend.pid')
  const env = {
    ...process.env,
    GYBACKEND_WS_ENABLE: '1',
    GYBACKEND_WS_HOST: process.env.GYBACKEND_WS_HOST || '0.0.0.0',
    GYBACKEND_WS_PORT: PORT,
    GYBACKEND_DATA_DIR: DATA_DIR,
  }
  const exe = gyBin()
  if (!exe) {
    log('gybackend still not on PATH after install. Open a new terminal and re-run.')
    process.exit(1)
  }
  const child = spawn(exe, [], {
    env,
    detached: true,
    stdio: ['ignore', 'ignore', 'ignore'],
    shell: IS_WIN,
    windowsHide: true,
  })
  child.unref()
  if (child.pid) writeFileSync(pidFile, String(child.pid))
  appendFileSync(logFile, `\n# started pid=${child.pid} ${new Date().toISOString()}\n`)
  for (let i = 0; i < 20; i++) {
    if (IS_WIN) spawnSync('timeout', ['/t', '1', '/nobreak'], { shell: true, stdio: 'ignore' })
    else spawnSync('sleep', ['1'])
    if (gatewayUp()) break
  }
}

const bin = rtermBin()
if (!gatewayUp()) {
  log('rterm-cli is installed but the gateway is down.')
  log(`Start it: gybackend   (GYBACKEND_WS_PORT=${PORT} GYBACKEND_DATA_DIR=${DATA_DIR})`)
  log(`Then: set RTERM_URL=${URL} && ${bin || 'rterm-cli'} ping`)
  process.exit(1)
}

log(`OK  cli=${bin}  url=${URL}`)
const ver = spawnSync(bin, ['version'], { encoding: 'utf8', env: { ...process.env, RTERM_URL: URL }, shell: IS_WIN })
process.stdout.write(ver.stdout || '')
if (ver.status !== 0) {
  spawnSync(bin, ['ping'], { stdio: 'inherit', env: { ...process.env, RTERM_URL: URL }, shell: IS_WIN })
}
process.exit(0)
