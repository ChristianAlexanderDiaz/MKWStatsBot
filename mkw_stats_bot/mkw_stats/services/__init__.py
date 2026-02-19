"""
Service layer for the MKW Stats Bot.

Services encapsulate business logic that spans multiple repositories,
providing single entry points for complex operations like war submission.
"""

from .war_service import WarService

__all__ = [
    "WarService",
]
