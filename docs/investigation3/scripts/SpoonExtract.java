/*
 * SpoonExtract — dump every declaration Spoon can see in a set of source roots.
 *
 *   java -cp <spoon classpath> SpoonExtract.java <out.json> <srcRoot> [srcRoot ...]
 *
 * Runs in noclasspath mode, so it needs sources only — never a successful build.
 * That is the whole point: coverage requires a working build, Spoon does not, so
 * the static half of the analysis stays available on build points that fail.
 *
 * Output is a JSON array. One object per declaration:
 *
 *   kind              method | constructor | field | static_init | instance_init
 *   qualified_class   a.b.Outer$Inner   ($-separated, matching JaCoCo)
 *   method            foo | <init> | <clinit> | <initblock> | the field's name
 *   descriptor        (Ljava/lang/String;I)V for an executable, Ljava/util/Map;
 *                     for a field. Method descriptors always start with '(' and
 *                     field descriptors never do, so the two cannot collide in a
 *                     (class, descriptor) index.
 *   superclass        qualified name of the declaring type's superclass, and
 *   interfaces        its interfaces — without these, a fixture or field declared
 *                     on an abstract test base class cannot be attributed to the
 *                     test that inherits it
 *   annotations       simple names, e.g. ["Before"] — the only reliable way to
 *                     tell a fixture from a helper
 *   is_anonymous      true for a.b.Outer$1 — these carry the concurrency evidence
 *                     and are exactly what the NOD-Test-Repair extractor dropped
 *   invokes           qualified targets called from the body, for later callee work
 *   body / raw_body   Spoon pretty-print (types fully qualified) and the original
 *                     source text. Both are kept because they are not
 *                     interchangeable: `body` invents tokens by qualifying types
 *                     and drops everything on the declaration line, so a
 *                     token-level feature must read `raw_body`.
 *
 * WHY FIELDS AND INITIALISER BLOCKS ARE HERE
 * ------------------------------------------
 * An earlier version emitted methods and constructors only. That silently lost
 * the two places where order-dependence is usually declared: the static field
 * (`private static final Map<String,X> CACHE = new HashMap<>()`) and the static
 * initialiser block. Both are emitted now; static blocks are merged into one
 * <clinit> record per class so the record joins directly against the <clinit>
 * JaCoCo reports, which until now could only be classified as synthetic.
 *
 * Type variables erase to java.lang.Object rather than to their first bound. That
 * is an approximation; it only matters for generic methods, and the join falls back
 * to (class, method, arity) when a descriptor does not match.
 */

import spoon.Launcher;
import spoon.reflect.CtModel;
import spoon.reflect.code.CtInvocation;
import spoon.reflect.code.CtNewClass;
import spoon.reflect.cu.SourcePosition;
import spoon.reflect.declaration.*;
import spoon.reflect.reference.CtArrayTypeReference;
import spoon.reflect.reference.CtExecutableReference;
import spoon.reflect.reference.CtTypeParameterReference;
import spoon.reflect.reference.CtTypeReference;

import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;

