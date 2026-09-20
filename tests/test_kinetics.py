"""Tests for the pure Monod kinetics kernel."""

from __future__ import annotations

import math

import pytest

from app.kinetics import specific_growth_rate


def test_monod_zero_substrate_is_zero():
    assert specific_growth_rate(0.0, 0.5, 10.0) == 0.0


def test_monod_half_saturation_equals_half_mumax():
    # At S = Ks, mu = mumax / 2 exactly.
    assert specific_growth_rate(10.0, 0.5, 10.0) == pytest.approx(0.25)


def test_monod_asymptotes_to_mumax():
    # mu -> mumax as S -> inf; at S = 1e6 the residual is Ks/(Ks+S) ~ 1e-5.
    assert specific_growth_rate(1e6, 0.5, 10.0) == pytest.approx(0.5, abs=1e-5)


def test_monod_monotone_in_substrate():
    samples = [specific_growth_rate(s, 0.7, 20.0) for s in range(1, 100)]
    assert all(a < b for a, b in zip(samples, samples[1:]))


def test_monod_formula_values():
    # mu = 0.5 * 30 / (10 + 30) = 0.375
    assert specific_growth_rate(30.0, 0.5, 10.0) == pytest.approx(0.375)
    assert math.isfinite(specific_growth_rate(30.0, 0.5, 10.0))
