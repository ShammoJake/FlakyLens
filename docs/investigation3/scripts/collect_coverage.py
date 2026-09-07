"""Turn a JaCoCo coverage.xml into executed_methods.csv.

    python collect_coverage.py <coverage.xml> <out.csv>

Keeps every method with LINE counter covered > 0. Two differences from the
equivalent script in NOD-Test-Repair, both deliberate:

  * class names keep their `$`. That script split on `$` and so could never match
    an anonymous class such as PeerCache$1.run() — which is exactly where the
    concurrency evidence lives.
  * a `nesting` column records whether a class is top-level, nested or anonymous,
    so the loss can be measured instead of assumed.
"""
import csv
import re
import sys
import xml.etree.ElementTree as ET

ANON = re.compile(r"\$\d+$")


def nesting(class_name):
    if ANON.search(class_name):
        return "anonymous"
    return "nested" if "$" in class_name else "top-level"


def main(xml_path, out_path):
    root = ET.parse(xml_path).getroot()
    rows = []
    seen_methods = 0

    for package in root.findall("package"):
        pkg = package.get("name", "").replace("/", ".")
        for clazz in package.findall("class"):
            cname = clazz.get("name", "").replace("/", ".")   # keep $
            for method in clazz.findall("method"):
                seen_methods += 1
                mname = method.get("name")
                desc = method.get("desc")
                line = method.find("counter[@type='LINE']")
                if line is None:
                    continue                      # abstract or native: no lines
                covered = int(line.get("covered", 0))
                missed = int(line.get("missed", 0))
                total = covered + missed
                if covered <= 0:
                    continue
                branch = method.find("counter[@type='BRANCH']")
                rows.append([
                    pkg, cname, mname, desc, nesting(cname),
                    covered, total, f"{(covered / total * 100.0) if total else 0.0:.1f}",
                    int(branch.get("covered", 0)) if branch is not None else 0,
                    int(branch.get("missed", 0)) if branch is not None else 0,
                    method.get("line", ""),
                ])

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["package", "class", "method", "descriptor", "nesting",
                    "lines_covered", "lines_total", "coverage_pct",
                    "branches_covered", "branches_missed", "first_line"])
        w.writerows(rows)

    by_nesting = {}
    for r in rows:
        by_nesting[r[4]] = by_nesting.get(r[4], 0) + 1
    print(f"executed={len(rows)} of seen={seen_methods} "
          f"top-level={by_nesting.get('top-level', 0)} "
          f"nested={by_nesting.get('nested', 0)} "
          f"anonymous={by_nesting.get('anonymous', 0)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])
