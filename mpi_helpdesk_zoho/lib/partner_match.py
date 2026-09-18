# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Match a Partner, then create."""


def _norm(value):
    if not value:
        return ""
    return str(value).strip().lower()


def resolve_partner(*, kind, email, vat, name, existing):
    email_n = _norm(email)
    vat_n = _norm(vat)
    name_n = _norm(name)

    if kind == "contact" and email_n:
        for row in existing:
            if _norm(row.get("email")) == email_n:
                return ("link", row["id"])

    if kind == "account":
        if vat_n:
            for row in existing:
                if _norm(row.get("vat")) == vat_n:
                    return ("link", row["id"])
        if name_n:
            for row in existing:
                if _norm(row.get("name")) == name_n:
                    return ("link", row["id"])
        if email_n:
            for row in existing:
                if _norm(row.get("email")) == email_n:
                    return ("link", row["id"])

    return ("create", None)
