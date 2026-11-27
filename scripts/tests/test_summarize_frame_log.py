"""Run the frame summary CLI on synthetic frame samples."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "summarize-frame-log.py"


def frame(second, dropped, building, date="2026-11-27"):
    return (
        f"{date}T12:00:{second:02d}.000000Z  INFO victory_gpu::host: "
        "20.0 fps, 50.0 ms/frame (34.0 preparing: copies 6.2 ms 20.2 MB, "
        "textures 0.8 ms 28.5 MB; 0.0 on the GPU; 3.1 copying back 0.0 MB), "
        f"4700 draws/frame, dropped {dropped} without a host pipeline ({building} being made) "
        "and 0 indirect (0 of all these left out on purpose: ray-tracing passes without the structure builder)\n"
    )


def recording(second, frames, wait_ms, date="2026-11-27"):
    return (
        f"{date}T12:00:{second:02d}.000000Z  INFO victory_gpu::copystat: "
        f"recording per frame ({frames} frames): 12 list calls 40.0 ms "
        f"(all recording threads); {wait_ms:.1f} ms waiting for pipelines; "
        "dynamic slots: 0 tables asked, 0 refused\n"
    )


class FrameSummaryTest(unittest.TestCase):
    def report(self, *options, lines=None):
        if lines is None:
            lines = [frame(0, 0, 0), frame(1, 234, 0), frame(2, 999, 5)]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.log"
            path.write_text("".join(lines), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), str(path), *options],
                                    check=True, capture_output=True, text=True)
            self.assertEqual(result.stderr, "")
            self.assertNotIn("victory_gpu::", result.stdout)
            return json.loads(result.stdout)

    def test_drops_with_zero_pipelines_building(self):
        report = self.report()
        self.assertEqual(report["samples"], 3)
        self.assertEqual(report["slow_samples"], 0)
        self.assertEqual(report["samples_with_zero_pipelines_building"], 2)
        self.assertEqual(report["median_dropped_draws_per_frame_with_zero_pipelines_building"], 117)

    def test_asymmetric_zero_build_samples_use_the_median(self):
        report = self.report(lines=[frame(0, 0, 0), frame(1, 100, 0),
                                    frame(2, 999, 5), frame(3, 2, 0)])
        self.assertEqual(report["samples"], 4)
        self.assertEqual(report["samples_with_zero_pipelines_building"], 3)
        self.assertEqual(report["median_dropped_draws_per_frame_with_zero_pipelines_building"], 2)

    def test_invalid_date_between_valid_frames_skips_only_that_record(self):
        report = self.report(lines=[frame(0, 0, 0), frame(1, 999, 0, date="2026-02-30"),
                                    frame(2, 8, 0)])
        self.assertEqual(report["samples"], 2)
        self.assertEqual(report["samples_with_zero_pipelines_building"], 2)
        self.assertEqual(report["median_dropped_draws_per_frame_with_zero_pipelines_building"], 4)

    def test_only_invalid_dates_returns_empty_report(self):
        report = self.report(lines=[frame(0, 4, 0, date="2026-02-30"),
                                    frame(1, 8, 0, date="2026-13-01")])
        self.assertEqual(report, {"samples": 0})

    def test_window_with_only_active_builds(self):
        report = self.report("--start", "2", "--slow-ms", "50")
        self.assertEqual(report["samples"], 1)
        self.assertEqual(report["slow_samples_with_zero_pipelines_building"], 0)
        self.assertEqual(report["samples_with_zero_pipelines_building"], 0)
        self.assertIsNone(report["median_dropped_draws_per_frame_with_zero_pipelines_building"])

    def test_no_eligible_frames_keeps_existing_result(self):
        self.assertEqual(self.report("--min-draws", "4701"), {"samples": 0})


    def test_wait_average_uses_interval_frame_counts(self):
        report = self.report(lines=[frame(0, 0, 5), recording(1, 10, 0),
                              frame(5, 0, 0), recording(6, 30, 35)])
        self.assertEqual(report["samples"], 2)
        self.assertEqual(report["recording_intervals"], {
            "count": 2, "frames": 40, "mean_pipeline_wait_ms_per_frame": 26.25,
        })

    def test_bounds_use_emission_time_and_ignore_frame_only_filters(self):
        lines = [frame(1, 0, 0), recording(2, 12, 5), recording(3, 30, 35),
                 frame(4, 0, 9), recording(6, 10, 0), recording(7, 40, 100)]
        report = self.report("--start", "2", "--end", "6", "--min-draws", "9000", lines=lines)
        self.assertEqual(report, {"samples": 0, "recording_intervals": {
            "count": 2, "frames": 40, "mean_pipeline_wait_ms_per_frame": 26.25,
        }})

    def test_reported_zero_is_distinct_from_missing(self):
        cases = [
            ([frame(0, 0, 5), recording(1, 20, 0)], 1, 20, 0.0),
            ([frame(0, 0, 5)], 0, 0, None),
            ([frame(0, 0, 0), recording(1, 0, 42)], 0, 0, None),
        ]
        for lines, count, frames, mean in cases:
            with self.subTest(count=count, frames=frames):
                self.assertEqual(self.report(lines=lines)["recording_intervals"], {
                    "count": count, "frames": frames, "mean_pipeline_wait_ms_per_frame": mean,
                })

    def test_invalid_recording_interval_leaves_valid_samples_and_waits(self):
        lines = [frame(0, 2, 0), recording(1, 10, 4),
                 recording(2, 500, 999, date="2026-02-30"),
                 frame(3, 6, 0), recording(4, 30, 20)]
        report = self.report(lines=lines)
        self.assertEqual(report["samples"], 2)
        self.assertEqual(report["median_dropped_draws_per_frame_with_zero_pipelines_building"], 4)
        self.assertEqual(report["recording_intervals"], {
            "count": 2, "frames": 40, "mean_pipeline_wait_ms_per_frame": 16.0,
        })


if __name__ == "__main__":
    unittest.main()
