"""Does the surrounding class context carry category signal the test body lacks?

Tests, weakest to strongest. The first three fit nothing and cannot overfit.

  A   Coverage      does the true category appear at all in each slice?
  B   Argmax proxy  score categories by distinct families present, take the
                    argmax, compare body-only against body+context.
  C   Flip analysis among the tests the shipped model got wrong, how many does
                    context move toward the truth, and how many away?
  D0  Validation    hand-rolled numpy model against scikit-learn on the same data
  D   Trained       scikit-learn multinomial logistic regression, repeated
                    stratified CV, macro-F1 with a scipy BCa bootstrap
  D2  Permutation   label-permutation null, which matters more than a confidence
                    interval at n=80
  E   Baselines     majority, uniform random, random tie-breaking
  E2  Binary        order dependency vs the rest; AUC and Mann-Whitney

Requires scikit-learn and scipy (both pinned in requirements.txt). Falls back to
a numpy implementation if they are absent, but the reported numbers are sklearn.
"""
import os, json, itertools
import numpy as np
import pandas as pd

try:
    import sklearn  # noqa: F401
    HAVE_SKLEARN = True
except ImportError:
    HAVE_SKLEARN = False
try:
    from scipy import stats as sps
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, ".."))
LEX  = json.load(open(os.path.join(BASE, "lexicon.json"), encoding="utf-8"))
CATS = list(LEX["categories"].keys())          # async conc time uc od
NAME = {"async": "async wait", "conc": "concurrency", "time": "time",
        "uc": "unordered collections", "od": "test order dependency"}
TRUTH2CAT = {"async": "async", "conc": "conc", "time": "time",
             "UC": "uc", "OD": "od"}
RNG = np.random.default_rng(20260904)
# Every entry keeps each slice as its OWN group of 5 features, except the two
# marked "merged", which pool four slices into one group. Comparing a separate
# entry against a merged one confounds *which* slices are used with *how many*
# feature groups there are, so both forms are reported.
CONFIGS = [("body only", ["body"]),
           ("body + fields", ["body", "fields"]),
           ("body + fixtures", ["body", "fixtures"]),
           ("body + siblings", ["body", "siblings"]),
           ("body + helpers", ["body", "helpers"]),
           ("body + callees", ["body", "callees"]),
           ("body + fields/fixtures", ["body", "fields", "fixtures"]),
           ("body + fld/fix + siblings", ["body", "fields", "fixtures", "siblings"]),
           ("all slices, separate", ["body", "fields", "fixtures", "siblings",
                                     "helpers", "callees"]),
           ("body + context (merged)", ["body", "context"]),
           ("body + contextall (merged)", ["body", "contextall"])]


def load():
    d = pd.read_csv(os.path.join(BASE, "token_counts.csv"))
    d["y"] = d.truth.map(TRUTH2CAT)
    d["yhat_model"] = d.pred.map(TRUTH2CAT)
    return d[d.y.notna()].reset_index(drop=True)


def presence(d, slices):
    """Family-presence matrix over the given slices, plus category sums."""
    cols = ["%s__%s__f" % (s, c) for s in slices for c in CATS]
    return d[cols].to_numpy(dtype=float), cols


def cat_score(d, slices):
    """score[i, c] = distinct families of category c present across slices."""
    out = np.zeros((len(d), len(CATS)))
    for j, c in enumerate(CATS):
        out[:, j] = sum(d["%s__%s__f" % (s, c)].to_numpy() for s in slices)
    return out


def argmax_pred(score):
    """Argmax with explicit tie reporting; ties resolved by lowest index."""
    best = score.max(axis=1, keepdims=True)
    ties = (score == best).sum(axis=1)
    return np.array(CATS)[score.argmax(axis=1)], ties


def macro_f1(y, yhat, labels=CATS):
    fs = []
    for c in labels:
        tp = np.sum((y == c) & (yhat == c))
        fp = np.sum((y != c) & (yhat == c))
        fn = np.sum((y == c) & (yhat != c))
        if tp + fp + fn == 0:
            continue
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        fs.append(2 * p * r / (p + r) if p + r else 0.0)
    return float(np.mean(fs)) if fs else 0.0


def rule(title):
    print("\n" + title)
    print("-" * len(title))


