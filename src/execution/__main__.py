import logging
import os
import sys

from src.config import DRY_RUN, LIVE_TRADING, MONITOR_INTERVAL_MIN
from src.deterministic_startup import DeterministicStartup
from src.execution.execution_engine import select_executor


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logger = logging.getLogger("kucoin-lane")

    startup = DeterministicStartup(diag_log_func=logger.info)
    startup.cleanup_leftover_state()

    verify_systems = ["working_directory", "heartbeat_io", "kucoin_api"]
    verified = startup.verify_critical_systems(required_systems=verify_systems)
    if not verified:
        logger.warning("Pre-flight verification had failures — continuing in dry_run mode")

    logger.info(f"DRY_RUN={DRY_RUN}, LIVE_TRADING={LIVE_TRADING}")
    executor = select_executor(DRY_RUN, LIVE_TRADING)

    interval = int(os.getenv("CYCLE_INTERVAL", str(MONITOR_INTERVAL_MIN)))
    logger.info(f"Starting continuous loop with interval={interval}m")
    executor.run_continuous(interval_minutes=interval)


if __name__ == "__main__":
    main()
