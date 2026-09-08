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
 *   PATH      the exposed value reaches an assertion   as data OR as control
 *   CONTROL   nothing on that path closes the choice   sort, LinkedHashMap, JSONAssert
 *
 * A test is flagged only when HAZARD and EXPOSURE and PATH and not CONTROL. All
 * four are emitted separately so an ablation can show what each contributes over
 * a plain hazard lexicon.
 *
 * WHY size() AND get(key) ARE NOT "CONTROL"
 * -----------------------------------------
 * An earlier version put size(), get(key) and containsKey() in CONTROL, on the
 * reasoning that they make the verdict order-independent. That conflated two
 * different things. Those operations do not *close* a choice; they never
 * *expose* it. Since the verdict is HAZARD and EXPOSURE and not CONTROL, simply
 * leaving them out of EXPOSURE gives the same answer for the right reason — and
 * the mining agrees: call:get scores z 0.96 as a control, no support at all.
 *
 * WHERE THE CONTROL VOCABULARY COMES FROM
 * ---------------------------------------
 * Not from guesswork. It is the fix-derived vocabulary in
 * docs/investigation3/fix_vocabulary_matched.csv, mined by log-odds from 609
 * real flakiness repairs against 1,217 background commits from the same
 * projects. See LEXICON.md. The hazard vocabulary stays typed and hand-specified
 * because the same mining is confounded for hazards: a fix commit touches a test
 * by construction, so type:Test outranks new:HashMap.
 *
 * PATH IS DATA *AND* CONTROL DEPENDENCE
 * -------------------------------------
 * Walking back only from assertion arguments is pure data dependence. It misses
 * `if (map.keySet().iterator().next().equals("a")) fail();`, where the choice
 * decides *whether* the assertion runs rather than what it compares. Measured on
 * FlakeBench: 18.9% of flaky test bodies have an assertion nested under control
 * flow, against 7.4% of non-flaky ones. So the walk is also seeded from the
 * conditions of every enclosing if / loop / switch.
 *
 * INTERPROCEDURAL, BOUNDED
 * ------------------------
 * The walk follows field reads to their initialisers and to assignments made in
 * fixtures, and follows calls into callee bodies to a bounded depth. Without
 * that it stops at the edge of the test method, which is why only 28% of flaky
 * unordered-collections tests had a hazard visible at all. In `snippets` mode
 * there is no surrounding class, so this degrades to intraprocedural silently —
 * `interproc_used` records whether it actually contributed.
 */

import spoon.Launcher;
import spoon.reflect.code.*;
import spoon.reflect.declaration.*;
import spoon.reflect.reference.CtExecutableReference;
import spoon.reflect.reference.CtFieldReference;
import spoon.reflect.reference.CtTypeReference;
import spoon.reflect.visitor.filter.TypeFilter;
import spoon.support.compiler.VirtualFile;

import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;
import java.util.regex.Pattern;

public class SliceAnalysis {

    // ---- hazards: typed, narrow, hand-specified (see header)
    static final Pattern HAZARD_TYPE = Pattern.compile(
            "java\\.util\\.(HashMap|HashSet|Hashtable|WeakHashMap|IdentityHashMap)"
            + "|com\\.google\\.common\\.collect\\.(HashMultimap|HashMultiset)");

    static final Set<String> HAZARD_CALLS = new HashSet<>(Arrays.asList(
            "getDeclaredMethods", "getDeclaredFields", "getMethods", "getFields",
            "listFiles", "list", "listStatus", "newHashMap", "newHashSet",
            "keySet", "values", "entrySet"));

    // ---- exposure: operations that reveal the order of an unordered container.
    // Note what is absent: size, isEmpty, get(key), containsKey. Those read the
    // container without ever revealing its order, so they are not exposures and
    // the verdict correctly stays unflagged.
    static final Set<String> EXPOSURE = new HashSet<>(Arrays.asList(
            "iterator", "toArray", "toString", "stream", "forEach",
            "next", "findFirst", "collect", "join",
            "toJSONString", "writeValueAsString"));

