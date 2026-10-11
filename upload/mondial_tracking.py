"""Links to the official public Mondial Relay tracking page, never another host."""
import re
from urllib.parse import urlencode

TRACKING_PAGE="https://www.mondialrelay.fr/suivi-de-colis/"


def mondial_tracking_url(number,postal_code):
    number=str(number or "").strip()
    postal_code=str(postal_code or "").strip()
    if not re.fullmatch(r"[0-9]{7,12}",number) or not re.fullmatch(r"[0-9]{4,5}",postal_code):
        return TRACKING_PAGE
    # The site may still ask for these fields; the bot also provides copy buttons.
    return TRACKING_PAGE+"?"+urlencode({"numeroExpedition":number,"CodePostal":postal_code})
