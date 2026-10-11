#!/usr/bin/env python3
"""Unit tests for scripts/ask_instance.py — the harness-agnostic runner.

Pins the always-JSON contract any third-party harness builds against:
  * answered ask  -> exit 0, stdout is the instance's envelope, verbatim
  * refused ask   -> exit 2, stdout still one JSON envelope
  * no ask.py / bad menu shape / timeout / unparsable stdout
                  -> exit 3 + a harness_error envelope on stdout
  * interpreter resolution: --python > NEURALOS_PYTHON > sys.executable
  * menu validation accepts all three documented shapes
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
ASK_INSTANCE = os.path.join(SCRIPTS, "ask_instance.py")
sys.path.insert(0, SCRIPTS)
import ask_instance as ai  # noqa: E402

MENU = [{"name": "count_rows", "description": "count",
         "triggers": ["count rows"], "parameters": {"type": "object",
                                                    "properties": {},
                                                    "required": []}}]

STUB_ASK = textwrap.dedent("""
    import json, os, sys, time
    q = sys.argv[1]
    base = {"question": q, "ask_id": "stub", "gate_version": 1,
            "argv": sys.argv[2:]}
    if os.environ.get("STUB_SLEEP"):
        time.sleep(float(os.environ["STUB_SLEEP"]))
    if os.environ.get("STUB_GARBAGE"):
        print("this is not json")
        raise SystemExit(0)
    if "forbidden" in q:
        print(json.dumps({**base, "refused": True, "refusal_reason": "action_intent",
                          "probe": None, "results": None, "mode": "refused"}))
        raise SystemExit(2)
    print(json.dumps({**base, "refused": False, "refusal_reason": None,
                      "probe": "count_rows", "mode": "retrieval",
                      "results": [{"rows": 5}]}))
    raise SystemExit(0)
