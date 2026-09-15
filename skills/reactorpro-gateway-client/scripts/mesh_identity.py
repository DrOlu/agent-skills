#!/usr/bin/env python3
"""Mint and inspect a ReactorPro mesh identity.

An identity is an Ed25519 keypair bound to an agent id. The fingerprint
covers BOTH the id and the public key, so the id is permanent: possession of
the private key is the only way to speak as this agent, and editing either
part invalidates the file. Peers pin this fingerprint on first verified
contact (trust-on-first-use), so treat the file like a password — it is
written 0600 and must never be committed or shared.

The JSON format matches the gateway's own identity file
(internal/mesh/identity.go), so a gateway and a script can share an identity
if you ever want them to (not recommended — one identity, one process).

Requires: cryptography  (pip install cryptography)

    mesh_identity.py init --id acme/lagos/edge-1 [--path ~/.mesh/identity.json]
    mesh_identity.py show [--path ~/.mesh/identity.json]
    mesh_identity.py verify [--path ~/.mesh/identity.json]

Choose the id once, carefully: `<org>/<site>/<edge>` reads well in logs and
audit trails, and two agents with the same id cannot coexist on a mesh.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

FP_PREFIX = "sha256:"


def fingerprint_for(agent_id: str, public_key_pem: str) -> str:
    """sha256:<16 hex> over `<agent id>\\n` + the raw public key bytes.

    Mirrors mesh.FingerprintFor byte for byte — this is wire contract, and a
    fingerprint minted here must match what a gateway derives from the same
    key."""
    public = serialization.load_pem_public_key(public_key_pem.encode())
    raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    digest = hashlib.sha256((agent_id + "\n").encode() + raw).hexdigest()
    return FP_PREFIX + digest[:16]


def generate(agent_id: str) -> dict:
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return {
        "identity": agent_id,
        "privateKeyPem": private_pem,
        "publicKeyPem": public_pem,
        "fingerprint": fingerprint_for(agent_id, public_pem),
    }


def save(identity: dict, path: str) -> None:
    directory = os.path.dirname(os.path.expanduser(path))
    if directory:
        os.makedirs(directory, mode=0o700, exist_ok=True)
    target = os.path.expanduser(path)
    if os.path.exists(target):
        raise SystemExit(f"refusing to overwrite {target} — an existing identity is "
                         "permanent; mint a new one only under a new path/id")
    with open(target, "w") as handle:
        json.dump(identity, handle, indent=2)
        handle.write("\n")
    os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)  # 0600 — private key material


def load_and_verify(path: str) -> dict:
    with open(os.path.expanduser(path)) as handle:
        identity = json.load(handle)
    if identity.get("fingerprint") != fingerprint_for(identity["identity"], identity["publicKeyPem"]):
        raise SystemExit("fingerprint mismatch: the id or the key was modified — "
                         "the file is unusable and peers would refuse it (code 3004)")
    # The private key must match the advertised public key.
    private = serialization.load_pem_private_key(identity["privateKeyPem"].encode(), password=None)
    derived = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    advertised = serialization.load_pem_public_key(identity["publicKeyPem"].encode()).public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if derived != advertised:
        raise SystemExit("private key does not match the public key in the identity file")
    return identity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default_path = os.environ.get("MESH_IDENTITY_PATH", "~/.mesh/identity.json")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="mint a new identity (refuses to overwrite)")
    init.add_argument("--id", required=True, help="agent id, e.g. acme/lagos/edge-1")
    init.add_argument("--path", default=default_path)
    show = sub.add_parser("show", help="print the public parts of an identity")
    show.add_argument("--path", default=default_path)
    verify = sub.add_parser("verify", help="check the file's internal consistency")
    verify.add_argument("--path", default=default_path)
    args = parser.parse_args()

    if args.command == "init":
        identity = generate(args.id.strip())
        save(identity, args.path)
        print(f"identity minted: {identity['identity']}")
        print(f"fingerprint:     {identity['fingerprint']}")
        print(f"file:            {os.path.expanduser(args.path)} (0600)")
        print("Share the fingerprint (not the file) with peers that pre-pin you:")
        print("  -mesh-trusted-peers=" + identity["fingerprint"])
    elif args.command == "show":
        identity = load_and_verify(args.path)
        print(f"id:          {identity['identity']}")
        print(f"fingerprint: {identity['fingerprint']}")
        print(f"public key:\n{identity['publicKeyPem']}")
    elif args.command == "verify":
        load_and_verify(args.path)
        print("identity is internally consistent")


if __name__ == "__main__":
    main()