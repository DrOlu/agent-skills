#!/usr/bin/env node
/**
 * set-api-key.mjs — set neuralos apiKey from env (never prints the key).
 * Usage: set OPENROUTER_API_KEY or RTERM_API_KEY, then: node set-api-key.mjs
 * Optional: --model moonshotai/kimi-k3 --base-url https://openrouter.ai/api/v1
 */
import { spawnSync } from 'node:child_process'

const IS_WIN = process.platform === 'win32'
const args = process.argv.slice(2)
function flag(name, def) {
  const i = args.indexOf(name)
  return i >= 0 ? args[i + 1] : def
}
const model = flag('--model', process.env.RTERM_MODEL || '')
const baseUrl = flag('--base-url', process.env.RTERM_BASE_URL || '')
const key = process.env.OPENROUTER_API_KEY || process.env.RTERM_API_KEY || process.env.OPENAI_API_KEY
if (!key) {
  console.error('Set OPENROUTER_API_KEY or RTERM_API_KEY in the environment. Do not pass the key as an argument.')
  process.exit(1)
}

function which(bin) {
  const r = spawnSync(IS_WIN ? 'where' : 'which', [bin], { encoding: 'utf8', shell: IS_WIN })
  return r.status === 0 ? (r.stdout || '').split(/\r?\n/).filter(Boolean)[0] : null
}
const rterm = which('rterm-cli') || which('rterm') || which('rterm-cli.cmd')
if (!rterm) {
  console.error('rterm-cli not on PATH. Run: node scripts/ensure-rterm.mjs')
  process.exit(1)
}

const settings = { apiKey: key }
if (model) settings.model = model
if (baseUrl) settings.baseUrl = baseUrl
const payload = JSON.stringify({ settings })
const r = spawnSync(rterm, ['call', 'settings:set', payload], { stdio: 'inherit', shell: IS_WIN })
process.exit(r.status === 0 ? 0 : 1)
