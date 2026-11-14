"""Plot measured effects and completion rates; show failures beside conditional means."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs/experiments/ml-route-study"
summary = json.loads((OUT / "summary.json").read_text())
groups = list(summary["by_condition"].values())
labels = [
    "1 úzký průjezd · 4 roboti",
    "1 úzký průjezd · 8 robotů",
    "2 úzké průjezdy · 8 robotů",
    "2 úzké průjezdy · 12 robotů",
    "2 široké průjezdy · 8 robotů",
    "Otevřený sklad · 8 robotů",
]
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)
fig, (a, b) = plt.subplots(
    1, 2, figsize=(13, 6), layout="constrained", gridspec_kw={"width_ratios": [1.2, 1]}
)
fig.suptitle(
    "Průjezdy a protisměrný provoz: kde ML pomohlo?",
    fontsize=17,
    fontweight="bold",
    x=0.02,
    ha="left",
)
y = np.arange(len(groups))
effects = np.array([g["improvement_percent"] for g in groups])
lo = np.array([g["bootstrap_95_percent"][0] for g in groups])
hi = np.array([g["bootstrap_95_percent"][1] for g in groups])
a.axvline(0, color="#a1a1aa", linewidth=1)
a.errorbar(
    effects,
    y,
    xerr=[np.maximum(0, effects - lo), np.maximum(0, hi - effects)],
    fmt="o",
    capsize=5,
    color="#4f46e5",
    markersize=6,
)
a.set_yticks(y, labels)
a.set_ylim(5.65, -0.65)
a.set_xlim(-3, 3)
a.set_xlabel("Zkrácení doby s ML (%) · kladné = rychlejší")
a.set_title("Doba dokončení všech úkolů", loc="left", pad=16)
a.grid(axis="x", color="#e4e4e7")
for i, value in enumerate(effects):
    a.annotate(
        f"{value:+.2f} %".replace(".", ","),
        (value, i),
        xytext=(6, 12),
        textcoords="offset points",
        color="#3f3f46",
        fontsize=9,
    )
w = 0.29
b.barh(
    y - w / 2,
    [g["baseline_successes"] for g in groups],
    w,
    color="#a1a1aa",
    label="Původní přiřazování",
)
b.barh(y + w / 2, [g["ml_successes"] for g in groups], w, color="#4f46e5", label="ML")
b.set_yticks(y, [""] * len(groups))
b.set_ylim(5.65, -0.65)
b.set_xlim(0, 13.8)
b.set_xticks([0, 3, 6, 9, 12])
b.set_xlabel("Úspěšné scénáře ze všech 12 pokusů")
b.set_title("Úspěšnost včetně neúspěchů plánování", loc="left", pad=16)
b.grid(axis="x", color="#e4e4e7")
b.set_axisbelow(True)
for i, g in enumerate(groups):
    for offset, field in [(-w / 2, "baseline_successes"), (w / 2, "ml_successes")]:
        b.text(g[field] + 0.12, i + offset, f"{g[field]}/12", va="center", fontsize=9)
b.legend(loc="lower left", bbox_to_anchor=(0, -0.24), frameon=False, ncol=2, fontsize=9)
fig.supxlabel(
    "64 úkolů na mapu · oba směry · 72 dvojic · 0 vykonaných kolizí\nVlevo pouze dvojice dokončené oběma metodami; 95% párový bootstrap, explorační. Úzký = šířka 1, široký = šířka 2 buněk.",
    fontsize=9,
    color="#52525b",
)
for suffix in ("png", "svg"):
    fig.savefig(OUT / ("comparison." + suffix), dpi=180, facecolor="white")