# ---------------------------------------------------------------- A coverage
def test_A(d):
    rule("A. Coverage of the TRUE category, by slice")
    slices = ["body", "fields", "fixtures", "siblings", "helpers", "callees",
              "context", "contextall"]
    rows = []
    for s in slices:
        hit = np.array([d.loc[i, "%s__%s__f" % (s, d.loc[i, "y"])] > 0
                        for i in d.index])
        rows.append(dict(slice=s,
                         all="%.0f%%" % (100 * hit.mean()),
                         model_wrong="%.0f%%" % (100 * hit[d.wrong.values].mean()),
                         model_right="%.0f%%" % (100 * hit[~d.wrong.values].mean())))
    print(pd.DataFrame(rows).to_string(index=False))

    body = np.array([d.loc[i, "body__%s__f" % d.loc[i, "y"]] > 0 for i in d.index])
    ctx  = np.array([d.loc[i, "context__%s__f" % d.loc[i, "y"]] > 0 for i in d.index])
    print("\nTrue category absent from body but present in context: %d of %d (%.0f%%)"
          % (np.sum(~body & ctx), len(d), 100 * np.mean(~body & ctx)))
    print("Absent from both:                                       %d (%.0f%%)"
          % (np.sum(~body & ~ctx), 100 * np.mean(~body & ~ctx)))
    return body, ctx


# ------------------------------------------------------------- B argmax proxy
def test_B(d):
    rule("B. Zero-training argmax over lexicon families")
    y = d.y.to_numpy()
    res = {}
    for tag, slices in CONFIGS:
        yhat, ties = argmax_pred(cat_score(d, slices))
        res[tag] = yhat
        print("%-24s accuracy %5.1f%%   macro-F1 %.3f   (%d ties)"
              % (tag, 100 * np.mean(yhat == y), macro_f1(y, yhat),
                 np.sum(ties > 1)))
    print("%-24s accuracy %5.1f%%   macro-F1 %.3f   <- the shipped model"
          % ("FlakyLens", 100 * np.mean(d.yhat_model.to_numpy() == y),
             macro_f1(y, d.yhat_model.to_numpy())))

    rule("B2. Per-category recall")
    rows = []
    for cat in CATS:
        m = y == cat
        if not m.any():
            continue
        rec = dict(category=NAME[cat], n=int(m.sum()))
        for tag, _ in CONFIGS:
            rec[tag.replace("body + ", "").replace("body only", "body")] =                 "%.0f%%" % (100 * np.mean(res[tag][m] == cat))
        rows.append(rec)
    print(pd.DataFrame(rows).to_string(index=False))
    return res


# ------------------------------------------------------------ C flip analysis
def test_C(d, res):
    rule("C. Effect on the tests the shipped model got wrong")
    y = d.y.to_numpy()
    b = res["body only"]
    w = d.wrong.values
    print("Among the %d misclassified tests, the body-only proxy already gets %d.\n"
          % (w.sum(), np.sum((b == y) & w)))
    for tag, _ in CONFIGS[1:]:
        c = res[tag]
        gained = (c == y) & (b != y) & w
        lost = (b == y) & (c != y) & w
        print("%s" % tag)
        print("  correct on misclassified tests    %d" % np.sum((c == y) & w))
        print("  gained over body only             %d" % gained.sum())
        print("  lost   against body only          %d" % lost.sum())
        for t, tr, pr in d.loc[gained, ["test", "truth", "pred"]].to_numpy():
            print("    + %-56s %s (model said %s)" % (t[:56], tr, pr))
        for t, tr, pr in d.loc[lost, ["test", "truth", "pred"]].to_numpy():
            print("    - %-56s %s" % (t[:56], tr))
        w2 = ~w
        print("  holds %d of the %d the model already gets right\n"
              % (np.sum((c == y) & w2), w2.sum()))


# ---------------------------------------------------------------- D trained
# Two implementations of the same model. sklearn is the one reported; the numpy
# one is kept so the two can be checked against each other (see validate_models).

def softmax_fit(X, y, classes, l2=1.0, iters=600, lr=0.5):
    """Multinomial logistic regression by gradient descent, class-balanced.

    Hand-rolled fallback, used only when scikit-learn is unavailable and by
    validate_models() as a cross-check on the sklearn result.
    """
    n, p = X.shape
    K = len(classes)
    Y = np.zeros((n, K))
    for j, c in enumerate(classes):
        Y[y == c, j] = 1.0
    w = np.zeros(n)
    for j, c in enumerate(classes):
        m = y == c
        w[m] = 1.0 / max(m.sum(), 1)
    w *= n / w.sum()
    W = np.zeros((p, K)); b = np.zeros(K)
    for _ in range(iters):
        Z = X @ W + b
        Z -= Z.max(axis=1, keepdims=True)
        P = np.exp(Z); P /= P.sum(axis=1, keepdims=True)
        G = (P - Y) * w[:, None]
        W -= lr * (X.T @ G / n + l2 / n * W)
        b -= lr * G.mean(axis=0)
    return W, b


