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
from services.attributed_positions_service import (
    reconcile_positions,
    get_attributed_positions,
    derive_closed_positions,
)


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

    # Authoritative Active Rule: when broker net is 0, contract is flat and NOT active
    assert len(contracts) == 0
    assert len(positions) == 0

    # Opposite directions with non-zero broker net: both strategy positions must be preserved
    broker_positions_active = [
        {
            "symbol": "BANKBARODA",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 50.0,
            "average_price": 22.50,
            "ltp": 22.55,
            "pnl": 2.5,
        }
    ]
    strategy_legs_active = [
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
            "quantity": -50.0,
            "average_price": 22.60,
            "realized_pnl": 0.0,
            "today_realized_pnl": 0.0,
        },
    ]
    res_active = reconcile_positions(broker_positions_active, strategy_legs_active)
    assert len(res_active["contracts"]) == 1
    assert len(res_active["positions"]) == 2
    c = res_active["contracts"][0]
    strat_sum, residual = _sum_quantities(c, res_active["positions"])
    assert round(strat_sum + residual, 4) == c["broker_quantity"]


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

    # Authoritative Active Position Rule:
    # A contract may appear in Active Positions ONLY when abs(broker_net_quantity) > 1e-9.
    # When broker_quantity == 0, the contract is completely flat:
    # - NEVER show the contract in Active Positions (len(positions) == 0)
    # - NEVER show its strategy leg in Active
    # - NEVER create a Manual / Unattributed residual row
    # - NEVER create a synthetic balancing position
    assert len(contracts) == 0
    assert len(positions) == 0


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


def test_derive_closed_positions_long_trade():
    """Test derive_closed_positions for a completed LONG trade (BUY then SELL)."""
    trades = [
        {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product": "MIS",
            "action": "BUY",
            "quantity": 50,
            "price": 2890.0,
            "trade_time": "2026-09-11 09:30:00",
            "strategy": "Macdfno",
        },
        {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product": "MIS",
            "action": "SELL",
            "quantity": 50,
            "price": 2900.0,
            "trade_time": "2026-09-11 10:15:00",
            "strategy": "Macdfno",
        },
    ]

    closed = derive_closed_positions(trades)
    assert len(closed) == 1
    cp = closed[0]
    assert cp["strategy"] == "Macdfno"
    assert cp["symbol"] == "RELIANCE"
    assert cp["exchange"] == "NSE"
    assert cp["product"] == "MIS"
    assert cp["direction"] == "LONG"
    assert cp["quantity"] == 50.0
    assert cp["entry_average"] == 2890.0
    assert cp["exit_average"] == 2900.0
    assert cp["realized_pnl"] == 500.0  # (2900 - 2890) * 50
    assert cp["entry_time"] == "2026-09-11 09:30:00"
    assert cp["exit_time"] == "2026-09-11 10:15:00"
    assert cp["status"] == "CLOSED"


def test_derive_closed_positions_short_trade():
    """Test derive_closed_positions for a completed SHORT trade (SELL then BUY)."""
    trades = [
        {
            "symbol": "NIFTY26SEPFUT",
            "exchange": "NFO",
            "product": "NRML",
            "action": "SELL",
            "quantity": 25,
            "price": 25100.0,
            "trade_time": "2026-09-11 09:20:00",
            "strategy": "Emacrossopen",
        },
        {
            "symbol": "NIFTY26SEPFUT",
            "exchange": "NFO",
            "product": "NRML",
            "action": "BUY",
            "quantity": 25,
            "price": 25000.0,
            "trade_time": "2026-09-11 09:50:00",
            "strategy": "Emacrossopen",
        },
    ]

    closed = derive_closed_positions(trades)
    assert len(closed) == 1
    cp = closed[0]
    assert cp["strategy"] == "Emacrossopen"
    assert cp["symbol"] == "NIFTY26SEPFUT"
    assert cp["direction"] == "SHORT"
    assert cp["quantity"] == 25.0
    assert cp["entry_average"] == 25100.0
    assert cp["exit_average"] == 25000.0
    assert cp["realized_pnl"] == 2500.0  # (25100 - 25000) * 25
    assert cp["status"] == "CLOSED"


