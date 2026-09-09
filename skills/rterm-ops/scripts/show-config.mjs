#!/usr/bin/env node
/** show-config.mjs — print model config WITHOUT apiKey. */
import { spawnSync } from 'node:child_process'

const IS_WIN = process.platform === 'win32'
function which(bin) {
  const r = spawnSync(IS_WIN ? 'where' : 'which', [bin], { encoding: 'utf8', shell: IS_WIN })
  return r.status === 0 ? (r.stdout || '').split(/\r?\n/).filter(Boolean)[0] : null
}
const rterm = which('rterm-cli') || which('rterm') || which('rterm-cli.cmd')
if (!rterm) {
  console.error('rterm-cli not on PATH')
  process.exit(1)
}
const r = spawnSync(rterm, ['call', 'settings:get', '{}'], { encoding: 'utf8', shell: IS_WIN })
if (r.status !== 0) {
  console.error(r.stderr || r.stdout || 'settings:get failed')
  process.exit(1)
}
let s
try {
  s = JSON.parse(r.stdout)
} catch {
  console.error('settings:get did not return JSON')
  process.exit(1)
}
const profiles = Array.isArray(s.models?.profiles) ? s.models.profiles : []
const out = {
  model: s.model || '',
  baseUrl: s.baseUrl || '',
  hasApiKey: typeof s.apiKey === 'string' && s.apiKey.length > 0,
  activeProfileId: s.models?.activeProfileId || null,
  profiles: profiles.map((p) => ({
    id: p.id,
    name: p.name,
    model: p.model,
    baseUrl: p.baseUrl,
    hasKey: typeof p.apiKey === 'string' && p.apiKey.length > 0,
  })),
  agentSettingsSlot: s.agentSettings?.activeProfileId || null,
  commandPolicyMode: s.commandPolicyMode || null,
  gatewayAccess: s.gateway?.ws?.access || null,
  gatewayPort: s.gateway?.ws?.port || null,
}
console.log(JSON.stringify(out, null, 2))
