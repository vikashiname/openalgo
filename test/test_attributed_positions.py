"""
Unit and integration tests for Strategy-Attributed Positions and Broker Reconciliation.

Tests all 10 mandatory scenarios:
1. One strategy, one symbol.
2. Two strategies, different symbols.
3. Two strategies, SAME symbol and SAME direction.
4. Two strategies, SAME symbol and OPPOSITE directions.
5. Partial fills.
6. Multiple entries/exits.
7. Manual/unattributed residual.
8. Zero broker quantity with active strategy positions.
9. No strategy records.
10. Empty position book.

For every test, asserts:
  SUM(strategy quantities) + residual == broker quantity
"""

import pytest
from services.attributed_positions_service import reconcile_positions, get_attributed_positions


def _sum_quantities(contract_summary: dict, positions: list) -> tuple:
    """Helper to compute sum of strategy quantities and residual for a contract."""
    sym = contract_summary["symbol"]
    exch = contract_summary["exchange"]
    prod = contract_summary["product"]

    strat_qty_sum = 0.0
    residual_qty = 0.0

    for p in positions:
        if (
            p["symbol"] == sym
            and p["exchange"] == exch
            and p["product"] == prod
        ):
            if p["strategy"] == "Manual / Unattributed":
                residual_qty += p["signed_quantity"]
            else:
                strat_qty_sum += p["signed_quantity"]

    return round(strat_qty_sum, 4), round(residual_qty, 4)


def test_scenario_1_one_strategy_one_symbol():
    """Scenario 1: One strategy, one symbol."""
    broker_positions = [
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 100.0,
            "average_price": 500.0,
            "ltp": 510.0,
            "pnl": 1000.0,
        }
    ]
    strategy_legs = [
        {
            "strategy": "MOMENTUM_V1",
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 100.0,
            "average_price": 500.0,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        }
    ]

    result = reconcile_positions(broker_positions, strategy_legs)
    contracts = result["contracts"]
    positions = result["positions"]

    assert len(contracts) == 1
    c = contracts[0]
    assert c["broker_quantity"] == 100.0
    assert c["tracked_quantity"] == 100.0
    assert c["residual_quantity"] == 0.0
    assert c["reconciliation_status"] == "RECONCILED"

    strat_sum, residual = _sum_quantities(c, positions)
    assert round(strat_sum + residual, 4) == c["broker_quantity"]

    assert len(positions) == 1
    p = positions[0]
    assert p["strategy"] == "MOMENTUM_V1"
    assert p["side"] == "LONG"
    assert p["quantity"] == 100.0
    assert p["unrealized_pnl"] == 1000.0  # 100 * (510 - 500)


def test_scenario_2_two_strategies_different_symbols():
    """Scenario 2: Two strategies, different symbols."""
    broker_positions = [
        {
            "symbol": "INFY",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 50.0,
            "average_price": 1500.0,
            "ltp": 1520.0,
            "pnl": 1000.0,
        },
        {
            "symbol": "TCS",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": -30.0,
            "average_price": 3500.0,
            "ltp": 3480.0,
            "pnl": 600.0,
        },
    ]
    strategy_legs = [
        {
            "strategy": "TECH_LONG",
            "symbol": "INFY",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 50.0,
            "average_price": 1500.0,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        },
        {
            "strategy": "TECH_SHORT",
            "symbol": "TCS",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": -30.0,
            "average_price": 3500.0,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        },
    ]

    result = reconcile_positions(broker_positions, strategy_legs)
    contracts = result["contracts"]
    positions = result["positions"]

    assert len(contracts) == 2
    for c in contracts:
        strat_sum, residual = _sum_quantities(c, positions)
        assert round(strat_sum + residual, 4) == c["broker_quantity"]
        assert c["reconciliation_status"] == "RECONCILED"
        assert c["residual_quantity"] == 0.0


