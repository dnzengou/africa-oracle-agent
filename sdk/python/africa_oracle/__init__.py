"""africa_oracle — Python SDK for the AFRI Africa Oracle.

Usage:
    from africa_oracle import Client
    feeds = Client().feeds_quorum(min_providers=2)
"""

from .client import Client, OracleError, PriceFeed, QuorumReport
from .skill import devflow_skill

__version__ = "0.4.0"
__all__ = ["Client", "OracleError", "PriceFeed", "QuorumReport", "devflow_skill"]
