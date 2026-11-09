"""Small regression checks for the statistical methods, without network access."""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import numpy as np
import pandas as pd

from data_quality import (_request_weather, download_weather, weather_mean, precipitation_spc,
                          temperature_lof, reservoir_stl, reservoir_spectrogram)


class WeatherDownloadTests(unittest.TestCase):
    def test_hourly_budget_waits_for_server_hour_with_reset_margin(self):
        hour_start = 1_800_000_000  # Divisible by 3600.
        clock = [hour_start + 1800.0]
        def advance(seconds):
            clock[0] += seconds
        response = Mock(status_code=200, content=b'{"complete": true}')
        response.json.return_value = {"complete": True}
        params = {"start_date": "2024-01-01", "end_date": "2024-12-31",
                  "latitude": ",".join(["63"] * 20)}
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "quota.json").write_text(json.dumps([[hour_start + 1200, 4500]]))
            with patch("data_quality.time.time", side_effect=lambda: clock[0]), \
                 patch("data_quality.time.sleep", side_effect=advance), \
                 patch("data_quality.requests.get", return_value=response) as request:
                self.assertEqual(_request_weather(params, folder), {"complete": True})
                request.assert_called_once()
            self.assertGreaterEqual(clock[0], hour_start + 3660)
            self.assertLess(clock[0], hour_start + 3720)

    def response(self, params, *args):
        latitudes = [float(value) for value in params["latitude"].split(",")]
        longitudes = [float(value) for value in params["longitude"].split(",")]
        times = pd.date_range("2024-01-01", periods=24, freq="h").strftime("%Y-%m-%dT%H:%M").tolist()
        return [{
            "location_id": index, "latitude": latitude, "longitude": longitude,
            "elevation": 100, "utc_offset_seconds": 0,
            "hourly_units": {"temperature_2m": "°C", "precipitation": "mm"},
            "hourly": {"time": times, "temperature_2m": [longitude] * 24,
                       "precipitation": [1.0] * 24},
        } for index, (latitude, longitude) in enumerate(zip(latitudes, longitudes))]

    def test_every_location_is_preserved_and_complete_cache_avoids_requests(self):
        coordinates = np.asarray(json.loads(Path("data/weather_locations.json").read_text())["NO3"])
        with tempfile.TemporaryDirectory() as folder:
            with patch("data_quality._request_weather", side_effect=self.response) as request:
                weather = download_weather("NO3", "2024-01-01", "2024-01-01", folder)
                self.assertEqual(request.call_count, 50)
            self.assertEqual(weather["temperature_2m"].shape, (1000, 24))
            np.testing.assert_allclose(weather["temperature_2m"][:, 0], coordinates[:, 0])
            np.testing.assert_allclose(weather_mean(weather).temperature_2m, coordinates[:, 0].mean())
            with patch("data_quality._request_weather", side_effect=AssertionError("Unexpected request")):
                cached = download_weather("NO3", "2024-01-01", "2024-01-01", folder)
            np.testing.assert_array_equal(cached["precipitation"], weather["precipitation"])

    def test_wrong_units_or_time_axis_do_not_create_a_complete_archive(self):
        for problem in ("units", "time"):
            def bad_response(params, *args):
                records = self.response(params)
                if problem == "units":
                    records[0]["hourly_units"]["precipitation"] = "inch"
                else:
                    records[0]["hourly"]["time"][0] = "2024-01-02T00:00"
                return records
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as folder:
                with patch("data_quality._request_weather", side_effect=bad_response):
                    with self.assertRaises(ValueError):
                        download_weather("NO3", "2024-01-01", "2024-01-01", folder)
                self.assertEqual(list(Path(folder).glob("*.npz")), [])


class DataQualityTests(unittest.TestCase):
    def setUp(self):
        self.time = pd.date_range("2024-01-01", periods=8784, freq="h", tz="UTC")
        self.rng = np.random.default_rng(42)

    def test_spc_detects_injected_rain_and_respects_units(self):
        series = pd.Series(0.2 + self.rng.normal(0, .01, len(self.time)), index=self.time)
        series.iloc[4000] = 5
        _, summary, result = precipitation_spc(series)
        _, wider, _ = precipitation_spc(series, deviations=5)
        _, _, scaled = precipitation_spc(series * 10)
        self.assertTrue(result.iloc[4000].outlier)
        self.assertLessEqual(wider["outlier_hours"], summary["outlier_hours"])
        np.testing.assert_array_equal(result.outlier, scaled.outlier)
        np.testing.assert_allclose(scaled.upper_limit, result.upper_limit * 10)

    def test_constant_precipitation_has_no_false_roundoff_outliers(self):
        _, summary, _ = precipitation_spc(pd.Series(.2, index=self.time))
        self.assertEqual(summary["outlier_hours"], 0)

    def test_lof_detects_temperature_spike_and_excludes_first_hour(self):
        series = pd.Series(self.rng.normal(5, 1, len(self.time)), index=self.time)
        series.iloc[4000] = 50
        _, summary, result = temperature_lof(series)
        _, higher, _ = temperature_lof(series, contamination=.02)
        self.assertTrue(result.iloc[4000].anomaly)
        self.assertTrue(pd.isna(result.iloc[0].lof_score))
        self.assertEqual(summary["scored_hours"], 8783)
        self.assertGreater(higher["anomaly_hours"], summary["anomaly_hours"])

    def test_gaps_and_nonfinite_values_are_rejected(self):
        series = pd.Series(1., index=self.time)
        with self.assertRaises(ValueError):
            precipitation_spc(series.drop(self.time[10]))
        series.iloc[10] = np.nan
        with self.assertRaises(ValueError):
            temperature_lof(series)

    def test_weekly_reconstruction_and_known_annual_frequency(self):
        weeks = pd.date_range("2015-01-04", periods=522, freq="7d")
        series = pd.Series(60 + 20 * np.sin(2 * np.pi * np.arange(522) / 52), index=weeks)
        _, components = reservoir_stl(series)
        np.testing.assert_allclose(components.observed, components[["trend", "seasonal", "residual"]].sum(axis=1))
        _, summary = reservoir_spectrogram(series)
        self.assertAlmostEqual(summary["dominant_nonzero_frequency"], 1, delta=.01)
        with self.assertRaises(ValueError):
            reservoir_stl(series, trend=52)
        with self.assertRaises(ValueError):
            reservoir_spectrogram(series, window=104, overlap=104)


if __name__ == "__main__":
    unittest.main()
