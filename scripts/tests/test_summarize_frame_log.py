"""Run the frame summary CLI on synthetic frame samples."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "summarize-frame-log.py"


def frame(second, dropped, building):
    return (
        f"2026-11-27T12:00:{second:02d}.000000Z  INFO victory_gpu::host: "
        "20.0 fps, 50.0 ms/frame (34.0 preparing: copies 6.2 ms 20.2 MB, "
        "textures 0.8 ms 28.5 MB; 0.0 on the GPU; 3.1 copying back 0.0 MB), "
        f"4700 draws/frame, dropped {dropped} without a host pipeline ({building} being made) "
        "and 0 indirect (0 of all these left out on purpose: ray-tracing passes without the structure builder)\n"
    )


class FrameSummaryTest(unittest.TestCase):
    def report(self, *options):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.log"
            path.write_text(frame(0, 0, 0) + frame(1, 234, 0) + frame(2, 999, 5),
                            encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), str(path), *options],
                                    check=True, capture_output=True, text=True)
            return json.loads(result.stdout)

    def test_drops_with_zero_pipelines_building(self):
        report = self.report()
        self.assertEqual(report["samples"], 3)
        self.assertEqual(report["slow_samples"], 0)
        self.assertEqual(report["samples_with_zero_pipelines_building"], 2)
        self.assertEqual(report["median_dropped_draws_per_frame_with_zero_pipelines_building"], 117)

    def test_window_with_only_active_builds(self):
        report = self.report("--start", "2", "--slow-ms", "50")
        self.assertEqual(report["samples"], 1)
        self.assertEqual(report["slow_samples_with_zero_pipelines_building"], 0)
        self.assertEqual(report["samples_with_zero_pipelines_building"], 0)
        self.assertIsNone(report["median_dropped_draws_per_frame_with_zero_pipelines_building"])

    def test_no_eligible_frames_keeps_existing_result(self):
        self.assertEqual(self.report("--min-draws", "4701"), {"samples": 0})


if __name__ == "__main__":
    unittest.main()
