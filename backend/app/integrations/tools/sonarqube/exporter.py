import logging
from typing import Any, Dict, List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import settings

logger = logging.getLogger(__name__)


class MetricsExporter:
    """Export metrics from SonarQube API for a given component."""

    def __init__(self):
        db_settings = self._get_db_settings()
        self.host = db_settings["host_url"]
        self.token = db_settings["token"]
        self.session = self._build_session()
        self.chunk_size = 25

    def _get_db_settings(self) -> Dict[str, Any]:
        """Load SonarQube settings from database (consistent with SonarQubeTool)."""
        try:
            from app.database.mongo import get_database
            from app.services.settings_service import SettingsService

            db = get_database()
            service = SettingsService(db)
            app_settings = service.get_settings()

            # Get decrypted token for actual use
            token = service.get_decrypted_token("sonarqube") or ""

            return {
                "host_url": app_settings.sonarqube.host_url.rstrip("/"),
                "token": token,
            }
        except Exception as e:
            logger.warning(f"Could not load SonarQube settings from DB: {e}")

        # Fallback to ENV vars
        return {
            "host_url": settings.SONAR_HOST_URL.rstrip("/"),
            "token": settings.SONAR_TOKEN or "",
        }

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=3,
            read=3,
            connect=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.auth = (self.token, "")
        session.headers.update({"Accept": "application/json"})
        return session

    def _chunks(self, items: List[str]):
        for idx in range(0, len(items), self.chunk_size):
            yield items[idx : idx + self.chunk_size]

    def _fetch_measures(self, project_key: str, metrics: List[str]) -> Dict[str, str]:
        """Fetch specific metrics from SonarQube API."""
        url = f"{self.host}/api/measures/component"
        payload: Dict[str, str] = {}

        for chunk in self._chunks(metrics):
            resp = self.session.get(
                url,
                params={"component": project_key, "metricKeys": ",".join(chunk)},
                timeout=30,
            )
            resp.raise_for_status()
            component = resp.json().get("component", {})
            for measure in component.get("measures", []):
                payload[measure.get("metric")] = measure.get("value")

        return payload

    def collect_metrics(
        self,
        component_key: str,
        selected_metrics: List[str],
    ) -> Dict[str, str]:
        """
        Collect metrics from SonarQube for a component.

        Args:
            component_key: SonarQube project/component key
            selected_metrics: List of metric keys to fetch. Metric keys can have 'sonar_' prefix which will be stripped.

        Returns:
            Dict mapping metric key to value
        """
        # Strip 'sonar_' prefix if present (user selection may have it)
        metrics_to_fetch = [
            m.replace("sonar_", "") if m.startswith("sonar_") else m for m in selected_metrics
        ]

        logger.debug(f"Fetching {len(metrics_to_fetch)} metrics for {component_key}")
        return self._fetch_measures(component_key, metrics_to_fetch)
