"""
ChartSpec → Plotly HTML/PNG renderer.

Used by the assembler node to produce final chart artefacts from the spec
that code_writer emits. Keeps Plotly out of the sandbox.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from app.schemas.report import ChartSpec

_CHART_BUILDERS: dict[str, str] = {
    "bar": "bar",
    "line": "line",
    "scatter": "scatter",
    "pie": "pie",
    "histogram": "histogram",
    "box": "box",
    "heatmap": "imshow",
}


def render_chart(spec: ChartSpec, df: pd.DataFrame) -> go.Figure:
    """Build a Plotly Figure from a ChartSpec + dataframe."""
    chart_type = spec.chart_type.lower()

    kwargs: dict = {"title": spec.title}
    if spec.x_col and spec.x_col in df.columns:
        kwargs["x"] = spec.x_col
    if spec.y_col and spec.y_col in df.columns:
        kwargs["y"] = spec.y_col
    if spec.color_col and spec.color_col in df.columns:
        kwargs["color"] = spec.color_col

    if chart_type == "bar":
        fig = px.bar(df, **kwargs)
    elif chart_type == "line":
        fig = px.line(df, **kwargs)
    elif chart_type == "scatter":
        fig = px.scatter(df, **kwargs)
    elif chart_type == "pie":
        kwargs.pop("x", None)
        fig = px.pie(df, names=spec.x_col, values=spec.y_col, title=spec.title)
    elif chart_type == "histogram":
        kwargs.pop("y", None)
        fig = px.histogram(df, **kwargs)
    elif chart_type == "box":
        fig = px.box(df, **kwargs)
    else:
        # Fallback: bar
        fig = px.bar(df, title=spec.title)

    fig.update_layout(template="plotly_dark", margin=dict(l=40, r=40, t=60, b=40))
    return fig


def fig_to_html(fig: go.Figure) -> str:
    return fig.to_html(include_plotlyjs="cdn", full_html=False)


def fig_to_png_bytes(fig: go.Figure) -> bytes:
    return fig.to_image(format="png", width=900, height=500, scale=2)


def save_chart_png(spec: ChartSpec, df: pd.DataFrame, out_dir: str | Path) -> Path:
    """Render chart to PNG and save to out_dir/{chart_id}.png. Returns path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig = render_chart(spec, df)
    path = out_dir / f"{spec.chart_id}.png"
    path.write_bytes(fig_to_png_bytes(fig))
    return path
