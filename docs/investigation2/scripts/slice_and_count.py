"""Split each located test class into body and context slices, then count
lexicon token families in each slice.

Slices
  body        the test method under analysis, nothing else
  fields      class-level field declarations
  fixtures    @Before / @After / @BeforeClass / @AfterClass method bodies
  siblings    the other @Test methods in the same class
  helpers     non-test, non-fixture methods the body actually calls
  callees     production methods at depth 1, resolved by receiver type against
              the project's own src/main/java (see fetch_callees.py)
  context     fields + fixtures + siblings + helpers
  contextall  context + callees

Writes token_counts.csv, one row per (test, slice, category) with a family count
and a family-presence count.
"""
import os, re, json
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(BASE, "..", ".."))
SRC  = os.path.join(BASE, "sources")
JOIN = chr(10)

LEX = json.load(open(os.path.join(BASE, "lexicon.json"), encoding="utf-8"))
CATS = LEX["categories"]

def strip_noise(src):
    """Blank out comments and string/char contents, preserving line structure.

    A single left-to-right scan, because regex stripping mis-handles the common
    cases: a "/*" inside a string literal swallows the rest of the file, and a
    "//" inside a URL truncates a line of real code.
    """
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '"' or c == "'":
            q = c
            out.append(q)
            i += 1
            while i < n and src[i] != q:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == "\n":       # unterminated literal: bail out
                    break
                i += 1
            out.append(q)
            i += 1
        elif c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                if src[i] == "\n":
                    out.append("\n")
                i += 1
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def parse_methods(src):
    """Return [(kind, name, text)] and the class-level field lines."""
    lines = src.split("\n")
    methods, ann, i = [], [], 0
    # A method declaration: optional modifiers and inline annotations, a return
    # type, the name, an open paren. Package-private methods have no modifier,
    # so modifiers must be optional; control keywords are excluded by name.
    DECL = re.compile(
        r"^\s{1,8}(?:@\w+(?:\([^)]*\))?\s+)*"
        r"(?:(?:public|private|protected|static|final|abstract|synchronized|native|default)\s+)*"
        r"(?:<[^>]+>\s*)?"
        r"[\w.$]+(?:<[^;=]*?>)?(?:\[\])*\s+"
        r"(\w+)\s*\([^;]*$")
    KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "new",
                "else", "do", "try", "throw", "synchronized", "assert", "case"}
    # Strip leading annotations off a line so "@Test public void f()" still
    # parses; anything left over is tested as a declaration.
    LEAD_ANN = re.compile(r"^(\s*)((?:@\w+(?:\s*\([^)]*\))?\s*)+)")
    while i < len(lines):
        stripped = lines[i].strip()
        line = lines[i]
        if stripped.startswith("@"):
            m_ann = LEAD_ANN.match(line)
            ann.append(m_ann.group(2).strip())
            rest = line[m_ann.end():]
            if not rest.strip():
                i += 1; continue
            line = m_ann.group(1) + rest       # keep indent, drop annotations
            stripped = line.strip()
        m = DECL.match(line)
        if m and m.group(1) not in KEYWORDS and not stripped.startswith(("//", "*")):
            name, depth, j, started = m.group(1), 0, i, False
            while j < len(lines):
                depth += lines[j].count("{") - lines[j].count("}")
                if "{" in lines[j]:
                    started = True
                if started and depth <= 0:
                    break
                j += 1
            a = " ".join(ann)
            kind = ("test" if "@Test" in a else
                    "fixture" if re.search(r"@(Before|After)", a) else "helper")
            methods.append((kind, name, "\n".join(lines[i:j + 1]), i, j))
            ann = []; i = j + 1; continue
        ann = []; i += 1

    covered = set()
    for _, _, _, a, b in methods:
        covered.update(range(a, b + 1))
    fields = [lines[k] for k in range(len(lines))
              if k not in covered
              and re.search(r"^\s*(?:private|protected|public|static|final)[^(){}]*[\w>\]]\s+\w+\s*[;=]",
                            lines[k])
              and " class " not in lines[k]]
    return methods, "\n".join(fields)


