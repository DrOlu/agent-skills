#!/usr/bin/env python3
"""Offline tests (no Restate server needed).
Run: python3 test_neuralosd_restate.py -v
"""
import json
import os
import unittest


class TestNightlyReport(unittest.TestCase):
    def test_report_lines(self):
        res = {"open_incidents": 38, "open_changes": 12, "open_tasks": 0,
               "open_work_orders": 10, "open_problems": 8}
        lines = [f"- {k.replace('_', ' ')}: {res[k]}"
                 for k in ("open_incidents", "open_changes", "open_tasks",
                           "open_work_orders", "open_problems") if k in res]
        self.assertEqual(len(lines), 5)
        self.assertTrue(all(l.startswith("- ") for l in lines))


class TestServiceHygiene(unittest.TestCase):
    def test_no_secrets_in_service(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "restate_neuralosd_service.py")
        src = open(path).read()
        for banned in ("password", "api_key", "Authorization"):
            self.assertNotIn(banned, src,
                             f"service file must not embed secrets: {banned}")

    def test_think_not_used_in_service(self):
        """The service wraps neuralosd asks (code gate); model calls belong
        to the reason loop, not this service."""
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "restate_neuralosd_service.py")
        src = open(path).read()
        self.assertNotIn("think", src.lower())


if __name__ == "__main__":
    unittest.main()
