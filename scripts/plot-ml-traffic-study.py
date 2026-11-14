"""Render measured traffic-study results as a shareable static figure."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "docs/experiments/ml-traffic-study"
report = json.loads((out / "summary.json").read_text())
levels = ["4", "8", "12", "16"]
groups = [report["by_fleet"][level] for level in levels]
plt.rcParams.update(
    {
        "font.size": 11,
        "font.family": "DejaVu Sans",
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)
fig, (a, b) = plt.subplots(1, 2, figsize=(12, 5.5), layout="constrained")
fig.suptitle("Pomáhá ML při větším provozu?", fontsize=18, fontweight="bold", x=0.03, ha="left")
x = np.arange(4)
y = np.array([g["improvement_percent"] for g in groups])
lo = np.array([g["bootstrap_95_percent"][0] for g in groups])
hi = np.array([g["bootstrap_95_percent"][1] for g in groups])
a.axhline(0, color="#71717a", linewidth=1)
a.errorbar(
    x,
    y,
    yerr=[np.maximum(0, y - lo), np.maximum(0, hi - y)],
    fmt="o",
    capsize=6,
    color="#4f46e5",
    markersize=7,
)
a.set_xticks(x, levels)
a.set_xlabel("Počet robotů")
a.set_ylabel("Zkrácení celkové doby s ML (%)")
a.set_title("Přínos proti původnímu přiřazování", loc="left", pad=20)
a.grid(axis="y", color="#e4e4e7")
for i, g in enumerate(groups):
    a.annotate(
        f"{g['improvement_percent']:+.2f} %".replace(".", ","),
        (i, y[i]),
        xytext=(8, 10),
        textcoords="offset points",
        fontsize=10,
    )
margin = max(0.2, (max(hi) - min(lo)) * 0.2)
a.set_ylim(min(min(lo), 0) - margin, max(max(hi), 0) + margin)
a.set_xlim(-0.5, 3.8)
w = 0.33
b.bar(
    x - w / 2,
    [g["baseline_waiting"] / 96 for g in groups],
    w,
    color="#a1a1aa",
    label="Původní přiřazování",
)
b.bar(x + w / 2, [g["ml_waiting"] / 96 for g in groups], w, color="#4f46e5", label="ML")
b.set_xticks(x, levels)
b.set_xlabel("Počet robotů")
b.set_ylabel("Čekání robotů / dokončený úkol (kroky)")
b.set_title("Skutečné čekání v provozu", loc="left", pad=20)
b.legend(frameon=False, fontsize=10)
b.grid(axis="y", color="#e4e4e7")
b.set_axisbelow(True)
fig.supxlabel(
    "15 map na skupinu · 96 úkolů na mapu · 95% párový bootstrap (explorační)\nKladná hodnota = rychlejší ML. Úspěšnost a všechny neúspěchy jsou uvedené v reportu.",
    fontsize=10,
    color="#52525b",
)
for suffix in ("png", "svg"):
    fig.savefig(out / ("comparison." + suffix), dpi=180, facecolor="white")
