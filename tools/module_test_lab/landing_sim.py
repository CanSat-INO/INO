"""Deterministic synthetic IMU/pressure traces for individual landing tests.

This is a *reference* demonstration algorithm, NOT an ESP32-S3 Arduino
program, and NOT a verification of any hardware firmware.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import random

SCENARIOS = {
    "normal": ("通常着地", "10秒で接地する基本ケース"),
    "noisy": ("センサーノイズ", "気圧・加速度に比較的大きな測定ノイズ"),
    "false_shock": ("空中で一度衝撃", "着地前の衝撃で誤判定しないか"),
    "soft": ("弱い着地衝撃", "加速度ピークが小さく検知しづらいケース"),
    "pressure_dropout": ("気圧データ欠損", "接地付近の気圧データが一時的に途切れる"),
}
CONTACT_TIME = 10.0

@dataclass
class Config:
    impact_threshold: float = 12.5
    descent_delta_pa: float = 2.0
    stable_delta_pa: float = 0.5
    stable_samples: int = 3


def make_trace(scenario: str, seed: int = 20261025) -> list[dict]:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")
    rng = random.Random(seed)
    trace: list[dict] = []
    noisy = scenario == "noisy"
    for n in range(161):
        t = round(n * .1, 1)
        z_noise = rng.gauss(0, 1.1 if noisy else .18)
        imu = 9.81 + z_noise
        if abs(t - CONTACT_TIME) < .01:
            imu += .8 if scenario == "soft" else 27.0
        if scenario == "false_shock" and abs(t - 4.0) < .01:
            imu += 25.0
        # Pressure increases as altitude decreases; settled after contact.
        has_pressure = n % 10 == 0
        if scenario == "pressure_dropout" and 8.0 <= t <= 12.0:
            has_pressure = False
        pressure = None
        if has_pressure:
            pressure = 101000.0 + 12.0 * min(t, CONTACT_TIME)
            pressure += rng.gauss(0, .22 if noisy else .05)
        trace.append({"time_s": t, "imu_z_mps2": round(imu, 4),
                      "pressure_pa": None if pressure is None else round(pressure, 3),
                      "truth_contact": t >= CONTACT_TIME})
    return trace


def reference_detect(trace: list[dict], cfg: Config) -> dict:
    """Toy detector; resets impact candidate if pressure keeps descending."""
    if (cfg.impact_threshold <= 0 or cfg.descent_delta_pa <= 0 or
        cfg.stable_delta_pa < 0 or cfg.stable_samples < 1):
        raise ValueError("Invalid thresholds")
    descended = False
    last_pressure = None
    impact_candidate = None
    stable_count = 0
    detected_time = None
    impact_events: list[float] = []
    for row in trace:
        t = row["time_s"]
        p = row["pressure_pa"]
        if p is not None:
            if last_pressure is not None:
                delta = p - last_pressure
                if delta > cfg.descent_delta_pa:
                    descended = True
                if impact_candidate is not None:
                    if abs(delta) <= cfg.stable_delta_pa:
                        stable_count += 1
                    else:
                        stable_count = 0
                        # High pressure increase shows descent is still occurring.
                        if delta > cfg.descent_delta_pa:
                            impact_candidate = None
                    if impact_candidate is not None and stable_count >= cfg.stable_samples:
                        detected_time = t
                        break
            last_pressure = p
        if row["imu_z_mps2"] > cfg.impact_threshold and descended:
            if impact_candidate is None:
                impact_candidate = t
                stable_count = 0
                impact_events.append(t)
    passed = (detected_time is not None and
              CONTACT_TIME <= detected_time <= CONTACT_TIME + 5.0)
    return {"detected_time_s": detected_time, "true_contact_s": CONTACT_TIME,
            "delay_s": None if detected_time is None else round(detected_time - CONTACT_TIME, 2),
            "passed": passed, "impact_events_s": impact_events}