public class SpoonExtract {

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("usage: SpoonExtract <out.json> <srcRoot> [srcRoot ...]");
            System.exit(2);
        }
        String out = args[0];

        Launcher launcher = new Launcher();
        launcher.getEnvironment().setNoClasspath(true);          // sources only
        launcher.getEnvironment().setIgnoreSyntaxErrors(true);   // survive one bad file
        launcher.getEnvironment().setCommentEnabled(true);
        launcher.getEnvironment().setComplianceLevel(11);
        launcher.getEnvironment().setLevel("OFF");

        int roots = 0;
        for (int i = 1; i < args.length; i++) {
            if (Files.isDirectory(Paths.get(args[i]))) {
                launcher.addInputResource(args[i]);
                roots++;
            }
        }
        if (roots == 0) {
            Files.write(Paths.get(out), "[]".getBytes(StandardCharsets.UTF_8));
            System.out.println("methods=0 fields=0 inits=0 roots=0");
            return;
        }

        launcher.buildModel();
        CtModel model = launcher.getModel();

        List<String> records = new ArrayList<>();
        Set<CtType<?>> seen = Collections.newSetFromMap(new IdentityHashMap<>());
        for (CtType<?> type : model.getAllTypes()) {
            collect(type, records, seen);
        }

        try (PrintWriter w = new PrintWriter(out, "UTF-8")) {
            w.println("[");
            for (int i = 0; i < records.size(); i++) {
                w.print(records.get(i));
                w.println(i < records.size() - 1 ? "," : "");
            }
            w.println("]");
        }
        System.out.println("methods=" + nMethods + " fields=" + nFields
                + " inits=" + nInits + " roots=" + roots
                + " records=" + records.size());
    }

    private static int nMethods = 0, nFields = 0, nInits = 0;

    /**
     * Walk a type and every type nested inside it, anonymous ones included.
     *
     * The `seen` set is load-bearing: getElements() searches the whole subtree, so
     * without it an anonymous class declared inside a nested class is collected once
     * for the outer type and again for the nested one.
     */
    private static void collect(CtType<?> type, List<String> out, Set<CtType<?>> seen) {
        if (!seen.add(type)) return;

        // Static initialiser blocks are merged into a single <clinit> record: javac
        // merges them too, so this is the record that lines up with coverage.
        StringBuilder staticBody = new StringBuilder(), staticRaw = new StringBuilder();
        StringBuilder instBody = new StringBuilder(), instRaw = new StringBuilder();
        Set<String> staticInvokes = new LinkedHashSet<>(), instInvokes = new LinkedHashSet<>();
        int staticLine = -1, instLine = -1;

        for (CtTypeMember m : type.getTypeMembers()) {
            if (m instanceof CtMethod) {
                out.add(record(type, (CtMethod<?>) m));
                nMethods++;
            } else if (m instanceof CtConstructor) {
                out.add(record(type, (CtConstructor<?>) m));
                nMethods++;
            } else if (m instanceof CtField) {
                out.add(fieldRecord(type, (CtField<?>) m));
                nFields++;
            } else if (m instanceof CtAnonymousExecutable) {
                CtAnonymousExecutable ae = (CtAnonymousExecutable) m;
                boolean isStatic = ae.getModifiers().contains(ModifierKind.STATIC);
                StringBuilder b = isStatic ? staticBody : instBody;
                StringBuilder r = isStatic ? staticRaw : instRaw;
                b.append(bodyText(ae)).append("\n");
                r.append(rawText(ae)).append("\n");
                (isStatic ? staticInvokes : instInvokes).addAll(invokesOf(ae));
                int ln = lineOf(ae, true);
                if (isStatic) { if (staticLine < 0) staticLine = ln; }
                else { if (instLine < 0) instLine = ln; }
            } else if (m instanceof CtType) {
                collect((CtType<?>) m, out, seen);          // nested named type
            }
        }
        if (staticBody.length() > 0) {
            out.add(initRecord(type, "static_init", "<clinit>", staticInvokes,
                               staticBody.toString(), staticRaw.toString(), staticLine));
            nInits++;
        }
        if (instBody.length() > 0) {
            out.add(initRecord(type, "instance_init", "<initblock>", instInvokes,
                               instBody.toString(), instRaw.toString(), instLine));
            nInits++;
        }

        // Anonymous classes are not type members; they hang off the expressions that
        // create them. Missing these is how a coverage-driven extractor loses every
        // Runnable body, which is precisely the concurrency evidence.
        for (CtNewClass<?> nc : type.getElements(
                new spoon.reflect.visitor.filter.TypeFilter<>(CtNewClass.class))) {
            CtClass<?> anon = nc.getAnonymousClass();
            if (anon != null) {
                collect(anon, out, seen);
            }
        }
    }

    // ------------------------------------------------------------- record builders

    private static String record(CtType<?> owner, CtExecutable<?> exec) {
        String name;
        String retDesc;
        String kind;
        if (exec instanceof CtConstructor) {
            name = "<init>";
            retDesc = "V";
            kind = "constructor";
        } else {
            name = exec.getSimpleName();
            retDesc = desc(((CtMethod<?>) exec).getType());
            kind = "method";
        }

        StringBuilder params = new StringBuilder();
        StringBuilder sig = new StringBuilder();
        List<CtParameter<?>> ps = exec.getParameters();
        for (int i = 0; i < ps.size(); i++) {
            params.append(desc(ps.get(i).getType()));
            if (i > 0) sig.append(",");
            CtTypeReference<?> t = ps.get(i).getType();
            sig.append(t == null ? "?" : t.getQualifiedName());
        }

        Set<String> mods = new LinkedHashSet<>();
        for (ModifierKind k : ((CtModifiable) exec).getModifiers()) mods.add(k.toString());
        Set<String> annots = annotationsOf(exec);

        boolean isTest = annots.contains("Test")
                || annots.contains("ParameterizedTest")
                || annots.contains("TestTemplate")
                || name.startsWith("test");

        StringBuilder b = new StringBuilder();
        b.append("{");
        head(b, kind, owner);
        kv(b, "method", name);                      b.append(",");
        kv(b, "descriptor", "(" + params + ")" + retDesc); b.append(",");
        kv(b, "signature", name + "(" + sig + ")"); b.append(",");
        b.append("\"arity\":").append(ps.size()).append(",");
        b.append("\"is_test\":").append(isTest).append(",");
        tail(b, owner, exec, mods, annots, invokesOf(exec),
             bodyText(exec), rawText(exec));
        b.append("}");
        return b.toString();
    }

    /**
     * A field. `body` is the initialiser expression and `raw_body` the whole
     * declaration, which is what carries `static final`, the annotations and the
     * concrete type the author wrote.
     */
    private static String fieldRecord(CtType<?> owner, CtField<?> f) {
        Set<String> mods = new LinkedHashSet<>();
        for (ModifierKind k : f.getModifiers()) mods.add(k.toString());
        Set<String> annots = annotationsOf(f);

        String init = "";
        try {
            init = f.getDefaultExpression() == null ? "" : f.getDefaultExpression().toString();
        } catch (Exception ignored) {
        }
        Set<String> invokes = new LinkedHashSet<>();
        try {
            for (CtInvocation<?> inv : f.getElements(
                    new spoon.reflect.visitor.filter.TypeFilter<>(CtInvocation.class))) {
                CtExecutableReference<?> r = inv.getExecutable();
                if (r == null) continue;
                CtTypeReference<?> dt = r.getDeclaringType();
                invokes.add((dt == null ? "?" : dt.getQualifiedName()) + "#" + r.getSimpleName());
            }
        } catch (Exception ignored) {
        }

        CtTypeReference<?> t = f.getType();
        StringBuilder b = new StringBuilder();
        b.append("{");
        head(b, "field", owner);
        kv(b, "method", f.getSimpleName());          b.append(",");
        kv(b, "descriptor", desc(t));                b.append(",");
        kv(b, "signature", (t == null ? "?" : t.getQualifiedName())
                + " " + f.getSimpleName());          b.append(",");
        b.append("\"arity\":-1,");
        b.append("\"is_test\":false,");
        tailPos(b, owner, mods, annots, invokes, init, rawOf(f.getPosition()),
                lineOf(f, true), lineOf(f, false));
        b.append("}");
        return b.toString();
    }

    private static String initRecord(CtType<?> owner, String kind, String name,
                                     Set<String> invokes, String body, String raw,
                                     int line) {
        Set<String> mods = new LinkedHashSet<>();
        if ("static_init".equals(kind)) mods.add("static");
        StringBuilder b = new StringBuilder();
        b.append("{");
        head(b, kind, owner);
        kv(b, "method", name);                       b.append(",");
        kv(b, "descriptor", "()V");                  b.append(",");
        kv(b, "signature", name + "()");             b.append(",");
        b.append("\"arity\":0,");
        b.append("\"is_test\":false,");
        tailPos(b, owner, mods, new LinkedHashSet<>(), invokes, body, raw, line, -1);
        b.append("}");
        return b.toString();
    }

    // ------------------------------------------------------------------- fragments

    private static void head(StringBuilder b, String kind, CtType<?> owner) {
        kv(b, "kind", kind);                                          b.append(",");
        kv(b, "qualified_class", owner.getQualifiedName());           b.append(",");
        kv(b, "simple_class", owner.getSimpleName());                 b.append(",");
        CtTypeReference<?> sup = null;
        try {
            sup = owner.getSuperclass();
        } catch (Exception ignored) {
        }
        kv(b, "superclass", sup == null ? "" : sup.getQualifiedName()); b.append(",");
        Set<String> ifaces = new LinkedHashSet<>();
        try {
            for (CtTypeReference<?> i : owner.getSuperInterfaces()) {
                ifaces.add(i.getQualifiedName());
            }
        } catch (Exception ignored) {
        }
        arr(b, "interfaces", ifaces);                                 b.append(",");
        b.append("\"is_anonymous\":").append(owner.isAnonymous()).append(",");
    }

    private static void tail(StringBuilder b, CtType<?> owner, CtExecutable<?> exec,
                             Set<String> mods, Set<String> annots, Set<String> invokes,
                             String body, String raw) {
        tailPos(b, owner, mods, annots, invokes, body, raw,
                lineOf(exec, true), lineOf(exec, false));
    }

    private static void tailPos(StringBuilder b, CtType<?> owner,
                                Set<String> mods, Set<String> annots,
                                Set<String> invokes, String body, String raw,
                                int lineStart, int lineEnd) {
        String file = owner.getPosition() != null && owner.getPosition().getFile() != null
                ? owner.getPosition().getFile().getPath() : "";
        kv(b, "file", file);                        b.append(",");
        b.append("\"line_start\":").append(lineStart).append(",");
        b.append("\"line_end\":").append(lineEnd).append(",");
        arr(b, "modifiers", mods);                  b.append(",");
        arr(b, "annotations", annots);              b.append(",");
        arr(b, "invokes", invokes);                 b.append(",");
        kv(b, "body", body);                        b.append(",");
        kv(b, "raw_body", raw);
    }

    private static Set<String> annotationsOf(CtElement e) {
        Set<String> annots = new LinkedHashSet<>();
        try {
            for (CtAnnotation<?> a : e.getAnnotations()) {
                if (a.getAnnotationType() != null) {
                    annots.add(a.getAnnotationType().getSimpleName());
                }
            }
        } catch (Exception ignored) {
        }
        return annots;
    }

    private static Set<String> invokesOf(CtExecutable<?> exec) {
        Set<String> invokes = new LinkedHashSet<>();
        try {
            if (exec.getBody() != null) {
                for (CtInvocation<?> inv : exec.getBody()
                        .getElements(new spoon.reflect.visitor.filter.TypeFilter<>(CtInvocation.class))) {
                    CtExecutableReference<?> r = inv.getExecutable();
                    if (r == null) continue;
                    CtTypeReference<?> dt = r.getDeclaringType();
                    invokes.add((dt == null ? "?" : dt.getQualifiedName()) + "#" + r.getSimpleName());
                }
            }
        } catch (Exception ignored) {
        }
        return invokes;
    }

    private static String bodyText(CtExecutable<?> exec) {
        try {
            return exec.getBody() == null ? "" : exec.getBody().toString();
        } catch (Exception ignored) {
            // toString can throw on a partially-resolved model; an empty body is
            // better than losing the whole record
            return "";
        }
    }

    private static String rawText(CtElement e) {
        return rawOf(e == null ? null : e.getPosition());
    }

    private static String rawOf(SourcePosition sp) {
        try {
            if (sp != null && sp.isValidPosition() && sp.getCompilationUnit() != null) {
                String src = sp.getCompilationUnit().getOriginalSourceCode();
                int a = sp.getSourceStart(), b = sp.getSourceEnd();
                if (src != null && a >= 0 && b >= a && b < src.length()) {
                    return src.substring(a, b + 1);
                }
            }
        } catch (Exception ignored) {
        }
        return "";
    }

    private static int lineOf(CtElement e, boolean start) {
        try {
            SourcePosition p = e.getPosition();
            if (p != null && p.isValidPosition()) return start ? p.getLine() : p.getEndLine();
        } catch (Exception ignored) {
        }
        return -1;
    }

    /** JVM descriptor for a Spoon type reference. */
    private static String desc(CtTypeReference<?> t) {
        if (t == null) return "Ljava/lang/Object;";
        if (t instanceof CtArrayTypeReference) {
            return "[" + desc(((CtArrayTypeReference<?>) t).getComponentType());
        }
        if (t instanceof CtTypeParameterReference) {
            return "Ljava/lang/Object;";      // erasure approximation, see header
        }
        String q = t.getQualifiedName();
        switch (q) {
            case "void":    return "V";
            case "boolean": return "Z";
            case "byte":    return "B";
            case "char":    return "C";
            case "short":   return "S";
            case "int":     return "I";
            case "long":    return "J";
            case "float":   return "F";
            case "double":  return "D";
            default:        return "L" + q.replace('.', '/') + ";";
        }
    }

    private static void kv(StringBuilder b, String k, String v) {
        b.append("\"").append(k).append("\":\"").append(esc(v)).append("\"");
    }

    private static void arr(StringBuilder b, String k, Collection<String> vs) {
        b.append("\"").append(k).append("\":[");
        int i = 0;
        for (String v : vs) {
            if (i++ > 0) b.append(",");
            b.append("\"").append(esc(v)).append("\"");
        }
        b.append("]");
    }

    private static String esc(String s) {
        if (s == null) return "";
        StringBuilder o = new StringBuilder(s.length() + 16);
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"':  o.append("\\\""); break;
                case '\\': o.append("\\\\"); break;
                case '\n': o.append("\\n");  break;
                case '\r': o.append("\\r");  break;
                case '\t': o.append("\\t");  break;
                default:
                    if (c < 0x20) o.append(String.format("\\u%04x", (int) c));
                    else o.append(c);
            }
        }
        return o.toString();
    }
}
