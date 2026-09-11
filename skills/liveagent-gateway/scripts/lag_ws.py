#!/usr/bin/env python3
"""
lag_ws.py - LiveAgent Gateway v2 WebSocket client (Python 3 stdlib only).

Speaks protocol v2 (WebSocket + Protobuf) with frames hand-encoded on the wire,
so it needs no protobuf or websockets package. Use it for anything the HTTP API
cannot do: chat control, live events, agent status, pass-through requests.

Usage
  export LAG_GW="http://localhost:3000"
  export LAG_TOKEN="<gateway token or agt_ per-agent token>"
  export LAG_AGENT="agent-<uuid>"
  python3 lag_ws.py <command> [options]

Commands
  probe                       Handshake only; print ServerHello
  status                      Agent online/ready snapshot
  agents                      Full agent directory with live status
  send "prompt"               Submit a chat turn; stream events until DONE
  watch                       Subscribe to a conversation and stream events
  cancel                      Cancel the active run in a conversation
  req <Arm> [--json JSON]     Any whitelisted pass-through request arm

Common options
  --conversation ID   --after-seq N   --workdir PATH   --run-id ID
  --timeout SEC       --raw           --gw URL / --token T / --agent ID

Examples
  python3 lag_ws.py probe
  python3 lag_ws.py agents
  python3 lag_ws.py send "list the files in the workspace" --timeout 120
  python3 lag_ws.py watch --conversation <id> --after-seq 0
  python3 lag_ws.py req HistoryList --json '{"1":1,"2":20}'
  python3 lag_ws.py req FsRoots

`req` needs envelope_arms.json to sit beside this file.
"""

import argparse
import base64
import json
import os
import select
import socket
import struct
import sys
import time

PROTOCOL_VERSION = 2
WS_SUBPROTOCOL = "liveagent.v2.pb"

# ---------------------------------------------------------------- protobuf ---
def _varint(n):
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        if n:
            out.append(b + 128)
        else:
            out.append(b)
            return bytes(out)


def _read_varint(buf, i):
    shift = 0
    val = 0
    while True:
        if i >= len(buf):
            raise ValueError("truncated varint")
        b = buf[i]
        i += 1
        val += (b % 128) << shift
        if b < 128:
            return val, i
        shift += 7


def f_varint(field, value):
    return _varint(field * 8) + _varint(int(value))


def f_bool(field, value):
    return f_varint(field, 1 if value else 0)


def f_bytes(field, value):
    if isinstance(value, str):
        value = value.encode()
    return _varint(field * 8 + 2) + _varint(len(value)) + value


def f_msg(field, value):
    return f_bytes(field, value)


def decode(buf):
    """Decode a protobuf message into {field: value | [values]}."""
    out = {}
    i = 0
    while i < len(buf):
        key, i = _read_varint(buf, i)
        field, wire = key // 8, key % 8
        if wire == 0:
            val, i = _read_varint(buf, i)
        elif wire == 2:
            ln, i = _read_varint(buf, i)
            val = buf[i:i + ln]
            i += ln
        elif wire == 5:
            val = struct.unpack("<I", buf[i:i + 4])[0]
            i += 4
        elif wire == 1:
            val = struct.unpack("<Q", buf[i:i + 8])[0]
            i += 8
        else:
            raise ValueError("unsupported wire type %s" % wire)
        if field in out:
            if not isinstance(out[field], list):
                out[field] = [out[field]]
            out[field].append(val)
        else:
            out[field] = val
    return out


def _txt(v):
    return v.decode("utf-8", "replace") if isinstance(v, bytes) else v


# --------------------------------------------------------- frame numbers ---
WEB_CLIENT_FRAME = {
    "request_id": 1, "hello": 2, "agent_request": 3, "status_get": 4,
    "chat_command": 5, "chat_prepare": 6, "chat_subscribe": 7,
    "chat_unsubscribe": 8, "chat_activities": 9, "workspace_subscribe": 10,
    "workspace_unsubscribe": 11, "pong": 12, "agent_id": 13, "agent_list": 14,
}

WEB_SERVER_FRAME = {
    "request_id": 1, "hello": 2, "agent_response": 3, "local_error": 4,
    "ping": 5, "status": 6, "chat_subscribed": 7, "chat_accepted": 8,
    "chat_activities": 9, "chat_event": 10, "chat_command_update": 11,
    "chat_subscription_reset": 12, "chat_activity": 13, "ack": 14,
    "chat_cancelled": 15, "agent_id": 16, "agent_list": 17,
}

