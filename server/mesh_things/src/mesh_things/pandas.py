"""API responses and exports as pandas DataFrames. Needs mesh-things[pandas].

Frames are wide by default: one row per time and one column per channel
(`<measurement>.<field>`). Pass `long=True` for one row per reading instead.
"""
import io
import json
import zipfile
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except ImportError as error:
    raise ImportError("mesh_things.pandas needs pandas: pip install 'mesh-things[pandas]'") from error

from mesh_things.channels import channels_in, origin_of


def to_dataframe(result: Any, *, long: bool = False, units: dict[str, str] | None = None) -> pd.DataFrame:
    """A DataFrame from a readings response, or from any list of records.

    Args:
        result: What a client method returned. Timeseries become a frame indexed by
            time. Latest readings and quality become one row per channel. A device's
            traffic becomes packets per time. A list becomes one row per element.
        long: One row per reading, with `time`, `channel` and `value` columns, instead of
            one column per channel. Only changes timeseries.
        units: Unit per channel, for example from `channel_units()`. Stored in
            `df.attrs["units"]`, and as a `unit` column when `long` is set.
    """
    if isinstance(result, list):
        return pd.DataFrame(result)
    if not isinstance(result, dict):
        raise TypeError(f"Cannot make a DataFrame from {type(result).__name__}")
    if "series" in result:
        frame = _series(result["series"], long, units or {})
    elif "readings" in result:
        frame = pd.DataFrame(result["readings"])
        if not frame.empty:
            frame = frame.assign(time=_times(frame["time"])).set_index("channel")
    elif "channels" in result:
        # An empty list still gives a frame indexed by channel.
        frame = pd.DataFrame(result["channels"], columns=None if result["channels"] else ["channel"]).set_index("channel")
    elif "points" in result:
        frame = _points(result["points"]).rename(columns={"value": "packets"})
    else:
        raise TypeError("Not a readings response: no series, readings, channels or points")
    frame.attrs.update({k: result[k] for k in ("mesh_id", "node_id", "payload_kind") if k in result})
    if "payload_kind" in result:
        frame.attrs["origin"] = origin_of(result["payload_kind"])
    if units:
        frame.attrs["units"] = dict(units)
    return frame


def channel_units(measurements: list[dict]) -> dict[str, str]:
    """Unit per channel from the measurement catalog (`api.measurements.list()`)."""
    return {m["channel"]: m["native_unit"] for m in measurements if m.get("channel") and m.get("native_unit")}


def read_export(source: str | Path | bytes) -> dict[str, pd.DataFrame]:
    """A downloaded export, as one frame per measurement.

    A CSV export gives one frame per measurement, its days concatenated, with each
    channel's unit in `attrs["units"]`. A Parquet export gives a single `archive` frame,
    and needs pyarrow (`mesh-things[archive]`).
    """
    with zipfile.ZipFile(io.BytesIO(source) if isinstance(source, bytes) else source) as zf:
        names = zf.namelist()
        if any(name.endswith(".parquet") for name in names):
            _require_parquet_engine()
            parts = [pd.read_parquet(io.BytesIO(zf.read(n))) for n in sorted(names) if n.endswith(".parquet")]
            return {"archive": pd.concat(parts, ignore_index=True)}
        units = {}
        if "channels.csv" in names:
            catalog = pd.read_csv(zf.open("channels.csv")).dropna(subset=["unit"])
            units = dict(zip(catalog["channel"], catalog["unit"]))
        days: dict[str, list[pd.DataFrame]] = {}
        for name in sorted(names):
            if name.endswith(".csv") and "/" in name:
                days.setdefault(Path(name).stem, []).append(pd.read_csv(zf.open(name)))
    frames = {}
    for measurement, parts in days.items():
        frame = pd.concat(parts, ignore_index=True)
        frame["time"] = _times(frame["time"])
        frame.attrs["units"] = {c: u for c, u in units.items() if c.startswith(f"{measurement}.")}
        frames[measurement] = frame
    return frames


def archive_frame(archive: pd.DataFrame, *, long: bool = False) -> pd.DataFrame:
    """Archive rows with their `payload_json` spread into one column per channel.

    The wide frame is indexed by `node_id` and `time`. Channels are named as the API
    names them.
    """
    rows = [
        {"node_id": row.node_id, "time": row.rx_time, "channel": channel, "value": value}
        for row in archive.itertuples()
        for channel, value in channels_in(row.payload_kind, json.loads(row.payload_json or "null"))
    ]
    frame = pd.DataFrame(rows, columns=["node_id", "time", "channel", "value"])
    frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
    if long:
        return frame
    return frame.pivot_table(index=["node_id", "time"], columns="channel", values="value", aggfunc="last")


def _require_parquet_engine() -> None:
    try:
        import pyarrow  # noqa: F401
    except ImportError as error:
        raise ImportError("Reading a Parquet export needs pyarrow: pip install 'mesh-things[archive]'") from error


def _times(values) -> pd.Series:
    return pd.to_datetime(values, utc=True, format="ISO8601")


def _points(points: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(points, columns=["time", "value"])
    return frame.assign(time=_times(frame["time"])).set_index("time")


def _series(series: list[dict], long: bool, units: dict[str, str]) -> pd.DataFrame:
    if long:
        rows = [{"time": p["time"], "channel": s["channel"], "value": p["value"]} for s in series for p in s["points"]]
        frame = pd.DataFrame(rows, columns=["time", "channel", "value"])
        frame["time"] = _times(frame["time"])
        if units:
            frame["unit"] = frame["channel"].map(units)
        return frame
    columns = {s["channel"]: _points(s["points"])["value"] for s in series}
    frame = pd.DataFrame(columns)
    frame.index.name = "time"
    return frame.sort_index()
