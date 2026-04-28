import pytest
from src.utils.error_handler import safe_call


def test_safe_call_success():
    def add(a, b):
        return a + b
    res = safe_call("add", add, 1, 2)
    assert res["ok"] is True
    assert res["value"] == 3


def test_safe_call_failure():
    def boom():
        raise ValueError("boom")
    res = safe_call("boom", boom)
    assert res["ok"] is False
