#!/usr/bin/env python3
"""Minimal regression tests for the L1/L2 pipeline."""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "data", "sample_hits.jsonl")


def run():
    out = subprocess.run([sys.executable, os.path.join(ROOT, "analyze.py"), SAMPLE],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_header_counts():
    text = run()
    first = text.splitlines()[0]
    for token in ("records", "real", "decoy", "review"):
        assert token in first, first


def test_trap_directory_flagged():
    text = run()
    assert "/etc" in text


def test_frozen_memcached_flagged():
    text = run()
    assert "cross-host fingerprint" in text or "3151236" in text


if __name__ == "__main__":
    test_header_counts(); test_trap_directory_flagged(); test_frozen_memcached_flagged()
    print("3 tests passed")
