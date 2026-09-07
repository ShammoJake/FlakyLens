/*
 * SliceAnalysis — the tier-2 question, asked over a real AST.
 *
 *   java -cp <spoon cp> SliceAnalysis.java snippets <in.json> <out.json>
 *   java -cp <spoon cp> SliceAnalysis.java sources  <out.json> <srcRoot> [srcRoot ...]
 *
 * Tier 1 asks "does a hazard token appear anywhere in this text". That flags
 * roughly half of all non-flaky tests, because most tests touch a hash container
 * without their verdict depending on its iteration order. This asks the question
 * the definition of flakiness actually states — a verdict that depends on a
 * choice the test does not control — which needs four things, not one:
 *
 *   HAZARD    an uncontrolled choice exists            new java.util.HashMap<>()
 *   EXPOSURE  an operation that reveals the choice     .values(), .iterator()
 *             (a keyed .get(k) or .size() reads the container without ever
 *              exposing its order, and is why "reaches the assertion" alone
 *              is not enough)
 *   PATH      the exposed value reaches an assertion
 *   CONTROL   nothing on that path closes the choice   sort, TreeMap, inAnyOrder
 *
 * A test is reported flaky-shaped only when HAZARD and EXPOSURE and PATH and not
 * CONTROL. The four are emitted separately so the ablation can show how much each
 * one contributes over a plain hazard lexicon.
 *
 * Two drivers, because there are two ways to get an AST and they cost very
 * differently:
 *
 *   snippets  parse the `body` text already stored in spoon_methods.json. Needs
 *             no checkout at all. The stored pretty-print carries fully
 *             qualified types, so `java.util.HashMap` versus `java.util.TreeMap`
 *             survives even without the surrounding class.
 *   sources   parse a real checkout, where fields, fixtures, the superclass and
 *             every helper method are visible too.
 *
 * Running both answers whether the cheap route loses anything that matters.
 */

import spoon.Launcher;
import spoon.reflect.code.*;
import spoon.reflect.declaration.*;
import spoon.reflect.reference.CtExecutableReference;
import spoon.reflect.reference.CtTypeReference;
import spoon.reflect.visitor.filter.TypeFilter;
import spoon.support.compiler.VirtualFile;

import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;
import java.util.regex.Pattern;

public class SliceAnalysis {

    // ---- the vocabulary. Narrow and typed, unlike the 38-family tier-1 lexicon.
    static final Pattern HAZARD_TYPE = Pattern.compile(
            "java\\.util\\.(HashMap|HashSet|Hashtable|WeakHashMap|IdentityHashMap)"
            + "|com\\.google\\.common\\.collect\\.(HashMultimap|HashMultiset)");

    static final Set<String> HAZARD_CALLS = new HashSet<>(Arrays.asList(
            "getDeclaredMethods", "getDeclaredFields", "getMethods", "getFields",
            "listFiles", "list", "listStatus", "newHashMap", "newHashSet",
            "keySet", "values", "entrySet"));

    // operations that reveal the order of an unordered container
    static final Set<String> EXPOSURE = new HashSet<>(Arrays.asList(
            "iterator", "toArray", "toString", "stream", "forEach", "keySet",
            "values", "entrySet", "next", "findFirst", "collect", "join"));

    // operations that close the choice: after these the verdict no longer depends on it
    static final Set<String> CONTROL_CALLS = new HashSet<>(Arrays.asList(
            "sort", "sorted", "size", "isEmpty", "contains", "containsKey",
            "containsAll", "containsInAnyOrder", "containsExactlyInAnyOrder",
            "hasSize", "get", "getOrDefault"));

    static final Pattern CONTROL_TYPE = Pattern.compile(
            "java\\.util\\.(TreeMap|TreeSet|LinkedHashMap|LinkedHashSet)"
            + "|com\\.google\\.common\\.collect\\.Immutable");

