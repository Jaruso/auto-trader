"""Trading engine - main execution loop."""

import signal
import time
from datetime import datetime
from typing import Optional

from trader.api.broker import Broker
from trader.rules.evaluator import RuleEvaluator
from trader.rules.loader import load_rules
from trader.utils.logging import get_logger


class TradingEngine:
    """Main trading engine that runs the evaluation loop."""

    def __init__(
        self,
        broker: Broker,
        poll_interval: int = 60,
        dry_run: bool = False,
    ) -> None:
        """Initialize trading engine.

        Args:
            broker: Broker instance.
            poll_interval: Seconds between price checks.
            dry_run: If True, don't execute real trades.
        """
        self.broker = broker
        self.poll_interval = poll_interval
        self.dry_run = dry_run
        self.evaluator = RuleEvaluator(broker)
        self.logger = get_logger("autotrader.engine")
        self._running = False
        self._stop_requested = False

    def start(self) -> None:
        """Start the trading engine loop."""
        self._running = True
        self._stop_requested = False

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        self.logger.info(
            f"Trading engine started | Poll interval: {self.poll_interval}s | "
            f"Dry run: {self.dry_run}"
        )

        try:
            self._run_loop()
        finally:
            self._running = False
            self.logger.info("Trading engine stopped")

    def stop(self) -> None:
        """Request engine stop."""
        self._stop_requested = True
        self.logger.info("Stop requested, will exit after current cycle")

    def _handle_shutdown(self, signum: int, frame: Optional[object]) -> None:
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop()

    def _run_loop(self) -> None:
        """Main trading loop."""
        while not self._stop_requested:
            cycle_start = time.time()

            try:
                self._run_cycle()
            except Exception as e:
                self.logger.error(f"Error in trading cycle: {e}")

            # Sleep until next interval
            elapsed = time.time() - cycle_start
            sleep_time = max(0, self.poll_interval - elapsed)

            if sleep_time > 0 and not self._stop_requested:
                time.sleep(sleep_time)

    def _run_cycle(self) -> None:
        """Run a single evaluation cycle."""
        # Check if market is open
        if not self.broker.is_market_open():
            self.logger.debug("Market closed, skipping cycle")
            return

        # Load current rules
        rules = load_rules()
        active_rules = [r for r in rules if r.enabled and not r.triggered]

        if not active_rules:
            self.logger.debug("No active rules")
            return

        self.logger.debug(f"Evaluating {len(active_rules)} active rules")

        # Evaluate and execute
        order_ids = self.evaluator.run_once(dry_run=self.dry_run)

        if order_ids:
            self.logger.info(f"Executed {len(order_ids)} orders: {order_ids}")

    def run_once(self) -> list[str]:
        """Run a single evaluation cycle manually.

        Returns:
            List of order IDs from executed trades.
        """
        self.logger.info("Running single evaluation cycle")

        if not self.broker.is_market_open():
            self.logger.warning("Market is closed")
            return []

        return self.evaluator.run_once(dry_run=self.dry_run)

    @property
    def is_running(self) -> bool:
        """Check if engine is running."""
        return self._running