CHAT_COMMAND = {"type": 1, "request": 2, "base_message_ref": 3, "cancel": 4}
CHAT_REQUEST = {
    "conversation_id": 1, "message": 2, "selected_model": 3,
    "execution_mode": 4, "workdir": 5, "uploaded_files": 7,
    "client_request_id": 8, "runtime_controls": 9, "queue_policy": 10,
    "command_safety_mode": 11, "referenced_conversations": 12,
}
CANCEL_CHAT = {"conversation_id": 1, "run_id": 2}


# --------------------------------------------------------- frame builders ---
def hello_frame(token, agent_id="", client_name="lag_ws"):
    h = (
        f_varint(1, PROTOCOL_VERSION)
        + f_varint(2, 1)  # CLIENT_ROLE_BROWSER
        + f_bytes(3, token)
        + f_bytes(4, agent_id)
        + f_bytes(6, client_name)
        + f_bytes(7, "1.0")
    )
    return f_msg(WEB_CLIENT_FRAME["hello"], h)


def _wrap(frame_field, payload, request_id="", agent_id=""):
    body = b""
    if request_id:
        body += f_bytes(1, request_id)
    if agent_id:
        body += f_bytes(WEB_CLIENT_FRAME["agent_id"], agent_id)
    body += f_msg(frame_field, payload)
    return body


def status_get(request_id="r1", agent_id=""):
    return _wrap(WEB_CLIENT_FRAME["status_get"], b"", request_id, agent_id)


def agent_list(request_id="r1"):
    return f_bytes(1, request_id) + f_msg(WEB_CLIENT_FRAME["agent_list"], b"")


def chat_prepare(request_id, agent_id, reason="submit"):
    return _wrap(WEB_CLIENT_FRAME["chat_prepare"], f_bytes(1, reason), request_id, agent_id)


def chat_subscribe(request_id, agent_id, conversation_id, after_seq=0, stream_epoch=""):
    p = f_bytes(1, conversation_id) + f_varint(2, after_seq)
    if stream_epoch:
        p += f_bytes(3, stream_epoch)
    return _wrap(WEB_CLIENT_FRAME["chat_subscribe"], p, request_id, agent_id)


def chat_submit(request_id, agent_id, message, conversation_id="", workdir="",
                client_request_id="", execution_mode=""):
    req = b""
    if conversation_id:
        req += f_bytes(CHAT_REQUEST["conversation_id"], conversation_id)
    req += f_bytes(CHAT_REQUEST["message"], message)
    if execution_mode:
        req += f_bytes(CHAT_REQUEST["execution_mode"], execution_mode)
    if workdir:
        req += f_bytes(CHAT_REQUEST["workdir"], workdir)
    if client_request_id:
        req += f_bytes(CHAT_REQUEST["client_request_id"], client_request_id)
    cmd = f_bytes(CHAT_COMMAND["type"], "chat.submit") + f_msg(CHAT_COMMAND["request"], req)
    return _wrap(WEB_CLIENT_FRAME["chat_command"], cmd, request_id, agent_id)


def chat_cancel(request_id, agent_id, conversation_id="", run_id=""):
    req = b""
    if conversation_id:
        req += f_bytes(CANCEL_CHAT["conversation_id"], conversation_id)
    if run_id:
        req += f_bytes(CANCEL_CHAT["run_id"], run_id)
    cmd = f_bytes(CHAT_COMMAND["type"], "chat.cancel") + f_msg(CHAT_COMMAND["cancel"], req)
    return _wrap(WEB_CLIENT_FRAME["chat_command"], cmd, request_id, agent_id)


def passthrough(request_id, agent_id, arm, inner=b""):
    """Build an agent_request (GatewayEnvelope) carrying one whitelisted arm."""
    env = f_bytes(1, request_id) + f_varint(2, int(time.time() * 1000)) + f_msg(arm, inner)
    return _wrap(WEB_CLIENT_FRAME["agent_request"], env, request_id, agent_id)


def pong(timestamp_ms):
    return f_msg(WEB_CLIENT_FRAME["pong"], f_varint(1, timestamp_ms))


