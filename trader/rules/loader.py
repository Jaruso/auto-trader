"""Rule loading and persistence."""

from pathlib import Path
from typing import Optional

import yaml

from trader.rules.models import Rule


def get_rules_file(config_dir: Optional[Path] = None) -> Path:
    """Get path to rules file."""
    if config_dir is None:
        config_dir = Path(__file__).parent.parent.parent / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "rules.yaml"


def load_rules(config_dir: Optional[Path] = None) -> list[Rule]:
    """Load all rules from YAML file.

    Args:
        config_dir: Config directory path.

    Returns:
        List of Rule objects.
    """
    rules_file = get_rules_file(config_dir)

    if not rules_file.exists():
        return []

    with open(rules_file) as f:
        data = yaml.safe_load(f)

    if not data or "rules" not in data:
        return []

    return [Rule.from_dict(r) for r in data["rules"]]


def save_rules(rules: list[Rule], config_dir: Optional[Path] = None) -> None:
    """Save all rules to YAML file.

    Args:
        rules: List of rules to save.
        config_dir: Config directory path.
    """
    rules_file = get_rules_file(config_dir)

    data = {"rules": [r.to_dict() for r in rules]}

    with open(rules_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def save_rule(rule: Rule, config_dir: Optional[Path] = None) -> None:
    """Add or update a single rule.

    Args:
        rule: Rule to save.
        config_dir: Config directory path.
    """
    rules = load_rules(config_dir)

    # Check if rule with same ID exists
    existing_idx = None
    for i, r in enumerate(rules):
        if r.id == rule.id:
            existing_idx = i
            break

    if existing_idx is not None:
        rules[existing_idx] = rule
    else:
        rules.append(rule)

    save_rules(rules, config_dir)


def delete_rule(rule_id: str, config_dir: Optional[Path] = None) -> bool:
    """Delete a rule by ID.

    Args:
        rule_id: Rule ID to delete.
        config_dir: Config directory path.

    Returns:
        True if rule was deleted, False if not found.
    """
    rules = load_rules(config_dir)
    original_count = len(rules)

    rules = [r for r in rules if r.id != rule_id]

    if len(rules) == original_count:
        return False

    save_rules(rules, config_dir)
    return True


def get_rule(rule_id: str, config_dir: Optional[Path] = None) -> Optional[Rule]:
    """Get a rule by ID.

    Args:
        rule_id: Rule ID to find.
        config_dir: Config directory path.

    Returns:
        Rule if found, None otherwise.
    """
    rules = load_rules(config_dir)
    for r in rules:
        if r.id == rule_id:
            return r
    return None


def enable_rule(rule_id: str, enabled: bool = True, config_dir: Optional[Path] = None) -> bool:
    """Enable or disable a rule.

    Args:
        rule_id: Rule ID.
        enabled: Whether to enable or disable.
        config_dir: Config directory path.

    Returns:
        True if rule was updated, False if not found.
    """
    rule = get_rule(rule_id, config_dir)
    if rule is None:
        return False

    rule.enabled = enabled
    save_rule(rule, config_dir)
    return True


def mark_triggered(rule_id: str, config_dir: Optional[Path] = None) -> bool:
    """Mark a rule as triggered (prevents re-triggering).

    Args:
        rule_id: Rule ID.
        config_dir: Config directory path.

    Returns:
        True if rule was updated, False if not found.
    """
    rule = get_rule(rule_id, config_dir)
    if rule is None:
        return False

    rule.triggered = True
    save_rule(rule, config_dir)
    return True
