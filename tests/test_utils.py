from app.utils import parse_identifier


def test_parse_username_ok():
    normalized, kind = parse_identifier("@ciao1234")
    assert normalized == "@ciao1234"
    assert kind == "username"


def test_parse_phone_ok():
    normalized, kind = parse_identifier("+39 333-12 34 567")
    assert normalized == "+393331234567"
    assert kind == "phone"
