"""analysis.py - HilalPy-style crescent visibility database analysis.

Faithful adaptation of the three analysis functions of the **HilalPy**
library (``cond``, ``equa``, ``thres``), reading the bundled ``data/Final.csv``
(8000+ crescent sighting records) instead of the original package's now-dead
remote URL.  Returns ready-to-draw data for the pygame UI instead of writing
matplotlib figures / CSVs.

See  https://github.com/msyazwanfaid/hilalpy  for the original library.
"""

import os
import math

import pandas as pd
import numpy as np

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "data", "Final.csv")

_df = None


def load_data():
    global _df
    if _df is None:
        _df = pd.read_csv(DATA_PATH, index_col=0)
    return _df


def _points(df, x, y):
    pts = []
    for _, row in df.iterrows():
        pts.append((float(row[x]), float(row[y]),
                    str(row["V"]), str(row["M"])))
    return pts


def condition_analysis(x="ArcL", y="MAlt", conditionx=6.4, conditiony=3.0,
                       limitx=30.0, limity=30.0):
    """Condition analysis: is the crescent visible when the criteria
    (x >= conditionx AND y >= conditiony) hold?"""
    df = load_data().copy()
    df[x] = df[x].abs()
    df[y] = df[y].abs()
    df = df[(df[x] <= limitx) & (df[y] <= limity)]

    def rates(sub):
        sub = sub.copy()
        vis = sub[sub["V"] == "V"]
        inv = sub[sub["V"] == "I"]
        vis_ok = vis[(vis[x] >= conditionx) & (vis[y] >= conditiony)]
        inv_ok = inv[(inv[x] <= conditionx) & (inv[y] <= conditiony)]
        pos = abs(len(vis) - len(vis_ok)) / len(vis) * 100 if len(vis) else 0.0
        neg = abs(len(inv) - len(inv_ok)) / len(inv) * 100 if len(inv) else 0.0
        return pos, neg

    return {
        "kind": "cond",
        "xlabel": x, "ylabel": y,
        "conditionx": conditionx, "conditiony": conditiony,
        "limitx": limitx, "limity": limity,
        "points": _points(df, x, y),
        "error_rates": {
            "Whole": rates(df),
            "Naked Eye": rates(df[df["M"] == "NE"]),
            "Optical Aided": rates(df[df["M"] == "OA"]),
        },
    }


def equation_analysis(a="LT", b="ArcL",
                      equation="-0.5058 * x + 0.0059 * x**2 "
                               "+ -0.000021 * x**3 + 10.8467",
                      limita=30.0, limitb=30.0):
    """Equation analysis: crescent visible when y >= f(x) along the curve."""
    df = load_data().copy()
    df[a] = df[a].abs()
    df[b] = df[b].abs()
    df = df[(df[a] <= limita) & (df[b] <= limitb)]

    xs = df[a].to_numpy(dtype=float)
    df["test"] = eval(equation, {"x": xs, "np": np, "math": math})

    def rates(sub):
        sub = sub.copy()
        vis = sub[sub["V"] == "V"]
        inv = sub[sub["V"] == "I"]
        vis_ok = vis[vis[b] >= vis["test"]]
        inv_ok = inv[inv[b] < inv["test"]]
        pos = abs(len(vis) - len(vis_ok)) / len(vis) * 100 if len(vis) else 0.0
        neg = abs(len(inv) - len(inv_ok)) / len(inv) * 100 if len(inv) else 0.0
        return pos, neg

    curve = []
    for v in np.linspace(0.0, limita, 160):
        y = eval(equation, {"x": np.array([v]), "np": np, "math": math})[0]
        curve.append((float(v), float(y)))

    return {
        "kind": "equa",
        "xlabel": a, "ylabel": b,
        "equation": equation,
        "limita": limita, "limitb": limitb,
        "points": _points(df, a, b),
        "curve": curve,
        "error_rates": {
            "Whole": rates(df),
            "Naked Eye": rates(df[df["M"] == "NE"]),
            "Optical Aided": rates(df[df["M"] == "OA"]),
        },
    }


def threshold_analysis(x="ArcL"):
    """Threshold analysis: boxplot statistics of parameter x for the
    visibly-observed evening crescents, split by observing method."""
    df = load_data().copy()
    df = df[df["V"] == "V"]
    df = df[df["O"] == "E"]
    df[x] = df[x].abs()

    series = {}
    for method, label in (("NE", "Naked Eye"), ("OA", "Optical Aided")):
        sub = df[df["M"] == method][x]
        if len(sub) == 0:
            continue
        s = sub.describe(percentiles=[0.25, 0.5, 0.75])
        series[label] = {
            "count": int(s["count"]),
            "min": float(s["min"]),
            "q1": float(s["25%"]),
            "median": float(s["50%"]),
            "q3": float(s["75%"]),
            "max": float(s["max"]),
            "mean": float(s["mean"]),
        }

    minima = {}
    for method, label in (("NE", "Naked Eye"), ("OA", "Optical Aided")):
        sub = df[df["M"] == method]
        if len(sub) == 0:
            continue
        vmin = float(sub[x].min())
        minima[label] = vmin

    return {
        "kind": "thres",
        "xlabel": x,
        "series": series,
        "minima": minima,
    }