    // ---- control: derived from 609 real repairs, not guessed.
    // z-scores from fix_vocabulary_matched.csv are in the comments.
    static final Set<String> CONTROL_CALLS = new HashSet<>(Arrays.asList(
            "sort",             // 6.43   50 fix / 14 background
            "comparing",        // 4.70   25 / 5
            "compareTo",        // 2.62   12 / 9
            "readTree",         // 3.57   20 / 12   parse JSON, then compare as a tree
            "containsAll",      // 2.66    9 / 3
            // Order-insensitive assertion forms. These are a Cut: the developer
            // wrote the check so the verdict cannot depend on order, even though
            // the container was iterated. Dropping them on the theory that they
            // were merely "non-exposing reads" was wrong, and measurably so --
            // non-flaky false positives went 29 -> 106 and lift 11.6x -> 5.0x.
            "contains", "containsKey", "containsEntry", "containsValue",
            "containsInAnyOrder", "containsExactlyInAnyOrder", "hasSize",
            "assertEquals"));   // only when the receiver is JSONAssert, see CONTROL_TYPE

    static final Pattern CONTROL_TYPE = Pattern.compile(
            "java\\.util\\.(TreeMap|TreeSet|LinkedHashMap|LinkedHashSet)"   // 8.12 / 3.70
            + "|org\\.skyscreamer\\.jsonassert\\.JSONAssert"                // 5.81, 32 fix / 0 bg
            + "|JSONAssert|JSONException"                                   // 4.39
            + "|com\\.google\\.common\\.collect\\.Immutable");

    // pinning serialisation order at the type — the "Own" repair move
    static final Pattern CONTROL_ANNOT = Pattern.compile("JsonPropertyOrder");  // 4.11, 16 / 0

    static final Pattern ASSERT_NAME = Pattern.compile(
            "^(assert\\w*|verify|expect\\w*|fail|should\\w*)$");

    // controls applied in place: they close the choice without producing a value,
    // so the backward walk needs them recorded per variable rather than per expression
    static final Set<String> MUTATING_CONTROL = new HashSet<>(Arrays.asList("sort"));

    static final Pattern FIXTURE_ANNOT = Pattern.compile(
            "^(Before|After)(Class|All|Each)?$|^(Class)?Rule$");

    // Feature toggles, so control dependence and the interprocedural walk can be
    // ablated independently of the vocabulary change. Both default on.
    //   -Dslice.controldep=false   -Dslice.interproc=false   -Dslice.legacyControl=true
    static final boolean USE_CONTROL_DEP =
            !"false".equals(System.getProperty("slice.controldep"));
    static final boolean USE_INTERPROC =
            !"false".equals(System.getProperty("slice.interproc"));
    static final boolean LEGACY_CONTROL =
            "true".equals(System.getProperty("slice.legacyControl"));

    /** The pre-mining control set, kept only so the change can be measured. */
    static final Set<String> LEGACY_CONTROL_CALLS = new HashSet<>(Arrays.asList(
            "sort", "sorted", "size", "isEmpty", "contains", "containsKey",
            "containsAll", "containsInAnyOrder", "containsExactlyInAnyOrder",
            "hasSize", "get", "getOrDefault"));

    static boolean isControlCall(String n, String declaring) {
        if (LEGACY_CONTROL) return LEGACY_CONTROL_CALLS.contains(n);
        if (!CONTROL_CALLS.contains(n)) return false;
        // assertEquals closes nothing unless the receiver is JSONAssert
        return !n.equals("assertEquals") || CONTROL_TYPE.matcher(declaring).find();
    }

    static final int MAX_EXPR_DEPTH = 6;
    static final int MAX_CALL_DEPTH = 2;

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
        // noclasspath mode tolerates every unresolved name inside it. There is no
        // surrounding class here, so the interprocedural steps find nothing.
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

        Walk w = new Walk();
        w.collectLocals(m);
        w.owner = USE_INTERPROC ? m.getDeclaringType() : null;
        if (w.owner != null) {
            w.collectFieldsAndFixtures(w.owner);
            // the class itself may carry @JsonPropertyOrder, which pins order for
            // everything it serialises
            for (CtAnnotation<?> a : w.owner.getAnnotations()) {
                if (a.getAnnotationType() != null
                        && CONTROL_ANNOT.matcher(a.getAnnotationType().getSimpleName()).find()) {
                    w.control = true;
                }
            }
        }