def stratified_folds(y, k, rng):
    idx = {c: rng.permutation(np.flatnonzero(y == c)) for c in np.unique(y)}
    folds = [[] for _ in range(k)]
    for c, ids in idx.items():
        for i, v in enumerate(ids):
            folds[i % k].append(v)
    return [np.array(sorted(f)) for f in folds]


def logreg_cv_numpy(X, y, folds=5, repeats=20):
    classes, counts = np.unique(y, return_counts=True)
    k = int(min(folds, counts.min()))
    if k < 2:
        return None, None
    rng = np.random.default_rng(11)
    scores, oof = [], np.empty(len(y), dtype=object)
    for _ in range(repeats):
        for te in stratified_folds(y, k, rng):
            tr = np.setdiff1d(np.arange(len(y)), te)
            mu, sd = X[tr].mean(axis=0), X[tr].std(axis=0)
            sd[sd == 0] = 1.0
            W, b = softmax_fit((X[tr] - mu) / sd, y[tr], classes)
            p = classes[np.argmax(((X[te] - mu) / sd) @ W + b, axis=1)]
            scores.append(macro_f1(y[te], p))
            oof[te] = p
    return np.array(scores), oof


def _pipeline():
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=5000, C=1.0, class_weight="balanced"))


def logreg_cv(X, y, train_frac=0.625, n_splits=40):
    """Repeated stratified split, reported as mean macro-F1 over the splits.

    StratifiedShuffleSplit rather than RepeatedStratifiedKFold, because k-fold
    caps n_splits at the smallest class, and unordered collections has 2
    examples, which forces a 40/40 split. A shuffle split takes any ratio.

    train_frac=0.625 gives 50 train / 30 test. That is the largest training set
    that still leaves all five classes present in the test half: at 60/20
    unordered collections is sometimes absent from the test set and at 64/16 it
    always is, so macro-F1 would silently be computed over four classes.
    """
    if not HAVE_SKLEARN:
        return logreg_cv_numpy(X, y)
    from sklearn.model_selection import StratifiedShuffleSplit
    classes, counts = np.unique(y, return_counts=True)
    if counts.min() < 2:
        return None, None
    sss = StratifiedShuffleSplit(n_splits=n_splits, train_size=train_frac,
                                 random_state=11)
    scores, oof = [], np.empty(len(y), dtype=object)
    for tr, te in sss.split(X, y):
        clf = _pipeline().fit(X[tr], y[tr])
        p = clf.predict(X[te])
        scores.append(macro_f1(y[te], p))
        oof[te] = p
    return np.array(scores), oof


def permutation_p(X, y, n_perm=300):
    """Label-permutation null for the CV macro-F1. Matters more than a CI at n=80."""
    if not HAVE_SKLEARN:
        return None, None, None
    from sklearn.model_selection import StratifiedShuffleSplit
    cv = StratifiedShuffleSplit(n_splits=8, train_size=0.625, random_state=3)

    def score(yy):
        out = []
        for tr, te in cv.split(X, yy):
            out.append(macro_f1(yy[te], _pipeline().fit(X[tr], yy[tr]).predict(X[te])))
        return float(np.mean(out))

    obs = score(y)
    rng = np.random.default_rng(5)
    null = np.array([score(rng.permutation(y)) for _ in range(n_perm)])
    p = (1.0 + np.sum(null >= obs)) / (n_perm + 1.0)
    return obs, float(null.mean()), p


def validate_models(d):
    """Check the hand-rolled numpy model against scikit-learn on the same data."""
    if not HAVE_SKLEARN:
        print("scikit-learn unavailable; nothing to validate against."); return
    rule("D0. Hand-rolled numpy model vs scikit-learn")
    y = d.y.to_numpy()
    for tag, slices in CONFIGS:
        X, _ = presence(d, slices)
        a, _ = logreg_cv_numpy(X, y, repeats=5)
        b, _ = logreg_cv(X, y, n_splits=10)
        print("%-24s numpy %.3f   sklearn %.3f   diff %+.3f"
              % (tag, a.mean(), b.mean(), b.mean() - a.mean()))
    print()
    print("The reported numbers come from scikit-learn. The numpy model is kept")
    print("only as this cross-check.")


