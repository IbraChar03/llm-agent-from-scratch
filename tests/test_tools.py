"""Unit tests for the tools layer — pure Python, no API calls.

Run with:  pytest
"""
import tools


def test_idempotency_key_is_deterministic():
    args = {"order_id": "ORD-1", "motivo": "ritardo"}
    k1 = tools.make_idempotency_key("apri_reclamo", args)
    k2 = tools.make_idempotency_key("apri_reclamo", args)
    assert k1 == k2


def test_idempotency_key_ignores_argument_order():
    a = {"order_id": "ORD-1", "motivo": "ritardo"}
    b = {"motivo": "ritardo", "order_id": "ORD-1"}        # same data, different order
    assert tools.make_idempotency_key("apri_reclamo", a) == tools.make_idempotency_key("apri_reclamo", b)


def test_idempotency_key_differs_on_different_args():
    a = {"order_id": "ORD-1", "motivo": "ritardo"}
    b = {"order_id": "ORD-2", "motivo": "ritardo"}
    assert tools.make_idempotency_key("apri_reclamo", a) != tools.make_idempotency_key("apri_reclamo", b)


def test_controlla_ordine_returns_status():
    result = tools.execute_tool("controlla_ordine", {"order_id": "ORD-1"})
    assert result["order_id"] == "ORD-1"
    assert "stato" in result


def test_unknown_tool_returns_error():
    result = tools.execute_tool("non_esiste", {})
    assert "errore" in result


def test_missing_argument_is_caught():
    result = tools.execute_tool("controlla_ordine", {})   # missing order_id
    assert "errore" in result                             # KeyError -> result, not a crash


def test_apri_reclamo_is_idempotent(capsys):
    args = {"order_id": "ORD-1", "motivo": "ritardo"}

    r1 = tools.execute_tool("apri_reclamo", args)
    r2 = tools.execute_tool("apri_reclamo", args)         # same args -> must NOT re-execute

    assert r1 == r2
    assert capsys.readouterr().out.count("SIDE EFFECT") == 1   # side effect fired exactly once


def test_apri_reclamo_idempotent_ignores_free_text_motivo(capsys):
    # Stesso ordine, motivo scritto DIVERSO -> resta UN solo reclamo: la key e'
    # sull'identita' (order_id), non sul testo libero.
    tools.execute_tool("apri_reclamo", {"order_id": "ORD-7", "motivo": "ritardo"})
    tools.execute_tool("apri_reclamo", {"order_id": "ORD-7", "motivo": "il pacco non arriva!!"})
    assert capsys.readouterr().out.count("SIDE EFFECT") == 1