def test_derive_closed_positions_partial_fill_and_strategy_filter():
    """Test partial closes and filtering by strategy."""
    trades = [
        # Strategy A: buy 100, sell 60 -> 60 closed
        {
            "symbol": "INFY",
            "exchange": "NSE",
            "product": "CNC",
            "action": "BUY",
            "quantity": 100,
            "price": 1500.0,
            "trade_time": "2026-09-11 09:15:00",
            "strategy": "StrategyA",
        },
        {
            "symbol": "INFY",
            "exchange": "NSE",
            "product": "CNC",
            "action": "SELL",
            "quantity": 60,
            "price": 1520.0,
            "trade_time": "2026-09-11 10:00:00",
            "strategy": "StrategyA",
        },
        # Strategy B: sell 50, buy 50 -> 50 closed
        {
            "symbol": "INFY",
            "exchange": "NSE",
            "product": "CNC",
            "action": "SELL",
            "quantity": 50,
            "price": 1530.0,
            "trade_time": "2026-09-11 10:30:00",
            "strategy": "StrategyB",
        },
        {
            "symbol": "INFY",
            "exchange": "NSE",
            "product": "CNC",
            "action": "BUY",
            "quantity": 50,
            "price": 1510.0,
            "trade_time": "2026-09-11 11:00:00",
            "strategy": "StrategyB",
        },
    ]

    all_closed = derive_closed_positions(trades)
    assert len(all_closed) == 2

    # Filter for StrategyA only
    strat_a_closed = derive_closed_positions(trades, strategy_filter="StrategyA")
    assert len(strat_a_closed) == 1
    assert strat_a_closed[0]["strategy"] == "StrategyA"
    assert strat_a_closed[0]["quantity"] == 60.0
    assert strat_a_closed[0]["realized_pnl"] == 1200.0  # (1520 - 1500) * 60

    # Filter for StrategyB only
    strat_b_closed = derive_closed_positions(trades, strategy_filter="StrategyB")
    assert len(strat_b_closed) == 1
    assert strat_b_closed[0]["strategy"] == "StrategyB"
    assert strat_b_closed[0]["quantity"] == 50.0
    assert strat_b_closed[0]["realized_pnl"] == 1000.0  # (1530 - 1510) * 50


def test_zero_broker_contract_without_trades_is_not_closed():
    """A zero-quantity broker position alone must NOT produce a closed position."""
    broker_positions = [
        {
            "symbol": "ABB",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 4500.0,
        }
    ]
    # Reconcile with no trades
    result = reconcile_positions(broker_positions, strategy_legs=[], trades=[])
    assert result["closed_positions"] == []
    assert result["positions"] == []
    assert result["contracts"] == []


def test_daily_reset_with_no_trades_returns_empty_closed():
    """At morning session rollover (03:00 IST), when today's tradebook has no trades, closed_positions is empty."""
    result = reconcile_positions(broker_positions=[], strategy_legs=[], trades=[])
    assert result["closed_positions"] == []
    assert result["positions"] == []
    assert result["contracts"] == []


# ============================================================================
# REGRESSION TESTS VERIFYING ALL 9 CRITICAL USER REQUIREMENTS
# ============================================================================

def test_requirement_1_and_2_and_3_strategy_normalization_and_no_unwanted_buckets():
    """
    Requirements 1, 2, 3:
    1. Strategy Overview returns canonical Macdfno and Emacrossopen.
    2. MACD_FNO_V1 normalizes to Macdfno and cannot reappear.
    3. UI Exit Position and Manual / Unattributed cannot become strategy buckets.
    """
    from utils.strategy_attribution import normalize_strategy_name, is_authoritative_strategy

    assert normalize_strategy_name("MACD_FNO_V1") == "Macdfno"
    assert normalize_strategy_name("macd_fno_v1") == "Macdfno"
    assert normalize_strategy_name("macdfno") == "Macdfno"
    assert normalize_strategy_name("Macdfno") == "Macdfno"

    assert normalize_strategy_name("EMACROSS_FNO_PAPER") == "Emacrossopen"
    assert normalize_strategy_name("emacrossopen") == "Emacrossopen"
    assert normalize_strategy_name("Emacrossopen") == "Emacrossopen"

    # Disallowed system tags return None
    assert normalize_strategy_name("UI Exit Position") is None
    assert normalize_strategy_name("ui_exit_position") is None
    assert normalize_strategy_name("Manual / Unattributed") is None
    assert normalize_strategy_name("untagged") is None
    assert normalize_strategy_name("") is None
    assert normalize_strategy_name(None) is None


