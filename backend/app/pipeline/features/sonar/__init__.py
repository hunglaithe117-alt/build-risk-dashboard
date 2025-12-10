"""
SonarQube Feature Nodes.

Extracts SonarQube quality metrics as pipeline features:
- Bug counts, vulnerabilities, code smells
- Coverage metrics
- Complexity metrics
- Duplication metrics
- Size metrics
"""

from app.pipeline.features.sonar.sonar import SonarMeasuresNode

__all__ = [
    "SonarMeasuresNode",
]