        // a plain hazard flag, so the ablation keeps its baseline
        boolean hazardAnywhere = false;
        for (CtConstructorCall<?> c : m.getElements(new TypeFilter<>(CtConstructorCall.class))) {
            if (c.getType() != null && HAZARD_TYPE.matcher(c.getType().toString()).find()) {
                hazardAnywhere = true;
            }
        }
        for (CtInvocation<?> inv : m.getElements(new TypeFilter<>(CtInvocation.class))) {
            if (name(inv) != null && HAZARD_CALLS.contains(name(inv))) hazardAnywhere = true;
        }

        int assertions = 0, guarded = 0;
        for (CtInvocation<?> inv : m.getElements(new TypeFilter<>(CtInvocation.class))) {
            String n = name(inv);
            if (n == null || !ASSERT_NAME.matcher(n).matches()) continue;
            assertions++;

            // data dependence: what the assertion compares
            for (CtExpression<?> arg : inv.getArguments()) w.visit(arg, 0, 0);
            // assertThat(x).isEqualTo(y) — the subject sits on the receiver chain
            if (inv.getTarget() != null) w.visit(inv.getTarget(), 0, 0);

            // control dependence: what decides whether this assertion runs at all
            boolean anyGuard = false;
            for (CtExpression<?> cond : (USE_CONTROL_DEP ? guards(inv)
                                         : Collections.<CtExpression<?>>emptyList())) {
                anyGuard = true;
                boolean before = w.hazard && w.exposure;
                w.visit(cond, 0, 0);
                if (!before && w.hazard && w.exposure) w.viaControlDep = true;
            }
            if (anyGuard) guarded++;
        }