def test_requirement_4_no_manual_unattributed_when_broker_net_is_zero():
    """
    Requirement 4:
    Manual / Unattributed is NOT generated when broker net quantity is zero
    and there is no genuine residual position.
    """
    broker_positions = [
        {
            "symbol": "HINDALCO29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 670.0,
        }
    ]
    strategy_legs = []

    # Even with include_zero_residual=True, when broker_quantity is 0,
    # Manual / Unattributed must NEVER be emitted!
    result = reconcile_positions(
        broker_positions,
        strategy_legs,
        include_zero_residual=True,
    )
    assert len(result["positions"]) == 0
    assert len(result["contracts"]) == 0
    assert not any(p.get("strategy") == "Manual / Unattributed" for p in result["positions"])


def test_requirement_5_6_7_hindalco_and_tatasteel_complete_exit_scenario():
    """
    Requirements 5, 6, 7:
    5. Current-session entry followed by exit appears exactly once in Closed.
    6. Closed trade retains original strategy attribution (Macdfno).
    7. Active becomes zero after a genuine complete exit (no phantom HINDALCO/TATASTEEL).
    """
    trades = [
        # HINDALCO entry under MACD_FNO_V1
        {
            "symbol": "HINDALCO29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "action": "BUY",
            "quantity": 700.0,
            "price": 665.0,
            "trade_time": "2026-09-11 15:10:00",
            "strategy": "MACD_FNO_V1",
        },
        # HINDALCO exit via UI exit (untagged or UI exit)
        {
            "symbol": "HINDALCO29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "action": "SELL",
            "quantity": 700.0,
            "price": 670.0,
            "trade_time": "2026-09-11 15:25:00",
            "strategy": "UI Exit Position",
        },
        # TATASTEEL entry under MACD_FNO_V1
        {
            "symbol": "TATASTEEL29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "action": "BUY",
            "quantity": 2750.0,
            "price": 140.0,
            "trade_time": "2026-09-11 15:15:00",
            "strategy": "MACD_FNO_V1",
        },
        # TATASTEEL exit via UI exit
        {
            "symbol": "TATASTEEL29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "action": "SELL",
            "quantity": 2750.0,
            "price": 142.0,
            "trade_time": "2026-09-11 15:30:00",
            "strategy": "UI Exit Position",
        },
    ]

    # Broker positions at flat (net 0)
    broker_positions = [
        {
            "symbol": "HINDALCO29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 670.0,
        },
        {
            "symbol": "TATASTEEL29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 142.0,
        },
    ]
    # Strategy legs also 0 after exit
    strategy_legs = []

    result = reconcile_positions(
        broker_positions=broker_positions,
        strategy_legs=strategy_legs,
        trades=trades,
        include_zero_residual=True,
    )

    # 1. Active positions MUST BE ZERO
    assert len(result["positions"]) == 0
    assert len(result["contracts"]) == 0

    # 2. Closed positions MUST CONTAIN EXACTLY 2 TRADES
    closed = result["closed_positions"]
    assert len(closed) == 2

    hindalco_closed = next(c for c in closed if c["symbol"] == "HINDALCO29SEP26FUT")
    # Original strategy attribution retained and normalized to Macdfno
    assert hindalco_closed["strategy"] == "Macdfno"
    assert hindalco_closed["quantity"] == 700.0
    assert hindalco_closed["direction"] == "LONG"
    assert hindalco_closed["entry_average"] == 665.0
    assert hindalco_closed["exit_average"] == 670.0
    assert hindalco_closed["realized_pnl"] == 3500.0  # 700 * (670 - 665)
    assert hindalco_closed["status"] == "CLOSED"

    tatasteel_closed = next(c for c in closed if c["symbol"] == "TATASTEEL29SEP26FUT")
    assert tatasteel_closed["strategy"] == "Macdfno"
    assert tatasteel_closed["quantity"] == 2750.0
    assert tatasteel_closed["direction"] == "LONG"
    assert tatasteel_closed["entry_average"] == 140.0
    assert tatasteel_closed["exit_average"] == 142.0
    assert tatasteel_closed["realized_pnl"] == 5500.0  # 2750 * (142 - 140)
    assert tatasteel_closed["status"] == "CLOSED"

    # Disallowed buckets must NOT appear in closed
    for c in closed:
        assert c["strategy"] != "MACD_FNO_V1"
        assert c["strategy"] != "UI Exit Position"
        assert c["strategy"] != "Manual / Unattributed"


