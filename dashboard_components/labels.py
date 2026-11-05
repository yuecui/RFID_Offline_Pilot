"""Extracted labels responsibilities; original calculations and widget behavior preserved."""
import html

def tag_formatters(USER_TAG_ALIASES):
    def short_epc(epc: str, keep: int = 8) -> str:
        epc = str(epc or "")
        if len(epc) <= keep * 2 + 1:
            compact = epc
        else:
            compact = f"{epc[:keep]}…{epc[-keep:]}"
        nickname = USER_TAG_ALIASES.get(epc.upper())
        return f"{nickname} · {compact}" if nickname else compact

    def full_tag_label(epc: str) -> str:
        """Show the entire unmodified EPC in selection widgets (nickname is local)."""
        original = str(epc or "").strip()
        nickname = USER_TAG_ALIASES.get(original.upper())
        return f"{nickname} · {original}" if nickname else original

    def full_epc_html(epc: str) -> str:
        """Copyable full EPC that wraps inside a narrow Streamlit sidebar/card."""
        return (
            '<div style="overflow-wrap:anywhere;word-break:break-word;'
            'font-family:monospace;font-size:0.86rem;line-height:1.5;'
            'padding:0.3rem 0;color:inherit">'
            + html.escape(str(epc)) + '</div>'
        )

    return short_epc, full_tag_label, full_epc_html

short_epc, full_tag_label, full_epc_html = tag_formatters({})
