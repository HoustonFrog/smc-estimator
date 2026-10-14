"""数据导入和新政后情景的回归检查。运行：python3 -m unittest discover -s scripts。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import smc_model_v2 as smc
import build_web_data as web


class DataLoadingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.raw = Path(self.temp.name)
        dates = ["2026-01-31", "2026-02-28", "2026-03-31"]
        self.frames = {}
        for kind, filename in {
            "R1": "R1_Residence_Decisions_by_Decision_Type_and_Application_Substream.csv",
            "R7": "R7_Residence_Accepted_by_Application_Stream.csv",
            "R8": "R8_Residence_On_Hand_by_Application_Stream.csv",
        }.items():
            rows = []
            for date in dates:
                if kind == "R1":
                    rows.extend([
                        [date, "SMC Skilled Residence", "Approved", 12],
                        [date, "SMC Skilled Residence", "Declined", 3],
                        [date, "Other", "Approved", 900],
                    ])
                else:
                    rows.extend([[date, "SMC Skilled Residence", 30 if kind == "R7" else 60],
                                 [date, "Other", 600]])
            columns = ["Date", "Application Substream"]
            if kind == "R1":
                columns.append("Decision Type")
            columns.append("Count")
            self.frames[kind] = (filename, pd.DataFrame(rows, columns=columns))
        self.write_frames()

    def tearDown(self):
        self.temp.cleanup()

    def write_frames(self):
        for filename, frame in self.frames.values():
            frame.to_csv(self.raw / filename, index=False)

    def test_other_residence_categories_never_enter_smc_series(self):
        dec, acc, oh = smc.load(str(self.raw) + "/")
        self.assertEqual(dec.tolist(), [15, 15, 15])
        self.assertEqual(acc.tolist(), [30, 30, 30])
        self.assertEqual(oh.tolist(), [60, 60, 60])

    def test_duplicate_decision_key_is_rejected(self):
        filename, frame = self.frames["R1"]
        self.frames["R1"] = filename, pd.concat([frame, frame.iloc[[0]]])
        self.write_frames()
        with self.assertRaises(ValueError):
            smc.load(str(self.raw) + "/")

    def test_missing_acceptance_month_is_rejected(self):
        filename, frame = self.frames["R7"]
        self.frames["R7"] = filename, frame[frame.Date != "2026-02-28"]
        self.write_frames()
        with self.assertRaises(ValueError):
            smc.load(str(self.raw) + "/")

    def test_previous_month_guard_understands_generated_javascript(self):
        html = web.DATA_START + '\nconst DATASETS = {CN: {series: {months: ["2026-08", "2026-09"]}}};\n' + web.DATA_END
        self.assertEqual(web.read_prev_datasets(html), {"CN": 2})


class ScenarioTests(unittest.TestCase):
    def test_latest_low_capacity_month_sets_initial_state(self):
        periods = pd.period_range("2025-01", "2026-09", freq="M")
        decisions = pd.Series([240 * smc.s_of(p) for p in periods], index=periods)
        decisions.iloc[-1] = 84
        with patch.object(smc, "DEC", decisions, create=True):
            par = smc.estimate(periods[-1], look=3)
        self.assertTrue(par.get("initial_disrupted", False))

    def test_temporary_low_capacity_state_can_continue_or_recover(self):
        par = dict(mu=240, sd_mu=0, pool=np.ones(6), p_enter=0, p_exit=0,
                   lo=0.3, initial_disrupted=True, g=0, sd_g=0)
        _, _, paths = smc.simulate(par, 100, 0, "2026-10", n=4, H=2)
        np.testing.assert_allclose(paths, 72)
        par["p_exit"] = 1
        _, _, recovered = smc.simulate(par, 100, 0, "2026-10", n=4, H=2)
        np.testing.assert_allclose(recovered, 240)

    def test_unfinished_low_capacity_episode_does_not_imply_faster_recovery(self):
        periods = pd.period_range("2025-01", "2026-09", freq="M")
        decisions = pd.Series([240 * smc.s_of(p) for p in periods], index=periods)
        decisions.loc['2025-09':'2025-10'] = 84
        decisions.iloc[-1] = 84
        with patch.object(smc, "DEC", decisions, create=True):
            par = smc.estimate(periods[-1], look=3)
        self.assertAlmostEqual(par['p_exit'], 0.5,
                               msg='9 月未结束的低谷不能被当作已完成的 1 个月冲击')

    def test_arrivals_revert_to_pre_policy_level_at_selected_half_life(self):
        periods = pd.period_range("2026-02", "2026-09", freq="M")
        acc = pd.Series([177, 189, 216, 222, 192, 210, 1041, 792], index=periods)
        assumptions = getattr(smc, "acceptance_assumptions", None)
        mean = getattr(smc, "acceptance_mean", None)
        self.assertIsNotNone(assumptions, "需要显式的受理量回归情景，不能混抽新旧制度月份")
        self.assertIsNotNone(mean)
        with patch.object(smc, "ACC", acc, create=True):
            cfg, pool = assumptions(periods[-1])
        self.assertEqual(pool.tolist(), [177, 189, 216, 222, 192, 210])
        self.assertEqual(cfg["baseline"], 201)
        self.assertEqual(cfg["latest"], 792)
        self.assertEqual(cfg["halfLifeMonths"], 3)
        self.assertEqual(mean(cfg, 0), 792)
        self.assertEqual(mean(cfg, 3), 496.5)
        self.assertEqual(mean(cfg, 6, half_life=6), 496.5)
        self.assertAlmostEqual(mean(cfg, 120), 201, places=6)


if __name__ == "__main__":
    unittest.main()