def test_requirement_8_refresh_does_not_duplicate_closed_trades():
    """
    Requirement 8:
    Refresh or restart does not duplicate closed trades.
    Multiple invocations with the same trades return identical closed trades.
    """
    trades = [
        {
            "symbol": "TATASTEEL29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "action": "BUY",
            "quantity": 2750.0,
            "price": 140.0,
            "trade_time": "2026-09-11 15:15:00",
            "strategy": "MACD_FNO_V1",
        },
        {
            "symbol": "TATASTEEL29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "action": "SELL",
            "quantity": 2750.0,
            "price": 142.0,
            "trade_time": "2026-09-11 15:30:00",
            "strategy": "MACD_FNO_V1",
        },
    ]

    closed_pass_1 = derive_closed_positions(trades)
    closed_pass_2 = derive_closed_positions(trades)

    assert len(closed_pass_1) == 1
    assert len(closed_pass_2) == 1
    assert closed_pass_1[0] == closed_pass_2[0]


def test_session_start_filtering_drops_pre_reset_trades():
    """
    Verify session_start filter drops trades from before the 2026-09-11 15:00 IST reset.
    """
    trades = [
        # Pre-reset trade (before 15:00 IST)
        {
            "symbol": "INFY",
            "exchange": "NSE",
            "product": "MIS",
            "action": "BUY",
            "quantity": 100,
            "price": 1500.0,
            "trade_time": "2026-09-11 14:30:00",
            "strategy": "Macdfno",
        },
        {
            "symbol": "INFY",
            "exchange": "NSE",
            "product": "MIS",
            "action": "SELL",
            "quantity": 100,
            "price": 1510.0,
            "trade_time": "2026-09-11 14:45:00",
            "strategy": "Macdfno",
        },
        # Post-reset trade (after 15:00 IST)
        {
            "symbol": "HINDALCO29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "action": "BUY",
            "quantity": 700,
            "price": 665.0,
            "trade_time": "2026-09-11 15:10:00",
            "strategy": "Macdfno",
        },
        {
            "symbol": "HINDALCO29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "action": "SELL",
            "quantity": 700,
            "price": 670.0,
            "trade_time": "2026-09-11 15:25:00",
            "strategy": "Macdfno",
        },
    ]

    closed = derive_closed_positions(trades, session_start="2026-09-11 15:00:00")
    # Only the post-reset trade is included!
    assert len(closed) == 1
    assert closed[0]["symbol"] == "HINDALCO29SEP26FUT"
    assert closed[0]["realized_pnl"] == 3500.0


# ============================================================================
# MANDATORY 15 AUTOMATED TESTS (SPECIFIED IN FINAL IMPLEMENTATION INSTRUCTION)
# ============================================================================

def test_1_entry_only():
    """1. Entry only: Broker +100 -> Active 100, Closed 0."""
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
            "strategy": "Macdfno",
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 100.0,
            "average_price": 500.0,
        }
    ]
    trades = [
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "action": "BUY",
            "quantity": 100.0,
            "price": 500.0,
            "strategy": "Macdfno",
            "trade_time": "2026-09-20 10:00:00",
        }
    ]
    result = reconcile_positions(broker_positions, strategy_legs, trades=trades)
    assert len(result["positions"]) == 1
    assert result["positions"][0]["quantity"] == 100.0
    assert result["positions"][0]["strategy"] == "Macdfno"
    assert len(result["closed_positions"]) == 0


