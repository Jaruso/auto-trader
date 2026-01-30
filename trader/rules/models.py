"""Rule models for trading automation."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional
import uuid


class RuleAction(Enum):
    """Action to take when rule triggers."""

    BUY = "buy"
    SELL = "sell"


class RuleCondition(Enum):
    """Price condition for triggering."""

    BELOW = "below"  # Trigger when price drops below target
    ABOVE = "above"  # Trigger when price rises above target


@dataclass
class Rule:
    """Trading rule definition.

    A rule defines when to automatically execute a trade based on price conditions.

    Example:
        Buy 10 shares of AAPL when price drops below $170
        Sell 5 shares of TSLA when price rises above $300
    """

    symbol: str
    action: RuleAction
    condition: RuleCondition
    target_price: Decimal
    quantity: int
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    enabled: bool = True
    triggered: bool = False
    description: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate rule after initialization."""
        self.symbol = self.symbol.upper()
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")
        if self.target_price <= 0:
            raise ValueError("Target price must be positive")

    def check(self, current_price: Decimal) -> bool:
        """Check if rule should trigger based on current price.

        Args:
            current_price: Current market price.

        Returns:
            True if rule condition is met.
        """
        if not self.enabled or self.triggered:
            return False

        if self.condition == RuleCondition.BELOW:
            return current_price <= self.target_price
        else:  # ABOVE
            return current_price >= self.target_price

    def to_dict(self) -> dict:
        """Convert rule to dictionary for serialization."""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "action": self.action.value,
            "condition": self.condition.value,
            "target_price": str(self.target_price),
            "quantity": self.quantity,
            "enabled": self.enabled,
            "triggered": self.triggered,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Rule":
        """Create rule from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            symbol=data["symbol"],
            action=RuleAction(data["action"]),
            condition=RuleCondition(data["condition"]),
            target_price=Decimal(str(data["target_price"])),
            quantity=int(data["quantity"]),
            enabled=data.get("enabled", True),
            triggered=data.get("triggered", False),
            description=data.get("description"),
        )

    def __str__(self) -> str:
        """Human-readable representation."""
        action = self.action.value.upper()
        cond = "≤" if self.condition == RuleCondition.BELOW else "≥"
        status = "✓" if self.enabled else "✗"
        return f"[{status}] {action} {self.quantity} {self.symbol} when price {cond} ${self.target_price}"
