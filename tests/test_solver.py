"""Steady-state solver tests.

Covers the normal operating region, both washout boundaries, the critical
point D == mumax, invalid input rejection and the cross-relationships the
brief demands be pinned by automated tests:

1. in the non-washout region, raising D raises S and lowers X;
2. with no decay term, doubling S0 (approximately) doubles X while S depends
   only on D and is independent of S0;
3. once D crosses mumax, X collapses cleanly to zero (never negative);
4. the critical point D == mumax has dedicated handling (no zero
   denominator).
"""

from __future__ import annotations

import pytest

from app.errors import InvalidParametersError
from app.kinetics import specific_growth_rate
from app.solver import steady_state, sweep_dilution_rate

BASE = dict(D=0.2, s0=200.0, mumax=0.5, ks=10.0, y=0.5)


# --------------------------------------------------------------------------
# Normal operating region
# --------------------------------------------------------------------------

def test_steady_state_matches_hand_calculation():
    r = steady_state(**BASE)
    # S* = Ks D / (mumax - D) = 10 * 0.2 / 0.3 = 6.6667
    assert r.S == pytest.approx(10.0 * 0.2 / 0.3)
    # X* = Y (S0 - S*) = 0.5 * (200 - 6.6667) = 96.6667
    assert r.X == pytest.approx(96.6666666667)
    assert r.washout is False
    assert r.mu == pytest.approx(r.D)  # steady-state identity D = mu


def test_biomass_is_positive_in_growth_region():
    r = steady_state(D=0.4, s0=50.0, mumax=0.8, ks=5.0, y=0.4)
    assert r.X > 0
    assert 0 < r.S < 50.0
    assert r.mu == pytest.approx(0.4)


def test_deterministic_repeated_calls():
    a = steady_state(**BASE)
    b = steady_state(**BASE)
    assert a == b


# --------------------------------------------------------------------------
# Washout boundaries
# --------------------------------------------------------------------------

def test_critical_point_d_equals_mumax_is_washout_no_zero_division():
    r = steady_state(D=0.5, s0=200.0, mumax=0.5, ks=10.0, y=0.5)
    assert r.washout is True
    assert r.X == 0.0
    assert r.S == 200.0
    # The formula's denominator would be zero here; kinetics is still finite.
    assert r.mu == pytest.approx(specific_growth_rate(200.0, 0.5, 10.0))


def test_d_above_mumax_is_washout():
    r = steady_state(D=0.9, s0=200.0, mumax=0.5, ks=10.0, y=0.5)
    assert r.washout is True
    assert r.X == 0.0
    assert r.S == 200.0


def test_far_above_mumax_still_clean_zero():
    r = steady_state(D=1000.0, s0=200.0, mumax=0.5, ks=10.0, y=0.5)
    assert r.X == 0.0
    assert r.S == 200.0
    assert r.washout is True


def test_biomass_never_negative_anywhere():
    for d in [0.001, 0.1, 0.49, 0.5, 0.51, 1.0, 10.0]:
        r = steady_state(D=d, s0=200.0, mumax=0.5, ks=10.0, y=0.5)
        assert r.X >= 0.0


def test_washout_when_formula_predicts_nonpositive_biomass():
    # D < mumax, but S* = Ks D / (mumax - D) >= S0 means the non-trivial
    # branch would demand X* <= 0 -> still washout.
    # Ks=10, D=0.4, mumax=0.5 -> S* = 40. Choose S0 = 40 (== S*).
    r = steady_state(D=0.4, s0=40.0, mumax=0.5, ks=10.0, y=0.5)
    assert r.washout is True
    assert r.X == 0.0
    assert r.S == 40.0

    # And S0 even smaller:
    r2 = steady_state(D=0.4, s0=5.0, mumax=0.5, ks=10.0, y=0.5)
    assert r2.washout is True
    assert r2.X == 0.0
    assert r2.S == 5.0


def test_zero_influent_substrate_steady_region():
    # No food in, no biomass out, S* = 0; classify as washout (X = 0).
    r = steady_state(D=0.1, s0=0.0, mumax=0.5, ks=10.0, y=0.5)
    assert r.washout is True
    assert r.X == 0.0
    assert r.S == 0.0
    assert r.mu == 0.0