# --------------------------------------------------------------------- ws ---
class WS:
    """Minimal RFC6455 client: binary frames, client->server masking."""

    def __init__(self, url, token, timeout=30):
        if url.startswith("https://"):
            hostport, self.tls = url[8:], True
        elif url.startswith("http://"):
            hostport, self.tls = url[7:], False
        else:
            raise ValueError("gateway url must start with http:// or https://")
        hostport = hostport.rstrip("/")
        if "/" in hostport:
            hostport = hostport.split("/", 1)[0]
        self.host, _, port = hostport.partition(":")
        self.port = int(port or (443 if self.tls else 80))
        self.path = "/ws/v2"
        self.token = token
        self.sock = None
        self.timeout = timeout
        self._buf = b""

    def connect(self):
        raw = socket.create_connection((self.host, self.port), timeout=self.timeout)
        if self.tls:
            import ssl
            raw = ssl.create_default_context().wrap_socket(raw, server_hostname=self.host)
        self.sock = raw
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET " + self.path + " HTTP/1.1\r\n"
            "Host: " + self.host + ":" + str(self.port) + "\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: " + key + "\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Sec-WebSocket-Protocol: " + WS_SUBPROTOCOL + "\r\n"
            "\r\n"
        )
        self.sock.sendall(req.encode())
        while b"\r\n\r\n" not in self._buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("gateway closed during handshake")
            self._buf += chunk
        head, _, rest = self._buf.partition(b"\r\n\r\n")
        self._buf = rest
        status = head.split(b"\r\n", 1)[0].decode()
        if "101" not in status:
            raise ConnectionError("websocket upgrade failed: " + status)
        return status

    def send(self, payload, opcode=0x2):
        header = bytes([0x80 | opcode])
        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + masked)

    def _recv_into_buf(self):
        chunk = self.sock.recv(65536)
        if not chunk:
            raise ConnectionError("gateway closed connection")
        self._buf += chunk

    def recv(self, timeout=None):
        """Return (opcode, payload). Handles fragmentation and control frames."""
        deadline = time.time() + (self.timeout if timeout is None else timeout)
        data = b""
        opcode = None
        while True:
            while len(self._buf) >= 2:
                b0 = self._buf[0]
                b1 = self._buf[1]
                fin = b0 // 128
                op = b0 % 16
                masked = b1 // 128
                ln = b1 % 128
                idx = 2
                if ln == 126:
                    if len(self._buf) < 4:
                        break
                    ln = struct.unpack(">H", self._buf[2:4])[0]
                    idx = 4
                elif ln == 127:
                    if len(self._buf) < 10:
                        break
                    ln = struct.unpack(">Q", self._buf[2:10])[0]
                    idx = 10
                if masked:
                    idx += 4
                if len(self._buf) < idx + ln:
                    break
                payload = self._buf[idx:idx + ln]
                self._buf = self._buf[idx + ln:]
                if op == 0x9:
                    self.send(payload, opcode=0xA)
                    continue
                if op == 0xA:
                    continue
                if op == 0x8:
                    raise ConnectionError("gateway sent close")
                data += payload
                if op != 0x0:
                    opcode = op
                if fin:
                    return opcode, data
                continue
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError("timed out waiting for a frame")
            r, _, _ = select.select([self.sock], [], [], min(remaining, 1.0))
            if r:
                self._recv_into_buf()

    def close(self):
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass


# ----------------------------------------------------------------- helpers ---
def extract(frame, *names):
    for name in names:
        fld = WEB_SERVER_FRAME.get(name)
        if fld and isinstance(frame.get(fld), bytes):
            return name, frame[fld]
    return None, None


def status_dict(buf):
    d = decode(buf)
    return {
        "online": bool(d.get(1, 0)),
        "agent_ready": bool(d.get(2, 0)),
        "chat_runtime_ready": bool(d.get(3, 0)),
        "agent_id": _txt(d.get(4, "")),
        "agent_version": _txt(d.get(5, "")),
        "session_id": _txt(d.get(6, "")),
        "connected_since": d.get(7),
        "runtime_state": _txt(d.get(9, "")),
        "runtime_visible": bool(d.get(12, 0)),
        "runtime_active_run_count": d.get(13, 0),
        "name": _txt(d.get(14, "")),
    }


def chat_event_dict(buf):
    d = decode(buf)
    payload = d.get(3, b"")
    try:
        payload = json.loads(payload.decode())
    except Exception:
        payload = _txt(payload)
    return {"conversation_id": _txt(d.get(1, "")), "seq": d.get(2, 0), "payload": payload}


