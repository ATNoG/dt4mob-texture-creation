from __future__ import annotations

import numpy as np
import pandas as pd


def get_color(flag: str) -> list[float]:
    f = str(flag).lower().strip()
    if "alert" in f:
        return [1.0, 1.0, 0.0]
    if "alarm" in f:
        return [1.0, 0.0, 0.0]
    return [0.0, 1.0, 0.0]


def compute_displacement_colors(dist_series: pd.Series) -> np.ndarray:
    dist = dist_series.fillna(0.0).to_numpy()
    dist_clipped = np.clip(dist, -0.02, 0.02)
    colors = np.zeros((len(dist_clipped), 3))
    neg_mask = dist_clipped < 0
    if neg_mask.any():
        d_neg = dist_clipped[neg_mask]
        t_neg = (d_neg + 0.02) / 0.02
        colors[neg_mask, 0] = 1.0 - t_neg
        colors[neg_mask, 1] = t_neg
        colors[neg_mask, 2] = 1.0 - t_neg
    pos_mask = dist_clipped > 0
    if pos_mask.any():
        d_pos = dist_clipped[pos_mask]
        t_pos = d_pos / 0.02
        colors[pos_mask, 0] = t_pos
        colors[pos_mask, 1] = 1.0 - t_pos
        colors[pos_mask, 2] = 0.0
    return colors