def test_scenario_3_two_strategies_same_symbol_same_direction():
    """Scenario 3: Two strategies, SAME symbol and SAME direction (user's exact example)."""
    broker_positions = [
        {
            "symbol": "BANKBARODA",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": -2925.0,
            "average_price": 22.54,
            "ltp": 22.40,
            "pnl": 409.50,
        }
    ]
    strategy_legs = [
        {
            "strategy": "ICHI_V2",
            "symbol": "BANKBARODA",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": -1500.0,
            "average_price": 22.50,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        },
        {
            "strategy": "MACD_FNO",
            "symbol": "BANKBARODA",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": -1425.0,
            "average_price": 22.60,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        },
    ]

    result = reconcile_positions(broker_positions, strategy_legs)
    contracts = result["contracts"]
    positions = result["positions"]

    assert len(contracts) == 1
    c = contracts[0]
    assert c["broker_quantity"] == -2925.0
    assert c["tracked_quantity"] == -2925.0
    assert c["residual_quantity"] == 0.0
    assert c["reconciliation_status"] == "RECONCILED"

    strat_sum, residual = _sum_quantities(c, positions)
    assert round(strat_sum + residual, 4) == c["broker_quantity"]

    # Must NOT assign all 2925 to one strategy
    assert len(positions) == 2
    ichi = next(p for p in positions if p["strategy"] == "ICHI_V2")
    macd = next(p for p in positions if p["strategy"] == "MACD_FNO")

    assert ichi["signed_quantity"] == -1500.0
    assert ichi["side"] == "SHORT"
    assert ichi["quantity"] == 1500.0
    assert ichi["average_price"] == 22.50
    assert ichi["unrealized_pnl"] == 150.0  # -1500 * (22.40 - 22.50)

    assert macd["signed_quantity"] == -1425.0
    assert macd["side"] == "SHORT"
    assert macd["quantity"] == 1425.0
    assert macd["average_price"] == 22.60
    assert macd["unrealized_pnl"] == 285.0  # -1425 * (22.40 - 22.60)


def test_scenario_4_two_strategies_same_symbol_opposite_directions():
    """Scenario 4: Two strategies, SAME symbol and OPPOSITE directions (Broker net is 0)."""
    broker_positions = []  # Broker position is net zero / absent from Fyers book
    strategy_legs = [
        {
            "strategy": "ICHI_V2",
            "symbol": "BANKBARODA",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 100.0,
            "average_price": 22.50,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        },
        {
            "strategy": "MACD_FNO",
            "symbol": "BANKBARODA",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": -100.0,
            "average_price": 22.60,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        },
    ]

    result = reconcile_positions(broker_positions, strategy_legs)
    contracts = result["contracts"]
    positions = result["positions"]

    assert len(contracts) == 1
    c = contracts[0]
    assert c["broker_quantity"] == 0.0
    assert c["tracked_quantity"] == 0.0
    assert c["residual_quantity"] == 0.0
    assert c["reconciliation_status"] == "RECONCILED"

    strat_sum, residual = _sum_quantities(c, positions)
    assert round(strat_sum + residual, 4) == c["broker_quantity"]

    # Both strategy positions must be preserved
    assert len(positions) == 2
    ichi = next(p for p in positions if p["strategy"] == "ICHI_V2")
    macd = next(p for p in positions if p["strategy"] == "MACD_FNO")

    assert ichi["signed_quantity"] == 100.0
    assert ichi["side"] == "LONG"
    assert macd["signed_quantity"] == -100.0
    assert macd["side"] == "SHORT"


def test_scenario_5_partial_fills():
    """Scenario 5: Partial fills properly accounted for."""
    broker_positions = [
        {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product": "NRML",
            "quantity": 400.0,
            "average_price": 2900.0,
            "ltp": 2950.0,
            "pnl": 20000.0,
        }
    ]
    # Strategy placed 1000, but only 400 filled so far
    strategy_legs = [
        {
            "strategy": "BREAKOUT",
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product": "NRML",
            "quantity": 400.0,
            "average_price": 2900.0,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        }
    ]

    result = reconcile_positions(broker_positions, strategy_legs)
    contracts = result["contracts"]
    positions = result["positions"]

    c = contracts[0]
    strat_sum, residual = _sum_quantities(c, positions)
    assert round(strat_sum + residual, 4) == c["broker_quantity"]
    assert c["residual_quantity"] == 0.0
    assert c["reconciliation_status"] == "RECONCILED"


def test_scenario_6_multiple_entries_exits():
    """Scenario 6: Multiple entries/exits with accumulated realized P&L."""
    broker_positions = [
        {
            "symbol": "NIFTY26SEP24000CE",
            "exchange": "NFO",
            "product": "NRML",
            "quantity": 100.0,
            "average_price": 150.0,
            "ltp": 160.0,
            "pnl": 1000.0,
        }
    ]
    # Strategy previously realized 5000 from partial exits, remaining open 100 @ 150
    strategy_legs = [
        {
            "strategy": "OPTION_SELLER",
            "symbol": "NIFTY26SEP24000CE",
            "exchange": "NFO",
            "product": "NRML",
            "quantity": 100.0,
            "average_price": 150.0,
            "realized_pnl": 5000.0,
            "today_realized_pnl": 5000.0,
        }
    ]

    result = reconcile_positions(broker_positions, strategy_legs)
    contracts = result["contracts"]
    positions = result["positions"]

    c = contracts[0]
    strat_sum, residual = _sum_quantities(c, positions)
    assert round(strat_sum + residual, 4) == c["broker_quantity"]

    p = positions[0]
    assert p["realized_pnl"] == 5000.0
    assert p["unrealized_pnl"] == 1000.0  # 100 * (160 - 150)
    assert p["total_pnl"] == 6000.0


