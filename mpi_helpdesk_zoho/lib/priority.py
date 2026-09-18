# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Built-in priority: Desk label ↔ Helpdesk selection."""

DESK_TO_HELPDESK = {
    "lowest": "0",
    "low": "1",
    "medium": "2",
    "normal": "2",
    "high": "3",
    "urgent": "3",
}

HELPDESK_TO_DESK = {
    "0": "Low",
    "1": "Low",
    "2": "Medium",
    "3": "High",
}


def desk_to_helpdesk(priority):
    if not priority:
        return False
    return DESK_TO_HELPDESK.get(str(priority).strip().lower(), False)


def helpdesk_to_desk(priority):
    if priority is False or priority is None:
        return None
    return HELPDESK_TO_DESK.get(str(priority), "Medium")
