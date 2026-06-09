"""построение графиков через matplotlib (backend Agg), возврат PNG в BytesIO."""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.family"] = "DejaVu Sans"  # есть кириллица


def _line_chart(
    x: list, y: list[float], title: str, ylabel: str,
    target: float | None = None,
) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(x, y, marker="o", linewidth=2, color="#d8412f")
    if target is not None:
        ax.axhline(target, color="#2f6fd8", linestyle="--", linewidth=1.5, label=f"норма {target:g}")
        ax.legend()
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    if x and hasattr(x[0], "year"):
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        fig.autofmt_xdate()
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf


def _bar_chart(labels: list[str], values: list[float], title: str, ylabel: str) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(labels, values, color="#d8412f")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(True, axis="y", alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf


def line_chart(x: list, y: list[float], title: str, ylabel: str, target: float | None = None):
    return _line_chart(x, y, title, ylabel, target)


def bar_chart(labels: list[str], values: list[float], title: str, ylabel: str):
    return _bar_chart(labels, values, title, ylabel)
