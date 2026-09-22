# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Seam: unique Desk statuses from organizationFields."""

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.desk_statuses import status_values_from_fields, unique_desk_statuses


class TestDeskStatuses(unittest.TestCase):
    def test_string_translations_collapse_to_api_value(self):
        self.assertEqual(
            unique_desk_statuses(["Open", "Offen", "Closed", "Geschlossen", "Warten auf Teil"]),
            ["Open", "Closed", "Warten auf Teil"],
        )

    def test_picklist_dicts_use_value_once(self):
        self.assertEqual(
            unique_desk_statuses(
                [
                    {"value": "Open", "displayValue": "Offen"},
                    {"value": "Open", "displayValue": "Open"},
                    {"value": "Closed"},
                ]
            ),
            ["Open", "Closed"],
        )

    def test_prefers_picklist_over_allowed_translations(self):
        fields = [
            {
                "apiName": "status",
                "allowedValues": ["Open", "Offen", "Closed", "Geschlossen"],
                "pickListValues": [
                    {"value": "Open"},
                    {"value": "Closed"},
                    {"value": "Escalated"},
                ],
            }
        ]
        self.assertEqual(
            status_values_from_fields(fields),
            ["Open", "Closed", "Escalated"],
        )


if __name__ == "__main__":
    unittest.main()
