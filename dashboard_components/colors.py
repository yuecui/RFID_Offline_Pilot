"""Extracted colors responsibilities; original calculations and widget behavior preserved."""
from dashboard_services.settings import TAG_PALETTE
import hashlib

def stable_tag_color(epc: str) -> str:
    digest = hashlib.sha256(str(epc).encode("utf-8")).digest()
    index = int.from_bytes(digest[:2], "big") % len(TAG_PALETTE)
    return TAG_PALETTE[index]

def build_tag_colors(epcs):
    return {str(epc): stable_tag_color(str(epc)) for epc in epcs}
