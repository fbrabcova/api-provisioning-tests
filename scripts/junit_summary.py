#!/usr/bin/env python3
"""Turn JUnit XML reports into a Markdown summary shown on the GitHub Actions run page.

Usage: python scripts/junit_summary.py results/*.xml
Writes to $GITHUB_STEP_SUMMARY when it exists, otherwise prints to the console.
The summary only reports results; it never changes the job's exit code.
"""

import os
import sys
import xml.etree.ElementTree as ET


def suites(root):
    return [root] if root.tag == "testsuite" else list(root.iter("testsuite"))


def case_status(case):
    if case.find("failure") is not None or case.find("error") is not None:
        return "failed"
    if case.find("skipped") is not None:
        return "skipped"
    return "passed"


def summarize(paths):
    rows, failed_cases, all_cases = [], [], []
    for path in paths:
        if not os.path.isfile(path):
            continue
        root = ET.parse(path).getroot()
        counts = {"passed": 0, "failed": 0, "skipped": 0}
        seconds = 0.0
        for suite in suites(root):
            for case in suite.iter("testcase"):
                status = case_status(case)
                counts[status] += 1
                seconds += float(case.get("time", 0) or 0)
                name = "%s :: %s" % (case.get("classname", ""), case.get("name", ""))
                all_cases.append((status, name))
                if status == "failed":
                    problem = case.find("failure")
                    if problem is None:
                        problem = case.find("error")
                    message = (problem.get("message") or problem.text or "").strip()
                    failed_cases.append((name, message.splitlines()[0][:200] if message else ""))
        rows.append((os.path.basename(path), counts, seconds))

    if not rows:
        return "## Test results\n\nNo JUnit reports were found.\n"

    icon = {"passed": "✅", "failed": "❌", "skipped": "⏭️"}
    total_failed = sum(c["failed"] for _, c, _ in rows)
    lines = ["## Test results %s" % ("✅" if total_failed == 0 else "❌"), "",
             "| Report | Passed | Failed | Skipped | Time |",
             "|---|---:|---:|---:|---:|"]
    for name, c, seconds in rows:
        lines.append("| %s | %d | %d | %d | %.1f s |"
                     % (name, c["passed"], c["failed"], c["skipped"], seconds))
    if failed_cases:
        lines += ["", "### Failed tests", ""]
        lines += ["- ❌ `%s` %s" % (name, msg) for name, msg in failed_cases]
    lines += ["", "<details><summary>All tests</summary>", ""]
    lines += ["- %s `%s`" % (icon[status], name) for status, name in all_cases]
    lines += ["", "</details>", ""]
    return "\n".join(lines)


def main(paths):
    text = summarize(paths)
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