        boolean flag = w.hazard && w.exposure && !w.control;
        StringBuilder b = new StringBuilder();
        b.append("{\"key\":\"").append(esc(key)).append("\",\"parsed\":true");
        b.append(",\"assertions\":").append(assertions);
        b.append(",\"guarded_assertions\":").append(guarded);
        b.append(",\"hazard_anywhere\":").append(hazardAnywhere);
        b.append(",\"hazard_on_path\":").append(w.hazard);
        b.append(",\"exposure\":").append(w.exposure);
        b.append(",\"control\":").append(w.control);
        b.append(",\"control_dep_used\":").append(w.viaControlDep);
        b.append(",\"interproc_used\":").append(w.viaInterproc);
        b.append(",\"flag\":").append(flag);
        b.append("}");
        return b.toString();
    }

    /**
     * The conditions of every if / loop / switch enclosing this element.
     *
     * These are what the assertion is control-dependent on: if an unordered value
     * decides whether the assertion executes, the verdict depends on it just as
     * surely as if it were compared.
     */
    static List<CtExpression<?>> guards(CtElement e) {
        List<CtExpression<?>> out = new ArrayList<>();
        CtElement cur = e;
        for (int i = 0; i < 12 && cur != null; i++) {
            CtElement p;
            try {
                p = cur.getParent();
            } catch (Exception ex) {
                break;
            }
            if (p == null || p instanceof CtMethod) break;
            if (p instanceof CtIf) {
                out.add(((CtIf) p).getCondition());
            } else if (p instanceof CtWhile) {
                out.add(((CtWhile) p).getLoopingExpression());
            } else if (p instanceof CtDo) {
                out.add(((CtDo) p).getLoopingExpression());
            } else if (p instanceof CtFor) {
                out.add(((CtFor) p).getExpression());
            } else if (p instanceof CtForEach) {
                out.add(((CtForEach) p).getExpression());
            } else if (p instanceof CtSwitch) {
                out.add(((CtSwitch<?>) p).getSelector());
            } else if (p instanceof CtConditional) {
                out.add(((CtConditional<?>) p).getCondition());
            }
            cur = p;
        }
        out.removeIf(Objects::isNull);
        return out;
    }

    /** Backward walk over everything the verdict depends on. */
    static class Walk {
        final Map<String, List<CtExpression<?>>> defs = new HashMap<>();
        final Map<String, String> declaredType = new HashMap<>();
        final Set<String> seenVar = new HashSet<>();
        final Set<String> controlledVars = new HashSet<>();
        final Set<String> seenMethod = new HashSet<>();
        CtType<?> owner;
        boolean hazard, exposure, control, viaControlDep, viaInterproc;

        /**
         * Controls applied by mutation rather than by assignment.
         *
         * `java.util.Collections.sort(keys)` and `keys.sort(cmp)` close the choice
         * without producing a new value, so a backward walk from the assertion
         * never encounters them — it follows `keys` to its definition and finds
         * only the hash container. Record which variables have been sorted in
         * place, and treat a read of one as controlled.
         */
        void collectMutatingControls(CtExecutable<?> m) {
            for (CtInvocation<?> inv : m.getElements(new TypeFilter<>(CtInvocation.class))) {
                String n = name(inv);
                if (n == null || !MUTATING_CONTROL.contains(n)) continue;
                List<CtExpression<?>> operands = new ArrayList<>(inv.getArguments());
                if (inv.getTarget() != null) operands.add(inv.getTarget());
                for (CtExpression<?> op : operands) {
                    if (op instanceof CtVariableRead) {
                        controlledVars.add(((CtVariableRead<?>) op).getVariable().getSimpleName());
                    }
                }
            }
        }

        void collectLocals(CtExecutable<?> m) {
            collectMutatingControls(m);
            for (CtLocalVariable<?> v : m.getElements(new TypeFilter<>(CtLocalVariable.class))) {
                if (v.getDefaultExpression() != null) {
                    defs.computeIfAbsent(v.getSimpleName(), k -> new ArrayList<>())
                            .add(v.getDefaultExpression());
                }
                if (v.getType() != null) declaredType.put(v.getSimpleName(), v.getType().toString());
            }
            for (CtAssignment<?, ?> a : m.getElements(new TypeFilter<>(CtAssignment.class))) {
                if (a.getAssigned() instanceof CtVariableWrite && a.getAssignment() != null) {
                    String n = ((CtVariableWrite<?>) a.getAssigned()).getVariable().getSimpleName();
                    defs.computeIfAbsent(n, k -> new ArrayList<>()).add(a.getAssignment());
                }
            }
        }

        /**
         * Fields of the test class and its superclasses, plus anything a fixture
         * assigns to them. A field seeded in @Before is the commonest way for a
         * hazard to reach a test without appearing in its body.
         */
        void collectFieldsAndFixtures(CtType<?> type) {
            for (CtType<?> t = type; t != null; ) {
                for (CtField<?> f : t.getFields()) {
                    if (f.getDefaultExpression() != null) {
                        defs.computeIfAbsent(f.getSimpleName(), k -> new ArrayList<>())
                                .add(f.getDefaultExpression());
                    }
                    if (f.getType() != null) {
                        declaredType.put(f.getSimpleName(), f.getType().toString());
                    }
                }
                for (CtMethod<?> fx : t.getMethods()) {
                    if (!isFixture(fx) || fx.getBody() == null) continue;
                    collectMutatingControls(fx);
                    for (CtAssignment<?, ?> a
                            : fx.getElements(new TypeFilter<>(CtAssignment.class))) {
                        if (a.getAssigned() instanceof CtVariableWrite && a.getAssignment() != null) {
                            String n = ((CtVariableWrite<?>) a.getAssigned())
                                    .getVariable().getSimpleName();
                            defs.computeIfAbsent(n, k -> new ArrayList<>()).add(a.getAssignment());
                        }
                    }
                }
                CtTypeReference<?> sup = null;
                try {
                    sup = t.getSuperclass();
                } catch (Exception ignored) {
                }
                t = sup == null ? null : sup.getTypeDeclaration();
            }
        }

        static boolean isFixture(CtMethod<?> m) {
            for (CtAnnotation<?> a : m.getAnnotations()) {
                if (a.getAnnotationType() != null
                        && FIXTURE_ANNOT.matcher(a.getAnnotationType().getSimpleName()).find()) {
                    return true;
                }
            }
            return false;
        }

        void visit(CtExpression<?> e, int depth, int callDepth) {
            if (e == null || depth > MAX_EXPR_DEPTH) return;

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
                CtExecutableReference<?> r = inv.getExecutable();
                String declaring = (r != null && r.getDeclaringType() != null)
                        ? r.getDeclaringType().toString() : "";

                if (n != null) {
                    if (HAZARD_CALLS.contains(n)) hazard = true;
                    if (EXPOSURE.contains(n)) exposure = true;
                    // assertEquals only counts as control on a JSONAssert receiver;
                    // plain Assert.assertEquals closes nothing
                    if (isControlCall(n, declaring)) control = true;
                }
                if (CONTROL_TYPE.matcher(declaring).find()) control = true;

                visit(inv.getTarget(), depth + 1, callDepth);
                for (CtExpression<?> a : inv.getArguments()) visit(a, depth + 1, callDepth);
                descendInto(r, callDepth);
                return;
            }
            if (e instanceof CtFieldRead) {
                CtFieldReference<?> fr = ((CtFieldRead<?>) e).getVariable();
                if (fr != null) {
                    checkVariable(fr.getSimpleName(), depth, callDepth);
                    CtField<?> decl = fr.getFieldDeclaration();
                    if (decl != null) {
                        for (CtAnnotation<?> a : decl.getAnnotations()) {
                            if (a.getAnnotationType() != null && CONTROL_ANNOT
                                    .matcher(a.getAnnotationType().getSimpleName()).find()) {
                                control = true;
                            }
                        }
                        if (decl.getDefaultExpression() != null) {
                            viaInterproc = true;
                            visit(decl.getDefaultExpression(), depth + 1, callDepth);
                        }
                    }
                }
                return;
            }
            if (e instanceof CtVariableRead) {
                checkVariable(((CtVariableRead<?>) e).getVariable().getSimpleName(),
                              depth, callDepth);
                return;
            }
            for (CtExpression<?> sub : e.getElements(new TypeFilter<>(CtExpression.class))) {
                if (sub != e) visit(sub, depth + 1, callDepth);
            }
        }

        void checkVariable(String n, int depth, int callDepth) {
            if (controlledVars.contains(n)) control = true;
            String dt = declaredType.get(n);
            if (dt != null) {
                if (HAZARD_TYPE.matcher(dt).find()) hazard = true;
                if (CONTROL_TYPE.matcher(dt).find()) control = true;
            }
            if (!seenVar.add(n)) return;
            for (CtExpression<?> d : defs.getOrDefault(n, Collections.emptyList())) {
                visit(d, depth + 1, callDepth);
            }
        }

        /**
         * Follow a call into the method it invokes.
         *
         * Bounded by MAX_CALL_DEPTH and a visited set: the point is to reach
         * `assertEquals(expected, service.getNames())`, where the hash container
         * lives inside the callee, not to build a whole-program analysis.
         */
        void descendInto(CtExecutableReference<?> r, int callDepth) {
            if (!USE_INTERPROC || r == null || callDepth >= MAX_CALL_DEPTH) return;
            CtExecutable<?> decl;
            try {
                decl = r.getDeclaration();
            } catch (Exception e) {
                return;
            }
            if (decl == null || decl.getBody() == null) return;
            String sig = (r.getDeclaringType() == null ? "?" : r.getDeclaringType().toString())
                    + "#" + r.getSimpleName();
            if (!seenMethod.add(sig)) return;
            viaInterproc = true;

            // the callee's own locals, so its returns can be traced
            Walk inner = new Walk();
            inner.collectLocals(decl);
            for (Map.Entry<String, List<CtExpression<?>>> en : inner.defs.entrySet()) {
                defs.computeIfAbsent(en.getKey(), k -> new ArrayList<>()).addAll(en.getValue());
            }
            declaredType.putAll(inner.declaredType);

            for (CtReturn<?> ret : decl.getBody().getElements(new TypeFilter<>(CtReturn.class))) {
                visit(ret.getReturnedExpression(), 0, callDepth + 1);
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