    static final Pattern ASSERT_NAME = Pattern.compile(
            "^(assert\\w*|verify|expect\\w*|fail|should\\w*)$");

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("usage: SliceAnalysis snippets <in.json> <out.json>");
            System.err.println("       SliceAnalysis sources  <out.json> <srcRoot>...");
            System.exit(2);
        }
        if (args[0].equals("snippets")) {
            runSnippets(args[1], args[2]);
        } else {
            runSources(args);
        }
    }

    // ------------------------------------------------------------------ drivers

    /** Input: [{"key":"...","body":"{ ... }"}, ...] — bodies out of spoon_methods.json. */
    static void runSnippets(String in, String out) throws Exception {
        String text = new String(Files.readAllBytes(Paths.get(in)), "UTF-8");
        List<String[]> items = parsePairs(text);
        List<String> results = new ArrayList<>();
        for (String[] it : items) {
            String verdictJson;
            try {
                verdictJson = analyseSnippet(it[0], it[1]);
            } catch (Throwable t) {
                verdictJson = "{\"key\":\"" + esc(it[0]) + "\",\"parsed\":false}";
            }
            results.add(verdictJson);
        }
        write(out, results);
        System.out.println("snippets=" + items.size());
    }

    static String analyseSnippet(String key, String body) {
        // The stored body is a bare block. Wrap it so it is a compilable unit;
        // noclasspath mode tolerates every unresolved name inside it.
        String code = "class Synthetic__ { void t__() throws Throwable " + body + " }";
        Launcher l = new Launcher();
        l.getEnvironment().setNoClasspath(true);
        l.getEnvironment().setIgnoreSyntaxErrors(true);
        l.getEnvironment().setComplianceLevel(11);
        l.getEnvironment().setLevel("OFF");
        l.addInputResource(new VirtualFile(code, "Synthetic__.java"));
        l.buildModel();
        for (CtType<?> t : l.getModel().getAllTypes()) {
            for (CtMethod<?> m : t.getMethods()) {
                return verdict(key, m);
            }
        }
        return "{\"key\":\"" + esc(key) + "\",\"parsed\":false}";
    }

    /** Analyse every @Test method found in a set of source roots. */
    static void runSources(String[] args) throws Exception {
        Launcher l = new Launcher();
        l.getEnvironment().setNoClasspath(true);
        l.getEnvironment().setIgnoreSyntaxErrors(true);
        l.getEnvironment().setIgnoreDuplicateDeclarations(true);
        l.getEnvironment().setComplianceLevel(11);
        l.getEnvironment().setLevel("OFF");
        int roots = 0;
        for (int i = 2; i < args.length; i++) {
            if (Files.isDirectory(Paths.get(args[i]))) {
                l.addInputResource(args[i]);
                roots++;
            }
        }
        if (roots == 0) {
            write(args[1], Collections.<String>emptyList());
            System.out.println("methods=0 roots=0");
            return;
        }
        l.buildModel();
        List<String> results = new ArrayList<>();
        for (CtType<?> t : l.getModel().getAllTypes()) {
            for (CtMethod<?> m : t.getMethods()) {
                if (!isTest(m)) continue;
                try {
                    results.add(verdict(t.getQualifiedName() + "#" + m.getSimpleName(), m));
                } catch (Throwable ignored) {
                }
            }
        }
        write(args[1], results);
        System.out.println("methods=" + results.size() + " roots=" + roots);
    }

    static boolean isTest(CtMethod<?> m) {
        for (CtAnnotation<?> a : m.getAnnotations()) {
            if (a.getAnnotationType() != null
                    && a.getAnnotationType().getSimpleName().startsWith("Test")) return true;
        }
        return m.getSimpleName().startsWith("test");
    }

    // ------------------------------------------------------------- the analysis

    static String verdict(String key, CtMethod<?> m) {
        if (m.getBody() == null) {
            return "{\"key\":\"" + esc(key) + "\",\"parsed\":false}";
        }

        // definitions: local variable name -> the expressions ever assigned to it
        Map<String, List<CtExpression<?>>> defs = new HashMap<>();
        Map<String, String> declaredType = new HashMap<>();
        for (CtLocalVariable<?> v : m.getElements(new TypeFilter<>(CtLocalVariable.class))) {
            if (v.getDefaultExpression() != null) {
                defs.computeIfAbsent(v.getSimpleName(), k -> new ArrayList<>())
                        .add(v.getDefaultExpression());
            }
            if (v.getType() != null) {
                declaredType.put(v.getSimpleName(), v.getType().toString());
            }
        }
        for (CtAssignment<?, ?> a : m.getElements(new TypeFilter<>(CtAssignment.class))) {
            if (a.getAssigned() instanceof CtVariableWrite) {
                String n = ((CtVariableWrite<?>) a.getAssigned()).getVariable().getSimpleName();
                if (a.getAssignment() != null) {
                    defs.computeIfAbsent(n, k -> new ArrayList<>()).add(a.getAssignment());
                }
            }
        }

        // a plain hazard flag, so the ablation has its baseline
        boolean hazardAnywhere = false;
        for (CtConstructorCall<?> c : m.getElements(new TypeFilter<>(CtConstructorCall.class))) {
            if (c.getType() != null && HAZARD_TYPE.matcher(c.getType().toString()).find()) {
                hazardAnywhere = true;
            }
        }
        for (CtInvocation<?> inv : m.getElements(new TypeFilter<>(CtInvocation.class))) {
            if (name(inv) != null && HAZARD_CALLS.contains(name(inv))) hazardAnywhere = true;
        }

        // walk back from every assertion argument
        Walk w = new Walk(defs, declaredType);
        int assertions = 0;
        for (CtInvocation<?> inv : m.getElements(new TypeFilter<>(CtInvocation.class))) {
            String n = name(inv);
            if (n == null || !ASSERT_NAME.matcher(n).matches()) continue;
            assertions++;
            for (CtExpression<?> arg : inv.getArguments()) {
                w.visit(arg, 0);
            }
            // assertThat(x).isEqualTo(y): the subject sits on the receiver chain
            if (inv.getTarget() != null) w.visit(inv.getTarget(), 0);
        }

        boolean flag = w.hazard && w.exposure && !w.control;
        StringBuilder b = new StringBuilder();
        b.append("{\"key\":\"").append(esc(key)).append("\",\"parsed\":true");
        b.append(",\"assertions\":").append(assertions);
        b.append(",\"hazard_anywhere\":").append(hazardAnywhere);
        b.append(",\"hazard_on_path\":").append(w.hazard);
        b.append(",\"exposure\":").append(w.exposure);
        b.append(",\"control\":").append(w.control);
        b.append(",\"flag\":").append(flag);
        b.append("}");
        return b.toString();
    }

    /** Backward walk over the expressions that feed an assertion. */
    static class Walk {
        final Map<String, List<CtExpression<?>>> defs;
        final Map<String, String> declaredType;
        final Set<String> seen = new HashSet<>();
        boolean hazard, exposure, control;

        Walk(Map<String, List<CtExpression<?>>> d, Map<String, String> t) {
            defs = d;
            declaredType = t;
        }

        void visit(CtExpression<?> e, int depth) {
            if (e == null || depth > 6) return;

            if (e instanceof CtConstructorCall) {
                CtTypeReference<?> t = ((CtConstructorCall<?>) e).getType();
                if (t != null) {
                    if (HAZARD_TYPE.matcher(t.toString()).find()) hazard = true;
                    if (CONTROL_TYPE.matcher(t.toString()).find()) control = true;
                }
            }
            if (e instanceof CtInvocation) {
                CtInvocation<?> inv = (CtInvocation<?>) e;
                String n = name(inv);
                if (n != null) {
                    if (HAZARD_CALLS.contains(n)) hazard = true;
                    if (EXPOSURE.contains(n)) exposure = true;
                    if (CONTROL_CALLS.contains(n)) control = true;
                }
                CtExecutableReference<?> r = inv.getExecutable();
                if (r != null && r.getDeclaringType() != null
                        && CONTROL_TYPE.matcher(r.getDeclaringType().toString()).find()) {
                    control = true;
                }
                visit(inv.getTarget(), depth + 1);
                for (CtExpression<?> a : inv.getArguments()) visit(a, depth + 1);
                return;
            }
            if (e instanceof CtVariableRead) {
                String n = ((CtVariableRead<?>) e).getVariable().getSimpleName();
                String dt = declaredType.get(n);
                if (dt != null) {
                    if (HAZARD_TYPE.matcher(dt).find()) hazard = true;
                    if (CONTROL_TYPE.matcher(dt).find()) control = true;
                }
                if (seen.add(n)) {
                    for (CtExpression<?> d : defs.getOrDefault(n, Collections.emptyList())) {
                        visit(d, depth + 1);
                    }
                }
                return;
            }
            for (CtExpression<?> sub : e.getElements(new TypeFilter<>(CtExpression.class))) {
                if (sub != e) visit(sub, depth + 1);
            }
        }
    }

    static String name(CtInvocation<?> inv) {
        CtExecutableReference<?> r = inv.getExecutable();
        return r == null ? null : r.getSimpleName();
    }

    // ------------------------------------------------------------------ plumbing

    /** Minimal reader for [{"key":"..","body":".."}] written by the Python driver. */
    static List<String[]> parsePairs(String json) {
        List<String[]> out = new ArrayList<>();
        int i = 0;
        while (true) {
            int k = json.indexOf("\"key\":\"", i);
            if (k < 0) break;
            int ks = k + 7, ke = endOfString(json, ks);
            int bIdx = json.indexOf("\"body\":\"", ke);
            if (bIdx < 0) break;
            int bs = bIdx + 8, be = endOfString(json, bs);
            out.add(new String[]{unesc(json.substring(ks, ke)), unesc(json.substring(bs, be))});
            i = be;
        }
        return out;
    }

    static int endOfString(String s, int start) {
        int i = start;
        while (i < s.length()) {
            char c = s.charAt(i);
            if (c == '\\') { i += 2; continue; }
            if (c == '"') return i;
            i++;
        }
        return s.length();
    }

    static String unesc(String s) {
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c != '\\') { b.append(c); continue; }
            char d = s.charAt(++i);
            switch (d) {
                case 'n': b.append('\n'); break;
                case 'r': b.append('\r'); break;
                case 't': b.append('\t'); break;
                case 'u':
                    b.append((char) Integer.parseInt(s.substring(i + 1, i + 5), 16));
                    i += 4;
                    break;
                default: b.append(d);
            }
        }
        return b.toString();
    }

    static String esc(String s) {
        StringBuilder o = new StringBuilder();
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"': o.append("\\\""); break;
                case '\\': o.append("\\\\"); break;
                case '\n': o.append("\\n"); break;
                case '\r': o.append("\\r"); break;
                case '\t': o.append("\\t"); break;
                default: if (c < 0x20) o.append(String.format("\\u%04x", (int) c)); else o.append(c);
            }
        }
        return o.toString();
    }

    static void write(String out, List<String> records) throws Exception {
        try (PrintWriter w = new PrintWriter(out, "UTF-8")) {
            w.println("[");
            for (int i = 0; i < records.size(); i++) {
                w.print(records.get(i));
                w.println(i < records.size() - 1 ? "," : "");
            }
            w.println("]");
        }
    }
}
