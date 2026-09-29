#!/usr/bin/env python3
"""A complete ReactorPro mesh citizen that wraps ANY harness in ~one command.

This is the reference bridge: it mints an identity, signs everything it
sends, answers requests on its inbox, publishes heartbeats, registers with
the mesh registry, answers discovery broadcasts, and (optionally) consumes
its own durable mailbox. The `--command` template turns any CLI — an LLM
agent, a monitoring tool, a shell script — into a mesh-servable skill.

Requires: nats-py, cryptography  (pip install nats-py cryptography)

Examples:
    # Wrap a CLI agent (the prompt arrives as {text}):
    mesh_bridge.py --id acme/lagos/hq-1 --command 'my-agent --prompt "{text}"'

    # Deterministic skill, no LLM:
    mesh_bridge.py --id acme/ops/report-1 --skill report='cat /srv/reports/daily.md'

    # Serve several skills from one process:
    mesh_bridge.py --id acme/ops/edge-1 \
        --skill status='uptime' --skill disk='df -h' \
        --command 'echo no handler for {skill}'

How a request flows: peer → mesh.agent.<id>.inbox (CORE NATS) → verify →
run --command → signed respond envelope → payload.reply_to (must start with
"_REPLY."). Replies to a ReactorPro edge carry payload.output; replies to
Synapse bridges carry payload.text — this bridge sends both.

Flags also read env vars: MESH_NATS_URL, MESH_NATS_USER, MESH_NATS_PASSWORD,
MESH_NATS_TOKEN, MESH_NATS_NKEY_SEED, MESH_IDENTITY_PATH.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import timedelta
from typing import Any

import nats
from nats.js import api as js_api
from nats.js.errors import NotFoundError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mesh import (  # noqa: E402  (in-skill library, same directory)
    MAILBOX_SUFFIX, PROTOCOL_VERSION, SUBJECT_REGISTRY_DISCOVER,
    SUBJECT_REGISTRY_REGISTER, REGISTRY_BUCKET, dumps, fingerprint_for,
    inbox_subject, load_identity, mailbox_subject, now_ts, sign_envelope,
    verify_envelope,
)

HEARTBEAT_INTERVAL_S = 25.0        # gateway default is 30s; stay under it
MAILBOX_STREAM = "MESH_AGENT_MAILBOX"  # the namespaced default, never AGENT_INBOXES
MAILBOX_RETRY_DELAY_S = 5.0
DEDUP_MAX = 512


def heartbeat_subject(agent_id: str) -> str:
    return f"mesh.heartbeat.{agent_id}"


def mailbox_durable_name(agent_id: str) -> str:
    """Same derivation as the gateway: agent ids contain '/' and cannot be a
    NATS durable name directly, so hash — stable across restarts so the
    consumer resumes its own position."""
    return "mailbox-" + hashlib.sha256(agent_id.encode()).hexdigest()[:16]


def is_jetstream_delivery(msg: Any) -> bool:
    return str(getattr(msg, "reply", "") or "").startswith("$JS.ACK")


async def ack_jetstream_only(msg: Any) -> None:
    """Ack a JetStream delivery and NEVER a core message: nats.py's ack()
    publishes an empty payload to msg.reply, and on a core delivery that is
    the CALLER'S inbox — it would send the caller a blank reply that can
    beat the real one."""
    if is_jetstream_delivery(msg):
        try:
            await msg.ack()
        except Exception:
            pass


class MeshBridge:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.agent_id = args.id
        self.identity = load_identity(args.identity) or self._mint_identity()
        self.nc: nats.aio.client.Client | None = None
        self.skills: dict[str, str] = dict(args.skill)  # name -> command template
        self._seen_ids: dict[str, float] = {}
        self._pinned: dict[str, str] = {}  # agent id -> fingerprint (TOFU)
        self._running = False

    # ── identity ────────────────────────────────────────────────────────────
    def _mint_identity(self) -> dict:
        from mesh_identity import generate, save  # same-directory module
        identity = generate(self.agent_id)
        save(identity, self.args.identity)
        print(f"[bridge] minted identity {self.agent_id} ({identity['fingerprint']}) "
              f"at {os.path.expanduser(self.args.identity)}", flush=True)
        return identity

    # ── manifest / registration / discovery ────────────────────────────────
    def manifest(self) -> dict:
        skills = [{"id": "ping", "name": "Ping", "description": "Liveness probe"},
                  {"id": "describe", "name": "Describe",
                   "description": "This agent's manifest"}]
        skills += [{"id": name, "name": name, "description": f"Runs: {command[:80]}"}
                   for name, command in self.skills.items()]
        return {
            "id": self.agent_id,
            "name": self.args.name,
            "description": self.args.description,
            "capabilities": self.args.capabilities,
            "skills": skills,
            "endpoint": inbox_subject(self.agent_id),
            "availability": "online",
            "last_heartbeat": now_ts(),
            "fingerprint": self.identity["fingerprint"],  # lets peers pin us pre-contact
        }

    async def register(self) -> None:
        envelope = sign_envelope({
            "v": PROTOCOL_VERSION, "id": uuid.uuid4().hex, "type": "register",
            "ts": now_ts(), "from": self.agent_id, "to": "REGISTRY",
            "trace": {"trace_id": uuid.uuid4().hex, "span_id": uuid.uuid4().hex},
            "payload": {"manifest": self.manifest()},
        }, self.identity)
        await self.nc.publish(SUBJECT_REGISTRY_REGISTER, dumps(envelope).encode())

    async def handle_discover(self, msg: Any) -> None:
        """Answer a discovery broadcast with our manifest. A registry service
        (if present) files register envelopes into the KV bucket; answering
        broadcasts directly is what makes us visible WITHOUT one — every
        ReactorPro edge subscribes here and answers the same way."""
        if not msg.reply:
            return
        try:
            envelope = json.loads(msg.data.decode())
        except ValueError:
            return
        if envelope.get("from") == self.agent_id:
            return  # never answer our own query
        payload = envelope.get("payload") or {}
        wanted_caps = payload.get("capabilities") or []
        wanted_skills = payload.get("skill_ids") or []
        if wanted_caps and not set(wanted_caps) <= set(self.args.capabilities):
            return
        if wanted_skills and not set(wanted_skills) <= set(self.skills) | {"ping"}:
            return
        reply = sign_envelope({
            "v": PROTOCOL_VERSION, "id": uuid.uuid4().hex, "type": "respond",
            "ts": now_ts(), "from": self.agent_id, "to": envelope.get("from", ""),
            "in_reply_to": envelope.get("id", ""),
            "trace": envelope.get("trace") or {"trace_id": uuid.uuid4().hex},
            "payload": self.manifest(),
        }, self.identity)
        await self.nc.publish(msg.reply, dumps(reply).encode())

    # ── trust (verify-if-signed, TOFU — mirrors the gateway's prefer mode) ──
    def check_inbound(self, envelope: dict) -> str | None:
        """Returns a refusal reason, or None when acceptable. Unsigned is
        accepted unless --require-signed (the gateway's `prefer` default);
        a bad signature or a swapped key is always refused."""
        valid, detail = verify_envelope(envelope)
        if not valid:
            return f"identity verification failed: {detail}"
        if detail == "unsigned":
            if self.args.require_signed:
                return "unsigned sender and this bridge requires signed envelopes"
            return None
        sender = str(envelope.get("from", ""))
        if detail in ("", "unsigned") or not sender:
            return None
        pinned = self._pinned.get(sender)
        if pinned and pinned != detail:
            return f"identity of {sender} changed: now {detail}, was pinned {pinned}"
        if not pinned:
            self._pinned[sender] = detail  # trust-on-first-use
        return None

    def dedup(self, envelope_id: str, redelivery: bool = False) -> bool:
        """True when this envelope is fresh. Skipped for JetStream redeliveries
        — a redelivery repeats the id by definition (the gateway's
        checkRedelivered does the same for its mailbox)."""
        if not envelope_id or redelivery:
            return True
        now = time.monotonic()
        if envelope_id in self._seen_ids:
            return False
        self._seen_ids[envelope_id] = now
        while len(self._seen_ids) > DEDUP_MAX:
            self._seen_ids.pop(next(iter(self._seen_ids)))
        return True

    # ── serving ────────────────────────────────────────────────────────────
    async def serve_forever(self) -> None:
        args = self.args
        options: dict[str, Any] = {"servers": [args.nats], "name": f"mesh-bridge-{self.agent_id}"}
        if args.nkey_seed:
            options["nkeys_seed"] = args.nkey_seed
        elif args.token:
            options["token"] = args.token
        elif args.user:
            options["user"], options["password"] = args.user, args.password or ""
        self.nc = nats.aio.client.Client()
        await self.nc.connect(**options)
        print(f"[bridge] connected to {args.nats}", flush=True)

        # The inbox MUST stay a core NATS subscription. Never build a JetStream
        # stream over mesh.agent.*.inbox: the server answers the publish with
        # a PubAck (breaking the caller's request) and a push consumer's
        # msg.reply becomes the ack subject (breaking the reply). See
        # references/protocol.md §inbox-streaming.
        await self.nc.subscribe(inbox_subject(self.agent_id), cb=self.handle_inbox)
        await self.nc.subscribe(SUBJECT_REGISTRY_DISCOVER, cb=self.handle_discover)
        await self.register()

        if args.mailbox:
            await self.consume_mailbox()

        self._running = True
        print(f"[bridge] LIVE  id={self.agent_id}  fp={self.identity['fingerprint']}", flush=True)
        print(f"[bridge] inbox={inbox_subject(self.agent_id)}  skills: ping, describe, "
              + ", ".join(self.skills), flush=True)

        while self._running:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            # A SIGNED heartbeat envelope (not a bare timestamp) lets every
            # ReactorPro edge on the mesh detect an id collision: only one key
            # should ever speak on mesh.heartbeat.<id>.
            heartbeat = sign_envelope({
                "v": PROTOCOL_VERSION, "id": uuid.uuid4().hex, "type": "heartbeat",
                "ts": now_ts(), "from": self.agent_id,
                "trace": {"trace_id": uuid.uuid4().hex, "span_id": uuid.uuid4().hex},
                "payload": {"ts": now_ts()},
            }, self.identity)
            await self.nc.publish(heartbeat_subject(self.agent_id), dumps(heartbeat).encode())
            await self.register()  # refresh the registry entry on the same cadence

    async def handle_inbox(self, msg: Any) -> None:
        try:
            envelope = json.loads(msg.data.decode())
        except ValueError as exc:
            await self.reply_error(msg, envelope=None, code=2001, message=f"malformed envelope: {exc}")
            return
        if envelope.get("type") != "request":
            return  # respond/emit/heartbeat on an inbox is not ours to act on
        envelope_id = str(envelope.get("id", ""))
        if not self.dedup(envelope_id):
            return
        reason = self.check_inbound(envelope)
        if reason:
            await self.reply_error(msg, envelope, code=3004, message=reason)
            return
        asyncio.create_task(self.run_request(msg, envelope))

    @staticmethod
    def prompt_of(payload: dict) -> str:
        """The peer's prompt, wherever it rides: top-level text (gateway
        dispatch mirrors it there) or inside input (mailbox sends don't)."""
        for source in (payload, payload.get("input") if isinstance(payload.get("input"), dict) else {}):
            for key in ("text", "message", "prompt"):
                value = source.get(key)
                if isinstance(value, str) and value:
                    return value
        return ""

    async def run_request(self, msg: Any, envelope: dict) -> None:
        payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
        skill = str(payload.get("skill") or "").strip()
        prompt = self.prompt_of(payload)
        task_id = str(envelope.get("task_id") or uuid.uuid4().hex)
        sender = str(envelope.get("from", "?"))
        started = time.monotonic()
        print(f"[inbox] {sender} -> {skill or '(no skill)'} task={task_id[:12]}", flush=True)

        try:
            if skill == "ping":
                output, text = {"pong": True, "ts": now_ts()}, "pong"
            elif skill == "describe":
                # Standard introspection, same as a ReactorPro edge serves.
                output, text = self.manifest(), f"{self.agent_id}: " + ", ".join(
                    s["id"] for s in self.manifest()["skills"])
            elif skill in self.skills:
                output, text = self.run_command(self.skills[skill], skill, payload)
            elif self.args.command and prompt:
                # Text-based callers — a desktop's Ask button sends
                # skill="invoke" with the prompt as text, and Synapse bridges
                # may send no skill at all — route any such prompt to the
                # default command, exactly how the fleet's bridges behave.
                output, text = self.run_command(self.args.command, skill or "default", payload)
            else:
                await self.reply_error(msg, envelope, code=3001,
                                      message=f"Skill {skill!r} not found")
                return
        except subprocess.TimeoutExpired:
            await self.reply_error(msg, envelope, code=4001,
                                  message=f"skill {skill!r} timed out after {self.args.exec_timeout}s")
            return
        except Exception as exc:  # noqa: BLE001 — a handler bug must not kill the bridge
            await self.reply_error(msg, envelope, code=5001, message=f"handler failed: {exc}")
            return

        latency_ms = round((time.monotonic() - started) * 1000)
        await self.reply_result(msg, envelope, task_id, output, text, latency_ms)

    def run_command(self, template: str, skill: str, payload: dict) -> tuple[dict, str]:
        """The universal harness adapter: render the template and shell out.
        {text} is the peer's prompt, {skill} the requested skill, {input} the
        compact JSON of payload.input, {task_id} the correlation id."""
        prompt = self.prompt_of(payload)
        rendered = template.format(
            text=prompt, skill=skill,
            input=dumps(payload.get("input") or {}),
            task_id=str(payload.get("task_id") or ""),
        )
        proc = subprocess.run(rendered, shell=True, capture_output=True, text=True,
                              timeout=self.args.exec_timeout)
        stdout = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        text = stdout or f"(command produced no output; exit {proc.returncode})"
        return {"raw": stdout, "exit": proc.returncode, "command": skill}, text

    # ── replies ────────────────────────────────────────────────────────────
    def reply_envelope(self, request: dict, payload: dict | None, *,
                       error: dict | None = None) -> dict:
        envelope: dict[str, Any] = {
            "v": PROTOCOL_VERSION, "id": uuid.uuid4().hex, "type": "respond",
            "ts": now_ts(), "from": self.agent_id,
            "to": str(request.get("from", "")) if request else "",
            "task_id": str(request.get("task_id", "")) if request else "",
            "in_reply_to": str(request.get("id", "")) if request else "",
            "trace": (request.get("trace") if request else None)
                     or {"trace_id": uuid.uuid4().hex, "span_id": uuid.uuid4().hex},
        }
        if payload is not None:
            envelope["payload"] = payload
        if error is not None:
            envelope["error"] = error
        return sign_envelope(envelope, self.identity)

    async def send_reply(self, msg: Any, request: dict, envelope: dict) -> None:
        """Reply to payload.reply_to when it starts with _REPLY (the fleet
        convention), else to msg.reply (core delivery). A JetStream delivery
        has msg.reply = the ack subject, where a reply reaches nobody."""
        payload = (request.get("payload") or {})
        reply_to = str(payload.get("reply_to") or "") if isinstance(payload, dict) else ""
        if reply_to.startswith("_REPLY"):
            await self.nc.publish(reply_to, dumps(envelope).encode())
        elif msg.reply and not is_jetstream_delivery(msg):
            await self.nc.publish(msg.reply, dumps(envelope).encode())

    async def reply_result(self, msg: Any, request: dict, task_id: str,
                           output: dict, text: str, latency_ms: int) -> None:
        # Both reply dialects: ReactorPro edges read payload.output;
        # Synapse bridges read payload.text.
        payload = {"output": output, "text": text, "task_id": task_id,
                   "latency_ms": latency_ms, "source": self.agent_id}
        await self.send_reply(msg, request, self.reply_envelope(request, payload))
        print(f"[inbox] replied to {request.get('from', '?')} in {latency_ms}ms", flush=True)

    async def reply_error(self, msg: Any, envelope: dict | None, *,
                          code: int, message: str) -> None:
        retryable = code in (3002, 4001, 4002, 4004, 5001)  # the wire table
        reply = self.reply_envelope(envelope or {}, None,
                                    error={"code": code, "message": message,
                                           "retryable": retryable})
        if envelope:
            await self.send_reply(msg, envelope, reply)
        elif msg.reply:
            await self.nc.publish(msg.reply, dumps(reply).encode())
        print(f"[inbox] refused: code={code} {message}", flush=True)

    # ── durable mailbox ────────────────────────────────────────────────────
    async def consume_mailbox(self) -> None:
        """At-least-once durable delivery of one-way mail left while we were
        away. Mirrors the gateway's design: adopt an existing stream whose
        subjects capture our mailbox, create it only when genuinely absent,
        never rewrite a stream we did not create."""
        js = self.nc.jetstream()
        subject = mailbox_subject(self.agent_id)
        try:
            stream = await js.stream_info(MAILBOX_STREAM)
            if not any(self._pattern_matches(p, subject) for p in stream.config.subjects):
                print(f"[mailbox] stream {MAILBOX_STREAM} exists but does not capture "
                      f"{subject} (subjects={stream.config.subjects}); refusing to touch it",
                      flush=True)
                return
        except NotFoundError:
            await js.add_stream(js_api.StreamConfig(
                name=MAILBOX_STREAM,
                description="durable mailbox for mesh agents (mesh.agent.*.mailbox)",
                subjects=["mesh.agent.*" + MAILBOX_SUFFIX],
                max_age=timedelta(days=7), max_msgs=10_000,
                storage=js_api.StorageType.FILE, discard=js_api.DiscardPolicy.OLD,
            ))
            print(f"[mailbox] created stream {MAILBOX_STREAM}", flush=True)

        async def deliver(msg: Any) -> None:
            try:
                envelope = json.loads(msg.data.decode())
            except ValueError:
                await ack_jetstream_only(msg)  # undecodable: retrying cannot help
                return
            redelivery = (getattr(msg.metadata, "num_delivered", 1) or 1) > 1
            if envelope.get("type") == "request":
                # No reply path exists here — accepting would strand the sender.
                print("[mailbox] refused a request: the mailbox is one-way", flush=True)
                await msg.term()
                return
            if not self.dedup(str(envelope.get("id", "")), redelivery=redelivery):
                await ack_jetstream_only(msg)
                return
            reason = self.check_inbound(envelope)
            if reason:
                print(f"[mailbox] refused: {reason}", flush=True)
                await msg.term()
                return
            payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
            skill = str(payload.get("skill") or "")
            prompt = self.prompt_of(payload)
            try:
                if skill == "ping":
                    text = "pong"
                elif skill == "describe":
                    text = f"{self.agent_id}: " + ", ".join(
                        s["id"] for s in self.manifest()["skills"])
                elif skill in self.skills:
                    _, text = self.run_command(self.skills[skill], skill, payload)
                elif self.args.command and prompt:
                    _, text = self.run_command(self.args.command, skill or "default", payload)
                else:
                    print(f"[mailbox] discarded: unknown skill {skill!r}", flush=True)
                    await msg.term()  # the skill will not appear by waiting
                    return
                print(f"[mailbox] handled {skill or 'default'} from "
                      f"{envelope.get('from', '?')}: {text[:80]}", flush=True)
                await ack_jetstream_only(msg)  # ack ONLY after the work succeeded
            except subprocess.TimeoutExpired:
                print(f"[mailbox] transient failure; retry in {MAILBOX_RETRY_DELAY_S}s",
                      flush=True)
                await msg.nak(delay=MAILBOX_RETRY_DELAY_S)  # a bare nak would spin
            except Exception as exc:  # noqa: BLE001
                print(f"[mailbox] permanent failure: {exc}; discarding", flush=True)
                await msg.term()

        await js.subscribe(subject, durable=mailbox_durable_name(self.agent_id),
                           stream=MAILBOX_STREAM, manual_ack=True, cb=deliver,
                           config=js_api.ConsumerConfig(
                               durable_name=mailbox_durable_name(self.agent_id),
                               filter_subject=subject,
                               ack_policy=js_api.AckPolicy.EXPLICIT,
                               # No max_deliver: capping silently discards work
                               # for a citizen that was away longer than the cap.
                               max_ack_pending=256))
        print(f"[mailbox] consuming {subject} (durable {mailbox_durable_name(self.agent_id)})",
              flush=True)

    @staticmethod
    def _pattern_matches(pattern: str, subject: str) -> bool:
        """NATS subject matching: `*` = exactly one token, `>` = one or more."""
        p, s = pattern.split("."), subject.split(".")
        for i, token in enumerate(p):
            if token == ">":
                return i < len(s)
            if i >= len(s):
                return False
            if token != "*" and token != s[i]:
                return False
        return len(p) == len(s)

    async def shutdown(self) -> None:
        self._running = False
        if self.nc:
            await self.nc.drain()
        print("[bridge] shut down", flush=True)


def parse_skill(value: str) -> tuple[str, str]:
    name, _, command = value.partition("=")
    name, command = name.strip(), command.strip()
    if not name or not command:
        raise SystemExit(f"--skill expects name='command' (got {value!r})")
    return name, command


def main() -> None:
    env = os.environ.get
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--id", required=True, help="unique mesh agent id, e.g. acme/lagos/hq-1")
    parser.add_argument("--nats", default=env("MESH_NATS_URL", "nats://localhost:4222"))
    parser.add_argument("--user", default=env("MESH_NATS_USER"))
    parser.add_argument("--password", default=env("MESH_NATS_PASSWORD"))
    parser.add_argument("--token", default=env("MESH_NATS_TOKEN"))
    parser.add_argument("--nkey-seed", default=env("MESH_NATS_NKEY_SEED"))
    parser.add_argument("--identity", default=env("MESH_IDENTITY_PATH", "~/.mesh/identity.json"))
    parser.add_argument("--name", default=None, help="display name (default: the id)")
    parser.add_argument("--description", default="A mesh citizen wrapped by mesh_bridge.py")
    parser.add_argument("--capabilities", nargs="*", default=[],
                        help="capability tags peers can filter discovery on")
    parser.add_argument("--skill", action="append", type=parse_skill, default=[],
                        metavar="NAME='COMMAND'",
                        help="named skill served by a shell command ({text}, {input})")
    parser.add_argument("--command", default=None,
                        help="default command for skill-less requests (the harness wrapper)")
    parser.add_argument("--exec-timeout", type=float, default=300.0,
                        help="seconds a command may run before the peer gets a 4001")
    parser.add_argument("--mailbox", action="store_true",
                        help="also consume our durable mailbox (needs JetStream)")
    parser.add_argument("--require-signed", action="store_true",
                        help="refuse unsigned senders (the gateway's `require` posture)")
    args = parser.parse_args()
    args.identity = os.path.expanduser(args.identity)
    args.name = args.name or args.id

    if not args.skill and not args.command:
        parser.error("serve something: pass --command and/or at least one --skill")

    bridge = MeshBridge(args)

    async def run() -> None:
        import signal
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(bridge.shutdown()))
        await bridge.serve_forever()

    try:
        asyncio.run(run())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


if __name__ == "__main__":
    main()