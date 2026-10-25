import io
import json
import subprocess
import sys
import zipfile

import pytest

pd = pytest.importorskip("pandas")

from mesh_things.pandas import archive_frame, channel_units, read_export, to_dataframe  # noqa: E402

READINGS = {
    "mesh_id": "m",
    "node_id": 42,
    "payload_kind": "telemetry:environment_metrics",
    "series": [
        {"channel": "environment_metrics.temperature", "points": [
            {"time": "2026-10-24T10:00:00Z", "value": 21.5}, {"time": "2026-10-24T10:05:00Z", "value": 21.7}]},
        {"channel": "environment_metrics.relative_humidity", "points": [
            {"time": "2026-10-24T10:00:00Z", "value": 55.0}]},
    ],
}


def test_timeseries_is_wide_by_default():
    frame = to_dataframe(READINGS, units={"environment_metrics.temperature": "degC"})
    assert list(frame.columns) == ["environment_metrics.temperature", "environment_metrics.relative_humidity"]
    assert len(frame) == 2 and str(frame.index.tz) == "UTC"
    assert pd.isna(frame["environment_metrics.relative_humidity"].iloc[1])
    assert frame.attrs == {
        "mesh_id": "m", "node_id": 42, "payload_kind": "telemetry:environment_metrics",
        "origin": "measured", "units": {"environment_metrics.temperature": "degC"},
    }


def test_timeseries_long():
    frame = to_dataframe(READINGS, long=True, units={"environment_metrics.temperature": "degC"})
    assert list(frame.columns) == ["time", "channel", "value", "unit"]
    assert len(frame) == 3
    assert frame.loc[frame.channel == "environment_metrics.temperature", "unit"].tolist() == ["degC", "degC"]


def test_latest_quality_traffic_and_lists():
    latest = {"readings": [{"channel": "device_metrics.voltage", "value": 4.1, "time": "2026-10-24T10:00:00Z",
                            "unit": "V", "payload_kind": "telemetry:device_metrics", "field_name": "voltage"}]}
    assert to_dataframe(latest).loc["device_metrics.voltage", "unit"] == "V"
    quality = {"channels": [{"channel": "device_metrics.voltage", "completeness_ratio": 0.9}]}
    assert to_dataframe(quality).loc["device_metrics.voltage", "completeness_ratio"] == 0.9
    traffic = {"points": [{"time": "2026-10-24T10:00:00Z", "value": 3}]}
    assert to_dataframe(traffic)["packets"].tolist() == [3]
    assert len(to_dataframe([{"id": 1}, {"id": 2}])) == 2
    with pytest.raises(TypeError):
        to_dataframe({"unexpected": True})


def test_channel_units_from_the_catalog():
    catalog = [{"channel": "device_metrics.voltage", "native_unit": "V"}, {"channel": "x.y", "native_unit": None}]
    assert channel_units(catalog) == {"device_metrics.voltage": "V"}


def _csv_export() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for day in ("2026-10-01", "2026-10-02"):
            zf.writestr(f"{day}/device_metrics.csv", f"time,node_id,voltage\n{day}T10:00:00Z,42,4.1\n")
        zf.writestr("channels.csv", "channel,name,unit\ndevice_metrics.voltage,voltage,V\n")
    return out.getvalue()


def test_read_csv_export():
    frames = read_export(_csv_export())
    assert list(frames) == ["device_metrics"]
    assert len(frames["device_metrics"]) == 2
    assert frames["device_metrics"].attrs["units"] == {"device_metrics.voltage": "V"}


def test_archive_rows_spread_into_channels():
    rows = pd.DataFrame([
        {"node_id": 42, "rx_time": 1761300000, "payload_kind": "telemetry:device_metrics",
         "payload_json": json.dumps({"device_metrics": {"voltage": 4.1, "battery_level": 90}})},
    ])
    wide = archive_frame(rows)
    assert wide.loc[(42, pd.Timestamp(1761300000, unit="s", tz="UTC")), "device_metrics.voltage"] == 4.1
    assert set(archive_frame(rows, long=True)["channel"]) == {"device_metrics.voltage", "device_metrics.battery_level"}


def test_a_missing_pandas_names_the_extra():
    code = "import sys; sys.modules['pandas'] = None\ntry:\n import mesh_things.pandas\nexcept ImportError as e:\n print(e)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout
    assert "mesh-things[pandas]" in out


def test_quality_without_data_is_an_empty_frame():
    frame = to_dataframe({"channels": []})
    assert frame.empty and frame.index.name == "channel"


def test_a_parquet_export_without_pyarrow_names_the_extra(monkeypatch):
    import builtins

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("2026-10-01/2026-10-01_13.parquet", b"not read")
    real_import = builtins.__import__

    def no_pyarrow(name, *args, **kwargs):
        if name == "pyarrow":
            raise ImportError("no pyarrow")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_pyarrow)
    with pytest.raises(ImportError, match=r"mesh-things\[archive\]"):
        read_export(out.getvalue())