def test_2_full_target_exit():
    """2. Full Target exit: +100 -> 0 -> Active 0, Closed 100."""
    broker_positions = [
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 520.0,
        }
    ]
    strategy_legs = []
    trades = [
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "action": "BUY",
            "quantity": 100.0,
            "price": 500.0,
            "strategy": "Macdfno",
            "trade_time": "2026-09-20 10:00:00",
        },
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "action": "SELL",
            "quantity": 100.0,
            "price": 520.0,
            "strategy": "target_exit",
            "trade_time": "2026-09-20 10:30:00",
        },
    ]
    result = reconcile_positions(broker_positions, strategy_legs, trades=trades)
    assert len(result["positions"]) == 0
    assert len(result["contracts"]) == 0
    assert len(result["closed_positions"]) == 1
    c = result["closed_positions"][0]
    assert c["strategy"] == "Macdfno"
    assert c["quantity"] == 100.0
    assert c["realized_pnl"] == 2000.0
    assert c["status"] == "CLOSED"


def test_3_full_sl_exit():
    """3. Full SL exit: +100 -> 0 -> Active 0, Closed 100."""
    broker_positions = [
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 490.0,
        }
    ]
    strategy_legs = []
    trades = [
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "action": "BUY",
            "quantity": 100.0,
            "price": 500.0,
            "strategy": "Macdfno",
            "trade_time": "2026-09-20 10:00:00",
        },
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "action": "SELL",
            "quantity": 100.0,
            "price": 490.0,
            "strategy": "sl_exit",
            "trade_time": "2026-09-20 10:15:00",
        },
    ]
    result = reconcile_positions(broker_positions, strategy_legs, trades=trades)
    assert len(result["positions"]) == 0
    assert len(result["contracts"]) == 0
    assert len(result["closed_positions"]) == 1
    c = result["closed_positions"][0]
    assert c["strategy"] == "Macdfno"
    assert c["quantity"] == 100.0
    assert c["realized_pnl"] == -1000.0


def test_4_ui_manual_exit():
    """4. UI/manual exit: +100 -> 0 -> Active 0, Closed 100, Strategy remains original strategy."""
    broker_positions = [
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 505.0,
        }
    ]
    strategy_legs = []
    trades = [
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "action": "BUY",
            "quantity": 100.0,
            "price": 500.0,
            "strategy": "Macdfno",
            "trade_time": "2026-09-20 10:00:00",
        },
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "action": "SELL",
            "quantity": 100.0,
            "price": 505.0,
            "strategy": "UI Exit Position",
            "trade_time": "2026-09-20 10:20:00",
        },
    ]
    result = reconcile_positions(broker_positions, strategy_legs, trades=trades)
    assert len(result["positions"]) == 0
    assert len(result["closed_positions"]) == 1
    c = result["closed_positions"][0]
    assert c["strategy"] == "Macdfno"
    assert c["quantity"] == 100.0
    assert c["realized_pnl"] == 500.0


def test_5_external_manual_broker_exit():
    """5. External/manual broker exit: +100 -> 0 -> Active 0, Closed when matching executed fills exist."""
    broker_positions = [
        {
            "symbol": "INFY",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 1520.0,
        }
    ]
    strategy_legs = []
    trades = [
        {
            "symbol": "INFY",
            "exchange": "NSE",
            "product": "MIS",
            "action": "BUY",
            "quantity": 100.0,
            "price": 1500.0,
            "strategy": "Emacrossopen",
            "trade_time": "2026-09-20 10:00:00",
        },
        {
            "symbol": "INFY",
            "exchange": "NSE",
            "product": "MIS",
            "action": "SELL",
            "quantity": 100.0,
            "price": 1520.0,
            "strategy": None,  # Untagged external/manual Fyers terminal exit
            "trade_time": "2026-09-20 10:45:00",
        },
    ]
    result = reconcile_positions(broker_positions, strategy_legs, trades=trades)
    assert len(result["positions"]) == 0
    assert len(result["closed_positions"]) == 1
    c = result["closed_positions"][0]
    assert c["strategy"] == "Emacrossopen"
    assert c["quantity"] == 100.0
    assert c["realized_pnl"] == 2000.0


