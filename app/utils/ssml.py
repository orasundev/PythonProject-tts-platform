"""
SSML validation using lxml. Rejects malformed XML before sending to edge_tts.
"""

from lxml import etree


def validate_ssml(text: str) -> str:
    """
    Parse text as XML; raise ValueError with a descriptive message if invalid.
    Returns the cleaned XML string.
    """
    try:
        root = etree.fromstring(text.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"Invalid SSML: {exc}") from exc

    # Basic sanity check: must have a <speak> root or be wrapped
    tag = etree.QName(root.tag).localname if root.tag else ""
    if tag not in {"speak", "voice", "p", "s"}:
        raise ValueError(
            f"SSML root element must be <speak>, got <{tag}>."
        )
    return text