def test_D(d):
    rule("D. Trained classifier on family-presence vectors")
    y = d.y.to_numpy()
    print("engine: %s  |  protocol: StratifiedShuffleSplit, 50 train / 30 test, "
          "40 splits" % ("scikit-learn" if HAVE_SKLEARN else "numpy fallback"))
    print("  k-fold would cap at 2 folds, i.e. 40/40, because uc has 2 examples;")
    print("  50/30 is the largest training set keeping all 5 classes in the test half.")
    out = {}
    for tag, slices in CONFIGS:
        X, _ = presence(d, slices)
        s, oof = logreg_cv(X, y)
        if s is None:
            print("too few examples per class for CV"); return
        out[tag] = s
        print("%-24s macro-F1 %.3f  (sd %.3f, %d fits, %d features)"
              % (tag, s.mean(), s.std(), len(s), X.shape[1]))

    base = out["body only"]
    for tag, _ in CONFIGS[1:]:
        diff = out[tag] - base
        if HAVE_SCIPY:
            ci = sps.bootstrap((diff,), np.mean, confidence_level=0.95,
                               n_resamples=4000, method="BCa",
                               random_state=7).confidence_interval
            lo, hi = ci.low, ci.high
            tag2 = "scipy BCa"
        else:
            lo, hi = np.percentile(
                [RNG.choice(diff, len(diff), replace=True).mean()
                 for _ in range(4000)], [2.5, 97.5])
            tag2 = "percentile"
        print("delta vs body only, %-22s %+.3f   95%% CI [%+.3f, %+.3f]  (%s)"
              % (tag, diff.mean(), lo, hi, tag2))
    print("\nThat interval resamples fold scores, which are correlated because they")
    print("come from the same 80 tests. It is therefore optimistic. The permutation")
    print("test below does not depend on it.")

    if HAVE_SKLEARN:
        rule("D2. Label-permutation null (does the model beat chance at n=80?)")
        for tag, slices in CONFIGS:
            X, _ = presence(d, slices)
            obs, null_mean, p = permutation_p(X, y)
            print("%-24s observed %.3f   null mean %.3f   p = %.4f"
                  % (tag, obs, null_mean, p))


def test_E(d):
    """Baselines, random tie-breaking, and the binary order-dependency task."""
    rule("E. Baselines and tie-breaking")
    y = d.y.to_numpy()
    maj = np.full(len(y), pd.Series(y).mode()[0])
    print("majority-class baseline      accuracy %5.1f%%   macro-F1 %.3f"
          % (100 * np.mean(maj == y), macro_f1(y, maj)))
    uni = []
    for _ in range(2000):
        p = RNG.choice(CATS, len(y))
        uni.append(macro_f1(y, p))
    print("uniform-random baseline      accuracy %5.1f%%   macro-F1 %.3f"
          % (100.0 / len(CATS), float(np.mean(uni))))

    print("\nArgmax with ties broken at random, mean of 2000 draws:")
    for tag, slices in CONFIGS:
        S = cat_score(d, slices)
        accs, f1s = [], []
        for _ in range(2000):
            noise = RNG.random(S.shape) * 1e-6
            yhat = np.array(CATS)[(S + noise).argmax(axis=1)]
            accs.append(np.mean(yhat == y)); f1s.append(macro_f1(y, yhat))
        print("  %-22s accuracy %5.1f%%   macro-F1 %.3f"
              % (tag, 100 * np.mean(accs), float(np.mean(f1s))))

    rule("E2. Binary task: order dependency vs everything else")
    yb = (y == "od").astype(int)
    print("positives %d of %d" % (yb.sum(), len(yb)))
    for tag, slices in CONFIGS:
        S = cat_score(d, slices)
        od = S[:, CATS.index("od")]
        other = np.delete(S, CATS.index("od"), axis=1).max(axis=1)
        margin = od - other
        if HAVE_SKLEARN:
            from sklearn.metrics import roc_auc_score
            auc = float(roc_auc_score(yb, margin))
        else:
            pos, neg = margin[yb == 1], margin[yb == 0]
            auc = float(np.mean([(a > b) + 0.5 * (a == b)
                                 for a in pos for b in neg]))
        best = max(((np.mean((margin > t).astype(int) == yb), t)
                    for t in np.unique(margin)), key=lambda z: z[0])
        extra = ""
        if HAVE_SCIPY:
            u = sps.mannwhitneyu(margin[yb == 1], margin[yb == 0],
                                 alternative="greater")
            extra = "   Mann-Whitney p = %.2e" % u.pvalue
        print("  %-22s AUC %.3f   best accuracy %5.1f%% at margin > %g%s"
              % (tag, auc, 100 * best[0], best[1], extra))


def main():
    d = load()
    print("Tests analysed: %d across %d projects (%d misclassified by FlakyLens)"
          % (len(d), d.project.nunique(), d.wrong.sum()))
    print(d.groupby("truth").size().to_string())
    test_A(d)
    res = test_B(d)

    test_C(d, res)
    validate_models(d)
    test_D(d)
    test_E(d)


if __name__ == "__main__":
    main()
