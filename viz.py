"""
viz.py — Pitch visualisations for Football Intelligence Hub.

All public functions accept a DataFrame + metadata and return a
matplotlib Figure.  Callers (app.py) control rendering via st.pyplot(fig).
"""

import numpy as np
import matplotlib.pyplot as plt
from mplsoccer import Pitch, Radar, VerticalPitch
import pandas as pd

import config

# ── internal helpers ──────────────────────────────────────────────────────────

def _dummy_pitch_df(n: int = 50, seed: int = 42) -> pd.DataFrame:
    """Random x/y coordinates for placeholder pitch visualisations."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "x": rng.uniform(5, 115, n),
        "y": rng.uniform(5, 75, n),
    })


def _base_pitch() -> Pitch:
    return Pitch(
        pitch_type="statsbomb",
        pitch_color=config.PITCH_COLOR,
        line_color=config.LINE_COLOR,
        line_zorder=2,
    )


def _style_fig(fig: plt.Figure) -> None:
    fig.patch.set_facecolor(config.PITCH_COLOR)


def _set_title(ax: plt.Axes, label: str) -> None:
    if label:
        ax.set_title(label, color="white", fontsize=13, pad=12, fontweight="bold")


def _placeholder_note(ax: plt.Axes) -> None:
    ax.text(
        0.5, 0.01,
        "Dati non disponibili — visualizzazione di esempio",
        ha="center", va="bottom",
        transform=ax.transAxes,
        color=config.NEUTRAL_COLOR,
        fontsize=9, style="italic",
    )


def _has_xy(df: pd.DataFrame | None) -> bool:
    return (
        df is not None
        and not df.empty
        and {"x", "y"}.issubset(df.columns)
    )


def _find_col(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


# ── public API ────────────────────────────────────────────────────────────────

def plot_heatmap(
    df: pd.DataFrame,
    team: str,
    title: str = "",
) -> plt.Figure:
    """
    Bin-based pitch heatmap from x/y action coordinates.
    Falls back to random placeholder data if df has no usable coordinates.
    """
    is_placeholder = not _has_xy(df)
    src = _dummy_pitch_df() if is_placeholder else df

    pitch = _base_pitch()
    fig, ax = pitch.draw(figsize=(10, 7))
    _style_fig(fig)

    bs = pitch.bin_statistic(src["x"], src["y"], statistic="count", bins=(24, 16))
    pitch.heatmap(
        bs, ax=ax,
        cmap=config.HEATMAP_CMAP,
        edgecolors=config.PITCH_COLOR,
        linewidth=0.3,
    )

    label = f"{team} — {title}" if team and title else (team or title or "Heatmap posizionale")
    _set_title(ax, label)
    if is_placeholder:
        _placeholder_note(ax)

    plt.tight_layout()
    return fig


def plot_pressing_map(
    df: pd.DataFrame,
    team: str,
    title: str = "",
) -> plt.Figure:
    """
    Heatmap of defensive actions (tackles + interceptions + pressures) on pitch.
    If df has a 'type' column, filters to defensive event types automatically.
    Falls back to a biased placeholder (weighted toward own half) when coordinates
    are unavailable.
    """
    _DEF_TYPES = {"Tackle", "Interception", "Ball Recovery", "Clearance", "Pressure"}

    df_def: pd.DataFrame = pd.DataFrame()
    if df is not None and not df.empty:
        if "type" in df.columns:
            df_def = df[df["type"].astype(str).isin(_DEF_TYPES)]
        else:
            df_def = df

    is_placeholder = not _has_xy(df_def)
    if is_placeholder:
        rng = np.random.default_rng(7)
        df_def = pd.DataFrame({
            # Concentrate in own half (x 0–60) to suggest defensive shape
            "x": rng.uniform(5, 65, 40),
            "y": rng.uniform(5, 75, 40),
        })

    pitch = _base_pitch()
    fig, ax = pitch.draw(figsize=(10, 7))
    _style_fig(fig)

    bs = pitch.bin_statistic(df_def["x"], df_def["y"], statistic="count", bins=(24, 16))
    # "Reds" — red zones = high pressing intensity, intuitive read
    pitch.heatmap(
        bs, ax=ax,
        cmap="Reds",
        edgecolors=config.PITCH_COLOR,
        linewidth=0.3,
    )

    label = (
        f"{team} — {title}" if team and title
        else (team or title or "Mappa del pressing")
    )
    _set_title(ax, label)
    if is_placeholder:
        _placeholder_note(ax)

    plt.tight_layout()
    return fig


def plot_passing_network(
    df: pd.DataFrame,
    team: str,
    title: str = "",
) -> plt.Figure:
    """
    Passing network: nodes = avg player positions, edges = pass connections.
    Expects StatsBomb-style event data (player, x, y, pass_recipient).
    Falls back to a synthetic 4-3-3 placeholder when real data is unavailable.
    """
    _PASSER_COLS   = ("player", "player_name")
    _RECEIVER_COLS = ("pass_recipient", "pass_recipient_name")

    nodes: pd.DataFrame | None = None
    edges: pd.DataFrame | None = None

    if df is not None and not df.empty:
        p_col = _find_col(df, _PASSER_COLS)
        r_col = _find_col(df, _RECEIVER_COLS)

        if p_col and _has_xy(df):
            nodes = (
                df.groupby(p_col)[["x", "y"]]
                .mean()
                .rename(columns={"x": "x_avg", "y": "y_avg"})
            )
            nodes["pass_count"] = df.groupby(p_col).size()

            if r_col:
                edges = (
                    df.groupby([p_col, r_col])
                    .size()
                    .reset_index(name="count")
                )

    is_placeholder = nodes is None or nodes.empty
    if is_placeholder:
        # 4-3-3 formation in statsbomb coords (attack left→right)
        _pos = {
            "GK":  (8,  40),
            "RB":  (28, 18), "CB1": (28, 32), "CB2": (28, 52), "LB": (28, 66),
            "CM1": (52, 26), "CM2": (52, 42), "CM3": (52, 58),
            "RW":  (82, 15), "CF":  (88, 40), "LW":  (82, 65),
        }
        rng = np.random.default_rng(0)
        nodes = pd.DataFrame(
            [{"player": k, "x_avg": v[0], "y_avg": v[1],
              "pass_count": int(rng.integers(30, 80))}
             for k, v in _pos.items()]
        ).set_index("player")

        player_list = list(_pos.keys())
        _edge_rows = []
        for i, src_p in enumerate(player_list):
            for j, tgt_p in enumerate(player_list):
                if i >= j:
                    continue
                w = int(rng.integers(0, 25))
                if w > 8:
                    _edge_rows.append({"src": src_p, "tgt": tgt_p, "count": w})
        edges = pd.DataFrame(_edge_rows)

    pitch = _base_pitch()
    fig, ax = pitch.draw(figsize=(10, 7))
    _style_fig(fig)

    # Draw edges
    if edges is not None and not edges.empty:
        src_col = edges.columns[0]
        tgt_col = edges.columns[1]
        max_count = max(edges["count"].max(), 1)
        for _, row in edges.iterrows():
            src_p, tgt_p = row[src_col], row[tgt_col]
            if src_p not in nodes.index or tgt_p not in nodes.index:
                continue
            ratio = row["count"] / max_count
            ax.plot(
                [nodes.loc[src_p, "x_avg"], nodes.loc[tgt_p, "x_avg"]],
                [nodes.loc[src_p, "y_avg"], nodes.loc[tgt_p, "y_avg"]],
                color=config.HOME_COLOR,
                lw=0.5 + 4.5 * ratio,
                alpha=0.3 + 0.5 * ratio,
                zorder=3,
            )

    # Draw nodes
    max_passes = max(nodes["pass_count"].max(), 1)
    node_sizes = 200 + 600 * nodes["pass_count"] / max_passes
    ax.scatter(
        nodes["x_avg"], nodes["y_avg"],
        s=node_sizes,
        color=config.HOME_COLOR,
        edgecolors="white",
        linewidths=1.5,
        zorder=4,
    )
    for player, row in nodes.iterrows():
        ax.text(
            row["x_avg"], row["y_avg"],
            str(player)[:3],
            ha="center", va="center",
            fontsize=7, color="white", fontweight="bold",
            zorder=5,
        )

    label = (
        f"{team} — {title}" if team and title
        else (team or title or "Rete di passaggi")
    )
    _set_title(ax, label)
    if is_placeholder:
        _placeholder_note(ax)

    plt.tight_layout()
    return fig


def plot_player_radar(
    player_row: dict,
    role_profile: dict,
    player_name: str = "",
) -> plt.Figure:
    """
    Radar chart comparing a player's stats against a role profile.

    Args:
        player_row:   {metric: value}     — actual per-90 stats for the player.
        role_profile: {metric: max_value} — benchmark ceiling per metric.
                      Pass config.ROLE_PROFILES[role] scaled to realistic
                      per-90 maxima (weights alone are not enough; caller scales).
        player_name:  Arc label shown as chart title.
    """
    params = [m for m in role_profile if m in player_row]

    is_placeholder = len(params) < 3
    if is_placeholder:
        params = [
            "Tiri/90", "Passaggi prog./90", "Dribbling/90",
            "Contrasti/90", "xG/90", "Assist/90",
        ]
        role_profile = {m: 1.0 for m in params}
        rng = np.random.default_rng(42)
        player_row = {m: round(float(rng.uniform(0.2, 0.85)), 2) for m in params}

    max_vals = [max(float(role_profile[m]), 1e-6) for m in params]
    values = [
        float(np.clip(player_row[m], 0.0, role_profile[m]))
        for m in params
    ]

    radar = Radar(
        params=params,
        min_range=[0.0] * len(params),
        max_range=max_vals,
        ring_width=1,
        center_circle_radius=1,
        num_rings=4,
    )
    fig, axes = radar.setup_axis(figsize=(8, 8))
    fig.patch.set_facecolor(config.RADAR_BG)

    radar.draw_circles(
        ax=axes["radar"],
        facecolor=config.LINE_COLOR,
        edgecolor=config.LINE_COLOR,
        alpha=0.2,
    )
    radar.draw_radar(
        values,
        ax=axes["radar"],
        kwargs_radar={"facecolor": config.RADAR_COLOR, "alpha": 0.55},
        kwargs_rings={"facecolor": config.RADAR_COLOR, "alpha": 0.25},
    )
    radar.draw_range_labels(ax=axes["radar"], fontsize=9, color="white")
    radar.draw_param_labels(ax=axes["radar"], fontsize=11, color="white")

    chart_title = player_name or "Profilo giocatore"
    if is_placeholder:
        chart_title += " (esempio)"
    axes["radar"].set_title(
        chart_title,
        color="white",
        fontsize=14,
        fontweight="bold",
        pad=20,
    )

    plt.tight_layout()
    return fig


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
