"""
Quality ratchet: fail if the current failing set grows beyond the committed baseline.
Usage:
  python scripts/check_failing_baseline.py --baseline tests/failing_baseline.txt --junit artifacts/test-baselines/pytest-after.xml
  python scripts/check_failing_baseline.py --baseline tests/failing_baseline.txt --text artifacts/test-baselines/pytest-after.txt
Exit: 0 = same or fewer failures; 1 = new failures; 2 = no junit/text file to compare.
"""
import argparse
import os
import sys
import xml.etree.ElementTree as ET


def classname_to_nodeid(classname: str, name: str) -> str:
    parts = classname.split(".")
    if len(parts) >= 3 and parts[-1][:1].isupper():
        filepath = "tests/" + "/".join(parts[1:-1]) + ".py"
        return f"{filepath}::{parts[-1]}::{name}"
    else:
        filepath = "tests/" + "/".join(parts[1:]) + ".py"
        return f"{filepath}::{name}"


def load_baseline(path: str) -> set:
    with open(path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def load_failures_from_junit(path: str) -> set:
    tree = ET.parse(path)
    root = tree.getroot()
    nodeids = []
    for suite in root.findall(".//testsuite"):
        for tc in suite.findall("testcase"):
            if tc.find("failure") is not None or tc.find("error") is not None:
                cls = tc.get("classname", "")
                name = tc.get("name", "")
                nodeids.append(classname_to_nodeid(cls, name))
    return set(nodeids)


def load_failures_from_text(path: str) -> set:
    nodeids = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("FAILED "):
                rest = line[7:].strip()
                if " - " in rest:
                    nodeid = rest.split(" - ", 1)[0].strip()
                else:
                    nodeid = rest
                if nodeid:
                    nodeids.append(nodeid)
    return set(nodeids)


def main():
    ap = argparse.ArgumentParser(description="Check failing tests against baseline.")
    ap.add_argument("--baseline", required=True, help="Path to tests/failing_baseline.txt")
    ap.add_argument("--junit", default=None, help="Path to JUnit XML (e.g. artifacts/test-baselines/pytest-after.xml)")
    ap.add_argument("--text", default=None, help="Path to pytest text output (e.g. artifacts/test-baselines/pytest-after.txt)")
    args = ap.parse_args()

    baseline = load_baseline(args.baseline)
    baseline_count = len(baseline)

    current: set = set()
    if args.junit:
        try:
            current = load_failures_from_junit(args.junit)
        except FileNotFoundError:
            pass
    if not current and args.text:
        try:
            current = load_failures_from_text(args.text)
        except FileNotFoundError:
            pass

    if not args.junit and not args.text:
        print("No --junit or --text path provided. Cannot load current failures.")
        sys.exit(2)
    junit_exists = args.junit and os.path.isfile(args.junit)
    text_exists = args.text and os.path.isfile(args.text)
    if not junit_exists and not text_exists:
        print("Neither JUnit nor text artifact file exists. Run pytest and write output to the given paths.")
        sys.exit(2)

    current_count = len(current)
    new_failures = current - baseline
    new_count = len(new_failures)

    print(f"baseline_count={baseline_count}, current_count={current_count}, new_count={new_count}")

    if new_count > 0:
        print("New failures (not in baseline):")
        for n in sorted(new_failures):
            print(f"  {n}")
        sys.exit(1)

    print("No new failures; same or fewer than baseline.")
    sys.exit(0)


if __name__ == "__main__":
    main()
