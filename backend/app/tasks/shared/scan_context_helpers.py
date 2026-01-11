"""
Context-aware scan tracking helpers.

Provides functions to increment scan counters for:
- TrainingScenario (scenario_id from Training Scenario pipeline)

Detection is done by checking which collection the ID belongs to.
"""

import logging

from pymongo.database import Database

logger = logging.getLogger(__name__)


def increment_scan_completed(db: Database, context_id: str) -> bool:
    """
    Increment scans_completed counter for the correct context.

    Detects whether context_id is a TrainingScenario
    and calls the appropriate repository method.
    """
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        ObjectId(context_id)
    except InvalidId:
        logger.warning(f"Invalid context_id for scan increment: {context_id}")
        return False

    # Check if it's a TrainingScenario
    from app.repositories.training_scenario import TrainingScenarioRepository

    scenario_repo = TrainingScenarioRepository(db)
    scenario = scenario_repo.find_by_id(context_id)
    if scenario:
        scenario_repo.increment_scans_completed(context_id)
        return True

    logger.warning(f"Context {context_id} not found in TrainingScenario")
    return False


def increment_scan_failed(db: Database, context_id: str) -> bool:
    """
    Increment scans_failed counter for the correct context.
    """
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        ObjectId(context_id)
    except InvalidId:
        logger.warning(f"Invalid context_id for scan increment: {context_id}")
        return False

    # Check if it's a TrainingScenario
    from app.repositories.training_scenario import TrainingScenarioRepository

    scenario_repo = TrainingScenarioRepository(db)
    scenario = scenario_repo.find_by_id(context_id)
    if scenario:
        scenario_repo.increment_scans_failed(context_id)
        return True

    logger.warning(f"Context {context_id} not found in TrainingScenario")
    return False


def check_and_mark_scans_completed(db: Database, context_id: str) -> bool:
    """
    Check if all scans are complete and mark scan_extraction_completed.

    Returns True if all scans are now complete, False if still pending.
    """
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        ObjectId(context_id)
    except InvalidId:
        return False

    # Check if it's a TrainingScenario
    from app.repositories.training_scenario import TrainingScenarioRepository

    scenario_repo = TrainingScenarioRepository(db)
    scenario = scenario_repo.find_by_id(context_id)
    if scenario:
        scans_total = getattr(scenario, "scans_total", 0) or 0
        scans_completed = getattr(scenario, "scans_completed", 0) or 0
        scans_failed = getattr(scenario, "scans_failed", 0) or 0

        if scans_total > 0 and (scans_completed + scans_failed) >= scans_total:
            if not getattr(scenario, "scan_extraction_completed", False):
                scenario_repo.mark_scan_extraction_completed(context_id)
                logger.info(f"TrainingScenario {context_id} scan extraction completed")
            return True
        return False

    logger.warning(f"Context {context_id} not found in TrainingScenario")
    return False
