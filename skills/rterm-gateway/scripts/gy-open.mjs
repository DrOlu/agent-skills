#!/usr/bin/env node
/**
 * gy-open — resolve a saved RTerm/neuralos connection (by name or id) and open it
 * as a terminal tab through the neuralos WebSocket gateway.
 *
 * The native `terminal:createTab` RPC does NOT resolve saved-connection names —
 * it passes `config` straight to the terminal service. This helper bridges that gap:
 * it reads the saved connection from the daemon's settings.json and expands it into
 * the full inline config the backend expects (same mapping as the backend's own
 * sshEntryToConfig/winrmEntryToConfig), then calls terminal:createTab.
 *
 * Usage:
 *   gy-open <nameOrId> [--open] [--json] [--gateway ws://localhost:17888]
 *     --open    actually open the tab (default: just print the resolved config)
 *     --json    print the resolved config JSON to stdout
 *     --exec "cmd"  after opening, write a command line to the tab
 *
 * As a module:
 *   import { resolveConnection, buildTabConfig } from './gy-open.mjs'
 */
import { readFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const DATA_DIR = process.env.GYBACKEND_DATA_DIR || path.join(os.homedir(), '.gybackend-data');
const SETTINGS = path.join(DATA_DIR, 'settings.json');
const norm = (s) => String(s ?? '').trim().toLowerCase();

export function loadSettings(settingsPath = SETTINGS) {
  return JSON.parse(readFileSync(settingsPath, 'utf8'));
}

/** Find a saved connection by name or id across ssh/winrm/serial. Returns {kind, entry} or null. */
export function resolveConnection(nameOrId, settings) {
  const conns = settings?.connections ?? {};
  const want = norm(nameOrId);
  const kinds = ['ssh', 'winrm', 'serial'];
  for (const kind of kinds) {
    const list = conns[kind] ?? [];
    // exact id match first, then exact name, then case-insensitive name
    const byId = list.find((e) => norm(e.id) === want);
    const byName = list.find((e) => norm(e.name) === want);
    const entry = byId || byName;
    if (entry) return { kind, entry };
  }
  return null;
}

/** Expand a saved connection entry into a full inline terminal config (mirrors backend mapping). */
export function buildTabConfig(kind, entry, settings, overrides = {}) {
  const base = { type: kind, title: entry.name, cols: 120, rows: 32 };
  if (kind === 'ssh') {
    const proxy = entry.proxyId
      ? (settings?.connections?.proxies ?? []).find((p) => p.id === entry.proxyId)
      : undefined;
    return {
      ...base,
      host: entry.host,
      port: entry.port,
      username: entry.username,
      authMethod: entry.authMethod,
      password: entry.password,
      privateKey: entry.privateKey,
      privateKeyPath: entry.privateKeyPath,
      passphrase: entry.passphrase,
      algorithmsPreset: entry.algorithmsPreset,
      termType: entry.termType,
      proxy,
      jumpHost: entry.jumpHost,
      ...overrides,
    };
  }
  if (kind === 'winrm') {
    return {
      ...base,
      host: entry.host,
      port: entry.port,
      username: entry.username,
      password: entry.password,
      transport: entry.transport,
      auth: entry.auth,
      domain: entry.domain,
      rejectUnauthorized: entry.rejectUnauthorized,
      ...overrides,
    };
  }
  // serial
  return {
    ...base,
    path: entry.path,
    baudRate: entry.baudRate,
    dataBits: entry.dataBits,
    parity: entry.parity,
    stopBits: entry.stopBits,
    flowControl: entry.flowControl,
    ...overrides,
  };
}

/** Resolve nameOrId -> ready-to-send terminal config. Throws with a helpful message if not found. */
export function resolveTabConfig(nameOrId, settings, overrides = {}) {
  const found = resolveConnection(nameOrId, settings);
  if (!found) {
    const all = ['ssh', 'winrm', 'serial'].flatMap((k) => (settings?.connections?.[k] ?? []).map((e) => `${e.name} (${k})`));
    throw new Error(`Saved connection not found: "${nameOrId}". Available: ${all.join(', ') || 'none'}`);
  }
  return buildTabConfig(found.kind, found.entry, settings, overrides);
}

// ─── CLI ────────────────────────────────────────────────────────────────────
import { realpathSync } from 'node:fs';
import { execSync } from 'node:child_process';

/** Resolve the `ws` package from a few common roots (global npm, ~/node_modules, cwd). */
async function loadWS() {
  const roots = ['ws', `${os.homedir()}/node_modules/ws`, '/usr/local/lib/node_modules/ws', '/opt/homebrew/lib/node_modules/ws'];
  try {
    const prefix = execSync('npm config get prefix', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
    if (prefix) roots.splice(1, 0, `${prefix}/lib/node_modules/ws`);
  } catch { /* ignore */ }
  for (const r of roots) {
    try { const m = await import(r); return m.default || m.WebSocket || m; } catch { /* next */ }
  }
  console.error('[gy-open] The `ws` package is required. Install it (npm i -g ws) or run from a dir that has it.');
  process.exit(3);
}

const thisFile = (() => { try { return realpathSync(new URL(import.meta.url).pathname); } catch { return new URL(import.meta.url).pathname; } })();
const invokedAs = (() => { try { return realpathSync(process.argv[1] || ''); } catch { return process.argv[1] || ''; } })();
const isMain = invokedAs && path.resolve(invokedAs) === path.resolve(thisFile);
if (isMain) {
  const args = process.argv.slice(2);
  const target = args.find((a) => !a.startsWith('--'));
  const flag = (n) => args.includes(n);
  const optVal = (n) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : undefined; };
  const gateway = optVal('--gateway') || process.env.GY_GATEWAY || 'ws://localhost:17888';
  const doOpen = flag('--open');
  const execCmd = optVal('--exec');

  if (!target) {
    console.error('Usage: gy-open <nameOrId> [--open] [--json] [--exec "cmd"] [--gateway ws://localhost:17888]');
    process.exit(2);
  }

  (async () => {
    const settings = loadSettings();
    const config = resolveTabConfig(target, settings);
    // redact secrets for display
    const safe = Object.fromEntries(Object.entries(config).map(([k, v]) => [k, ['password', 'privateKey', 'passphrase'].includes(k) && v ? '***' : v]));
    console.log(`Resolved "${target}" -> ${config.type} ${config.host ?? config.path}:${config.port ?? ''} (user ${config.username ?? '-'})`);
    if (flag('--json')) console.log(JSON.stringify(safe, null, 2));

    if (doOpen || execCmd) {
      const WebSocket = await loadWS();
      const ws = new WebSocket(gateway);
      let idc = 0; const pending = new Map();
      const call = (method, params = {}) => new Promise((resolve, reject) => {
        const id = `c${++idc}`; pending.set(id, { resolve, reject });
        ws.send(JSON.stringify({ method, params, id }));
        setTimeout(() => { if (pending.has(id)) { pending.delete(id); reject(new Error('timeout ' + method)); } }, 25000);
      });
      ws.on('message', (d) => { let m; try { m = JSON.parse(d.toString()); } catch { return; } if (m.type === 'gateway:response' && m.id && pending.has(m.id)) { const { resolve, reject } = pending.get(m.id); pending.delete(m.id); m.ok ? resolve(m.result) : reject(new Error(m.error?.message || 'err')); } });
      await new Promise((res, rej) => { ws.on('open', res); ws.on('error', rej); });

      const created = await call('terminal:createTab', { config });
      console.log('Opened tab:', created.id, `(${config.type})`);
      if (execCmd) {
        await new Promise((r) => setTimeout(r, 5000)); // let the transport establish
        await call('terminal:write', { terminalId: created.id, data: execCmd.endsWith('\n') ? execCmd : execCmd + '\n' });
        await new Promise((r) => setTimeout(r, 2500));
        const buf = await call('terminal:getBufferDelta', { terminalId: created.id, fromOffset: 0 });
        const text = (buf.data || '').replace(/\x1b\[[0-9;]*m/g, '');
        console.log('--- tab output (tail) ---');
        console.log(text.split('\n').slice(-12).join('\n'));
      }
      ws.close();
    }
  })().catch((e) => { console.error('Error:', e.message); process.exit(1); });
}