# --------------------------------------------------------------------------
# Cross-relationships pinned by the brief
# --------------------------------------------------------------------------

def test_raising_d_raises_s_and_lowers_x_before_washout():
    # Washout threshold for this case is D_c = mumax*S0/(Ks+S0) ~= 0.4762,
    # so stay clearly below it.
    rates = [0.05, 0.1, 0.2, 0.3, 0.4, 0.45]
    results = [
        steady_state(D=d, s0=200.0, mumax=0.5, ks=10.0, y=0.5)
        for d in rates
    ]
    assert all(not r.washout for r in results)
    s_values = [r.S for r in results]
    x_values = [r.X for r in results]
    assert all(a < b for a, b in zip(s_values, s_values[1:]))
    assert all(a > b for a, b in zip(x_values, x_values[1:]))
    # mu tracks D exactly throughout the growth region.
    assert all(r.mu == pytest.approx(r.D) for r in results)


def test_doubling_s0_doubles_x_but_s_unchanged():
    # Large S0 relative to S* makes X* = Y(S0 - S*) almost exactly proportional.
    low = steady_state(D=0.15, s0=1000.0, mumax=0.5, ks=10.0, y=0.5)
    high = steady_state(D=0.15, s0=2000.0, mumax=0.5, ks=10.0, y=0.5)
    # S* is set by D alone.
    assert high.S == pytest.approx(low.S)
    # X* = Y (S0 - S*) nearly doubles when S0 >> S*.
    assert high.X == pytest.approx(2.0 * low.X, rel=0.01)
    assert not low.washout and not high.washout


def test_s_independent_of_s0_across_values():
    s0_values = [50.0, 100.0, 500.0, 5000.0]
    s_stars = {
        s0: steady_state(D=0.25, s0=s0, mumax=0.6, ks=8.0, y=0.4).S
        for s0 in s0_values
    }
    first = s_stars[s0_values[0]]
    for s0 in s0_values[1:]:
        assert s_stars[s0] == pytest.approx(first)


def test_x_collapses_to_zero_crossing_mumax():
    # Immediately below the boundary X is positive; at/above it X == 0.
    # Use a high S0 so that D = 0.499 is not additionally beyond the
    # S* >= S0 washout threshold (D_c ~= 0.4995 here).
    below = steady_state(D=0.49, s0=10000.0, mumax=0.5, ks=10.0, y=0.5)
    at = steady_state(D=0.5, s0=10000.0, mumax=0.5, ks=10.0, y=0.5)
    above = steady_state(D=0.51, s0=10000.0, mumax=0.5, ks=10.0, y=0.5)
    assert below.X > 0 and below.washout is False
    assert at.X == 0.0 and at.washout is True
    assert above.X == 0.0 and above.washout is True


# --------------------------------------------------------------------------
# Invalid parameters
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"D": 0.0}, "D"),
        ({"D": -1.0}, "D"),
        ({"mumax": 0.0}, "mumax"),
        ({"mumax": -0.5}, "mumax"),
        ({"ks": 0.0}, "Ks"),
        ({"ks": -3.0}, "Ks"),
        ({"y": 0.0}, "Y"),
        ({"y": -0.1}, "Y"),
        ({"s0": -0.001}, "S0"),
    ],
)
def test_invalid_scalar_parameters_rejected(overrides, field):
    params = {**BASE, **overrides}
    with pytest.raises(InvalidParametersError) as exc:
        steady_state(**params)
    assert field in exc.value.details["reasons"]


def test_multiple_bad_fields_all_reported():
    with pytest.raises(InvalidParametersError) as exc:
        steady_state(D=-1, s0=-5, mumax=0, ks=0, y=0)
    assert set(exc.value.details["reasons"]) == {"D", "S0", "mumax", "Ks", "Y"}


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_parameters_rejected(bad):
    with pytest.raises(InvalidParametersError) as exc:
        steady_state(D=bad, s0=200.0, mumax=0.5, ks=10.0, y=0.5)
    assert "D" in exc.value.details["reasons"]


def test_bool_is_not_a_valid_parameter():
    with pytest.raises(InvalidParametersError):
        steady_state(D=True, s0=200.0, mumax=0.5, ks=10.0, y=0.5)  # noqa: FBT003


