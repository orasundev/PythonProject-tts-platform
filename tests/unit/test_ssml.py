"""
Unit tests for SSML validation.
"""

import pytest

from app.utils.ssml import validate_ssml


def test_valid_speak_element():
    ssml = "<speak>Hello world</speak>"
    result = validate_ssml(ssml)
    assert result == ssml


def test_valid_speak_with_break():
    ssml = '<speak>Hello <break time="500ms"/> world</speak>'
    assert validate_ssml(ssml) == ssml


def test_malformed_xml_raises():
    with pytest.raises(ValueError, match="Invalid SSML"):
        validate_ssml("<speak>unclosed tag")


def test_wrong_root_element_raises():
    with pytest.raises(ValueError, match="root element"):
        validate_ssml("<html>not ssml</html>")


def test_empty_speak_allowed():
    validate_ssml("<speak></speak>")


def test_nested_voice_element():
    ssml = '<speak><voice name="en-US-AriaNeural">Hi</voice></speak>'
    validate_ssml(ssml)


def test_non_xml_raises():
    with pytest.raises(ValueError, match="Invalid SSML"):
        validate_ssml("plain text, not xml at all!")
