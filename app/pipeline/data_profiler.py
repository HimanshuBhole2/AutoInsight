"""Node 1: DATA_PROFILER — load dataset, infer schema, build sample string."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.schemas.data_profile import ColumnStat, DataProfile


def data_profiler_node(state: dict[str, Any]) -> dict[str, Any]:
    dataset_id: str = state["dataset_id"]

    # TODO Phase 3: fetch from S3; for now load from local data/ dir
    csv_path = f"data/uploads/{dataset_id}.csv"
    df = pd.read_csv(csv_path)

    columns = []
    for col in df.columns:
        series = df[col]
        columns.append(
            ColumnStat(
                name=col,
                dtype=str(series.dtype),
                null_pct=round(float(series.isna().mean()), 4),
                unique_count=int(series.nunique()),
                sample_values=[str(v) for v in series.dropna().head(5).tolist()],
                min_val=str(series.min()) if pd.api.types.is_numeric_dtype(series) else None,
                max_val=str(series.max()) if pd.api.types.is_numeric_dtype(series) else None,
            )
        )

    profile = DataProfile(
        dataset_id=dataset_id,
        filename=f"{dataset_id}.csv",
        row_count=len(df),
        col_count=len(df.columns),
        columns=columns,
        s3_path=csv_path,
    )

    sample_str = df.head(10).to_markdown(index=False)

    return {
        "data_profile": profile.model_dump(),
        "dataset_sample": sample_str,
        "csv_path": csv_path,
    }