def test_6_partial_exit():
    """6. Partial exit: +1000 -> +400 -> Active 400, Closed 600."""
    broker_positions = [
        {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 400.0,
            "average_price": 2500.0,
            "ltp": 2550.0,
        }
    ]
    strategy_legs = [
        {
            "strategy": "Macdfno",
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 400.0,
            "average_price": 2500.0,
        }
    ]
    trades = [
        {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product": "MIS",
            "action": "BUY",
            "quantity": 1000.0,
            "price": 2500.0,
            "strategy": "Macdfno",
            "trade_time": "2026-09-20 09:30:00",
        },
        {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product": "MIS",
            "action": "SELL",
            "quantity": 600.0,
            "price": 2550.0,
            "strategy": "Macdfno",
            "trade_time": "2026-09-20 10:00:00",
        },
    ]
    result = reconcile_positions(broker_positions, strategy_legs, trades=trades)
    assert len(result["positions"]) == 1
    assert result["positions"][0]["quantity"] == 400.0
    assert len(result["closed_positions"]) == 1
    assert result["closed_positions"][0]["quantity"] == 600.0
    assert result["closed_positions"][0]["realized_pnl"] == 30000.0


def test_7_final_partial_exit():
    """7. Final partial exit: +400 -> 0 -> Active 0, Closed total 1000."""
    broker_positions = [
        {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 2600.0,
        }
    ]
    strategy_legs = []
    trades = [
        {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product": "MIS",
            "action": "BUY",
            "quantity": 1000.0,
            "price": 2500.0,
            "strategy": "Macdfno",
            "trade_time": "2026-09-20 09:30:00",
        },
        {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product": "MIS",
            "action": "SELL",
            "quantity": 600.0,
            "price": 2550.0,
            "strategy": "Macdfno",
            "trade_time": "2026-09-20 10:00:00",
        },
        {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "product": "MIS",
            "action": "SELL",
            "quantity": 400.0,
            "price": 2600.0,
            "strategy": "Macdfno",
            "trade_time": "2026-09-20 11:00:00",
        },
    ]
    result = reconcile_positions(broker_positions, strategy_legs, trades=trades)
    assert len(result["positions"]) == 0
    assert len(result["closed_positions"]) == 2
    total_closed_qty = sum(c["quantity"] for c in result["closed_positions"])
    assert total_closed_qty == 1000.0


def test_8_broker_zero_stale_tracked_quantity():
    """8. Broker zero + stale tracked quantity: Broker 0 / Tracked 700 -> Active = 0."""
    broker_positions = [
        {
            "symbol": "HINDALCO29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 670.0,
        }
    ]
    strategy_legs = [
        {
            "strategy": "Macdfno",
            "symbol": "HINDALCO29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "quantity": 700.0,
            "average_price": 665.0,
        }
    ]
    result = reconcile_positions(broker_positions, strategy_legs)
    assert len(result["positions"]) == 0
    assert len(result["contracts"]) == 0


def test_9_broker_zero_synthetic_residual():
    """9. Broker zero + synthetic residual: Broker 0 / Tracked 700 / Residual -700 -> Active = 0, No Manual row."""
    broker_positions = [
        {
            "symbol": "HINDALCO29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 670.0,
        }
    ]
    strategy_legs = [
        {
            "strategy": "Macdfno",
            "symbol": "HINDALCO29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "quantity": 700.0,
            "average_price": 665.0,
        }
    ]
    result = reconcile_positions(broker_positions, strategy_legs, include_zero_residual=True)
    assert len(result["positions"]) == 0
    assert len(result["contracts"]) == 0
    assert not any(p.get("strategy") == "Manual / Unattributed" for p in result["positions"])