class Client:
    def __init__(self, gw, token, agent, timeout, raw=False):
        self.token = token
        self.agent = agent
        self.raw = raw
        self.timeout = timeout
        self.ws = WS(gw, token, timeout=timeout)
        self._seq = 0
        self.hello = {}

    def rid(self):
        self._seq += 1
        return "lag-" + str(self._seq)

    def open(self):
        """Handshake, tolerating non-hello frames the gateway may push first."""
        self.ws.connect()
        self.ws.send(hello_frame(self.token, client_name="lag_ws"))
        deadline = time.time() + self.timeout
        while True:
            _, payload = self.ws.recv(timeout=max(1.0, deadline - time.time()))
            frame = decode(payload)
            if isinstance(frame.get(2), bytes):
                h = decode(frame[2])
                break
            if isinstance(frame.get(5), bytes):
                self.ws.send(pong(int(time.time() * 1000)))
                continue
            if isinstance(frame.get(4), bytes):
                d = decode(frame[4])
                raise ConnectionError("gateway rejected hello: " + _txt(d.get(2, b"")))
            if time.time() > deadline:
                raise ConnectionError("gateway did not return ServerHello")
        if not bool(h.get(1, 0)):
            raise ConnectionError("gateway rejected hello: " + _txt(h.get(2, b"")))
        self.hello = {
            "ok": True,
            "session_id": _txt(h.get(3, "")),
            "heartbeat_period_seconds": h.get(5, 0),
            "max_message_bytes": h.get(6, 0),
        }
        return self.hello

    def pump(self, stop=None, until=None, deadline=None):
        """Read frames, print what matters, auto-pong, until stop/until/deadline."""
        deadline = deadline or (time.time() + self.timeout)
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return "timeout"
            try:
                _, payload = self.ws.recv(timeout=min(remaining, 2.0))
            except TimeoutError:
                continue
            frame = decode(payload)
            name, buf = extract(frame, "chat_event", "status", "agent_list",
                                "chat_accepted", "chat_command_update",
                                "chat_subscribed", "chat_subscription_reset",
                                "local_error", "agent_response", "hello", "ping",
                                "ack", "chat_cancelled", "chat_activities")
            if name == "ping":
                self.ws.send(pong(int(time.time() * 1000)))
                continue
            if name is None:
                continue

            if name == "chat_event":
                ev = chat_event_dict(buf)
                print(json.dumps(ev) if self.raw
                      else "[seq %s] %s" % (ev["seq"], json.dumps(ev["payload"])[:2000]))
                if stop and stop(ev):
                    return "done"
            elif name == "status":
                s = status_dict(buf)
                print(json.dumps(s, indent=2) if self.raw else
                      "agent %s online=%s ready=%s chat_ready=%s version=%s" % (
                          s["agent_id"] or "(none)", s["online"], s["agent_ready"],
                          s["chat_runtime_ready"], s["agent_version"]))
                if until == "status":
                    return "done"
            elif name == "agent_list":
                d = decode(buf)
                agents = d.get(1)
                if agents is None:
                    agents = []
                elif isinstance(agents, bytes):
                    agents = [agents]
                print(json.dumps([status_dict(a) for a in agents], indent=2))
                if until == "agent_list":
                    return "done"
            elif name == "chat_accepted":
                d = decode(buf)
                print("accepted run_id=%s conversation=%s accepted_seq=%s deduped=%s" % (
                    _txt(d.get(1, b"")), _txt(d.get(2, b"")), d.get(3, 0), bool(d.get(4, 0))))
                if until == "accepted":
                    return "done"
            elif name == "chat_command_update":
                d = decode(buf)
                print("update phase=%s run=%s code=%s msg=%s" % (
                    _txt(d.get(4, b"")), _txt(d.get(1, b"")), _txt(d.get(5, b"")),
                    _txt(d.get(6, b""))))
                if until == "update":
                    return "done"
            elif name == "chat_subscribed":
                d = decode(buf)
                print("subscribed conversation=%s epoch=%s latest_seq=%s reset=%s" % (
                    _txt(d.get(1, b"")), _txt(d.get(2, b"")), d.get(3, 0), bool(d.get(4, 0))))
                for raw in (d.get(7) or []):
                    if isinstance(raw, bytes):
                        print("replay:", raw.decode("utf-8", "replace")[:1500])
                if until == "subscribed":
                    return "done"
            elif name == "chat_subscription_reset":
                print("subscription_reset -> re-subscribe with after_seq=0")
                if until == "reset":
                    return "done"
            elif name == "local_error":
                d = decode(buf)
                print("LOCAL ERROR code=%s message=%s" % (d.get(1), _txt(d.get(2, b""))))
                return "error"
            elif name == "agent_response":
                print(json.dumps({"agent_response_bytes": len(buf)}))
                if until == "response":
                    return "done"
            elif name == "chat_cancelled":
                d = decode(buf)
                print("cancelled ok=%s run=%s" % (bool(d.get(1, 0)), _txt(d.get(2, b""))))
                if until == "cancelled":
                    return "done"


