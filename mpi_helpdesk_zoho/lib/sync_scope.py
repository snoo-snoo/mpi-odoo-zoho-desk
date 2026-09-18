# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Team Map outbound; Department Map inbound."""


def allows_outbound(*, team_id, mapped_team_ids):
    return bool(team_id) and team_id in mapped_team_ids


def allows_inbound(*, department_id, mapped_department_ids):
    return bool(department_id) and department_id in mapped_department_ids