# --------------------------------------------------------------------------
# Sweep
# --------------------------------------------------------------------------

def test_sweep_point_count_inclusive_endpoint():
    pts = sweep_dilution_rate(
        d_start=0.1, d_stop=0.5, d_step=0.1,
        s0=200.0, mumax=0.5, ks=10.0, y=0.5, max_points=1000,
    )
    assert len(pts) == 5
    assert pts[0].D == pytest.approx(0.1)
    assert pts[-1].D == pytest.approx(0.5)


def test_sweep_zero_length_interval_is_single_point():
    pts = sweep_dilution_rate(
        d_start=0.2, d_stop=0.2, d_step=0.1,
        s0=200.0, mumax=0.5, ks=10.0, y=0.5, max_points=1000,
    )
    assert len(pts) == 1
    assert pts[0].D == pytest.approx(0.2)


def test_sweep_non_multiple_interval_does_not_extrapolate_past_stop():
    pts = sweep_dilution_rate(
        d_start=0.1, d_stop=0.35, d_step=0.1,
        s0=10000.0, mumax=0.5, ks=10.0, y=0.5, max_points=1000,
    )
    assert len(pts) == 3
    assert [round(p.D, 6) for p in pts] == [0.1, 0.2, 0.3]
    assert all(p.D <= 0.35 for p in pts)


def test_sweep_shows_x_decline_then_zero_and_snap_to_stop():
    pts = sweep_dilution_rate(
        d_start=0.1, d_stop=0.6, d_step=0.1,
        s0=200.0, mumax=0.5, ks=10.0, y=0.5, max_points=1000,
    )
    assert [round(p.D, 6) for p in pts] == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    # X strictly decreases while biomass survives, then stays exactly zero.
    biomass = [p.X for p in pts]
    surviving = biomass[:4]  # D = 0.1..0.4 all below the washout boundary
    assert all(a > b for a, b in zip(surviving, surviving[1:]))
    assert biomass[4] == 0.0 and biomass[5] == 0.0
    assert pts[4].X == 0.0 and pts[4].washout is True  # D == mumax
    assert pts[5].X == 0.0 and pts[5].washout is True
    assert pts[5].S == 200.0
    # Every washout-transition point is monotone-safe; S never exceeds S0.
    assert all(0.0 <= p.S <= 200.0 for p in pts)


def test_sweep_fully_below_washout_all_positive():
    pts = sweep_dilution_rate(
        d_start=0.05, d_stop=0.2, d_step=0.05,
        s0=300.0, mumax=0.8, ks=10.0, y=0.5, max_points=1000,
    )
    assert all(p.X > 0 and not p.washout for p in pts)


def test_sweep_fully_above_washout_all_zero():
    pts = sweep_dilution_rate(
        d_start=0.9, d_stop=1.2, d_step=0.1,
        s0=100.0, mumax=0.5, ks=10.0, y=0.5, max_points=1000,
    )
    assert all(p.X == 0.0 and p.washout for p in pts)
    assert all(p.S == 100.0 for p in pts)


def test_sweep_rejects_bad_range():
    with pytest.raises(InvalidParametersError):
        sweep_dilution_rate(
            d_start=0.5, d_stop=0.1, d_step=0.1,
            s0=100.0, mumax=0.5, ks=10.0, y=0.5, max_points=1000,
        )
    with pytest.raises(InvalidParametersError):
        sweep_dilution_rate(
            d_start=0.1, d_stop=0.5, d_step=0.0,
            s0=100.0, mumax=0.5, ks=10.0, y=0.5, max_points=1000,
        )


def test_sweep_rejects_too_many_points():
    with pytest.raises(InvalidParametersError) as exc:
        sweep_dilution_rate(
            d_start=0.0001, d_stop=100.0, d_step=0.00001,
            s0=100.0, mumax=0.5, ks=10.0, y=0.5, max_points=1000,
        )
    assert "D_step" in exc.value.details["reasons"]


def test_sweep_rejects_invalid_process_params():
    with pytest.raises(InvalidParametersError):
        sweep_dilution_rate(
            d_start=0.1, d_stop=0.5, d_step=0.1,
            s0=-1.0, mumax=0.5, ks=10.0, y=0.5, max_points=1000,
        )