def slices_for(src, method_name):
    methods, fields = parse_methods(src)
    body = ""
    for kind, name, text, _, _ in methods:
        if name == method_name:
            body = text
            break
    fixtures = "\n".join(t for k, n, t, _, _ in methods if k == "fixture")
    siblings = "\n".join(t for k, n, t, _, _ in methods
                         if k == "test" and n != method_name)
    # A list, not a dict: overloaded helpers share a name and must all be kept.
    helper_src = [(n, t) for k, n, t, _, _ in methods if k == "helper"]
    helpers = "\n".join(t for n, t in helper_src
                        if re.search(r"\b" + re.escape(n) + r"\s*\(", body))
    return {"body": body, "fields": fields, "fixtures": fixtures,
            "siblings": siblings, "helpers": helpers,
            "context": "\n".join([fields, fixtures, siblings, helpers])}


def count(text, cat):
    """(total family hits, distinct families present) for one category."""
    total, present = 0, 0
    for fam, pat in CATS[cat]["families"].items():
        n = len(re.findall(pat, text, re.M))
        total += n
        present += 1 if n else 0
    return total, present


def main(body_from_benchmark=True):
    """Count families per slice for every located test.

    body_from_benchmark: take the body slice from FlakeBench's own full_code
    column rather than from the cloned file. The two disagree for 37 of the 80
    tests because the pinned commit often holds a different version of the test
    than the one the benchmark shipped. The benchmark's copy is what the model
    actually consumed and what the label describes, so it is the honest body.
    Context still comes from the cloned file; there is no other source for it.
    """
    idx = pd.read_csv(os.path.join(SRC, "index.csv"))
    idx = idx[idx.file.notna()]
    bench = pd.read_csv(os.path.join(ROOT, "FlakeBench", "FlakeBench_dataset.csv"))
    bench_body = {(p, t): c for p, t, c in
                  zip(bench.project, bench.test_name, bench.full_code)}
    cal_dir = os.path.join(SRC, "_callees")
    cal_idx = {}
    cpath = os.path.join(cal_dir, "callees_index.csv")
    if os.path.exists(cpath):
        c = pd.read_csv(cpath)
        cal_idx = {(p, t): f for p, t, f in zip(c.project, c.test, c.file)}
    rows, substituted, with_callees = [], 0, 0
    for _, r in idx.iterrows():
        path = os.path.join(SRC, r.project, r.file)
        if not os.path.exists(path):
            continue
        src = strip_noise(open(path, encoding="utf-8", errors="replace").read())
        sl = slices_for(src, r.test.split(".")[-1])
        if body_from_benchmark:
            bb = bench_body.get((r.project, r.test))
            if bb:
                sl["body"] = strip_noise(bb)
                sl["context"] = JOIN.join(
                    [sl["fields"], sl["fixtures"],
                     sl["siblings"], sl["helpers"]])
                substituted += 1
        cf = cal_idx.get((r.project, r.test))
        cal = ""
        if cf and os.path.exists(os.path.join(cal_dir, cf)):
            cal = strip_noise(open(os.path.join(cal_dir, cf), encoding="utf-8",
                                   errors="replace").read())
            if cal.strip():
                with_callees += 1
        sl["callees"] = cal
        sl["contextall"] = JOIN.join([sl["context"], cal])
        if not sl["body"].strip():
            continue
        rec = dict(project=r.project, test=r.test, truth=r.truth, pred=r.pred,
                   wrong=bool(r.wrong), body_lines=len(sl["body"].split("\n")))
        for name, text in sl.items():
            for cat in CATS:
                t, p = count(text, cat)
                rec["%s__%s__n" % (name, cat)] = t
                rec["%s__%s__f" % (name, cat)] = p
            rec["%s__lines" % name] = len(text.split("\n")) if text.strip() else 0
        rows.append(rec)
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(BASE, "token_counts.csv"), index=False)
    print("wrote token_counts.csv:", len(out), "tests,",
          out.project.nunique(), "projects")
    if body_from_benchmark:
        print("body slice taken from FlakeBench full_code for", substituted, "tests")
    print("callees slice non-empty for", with_callees, "tests")
    print(out.groupby("project").agg(n=("test", "size"),
                                     wrong=("wrong", "sum")).to_string())


if __name__ == "__main__":
    main()
