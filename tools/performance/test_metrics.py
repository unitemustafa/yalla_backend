import unittest
import tempfile
from pathlib import Path

from tools.performance.metrics import (
    distribution,
    frames,
    journeys_summary,
    requests_summary,
)
from tools.performance.run import classify, read_rows
from tools.performance.schedule import spike_target
from tools.performance.summarize import summarize_mobile
from tools.performance.resources import summarize_resources
from tools.performance.trace_summary import summarize_trace


class MeasurementTests(unittest.TestCase):
    def test_low_frame_times_do_not_certify_a_stationary_scroll_window(self):
        raw = {
            "scroll_protocol": "edge_reversal_with_motion_validation_v2",
            "store_scroll_1": {
                "frame_build_times": [1000] * 100,
                "frame_rasterizer_times": [1000] * 100,
            },
            "observations": {},
        }
        result = summarize_mobile(raw)
        self.assertTrue(result["all_recorded_frames_pass"])
        self.assertEqual(result["scroll_motion_quality"], "motion_verification_failed")
        raw["observations"]["scroll_motion_1"] = {
            "elapsed_ms": 30000,
            "distance_px": 6000,
            "flings": 10,
            "moving_flings": 9,
        }
        self.assertEqual(
            summarize_mobile(raw)["scroll_motion_quality"], "verified_motion_v2"
        )
        raw["observations"]["scroll_motion_1"]["moving_flings"] = 4
        self.assertEqual(
            summarize_mobile(raw)["scroll_motion_quality"], "motion_verification_failed"
        )

    def test_timeline_nested_threads_and_clipped_window_are_not_mixed(self):
        events = [
            {"ph": "E", "tid": 1, "ts": 1},
            {"ph": "B", "tid": 1, "ts": 1000, "name": "frame"},
            {"ph": "B", "tid": 2, "ts": 2000, "name": "frame"},
            {"ph": "B", "tid": 1, "ts": 2000, "name": "paint"},
            {"ph": "E", "tid": 1, "ts": 3000},
            {"ph": "E", "tid": 1, "ts": 5000},
            {"ph": "E", "tid": 2, "ts": 8000},
            {"ph": "B", "tid": 1, "ts": 9000, "name": "clipped"},
        ]
        result = summarize_trace({"traceEvents": events})
        self.assertEqual(result["spans"]["frame"]["n"], 2)
        self.assertEqual(result["spans"]["frame"]["max_ms"], 6)
        self.assertEqual(result["spans"]["paint"]["max_ms"], 1)
        self.assertEqual(result["unmatched_end"], 1)
        self.assertEqual(result["unmatched_begin"], 1)

    def test_journey_cut_at_window_end_is_preserved_outside_full_journey_stats(self):
        rows = [
            {
                "name": "checkout",
                "phase": "measurement",
                "time": 50,
                "duration_ms": 9000,
                "ok": True,
            },
            {
                "name": "checkout",
                "phase": "measurement",
                "time": 100,
                "duration_ms": 442,
                "ok": False,
            },
            {
                "name": "checkout",
                "phase": "measurement",
                "time": 70,
                "duration_ms": 1000,
                "ok": False,
            },
        ]
        result = journeys_summary(rows, 10, 100)
        self.assertEqual(result["boundary_rows"], 1)
        self.assertEqual(result["groups"]["checkout"]["n"], 2)
        self.assertEqual(result["groups"]["checkout"]["failures"], 1)
        self.assertEqual(result["groups"]["checkout"]["p95_ms"], 9000)

    def test_resource_parser_excludes_stale_cpu_and_does_not_fabricate_missing_pss(
        self,
    ):
        rows = [
            {
                "time": 1,
                "memory": "TOTAL PSS: 204800",
                "cpu": "12% com.yallamarket.app.performance",
                "battery": "temperature: 324",
            },
            {
                "time": 6,
                "memory": "TOTAL PSS: 307200",
                "cpu_method": "top second 1-second window",
                "cpu": "123 u0_a1979 10 -10 10G 287M 143M R 9.0 3.7 0:42.29 com.yallamarket.app.performance",
            },
        ]
        result = summarize_resources(rows)
        self.assertEqual(result["current_cpu_samples"], 1)
        self.assertEqual(result["cpu_mean_one_core_percent"], 9)
        self.assertEqual(result["pss_first_mib"], 200)
        self.assertEqual(result["pss_last_mib"], 300)
        self.assertEqual(result["battery_max_c"], 32.4)
        self.assertIsNone(summarize_resources([{"time": 1}])["pss_max_mib"])

    def test_mobile_summary_keeps_bad_round_and_microsecond_actions(self):
        result = summarize_mobile(
            {
                "refresh_hz": 60,
                "completed": True,
                "round1": {
                    "frame_build_times": [1000] * 20,
                    "frame_rasterizer_times": [1000] * 20,
                },
                "round2": {
                    "frame_build_times": [1000] * 19 + [100001],
                    "frame_rasterizer_times": [1000] * 20,
                },
                "observations": {"action_us": [1000] * 29 + [100000]},
            }
        )
        self.assertEqual(len(result["scenarios"]), 2)
        self.assertTrue(result["scenarios"]["round1"]["passes"])
        self.assertFalse(result["scenarios"]["round2"]["passes"])
        self.assertFalse(result["all_recorded_frames_pass"])
        self.assertFalse(result["full_plan_complete"])
        self.assertEqual(result["actions"]["action_us"]["n"], 30)
        self.assertEqual(result["actions"]["action_us"]["p50_ms"], 1)
        self.assertEqual(result["actions"]["action_us"]["p99_ms"], 100)

    def test_only_unterminated_last_json_record_can_be_in_flight(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "requests.jsonl"
            path.write_text('{"ok":true}\n{"ok":', encoding="utf-8")
            self.assertEqual(read_rows(path), [{"ok": True}])
            for content in ('broken\n{"ok":true}\n', '{"ok":true}\nbroken\n'):
                path.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Corrupt measurement"):
                    read_rows(path)

    def test_spike_is_half_full_half_without_restarting_users(self):
        self.assertEqual(spike_target(119.9, 100), (50, 2))
        self.assertEqual(spike_target(120, 100), (100, 100))
        self.assertEqual(spike_target(239.9, 100), (100, 100))
        self.assertEqual(spike_target(240, 100), (50, 100))
        self.assertEqual(spike_target(539.9, 100), (50, 100))
        self.assertIsNone(spike_target(540, 100))

    def test_tail_percentile_uses_raw_samples_not_mean(self):
        stats = distribution([1] * 94 + [100] * 6)
        self.assertEqual(stats["p95_ms"], 100)
        self.assertEqual(stats["n"], 100)

    def test_empty_recording_cannot_pass(self):
        self.assertFalse(frames([])["passes"])
        self.assertIsNone(frames([])["p95_ms"])
        self.assertFalse(classify([], 300, [], complete=True)["stable"])

    def test_frame_budget_tracks_device_refresh(self):
        self.assertTrue(frames([16000] * 100, 60)["passes"])
        self.assertFalse(frames([16000] * 100, 120)["passes"])

    def test_five_percent_is_failure_and_one_long_frame_is_retained(self):
        self.assertFalse(frames([1000] * 95 + [18000] * 5)["passes"])
        stats = frames([1000] * 999 + [101000])
        self.assertFalse(stats["passes"])
        self.assertEqual(stats["max_ms"], 101)

    def test_warmup_is_excluded_and_429_stays_visible(self):
        rows = [
            {
                "name": "home",
                "phase": "warmup",
                "duration_ms": 10000,
                "ok": False,
                "status": 500,
            },
            {
                "name": "home",
                "phase": "measurement",
                "duration_ms": 100,
                "ok": True,
                "status": 200,
            },
            {
                "name": "home",
                "phase": "measurement",
                "duration_ms": 50,
                "ok": False,
                "status": 429,
            },
        ]
        stats = requests_summary(rows, 10)["home"]
        self.assertEqual(stats["n"], 2)
        self.assertEqual(stats["unexpected_failures"], 0)
        self.assertEqual(stats["rate_limited"], 1)
        self.assertEqual(stats["rps"], 0.2)

    def test_missing_checkout_cannot_certify_capacity(self):
        rows = [
            {
                "name": "home",
                "phase": "measurement",
                "duration_ms": 100,
                "ok": True,
                "status": 200,
            }
        ]
        result = classify(rows, 300, [{"errors": [], "ready": True}], complete=True)
        self.assertFalse(result["stable"])
        self.assertIn("order_create", result["missing_endpoints"])

    def test_wrong_data_is_failure_even_with_http_200(self):
        rows = [
            {
                "name": "home",
                "phase": "measurement",
                "duration_ms": 100,
                "ok": False,
                "status": 200,
            }
        ]
        self.assertEqual(requests_summary(rows, 1)["home"]["unexpected_failures"], 1)

    def test_interrupted_run_does_not_pass(self):
        result = classify(
            [], 300, [], complete=False, stop_reason="readiness_failed_twice"
        )
        self.assertFalse(result["complete"])
        self.assertFalse(result["stable"])
        self.assertEqual(result["stop_reason"], "readiness_failed_twice")

    def test_negative_frame_and_invalid_refresh_rejected(self):
        with self.assertRaises(ValueError):
            frames([-1])
        with self.assertRaises(ValueError):
            frames([100], 0)


if __name__ == "__main__":
    unittest.main()