def test_scenario_7_manual_unattributed_residual():
    """Scenario 7: Manual/unattributed residual (user's exact example)."""
    broker_positions = [
        {
            "symbol": "BANKBARODA",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": -3025.0,
            "average_price": 22.55,
            "ltp": 22.40,
            "pnl": 453.75,
        }
    ]
    strategy_legs = [
        {
            "strategy": "ICHI_V2",
            "symbol": "BANKBARODA",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": -1500.0,
            "average_price": 22.50,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        },
        {
            "strategy": "MACD_FNO",
            "symbol": "BANKBARODA",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": -1425.0,
            "average_price": 22.60,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        },
    ]

    result = reconcile_positions(broker_positions, strategy_legs)
    contracts = result["contracts"]
    positions = result["positions"]

    assert len(contracts) == 1
    c = contracts[0]
    assert c["broker_quantity"] == -3025.0
    assert c["tracked_quantity"] == -2925.0
    assert c["residual_quantity"] == -100.0
    assert c["has_residual"] is True
    assert c["reconciliation_status"] == "RECONCILED"

    strat_sum, residual = _sum_quantities(c, positions)
    assert round(strat_sum + residual, 4) == c["broker_quantity"]

    # Manual / Unattributed row must be present
    assert len(positions) == 3
    manual = next(p for p in positions if p["strategy"] == "Manual / Unattributed")
    assert manual["signed_quantity"] == -100.0
    assert manual["quantity"] == 100.0
    assert manual["side"] == "SHORT"
    assert manual["average_price"] == 22.55
    assert manual["unrealized_pnl"] == 15.0  # -100 * (22.40 - 22.55)


def test_scenario_8_zero_broker_quantity_with_active_strategy():
    """Scenario 8: Zero broker quantity with active strategy positions (e.g. external square-off)."""
    broker_positions = [
        {
            "symbol": "TATASTEEL",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 150.0,
            "pnl": 0.0,
        }
    ]
    strategy_legs = [
        {
            "strategy": "ALPHA_1",
            "symbol": "TATASTEEL",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 500.0,
            "average_price": 145.0,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        }
    ]

    result = reconcile_positions(broker_positions, strategy_legs)
    contracts = result["contracts"]
    positions = result["positions"]

    c = contracts[0]
    assert c["broker_quantity"] == 0.0
    assert c["tracked_quantity"] == 500.0
    assert c["residual_quantity"] == -500.0
    assert c["reconciliation_status"] == "RECONCILED"

    strat_sum, residual = _sum_quantities(c, positions)
    assert round(strat_sum + residual, 4) == c["broker_quantity"]

    manual = next(p for p in positions if p["strategy"] == "Manual / Unattributed")
    assert manual["signed_quantity"] == -500.0
    assert manual["side"] == "SHORT"


def test_scenario_9_no_strategy_records():
    """Scenario 9: No strategy records (100% manual broker positions)."""
    broker_positions = [
        {
            "symbol": "HDFCBANK",
            "exchange": "NSE",
            "product": "CNC",
            "quantity": 250.0,
            "average_price": 1600.0,
            "ltp": 1650.0,
            "pnl": 12500.0,
        }
    ]
    strategy_legs = []

    result = reconcile_positions(broker_positions, strategy_legs)
    contracts = result["contracts"]
    positions = result["positions"]

    assert len(contracts) == 1
    c = contracts[0]
    assert c["broker_quantity"] == 250.0
    assert c["tracked_quantity"] == 0.0
    assert c["residual_quantity"] == 250.0
    assert c["reconciliation_status"] == "RECONCILED"

    strat_sum, residual = _sum_quantities(c, positions)
    assert round(strat_sum + residual, 4) == c["broker_quantity"]

    assert len(positions) == 1
    manual = positions[0]
    assert manual["strategy"] == "Manual / Unattributed"
    assert manual["signed_quantity"] == 250.0
    assert manual["side"] == "LONG"
    assert manual["average_price"] == 1600.0
    assert manual["unrealized_pnl"] == 12500.0


