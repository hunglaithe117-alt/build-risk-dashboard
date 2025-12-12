"""
Security Features - Trivy vulnerability scanner.
"""

from app.pipeline.extract_nodes.security.trivy import TrivyVulnerabilityNode

__all__ = ["TrivyVulnerabilityNode"]
