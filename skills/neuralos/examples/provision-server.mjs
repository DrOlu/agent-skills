#!/usr/bin/env node
/**
 * provision-server.mjs — provision a new machine as a neuralOS node.
 *
 * Copies the lifecycle script to a remote host over SSH and runs
 * `setup` there: install (neuralos + rterm-cli) → start daemon → verify.
 * Pure Node built-ins; no dependencies.
 *
 * Usage:
 *   node provision-server.mjs user@host [--port N] [--key ~/.ssh/id_ed25519]
 *
 * What it does on the remote host:
 *   1. checks Node >= 18 (installs nothing itself — Node must exist)
 *   2. uploads scripts/neuralos.mjs
 *   3. runs: node neuralos.mjs setup --daemon [--port N]
 *   4. runs: node neuralos.mjs verify  (exit 1 on failure → this script fails)
 *
 * The remote node then exposes ws://<host>:<port> — drive it from anywhere:
 *   RTERM_URL=ws://<host>:<port> rterm ping
 */
import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const HERE = path.dirname(fileURLToPath(import.meta.url))
const SCRIPT = path.join(HERE, 'neuralos.mjs')

const args = process.argv.slice(2)
const target = args.find((a) => !a.startsWith('--'))
if (!target || !target.includes('@')) {
  console.error('usage: node provision-server.mjs user@host [--port N] [--key PATH]')
  process.exit(2)
}
const port = (() => {
  const i = args.indexOf('--port')
  return i >= 0 ? args[i + 1] : '17888'
})()
const key = (() => {
  const i = args.indexOf('--key')
  return i >= 0 ? args[i + 1] : null
})()

const sshBase = key ? ['-i', key] : []
function ssh(cmd, opts = {}) {
  const r = spawnSync('ssh', [...sshBase, '-o', 'StrictHostKeyChecking=accept-new', target, cmd],
    { encoding: 'utf8', timeout: opts.timeout ?? 300000 })
  return { code: r.status ?? 1, out: (r.stdout || '').trim(), err: (r.stderr || '').trim() }
}
function scp(src, dst) {
  const r = spawnSync('scp', [...sshBase, src, `${target}:${dst}`], { encoding: 'utf8', timeout: 120000 })
  return r.status === 0
}

console.log(`provisioning ${target} (port ${port})`)

// 1. preflight: node present?
console.log('1. preflight (node >= 18)')
const pre = ssh('node --version')
if (pre.code !== 0) {
  console.error(`  ✘ node missing or not on PATH for ${target} — install Node >= 18 first`)
  process.exit(1)
}
console.log(`  ✔ ${pre.out}`)

// 2. upload the lifecycle script
console.log('2. upload scripts/neuralos.mjs')
if (!scp(SCRIPT, '/tmp/neuralos.mjs')) {
  console.error('  ✘ scp failed')
  process.exit(1)
}
console.log('  ✔ uploaded')

// 3. setup (install + start + verify) — the EACCES retry is built in
console.log('3. setup (install neuralos + rterm-cli, start daemon, verify)')
const setup = ssh(`node /tmp/neuralos.mjs setup --daemon --port ${port}`, { timeout: 600000 })
console.log(setup.out || setup.err)
if (setup.code !== 0) {
  console.error('  ✘ remote setup failed')
  process.exit(1)
}

// 4. final verify from the remote side
console.log('4. verify (remote side)')
const verify = ssh(`node /tmp/neuralos.mjs verify --port ${port}`, { timeout: 120000 })
console.log(verify.out || verify.err)
if (verify.code !== 0) {
  console.error('  ✘ remote verify failed')
  process.exit(1)
}

console.log(`\n✔ ${target} provisioned — gateway at ws://<host>:${port}`)
console.log(`   drive it: RTERM_URL=ws://<host>:${port} rterm ping`)