def test_10_no_executed_fills():
    """10. No executed fills: Broker 0 -> Do NOT fabricate Closed position."""
    broker_positions = [
        {
            "symbol": "TATASTEEL",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 140.0,
        }
    ]
    result = reconcile_positions(broker_positions, strategy_legs=[], trades=[])
    assert len(result["positions"]) == 0
    assert len(result["closed_positions"]) == 0


def test_11_target_sl_exit_with_legacy_ui_tag():
    """11. Target/SL exit with legacy/UI tag: Closed under original canonical strategy."""
    trades = [
        {
            "symbol": "HINDALCO29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "action": "BUY",
            "quantity": 700.0,
            "price": 665.0,
            "strategy": "MACD_FNO_V1",
            "trade_time": "2026-09-20 10:00:00",
        },
        {
            "symbol": "HINDALCO29SEP26FUT",
            "exchange": "NFO",
            "product": "NRML",
            "action": "SELL",
            "quantity": 700.0,
            "price": 670.0,
            "strategy": "UI Exit Position",
            "trade_time": "2026-09-20 10:30:00",
        },
    ]
    closed = derive_closed_positions(trades)
    assert len(closed) == 1
    assert closed[0]["strategy"] == "Macdfno"
    assert closed[0]["quantity"] == 700.0
    assert closed[0]["realized_pnl"] == 3500.0


def test_12_refresh_reload():
    """12. Refresh/reload: Closed quantity/P&L does not duplicate."""
    trades = [
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "action": "BUY",
            "quantity": 100.0,
            "price": 500.0,
            "strategy": "Macdfno",
            "trade_time": "2026-09-20 10:00:00",
        },
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "action": "SELL",
            "quantity": 100.0,
            "price": 510.0,
            "strategy": "Macdfno",
            "trade_time": "2026-09-20 10:30:00",
        },
    ]
    pass_1 = derive_closed_positions(trades)
    pass_2 = derive_closed_positions(trades)
    assert len(pass_1) == 1
    assert len(pass_2) == 1
    assert pass_1[0]["quantity"] == pass_2[0]["quantity"]
    assert pass_1[0]["realized_pnl"] == pass_2[0]["realized_pnl"]


def test_13_restart():
    """13. Restart: Active/Closed result remains identical."""
    broker_positions = [
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "quantity": 0.0,
            "average_price": 0.0,
            "ltp": 510.0,
        }
    ]
    trades = [
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "action": "BUY",
            "quantity": 100.0,
            "price": 500.0,
            "strategy": "Macdfno",
            "trade_time": "2026-09-20 10:00:00",
        },
        {
            "symbol": "SBIN",
            "exchange": "NSE",
            "product": "MIS",
            "action": "SELL",
            "quantity": 100.0,
            "price": 510.0,
            "strategy": "Macdfno",
            "trade_time": "2026-09-20 10:30:00",
        },
    ]
    run_1 = reconcile_positions(broker_positions, [], trades=trades)
    run_2 = reconcile_positions(broker_positions, [], trades=trades)
    assert run_1["positions"] == run_2["positions"]
    assert run_1["closed_positions"] == run_2["closed_positions"]


def test_14_macd_fno_v1():
    """14. MACD_FNO_V1: Normalize to Macdfno."""
    from utils.strategy_attribution import normalize_strategy_name
    assert normalize_strategy_name("MACD_FNO_V1") == "Macdfno"
    assert normalize_strategy_name("macd_fno_v1") == "Macdfno"
    assert normalize_strategy_name("macdfno_v1") == "Macdfno"


def test_15_ui_exit_position():
    """15. UI Exit Position: Never becomes a strategy bucket."""
    from utils.strategy_attribution import normalize_strategy_name
    assert normalize_strategy_name("UI Exit Position") is None
    assert normalize_strategy_name("ui_exit_position") is None
    assert normalize_strategy_name("ui exit") is None
    assert normalize_strategy_name("Manual / Unattributed") is None
    assert normalize_strategy_name("target_exit") is None
    assert normalize_strategy_name("sl_exit") is None



