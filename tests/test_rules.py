"""Tests for rules module."""

import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from trader.rules.models import Rule, RuleAction, RuleCondition
from trader.rules.loader import (
    load_rules,
    save_rule,
    save_rules,
    delete_rule,
    get_rule,
    enable_rule,
)


@pytest.fixture
def temp_config_dir():
    """Create temporary config directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_rule_creation() -> None:
    """Test creating a rule."""
    rule = Rule(
        symbol="AAPL",
        action=RuleAction.BUY,
        condition=RuleCondition.BELOW,
        target_price=Decimal("170.00"),
        quantity=10,
    )
    assert rule.symbol == "AAPL"
    assert rule.action == RuleAction.BUY
    assert rule.condition == RuleCondition.BELOW
    assert rule.target_price == Decimal("170.00")
    assert rule.quantity == 10
    assert rule.enabled is True
    assert rule.triggered is False


def test_rule_symbol_uppercase() -> None:
    """Test that symbol is converted to uppercase."""
    rule = Rule(
        symbol="aapl",
        action=RuleAction.BUY,
        condition=RuleCondition.BELOW,
        target_price=Decimal("170.00"),
        quantity=10,
    )
    assert rule.symbol == "AAPL"


def test_rule_invalid_quantity() -> None:
    """Test that invalid quantity raises error."""
    with pytest.raises(ValueError, match="Quantity must be positive"):
        Rule(
            symbol="AAPL",
            action=RuleAction.BUY,
            condition=RuleCondition.BELOW,
            target_price=Decimal("170.00"),
            quantity=0,
        )


def test_rule_invalid_price() -> None:
    """Test that invalid price raises error."""
    with pytest.raises(ValueError, match="Target price must be positive"):
        Rule(
            symbol="AAPL",
            action=RuleAction.BUY,
            condition=RuleCondition.BELOW,
            target_price=Decimal("-10.00"),
            quantity=10,
        )


def test_rule_check_below_triggered() -> None:
    """Test rule triggers when price drops below target."""
    rule = Rule(
        symbol="AAPL",
        action=RuleAction.BUY,
        condition=RuleCondition.BELOW,
        target_price=Decimal("170.00"),
        quantity=10,
    )
    assert rule.check(Decimal("169.99")) is True
    assert rule.check(Decimal("170.00")) is True
    assert rule.check(Decimal("170.01")) is False


def test_rule_check_above_triggered() -> None:
    """Test rule triggers when price rises above target."""
    rule = Rule(
        symbol="AAPL",
        action=RuleAction.SELL,
        condition=RuleCondition.ABOVE,
        target_price=Decimal("200.00"),
        quantity=10,
    )
    assert rule.check(Decimal("200.01")) is True
    assert rule.check(Decimal("200.00")) is True
    assert rule.check(Decimal("199.99")) is False


def test_rule_check_disabled() -> None:
    """Test disabled rule doesn't trigger."""
    rule = Rule(
        symbol="AAPL",
        action=RuleAction.BUY,
        condition=RuleCondition.BELOW,
        target_price=Decimal("170.00"),
        quantity=10,
        enabled=False,
    )
    assert rule.check(Decimal("150.00")) is False


def test_rule_check_already_triggered() -> None:
    """Test already triggered rule doesn't trigger again."""
    rule = Rule(
        symbol="AAPL",
        action=RuleAction.BUY,
        condition=RuleCondition.BELOW,
        target_price=Decimal("170.00"),
        quantity=10,
        triggered=True,
    )
    assert rule.check(Decimal("150.00")) is False


def test_rule_to_dict() -> None:
    """Test rule serialization."""
    rule = Rule(
        id="test123",
        symbol="AAPL",
        action=RuleAction.BUY,
        condition=RuleCondition.BELOW,
        target_price=Decimal("170.00"),
        quantity=10,
    )
    data = rule.to_dict()
    assert data["id"] == "test123"
    assert data["symbol"] == "AAPL"
    assert data["action"] == "buy"
    assert data["condition"] == "below"
    assert data["target_price"] == "170.00"
    assert data["quantity"] == 10


