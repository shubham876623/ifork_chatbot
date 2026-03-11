"""HubSpot – create Contact for qualified chatbot lead. Same endpoint and properties as lead scraper; only Lead source = Chatbot."""
import re
import httpx

HUBSPOT_BASE = "https://api.hubapi.com"


def _clean(value) -> str:
    """Avoid sending 'nan' or empty to HubSpot."""
    if value is None:
        return ""
    s = str(value).strip()
    if s.lower() in ("nan", "none", ""):
        return ""
    return s


def create_contact(
    access_token: str,
    firstname: str,
    lastname: str,
    email: str = "",
    phone: str = "",
    company: str = "",
    address: str = "",
    lead_source: str = "Chatbot",
    lead_status: str = "OPEN",
    timeout: int = 15,
) -> tuple[bool, dict | str]:
    """
    Create one Contact in HubSpot – same structure as scraper (ifork_lead_scraper push_leads_to_hubspot).
    Only difference: lead_source is "Chatbot" instead of "Google map". Same properties and fallbacks.
    """
    firstname = _clean(firstname)[:40]
    lastname = _clean(lastname)[:40] or "—"
    email = _clean(email)[:255] if _clean(email) else ""
    phone = _clean(phone)[:50]
    company = _clean(company)[:255]
    address = _clean(address)[:65535]
    if not firstname and not lastname:
        return False, "firstname and lastname required"

    lead_src = (lead_source or "Chatbot").strip()
    lead_st = lead_status.strip().upper()

    # Same property set as scraper: firstname, lastname, company, phone, address, hs_lead_status, lead_source
    contact_props = {
        "firstname": firstname,
        "lastname": lastname,
        "company": company[:255] if company else None,
        "phone": phone if phone else None,
        "address": address if address else None,
        "hs_lead_status": lead_st,
        "hs_lead_source": lead_src,
    }
    if email:
        contact_props["email"] = email
    contact_props = {k: v for k, v in contact_props.items() if v is not None and v != ""}

    url = f"{HUBSPOT_BASE}/crm/v3/objects/contacts"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    try:
        r = httpx.post(url, headers=headers, json={"properties": contact_props}, timeout=timeout)
        if r.status_code in (200, 201):
            return True, r.json()
        # Contact already exists (e.g. same email) – update existing contact so Lead source = Chatbot
        if r.status_code == 409:
            match = re.search(r"Existing ID:\s*(\d+)", r.text)
            if match:
                contact_id = match.group(1)
                patch_url = f"{HUBSPOT_BASE}/crm/v3/objects/contacts/{contact_id}"
                patch_props = {"hs_lead_status": lead_st, "hs_lead_source": lead_src}
                rp = httpx.patch(patch_url, headers=headers, json={"properties": patch_props}, timeout=timeout)
                if rp.status_code == 200:
                    return True, rp.json()
                if rp.status_code == 400 and "hs_lead_source" in rp.text:
                    patch_props.pop("hs_lead_source", None)
                    patch_props["lead_source"] = lead_src
                    rp2 = httpx.patch(patch_url, headers=headers, json={"properties": patch_props}, timeout=timeout)
                    if rp2.status_code == 200:
                        return True, rp2.json()
            return True, {"id": match.group(1)} if match else {}  # treat 409 as success
        if r.status_code == 400 and "PROPERTY_DOESNT_EXIST" in r.text and "hs_lead_source" in r.text:
            contact_props.pop("hs_lead_source", None)
            contact_props["lead_source"] = lead_src
            r2 = httpx.post(url, headers=headers, json={"properties": contact_props}, timeout=timeout)
            if r2.status_code in (200, 201):
                return True, r2.json()
            return False, f"{r2.status_code}: {r2.text[:500]}"
        if r.status_code == 400 and "PROPERTY_DOESNT_EXIST" in r.text:
            core = {k: contact_props[k] for k in ("firstname", "lastname", "company", "phone", "address", "email", "hs_lead_status") if k in contact_props and contact_props.get(k)}
            if "lead_source" in contact_props:
                core["lead_source"] = contact_props["lead_source"]
            elif "hs_lead_source" not in str(contact_props):
                core["lead_source"] = lead_src
            r3 = httpx.post(url, headers=headers, json={"properties": core}, timeout=timeout)
            if r3.status_code in (200, 201):
                return True, r3.json()
            return False, f"{r3.status_code}: {r3.text[:500]}"
        return False, f"{r.status_code}: {r.text[:500]}"
    except Exception as e:
        return False, str(e)
