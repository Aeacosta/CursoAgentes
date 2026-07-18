"""
dashboard/score_calculator.py
------------------------------
Translates the LLM's qualitative `severidad` labels into numeric scores
and derives the overall code quality score.

This module owns all scoring logic so that app.py and worker.py stay free
of arithmetic concerns (Single Responsibility Principle).
"""

from __future__ import annotations


# Severity label → 0-100 impact value (higher = more damaging to quality).
_SEVERITY_IMPACT: dict[str, int] = {
    "critico": 85,
    "mayor":   55,
    "menor":   20,
}

_DEFAULT_IMPACT = _SEVERITY_IMPACT["mayor"]


class ScoreCalculator:
    """
    Enriches a parsed LLM report dict with numeric scores.

    Responsibilities
    ----------------
    - Map each smell's `severidad` string to a `metrica` integer (0–100).
    - Derive `puntuacion_general` as 100 − mean(impact values).
      High severity → low overall quality score.

    Usage
    -----
        enriched = ScoreCalculator().enrich(parsed_dict)
    """

    def enrich(self, report: dict) -> dict:
        """
        Mutates `report` in-place: adds `metrica` to every reporte entry
        and sets `puntuacion_general` at the top level.

        Parameters
        ----------
        report : dict
            Parsed JSON dict as returned by the LLM (must contain "reporte").

        Returns
        -------
        The same dict, now with numeric score fields populated.
        """
        smells = report.get("reporte") or report.get("report") or []
        impacts = []

        for row in smells:
            sev    = str(row.get("severidad", "")).strip().lower()
            impact = _SEVERITY_IMPACT.get(sev, _DEFAULT_IMPACT)
            row["metrica"] = impact
            impacts.append(impact)

        report["puntuacion_general"] = self._overall(impacts)
        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _overall(impacts: list[int]) -> int:
        """100 − mean(impacts), clamped to [0, 100]."""
        if not impacts:
            return 100
        return max(0, min(100, round(100 - sum(impacts) / len(impacts))))