def test_scenario_10_empty_position_book():
    """Scenario 10: Empty position book."""
    broker_positions = []
    strategy_legs = []

    result = reconcile_positions(broker_positions, strategy_legs)
    contracts = result["contracts"]
    positions = result["positions"]
    summary = result["summary"]

    assert len(contracts) == 0
    assert len(positions) == 0
    assert summary["total_broker_positions"] == 0
    assert summary["total_tracked_positions"] == 0
    assert summary["total_residual_positions"] == 0
    assert summary["reconciliation_status"] == "RECONCILED"


def test_service_with_overrides():
    """Test get_attributed_positions service method with overrides."""
    broker_positions = [
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 100.0,
            "average_price": 500.0,
            "ltp": 510.0,
        }
    ]
    strategy_legs = [
        {
            "strategy": "TEST_STRAT",
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 100.0,
            "average_price": 500.0,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        }
    ]

    ok, resp, code = get_attributed_positions(
        api_key="mock-key",
        broker_positions_override=broker_positions,
        strategy_legs_override=strategy_legs,
    )

    assert ok is True
    assert code == 200
    assert resp["status"] == "success"
    assert len(resp["data"]["positions"]) == 1
    assert resp["data"]["positions"][0]["strategy"] == "TEST_STRAT"


def test_missing_api_key_rejected():
    """Test that missing API key is rejected."""
    ok, resp, code = get_attributed_positions(api_key="")
    assert ok is False
    assert code == 400
    assert "API key is required" in resp["message"]


def test_api_v1_positions_attributed_endpoint(monkeypatch):
    """Test the Flask REST API endpoint directly via test client."""
    from flask import Flask
    from flask_restx import Api
    from limiter import limiter
    from restx_api.attributed_positions import api as attributed_ns
    import services.attributed_positions_service as svc

    monkeypatch.setattr(limiter, "enabled", False)

    app = Flask(__name__)
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=False)
    api = Api(app)
    api.add_namespace(attributed_ns, path="/api/v1/positions/attributed")
    api.add_namespace(attributed_ns, path="/api/v1/positionbook/attributed")
    client = app.test_client()

    # 1. Missing apikey returns 400
    res_bad = client.post("/api/v1/positions/attributed/", json={})
    assert res_bad.status_code == 400
    assert res_bad.json["status"] == "error"

    # 2. Mock service call
    def mock_get(api_key, strategy=None, include_zero_residual=False):
        return True, {
            "status": "success",
            "data": {
                "positions": [
                    {
                        "strategy": "ICHI_V2",
                        "symbol": "BANKBARODA",
                        "exchange": "NSE",
                        "product": "MIS",
                        "signed_quantity": -1500.0,
                        "side": "SHORT",
                        "quantity": 1500.0,
                        "average_price": 22.50,
                        "ltp": 22.40,
                        "realized_pnl": 0.0,
                        "today_realized_pnl": 0.0,
                        "unrealized_pnl": 150.0,
                        "total_pnl": 150.0,
                        "pnlpercent": 0.44,
                        "broker_quantity": -2925.0,
                        "tracked_quantity": -2925.0,
                        "residual_quantity": 0.0,
                        "reconciliation_status": "RECONCILED",
                    }
                ],
                "contracts": [
                    {
                        "symbol": "BANKBARODA",
                        "exchange": "NSE",
                        "product": "MIS",
                        "broker_quantity": -2925.0,
                        "tracked_quantity": -2925.0,
                        "residual_quantity": 0.0,
                        "has_residual": False,
                        "strategies_count": 1,
                        "reconciliation_status": "RECONCILED",
                    }
                ],
                "summary": {
                    "total_broker_positions": 1,
                    "total_tracked_positions": 1,
                    "total_residual_positions": 0,
                    "total_realized_pnl": 0.0,
                    "total_unrealized_pnl": 150.0,
                    "total_pnl": 150.0,
                    "reconciliation_status": "RECONCILED",
                },
            },
        }, 200

    monkeypatch.setattr("restx_api.attributed_positions.get_attributed_positions", mock_get)

    res_good = client.post("/api/v1/positions/attributed/", json={"apikey": "test-key-123"})
    assert res_good.status_code == 200
    assert res_good.json["status"] == "success"
    assert len(res_good.json["data"]["positions"]) == 1
    assert res_good.json["data"]["positions"][0]["strategy"] == "ICHI_V2"
    assert res_good.json["data"]["summary"]["reconciliation_status"] == "RECONCILED"


