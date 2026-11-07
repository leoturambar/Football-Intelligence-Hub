"""
viz.py — Pitch visualisations for Football Intelligence Hub.

All public functions accept a DataFrame + metadata and return a
matplotlib Figure.  Callers (app.py) control rendering via st.pyplot(fig).
"""

import textwrap

import numpy as np
import matplotlib.pyplot as plt
from mplsoccer import Pitch, VerticalPitch
import pandas as pd

import config

# ── internal helpers ──────────────────────────────────────────────────────────


def _style_fig(fig: plt.Figure) -> None:
    fig.patch.set_facecolor(config.PITCH_COLOR)


def _set_title(ax: plt.Axes, label: str) -> None:
    if label:
        ax.set_title(label, color="white", fontsize=13, pad=12, fontweight="bold")


def _has_xy(df: pd.DataFrame | None) -> bool:
    return (
        df is not None
        and not df.empty
        and {"x", "y"}.issubset(df.columns)
    )


# ── public API ────────────────────────────────────────────────────────────────


def plot_shot_map(
    shots: pd.DataFrame,
    title: str = "",
    color: str | None = None,
) -> plt.Figure:
    """
    Half-pitch shot map from FotMob shot coordinates (105x68 frame, attacking
    towards x=105). Marker size = xG; filled = goal, hollow = no goal.
    Never draws placeholder data: an empty frame shows an explicit note.
    """
    color = color or config.HOME_COLOR
    pitch = VerticalPitch(
        pitch_type="uefa", half=True,
        pitch_color=config.PITCH_COLOR, line_color=config.LINE_COLOR, line_zorder=2,
    )
    fig, ax = pitch.draw(figsize=(7, 6))
    _style_fig(fig)

    if shots is None or shots.empty or not _has_xy(shots):
        ax.text(34, 75, "Nessun tiro nei dati selezionati", ha="center",
                color=config.NEUTRAL_COLOR, fontsize=11, style="italic")
    else:
        sizes = 60 + 900 * shots["xg"].fillna(0.02).clip(0, 1)
        miss = shots[~shots["is_goal"].astype(bool)]
        goal = shots[shots["is_goal"].astype(bool)]
        pitch.scatter(miss["x"], miss["y"], s=sizes[miss.index], ax=ax,
                      facecolors="none", edgecolors=color, linewidths=1.2, alpha=0.75, zorder=3)
        pitch.scatter(goal["x"], goal["y"], s=sizes[goal.index], ax=ax,
                      color=color, edgecolors="white", linewidths=1, alpha=0.95, zorder=4)
        ax.text(
            34, 53.5,
            f"{len(shots)} tiri · {int(goal.shape[0])} gol · xG {shots['xg'].sum():.1f}",
            ha="center", color="white", fontsize=10,
        )

    _set_title(ax, title or "Mappa dei tiri")
    plt.tight_layout()
    return fig


def plot_role_percentiles(detail: pd.DataFrame, title: str = "") -> plt.Figure:
    """
    Horizontal percentile bars for a player's role metrics (from
    analysis.role_fit). 50 = league median for the role. Bars are coloured
    by band: <30 weak, 30-70 average, >70 strong.
    """
    d = detail.sort_values("Percentile") if detail is not None and not detail.empty else pd.DataFrame()
    fig, ax = plt.subplots(figsize=(7, 0.45 * max(len(d), 3) + 1))
    _style_fig(fig)
    ax.set_facecolor(config.PITCH_COLOR)
    if d.empty:
        ax.text(0.5, 0.5, "Dati insufficienti per questo ruolo", ha="center", va="center",
                color=config.NEUTRAL_COLOR, transform=ax.transAxes, style="italic")
        ax.axis("off")
        return fig
    colors = ["#F55B5B" if p < 30 else (config.NEUTRAL_COLOR if p <= 70 else "#5BD08A")
              for p in d["Percentile"]]
    ax.barh(d["Metrica"], d["Percentile"], color=colors, alpha=0.9)
    ax.axvline(50, color="white", lw=0.8, ls="--", alpha=0.6)
    ax.set_xlim(0, 100)
    for y, (p, v) in enumerate(zip(d["Percentile"], d["Valore"])):
        ax.text(min(p + 1.5, 88), y, f"{p:.0f}° · {v:.2f}", va="center", color="white", fontsize=8)
    ax.tick_params(colors="white", labelsize=9)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xlabel("Percentile nel ruolo (50 = mediana del campionato)", color="white", fontsize=9)
    _set_title(ax, title)
    plt.tight_layout()
    return fig