""")


def write_instance(menu_payload, ask_source=STUB_ASK, with_ask=True):
    tmp = tempfile.TemporaryDirectory()
    if with_ask:
        with open(os.path.join(tmp.name, "ask.py"), "w", encoding="utf-8") as fh:
            fh.write(ask_source)
    with open(os.path.join(tmp.name, "needle_menu.json"), "w",
              encoding="utf-8") as fh:
        json.dump(menu_payload, fh)
    return tmp


def run(args, env_extra=None):
    env = dict(os.environ)
    env.pop("NEURALOS_PYTHON", None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, ASK_INSTANCE] + args,
                          capture_output=True, text=True, env=env, timeout=60)


class TestHappyPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = write_instance(MENU)
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_answered_exit_zero_envelope_passthrough(self):
        proc = run([self.dir, "count rows"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        env = json.loads(proc.stdout)
        self.assertEqual(env["probe"], "count_rows")
        self.assertEqual(env["refused"], False)
        self.assertEqual(env["results"], [{"rows": 5}])

    def test_refused_exit_two_envelope_passthrough(self):
        proc = run([self.dir, "forbidden operation"])
        self.assertEqual(proc.returncode, 2)
        env = json.loads(proc.stdout)
        self.assertEqual(env["refused"], True)
        self.assertEqual(env["refusal_reason"], "action_intent")

    def test_no_cache_flag_forwarded(self):
        proc = run([self.dir, "count rows", "--no-cache"])
        env = json.loads(proc.stdout)
        self.assertIn("--no-cache", env["argv"])

    def test_probes_key_menu_shape_accepted(self):
        tmp = write_instance({"probes": MENU})
        try:
            proc = run([tmp.name, "count rows"])
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(json.loads(proc.stdout)["probe"], "count_rows")
        finally:
            tmp.cleanup()

    def test_menu_key_menu_shape_accepted(self):
        tmp = write_instance({"name": "x", "menu": MENU})
        try:
            proc = run([tmp.name, "count rows"])
            self.assertEqual(proc.returncode, 0)
        finally:
            tmp.cleanup()


class TestHarnessErrors(unittest.TestCase):
    """Exit 3 + harness_error envelope — the contract for machine consumers."""

    def assertHarnessError(self, proc, fragment):
        self.assertEqual(proc.returncode, 3, proc.stdout)
        env = json.loads(proc.stdout)
        self.assertEqual(env["mode"], "harness_error")
        self.assertIn(fragment, env["error"])

    def test_missing_ask_py(self):
        tmp = write_instance(MENU, with_ask=False)
        try:
            proc = run([tmp.name, "count rows"])
            self.assertHarnessError(proc, "no ask.py")
        finally:
            tmp.cleanup()

    def test_metadata_only_menu_rejected(self):
        tmp = write_instance({"name": "x", "version": "1"})
        try:
            proc = run([tmp.name, "count rows"])
            self.assertHarnessError(proc, "not a probe array")
        finally:
            tmp.cleanup()

    def test_garbage_stdout(self):
        tmp = write_instance(MENU)
        try:
            proc = run([tmp.name, "count rows"], {"STUB_GARBAGE": "1"})
            self.assertHarnessError(proc, "not a single JSON envelope")
        finally:
            tmp.cleanup()

    def test_timeout(self):
        tmp = write_instance(MENU)
        try:
            proc = run([tmp.name, "count rows", "--timeout", "1"],
                       {"STUB_SLEEP": "3"})
            self.assertHarnessError(proc, "timed out")
        finally:
            tmp.cleanup()


class TestActionGate(unittest.TestCase):
    """The runner's own GATE_VERSION 1 action gate — enforced BEFORE ask.py
    runs, so gateless hand-authored instances cannot answer imperative
    questions for non-SuperAgent consumers."""

    def setUp(self):
        self.tmp = write_instance(MENU)
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_imperative_refused_without_running_ask_py(self):
        proc = run([self.dir, "delete all the rows"])
        self.assertEqual(proc.returncode, 2)
        env = json.loads(proc.stdout)
        self.assertEqual(env["refused"], True)
        self.assertEqual(env["refusal_reason"], "action_intent")
        self.assertEqual(env["gate_version"], 1)
        self.assertEqual(env["via"], "ask-instance")
        # the stub echoes argv — its presence would mean ask.py executed
        self.assertNotIn("argv", env)

    def test_second_verb_also_refused(self):
        proc = run([self.dir, "wipe the archive"])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["refusal_reason"], "action_intent")

    def test_capability_carve_out_still_answers(self):
        # the stub always answers count_rows; what matters is that the gate
        # lets a delete-claiming menu through instead of refusing
        menu = [dict(MENU[0]),
                {"name": "delete_records", "description": "remove",
                 "triggers": ["delete records"],
                 "parameters": {"type": "object", "properties": {},
                                "required": []}}]
        tmp = write_instance(menu)
        try:
            proc = run([tmp.name, "delete records"])
            self.assertEqual(proc.returncode, 0, proc.stdout)
            env = json.loads(proc.stdout)
            self.assertEqual(env["refused"], False)
        finally:
            tmp.cleanup()

    def test_enum_value_does_not_teach_the_verb(self):
        menu = [{"name": "bucket_files", "description": "list files",
                 "triggers": ["bucket files"],
                 "parameters": {"type": "object",
                                "properties": {"bucket": {"type": "string",
                                                          "enum": ["do-not-delete-backups"]}},
                                "required": []}}]
        tmp = write_instance(menu)
        try:
            proc = run([tmp.name, "delete all the buckets"])
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(json.loads(proc.stdout)["refusal_reason"],
                             "action_intent")
        finally:
            tmp.cleanup()


class TestInterpreterResolution(unittest.TestCase):
    def setUp(self):
        # isolate the shell's NEURALOS_PYTHON (real deployments set it)
        self._old = os.environ.pop("NEURALOS_PYTHON", None)

    def tearDown(self):
        if self._old is not None:
            os.environ["NEURALOS_PYTHON"] = self._old

    def test_explicit_flag_wins(self):
        self.assertEqual(ai.resolve_python("/custom/python"), "/custom/python")

    def test_default_is_this_interpreter(self):
        self.assertEqual(ai.resolve_python("auto"), sys.executable)

    def test_env_var_wins_over_default(self):
        os.environ["NEURALOS_PYTHON"] = "/env/python"
        self.assertEqual(ai.resolve_python("auto"), "/env/python")

    def test_explicit_flag_beats_env_var(self):
        os.environ["NEURALOS_PYTHON"] = "/env/python"
        self.assertEqual(ai.resolve_python("/flag/python"), "/flag/python")


if __name__ == "__main__":
    unittest.main()
