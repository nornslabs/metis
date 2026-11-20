"""The written scale behind each rubric parameter: what a mark of 2, 5, 8 and 10 means.

The weights are not here: they come from the ``scoring`` module. Marks between two anchors
are allowed (0-1, 3-4, 6-7, 9).
"""

from __future__ import annotations

from types import MappingProxyType

from metis.modules.scoring import ScoreParam

SCALE: MappingProxyType[ScoreParam, MappingProxyType[int, str]] = MappingProxyType(
    {
        ScoreParam.PROBLEM_SEVERITY: MappingProxyType(
            {
                2: "Nice to have; few people notice the problem.",
                5: "A real, recurring annoyance; workarounds exist.",
                8: "Costly or painful; people already pay or spend time on it.",
                10: "Urgent, frequent, expensive and hard to ignore.",
            }
        ),
        ScoreParam.UNIQUENESS: MappingProxyType(
            {
                2: "Many strong incumbents do the same thing.",
                5: "A crowded market, but there is a clear gap.",
                8: "Few, weak competitors and a clear difference.",
                10: "No direct competitor and a defensible angle.",
            }
        ),
        ScoreParam.MARKET_DEMAND: MappingProxyType(
            {
                2: "No sign of demand.",
                5: "Some demand signals; a small market.",
                8: "Clear, growing demand and a sizeable market.",
                10: "A large, fast-growing market with many paying customers.",
            }
        ),
        ScoreParam.VALUE: MappingProxyType(
            {
                2: "A marginal benefit.",
                5: "A clear but modest benefit.",
                8: "A large benefit; users would switch for it.",
                10: "Transformative; the payback is obvious.",
            }
        ),
        ScoreParam.FEASIBILITY: MappingProxyType(
            {
                2: "Needs technology, approval or capital that is not at hand.",
                5: "Doable by a small team, with real risk.",
                8: "Standard technology, a small team and few unknowns.",
                10: "Quick to build with proven tools.",
            }
        ),
        ScoreParam.TIMING: MappingProxyType(
            {
                2: "Too early, or the market is shrinking.",
                5: "Neutral.",
                8: "A clear trend or enabler is arriving.",
                10: "A strong tailwind right now.",
            }
        ),
    }
)