def test_strategy_filter_and_include_zero_residual():
    """Test filtering by strategy and including zero residual."""
    broker_positions = [
        {
            "symbol": "BANKBARODA",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": -2925.0,
            "average_price": 22.54,
            "ltp": 22.40,
        }
    ]
    strategy_legs = [
        {
            "strategy": "ICHI_V2",
            "symbol": "BANKBARODA",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": -1500.0,
            "average_price": 22.50,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        },
        {
            "strategy": "MACD_FNO",
            "symbol": "BANKBARODA",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": -1425.0,
            "average_price": 22.60,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        },
    ]

    # Filter by strategy ICHI_V2 only
    filtered = reconcile_positions(
        broker_positions,
        strategy_legs,
        strategy_filter="ICHI_V2",
    )
    assert len(filtered["positions"]) == 1
    assert filtered["positions"][0]["strategy"] == "ICHI_V2"
    # Even when filtered to ICHI_V2, contract tracked_quantity represents total tracked on contract
    assert filtered["contracts"][0]["broker_quantity"] == -2925.0
    assert filtered["contracts"][0]["tracked_quantity"] == -2925.0
    assert filtered["contracts"][0]["residual_quantity"] == 0.0

    # Test include_zero_residual=True emits Manual row with 0 quantity
    zero_res = reconcile_positions(
        broker_positions,
        strategy_legs,
        include_zero_residual=True,
    )
    assert len(zero_res["positions"]) == 3
    manual = next(p for p in zero_res["positions"] if p["strategy"] == "Manual / Unattributed")
    assert manual["quantity"] == 0.0
    assert manual["side"] == "FLAT"


def test_service_with_mocked_broker_and_db(monkeypatch):
    """Test full get_attributed_positions flow with mocked broker and db calls."""
    import services.attributed_positions_service as svc

    monkeypatch.setattr(svc, "get_auth_token_broker", lambda k: ("test-token", "fyers"))
    monkeypatch.setattr(
        svc,
        "get_positionbook",
        lambda api_key: (
            True,
            {
                "status": "success",
                "data": [
                    {
                        "symbol": "SBIN",
                        "exchange": "NSE",
                        "product": "MIS",
                        "quantity": 100.0,
                        "average_price": 500.0,
                        "ltp": 510.0,
                    }
                ],
            },
            200,
        ),
    )
    monkeypatch.setattr(
        svc,
        "get_strategy_legs",
        lambda user_id=None, strategy=None: [
            {
                "strategy": "MY_STRAT",
                "symbol": "SBIN",
                "exchange": "NSE",
                "product": "MIS",
                "quantity": 100.0,
                "average_price": 500.0,
                "realized_pnl": 0.0,
                "today_realized_pnl": 0.0,
            }
        ],
    )

    ok, resp, code = svc.get_attributed_positions(api_key="valid-test-key")
    assert ok is True
    assert code == 200
    assert resp["status"] == "success"
    assert len(resp["data"]["positions"]) == 1
    assert resp["data"]["positions"][0]["strategy"] == "MY_STRAT"
    assert resp["data"]["positions"][0]["reconciliation_status"] == "RECONCILED"


def test_zero_quantity_stale_positions_filtered_out():
    """Stale/closed contracts with broker=0, tracked=0, residual=0 must be skipped."""
    broker_positions = [
        # Active position: broker != 0
        {
            "symbol": "TATASTEEL",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": -2750.0,
            "average_price": 140.0,
            "ltp": 139.0,
        },
        # Stale zero positions: broker == 0, no legs
        {
            "symbol": "ABB",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 4500.0,
        },
        {
            "symbol": "ADANIGREEN",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 1200.0,
        },
    ]
    strategy_legs = [
        {
            "strategy": "MOMENTUM",
            "symbol": "TATASTEEL",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": -2750.0,
            "average_price": 140.0,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        }
    ]

    # Even with include_zero_residual=True, stale zero positions must NOT appear
    result = reconcile_positions(broker_positions, strategy_legs, include_zero_residual=True)
    contracts = result["contracts"]
    positions = result["positions"]

    # Only TATASTEEL should be present
    symbols = [c["symbol"] for c in contracts]
    assert symbols == ["TATASTEEL"]
    assert "ABB" not in symbols
    assert "ADANIGREEN" not in symbols

    pos_symbols = [p["symbol"] for p in positions]
    assert all(s == "TATASTEEL" for s in pos_symbols)
    assert "ABB" not in pos_symbols
    assert "ADANIGREEN" not in pos_symbols

