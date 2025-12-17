import requests
from typing import Dict, List, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import settings


import yaml
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class MetricsExporter:
    def __init__(self):
        self.host = settings.SONAR_HOST_URL.rstrip("/")
        self.token = settings.SONAR_TOKEN
        self.session = self._build_session()
        self.chunk_size = 25
        self.metrics = self._load_metrics_config()

    def _load_metrics_config(self) -> List[str]:
        """Load metrics keys from sonar_metrics.yml"""
        default_metrics = [
            "ncloc",
            "complexity",
            "cognitive_complexity",
            "duplicated_lines_density",
            "violations",
            "bugs",
            "vulnerabilities",
            "code_smells",
            "sqale_index",
            "reliability_rating",
            "security_rating",
            "sqale_rating",
        ]

        try:
            config_path = Path(__file__).resolve().parents[5] / "sonar_metrics.yml"

            if not config_path.exists():
                logger.warning(
                    f"Metrics config not found at {config_path}, using defaults"
                )
                return default_metrics

            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            metrics = config.get("sonarqube", {}).get("measures", {}).get("keys", [])
            if not metrics:
                logger.warning("No metrics found in config, using defaults")
                return default_metrics

            return metrics

        except Exception as e:
            logger.error(f"Failed to load metrics config: {e}")
            return default_metrics

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

    def collect_metrics(self, component_key: str) -> Dict[str, str]:
        return self._fetch_measures(component_key, self.metrics)