def plot_percentile_radar(series: dict[str, dict[str, float]], title: str = "") -> plt.Figure:
    """
    Overlaid polar chart of league percentiles (0-100) for up to 4 players.
    series: {player label: {metric label: percentile}} — same metrics for all.
    """
    palette = [config.HOME_COLOR, config.AWAY_COLOR, config.NEUTRAL_COLOR, config.ACCENT_COLOR]
    labels = list(next(iter(series.values())).keys()) if series else []
    fig = plt.figure(figsize=(7, 7))
    _style_fig(fig)
    ax = fig.add_subplot(111, polar=True)
    ax.set_facecolor(config.PITCH_COLOR)
    if len(labels) < 3:
        ax.text(0, 0, "Metriche insufficienti", ha="center", color=config.NEUTRAL_COLOR)
        return fig
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    angles += angles[:1]
    for (name, vals), color in zip(series.items(), palette):
        v = [float(vals.get(l, np.nan)) for l in labels]
        v = [0.0 if np.isnan(x) else x for x in v]
        v += v[:1]
        ax.plot(angles, v, color=color, lw=2, label=name)
        ax.fill(angles, v, color=color, alpha=0.12)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75])
    ax.set_yticklabels(["25", "50", "75"], color="#999999", fontsize=7)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([textwrap.fill(l, 16) for l in labels], color="white", fontsize=8)
    ax.grid(color=config.LINE_COLOR, alpha=0.6)
    ax.spines["polar"].set_color(config.LINE_COLOR)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=2, frameon=False,
              labelcolor="white", fontsize=9)
    if title:
        ax.set_title(title, color="white", fontsize=13, fontweight="bold", pad=18)
    plt.tight_layout()
    return fig


def plot_match_shots(shots: pd.DataFrame, home: str, away: str) -> plt.Figure:
    """
    Both teams' shots on one full pitch (FotMob 105x68): home attacks right,
    away is mirrored to attack left. Size = xG, filled = goal.
    shots needs columns: side ('home'/'away'), x, y, xg, is_goal.
    """
    pitch = Pitch(pitch_type="uefa", pitch_color=config.PITCH_COLOR,
                  line_color=config.LINE_COLOR, line_zorder=2)
    fig, ax = pitch.draw(figsize=(10, 6.5))
    _style_fig(fig)
    if shots is None or shots.empty:
        ax.text(52.5, 34, "Nessun tiro registrato", ha="center", color=config.NEUTRAL_COLOR)
        return fig
    for side, color in (("home", config.HOME_COLOR), ("away", config.AWAY_COLOR)):
        s = shots[shots["side"] == side]
        if s.empty:
            continue
        x = s["x"] if side == "home" else 105 - s["x"]
        y = s["y"] if side == "home" else 68 - s["y"]
        size = 60 + 900 * s["xg"].fillna(0.02).clip(0, 1)
        goal = s["is_goal"].astype(bool)
        pitch.scatter(x[~goal], y[~goal], s=size[~goal], ax=ax, facecolors="none",
                      edgecolors=color, linewidths=1.3, alpha=0.8, zorder=3)
        pitch.scatter(x[goal], y[goal], s=size[goal], ax=ax, color=color,
                      edgecolors="white", linewidths=1, zorder=4)
    xg_h = shots.loc[shots["side"] == "home", "xg"].sum()
    xg_a = shots.loc[shots["side"] == "away", "xg"].sum()
    ax.text(26, -3, f"← {away} · xG {xg_a:.2f}", ha="center", color=config.AWAY_COLOR, fontsize=11)
    ax.text(79, -3, f"{home} · xG {xg_h:.2f} →", ha="center", color=config.HOME_COLOR, fontsize=11)
    plt.tight_layout()
    return fig


def plot_xg_race(shots: pd.DataFrame, home: str, away: str) -> plt.Figure:
    """Cumulative xG by minute for both teams, goals marked."""
    fig, ax = plt.subplots(figsize=(10, 3.6))
    _style_fig(fig)
    ax.set_facecolor(config.PITCH_COLOR)
    end = 95
    if shots is not None and not shots.empty:
        end = max(95, int(shots["minute"].max() or 90) + 3)
    for side, name, color in (("home", home, config.HOME_COLOR), ("away", away, config.AWAY_COLOR)):
        s = (shots[shots["side"] == side].sort_values("minute")
             if shots is not None and not shots.empty else pd.DataFrame(columns=["minute", "xg", "is_goal"]))
        mins = [0] + s["minute"].fillna(0).tolist() + [end]
        cum = [0] + s["xg"].fillna(0).cumsum().tolist()
        cum = cum + [cum[-1]]
        ax.step(mins, cum, where="post", color=color, lw=2, label=f"{name} ({cum[-1]:.2f})")
        g = s[s["is_goal"].astype(bool)]
        if not g.empty:
            g_cum = s["xg"].fillna(0).cumsum()[g.index]
            ax.scatter(g["minute"], g_cum, color=color, edgecolors="white", s=70, zorder=5)
    ax.axvline(45, color=config.LINE_COLOR, ls="--", lw=0.8)
    ax.set_xlim(0, end)
    ax.set_xlabel("Minuto", color="white")
    ax.set_ylabel("xG cumulati", color="white")
    ax.tick_params(colors="white")
    for s in ax.spines.values():
        s.set_color(config.LINE_COLOR)
    ax.legend(frameon=False, labelcolor="white", loc="upper left")
    plt.tight_layout()
    return fig
