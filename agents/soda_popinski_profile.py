"""Soda Popinski — character profile data.

Module-level constant chosen because the data is consumed only by
`agents.soda_popinski.py::SodaPopinskiAgent.system_prompt()`. Article
1.3 procedural memory rule: only the originating agent may modify
this data; treat it as read-only for everyone else.
"""
from typing import Dict, Any


SODA_POPINSKI_PROFILE: Dict[str, Any] = {
    "name": "Soda Popinski",
    "original_name": "Vodka Drunkenski",
    "first_appearance": "Super Punch-Out!! (1984 Arcade)",
    "renamed_in": "Punch-Out!! (NES)",
    "height": "6'6\"",
    "stance": "Southpaw",
    "traits": [
        "Constant soda drinking between rounds (heals in-game)",
        "Distinctive laugh",
        "Brutal uppercuts",
        "Hides bottles in trunks",
        "Rule-breaker",
    ],
    "bio": (
        "Soda Popinski is the Russian boxer from the Punch-Out!! series "
        "(originally 'Vodka Drunkenski' in the 1984 arcade release). "
        "A 6'6\" southpaw whose Title Defense make him progressively redder "
        "and harder to read. One Hit Knockdown in NES: intercept uppercut "
        "with gut punch (hold down), then Star Punch."
    ),
}