def arm_field(arm):
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "envelope_arms.json")
    arms = json.load(open(src)) if os.path.exists(src) else {}
    if arm not in arms:
        raise SystemExit("unknown arm '%s'.\nKnown arms: %s" % (arm, ", ".join(sorted(arms))))
    return arms[arm]


def main():
    p = argparse.ArgumentParser(description="LiveAgent Gateway v2 WebSocket client")
    p.add_argument("command", help="probe|status|agents|send|watch|cancel|req")
    p.add_argument("arg", nargs="?", help="prompt text for send; arm name for req")
    p.add_argument("--gw", default=os.environ.get("LAG_GW", "http://localhost:3000"))
    p.add_argument("--token", default=os.environ.get("LAG_TOKEN", ""))
    p.add_argument("--agent", default=os.environ.get("LAG_AGENT", ""))
    p.add_argument("--conversation", default="")
    p.add_argument("--after-seq", type=int, default=0)
    p.add_argument("--run-id", default="")
    p.add_argument("--workdir", default="")
    p.add_argument("--json", default="{}")
    p.add_argument("--timeout", type=float, default=60)
    p.add_argument("--raw", action="store_true")
    a = p.parse_args()

    if not a.token:
        raise SystemExit("no token: pass --token or set LAG_TOKEN")
    if a.command not in ("status", "agents", "probe") and not a.agent:
        raise SystemExit("no agent id: pass --agent or set LAG_AGENT")

    c = Client(a.gw, a.token, a.agent, a.timeout, a.raw)
    c.open()

    if a.command == "probe":
        print(json.dumps(c.hello, indent=2))
        return

    if a.command == "status":
        c.ws.send(status_get(c.rid(), a.agent) if a.agent else status_get(c.rid()))
        print("result:", c.pump(until="status", deadline=time.time() + min(a.timeout, 15)))
        return

    if a.command == "agents":
        c.ws.send(agent_list(c.rid()))
        print("result:", c.pump(until="agent_list", deadline=time.time() + min(a.timeout, 15)))
        return

    if a.command == "send":
        if not a.arg:
            raise SystemExit('send needs a prompt: lag_ws.py send "..."')
        c.ws.send(chat_prepare(c.rid(), a.agent, "send"))
        c.pump(until="status", deadline=time.time() + min(a.timeout, 10))
        c.ws.send(chat_submit(c.rid(), a.agent, a.arg, a.conversation, a.workdir))
        print("submitted; streaming events (Ctrl+C to stop)\n")

        def stop(ev):
            pl = ev.get("payload")
            if isinstance(pl, dict):
                return str(pl.get("type", "")).upper() in ("DONE", "RUN.COMPLETED", "RUN.FAILED")
            return False

        print("result:", c.pump(stop=stop))
        return

    if a.command == "watch":
        if not a.conversation:
            raise SystemExit("watch needs --conversation")
        c.ws.send(chat_subscribe(c.rid(), a.agent, a.conversation, a.after_seq))
        print("watching %s from seq %s (Ctrl+C to stop)\n" % (a.conversation, a.after_seq))
        print("result:", c.pump())
        return

    if a.command == "cancel":
        c.ws.send(chat_cancel(c.rid(), a.agent, a.conversation, a.run_id))
        print("result:", c.pump(until="cancelled", deadline=time.time() + 15))
        return

    if a.command == "req":
        if not a.arg:
            raise SystemExit("req needs an arm name, e.g. req HistoryList")
        inside = b""
        obj = json.loads(a.json)
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, bool):
                    inside += f_bool(int(k), v)
                elif isinstance(v, int):
                    inside += f_varint(int(k), v)
                else:
                    inside += f_bytes(int(k), str(v))
        c.ws.send(passthrough(c.rid(), a.agent, arm_field(a.arg), inside))
        print("result:", c.pump(until="response", deadline=time.time() + min(a.timeout, 30)))
        return

    raise SystemExit("unknown command " + a.command)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\ninterrupted")
    except (ConnectionError, TimeoutError, ValueError) as e:
        print("ERROR: %s" % e, file=sys.stderr)
        sys.exit(1)