def test_rule_from_dict() -> None:
    """Test rule deserialization."""
    data = {
        "id": "test123",
        "symbol": "AAPL",
        "action": "buy",
        "condition": "below",
        "target_price": "170.00",
        "quantity": 10,
    }
    rule = Rule.from_dict(data)
    assert rule.id == "test123"
    assert rule.symbol == "AAPL"
    assert rule.action == RuleAction.BUY
    assert rule.condition == RuleCondition.BELOW


def test_save_and_load_rules(temp_config_dir: Path) -> None:
    """Test saving and loading rules."""
    rule1 = Rule(
        symbol="AAPL",
        action=RuleAction.BUY,
        condition=RuleCondition.BELOW,
        target_price=Decimal("170.00"),
        quantity=10,
    )
    rule2 = Rule(
        symbol="TSLA",
        action=RuleAction.SELL,
        condition=RuleCondition.ABOVE,
        target_price=Decimal("300.00"),
        quantity=5,
    )

    save_rules([rule1, rule2], temp_config_dir)
    loaded = load_rules(temp_config_dir)

    assert len(loaded) == 2
    assert loaded[0].symbol == "AAPL"
    assert loaded[1].symbol == "TSLA"


def test_save_single_rule(temp_config_dir: Path) -> None:
    """Test saving a single rule."""
    rule = Rule(
        symbol="AAPL",
        action=RuleAction.BUY,
        condition=RuleCondition.BELOW,
        target_price=Decimal("170.00"),
        quantity=10,
    )

    save_rule(rule, temp_config_dir)
    loaded = load_rules(temp_config_dir)

    assert len(loaded) == 1
    assert loaded[0].symbol == "AAPL"


def test_delete_rule(temp_config_dir: Path) -> None:
    """Test deleting a rule."""
    rule = Rule(
        id="delete-me",
        symbol="AAPL",
        action=RuleAction.BUY,
        condition=RuleCondition.BELOW,
        target_price=Decimal("170.00"),
        quantity=10,
    )

    save_rule(rule, temp_config_dir)
    assert delete_rule("delete-me", temp_config_dir) is True
    assert load_rules(temp_config_dir) == []


def test_delete_nonexistent_rule(temp_config_dir: Path) -> None:
    """Test deleting non-existent rule returns False."""
    assert delete_rule("fake-id", temp_config_dir) is False


def test_get_rule(temp_config_dir: Path) -> None:
    """Test getting a rule by ID."""
    rule = Rule(
        id="find-me",
        symbol="AAPL",
        action=RuleAction.BUY,
        condition=RuleCondition.BELOW,
        target_price=Decimal("170.00"),
        quantity=10,
    )

    save_rule(rule, temp_config_dir)
    found = get_rule("find-me", temp_config_dir)

    assert found is not None
    assert found.symbol == "AAPL"


def test_enable_disable_rule(temp_config_dir: Path) -> None:
    """Test enabling and disabling a rule."""
    rule = Rule(
        id="toggle-me",
        symbol="AAPL",
        action=RuleAction.BUY,
        condition=RuleCondition.BELOW,
        target_price=Decimal("170.00"),
        quantity=10,
        enabled=True,
    )

    save_rule(rule, temp_config_dir)

    # Disable
    assert enable_rule("toggle-me", enabled=False, config_dir=temp_config_dir) is True
    found = get_rule("toggle-me", temp_config_dir)
    assert found is not None
    assert found.enabled is False

    # Enable
    assert enable_rule("toggle-me", enabled=True, config_dir=temp_config_dir) is True
    found = get_rule("toggle-me", temp_config_dir)
    assert found is not None
    assert found.enabled is True


def test_load_empty_rules(temp_config_dir: Path) -> None:
    """Test loading rules when none exist."""
    loaded = load_rules(temp_config_dir)
    assert loaded == []
