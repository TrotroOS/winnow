from __future__ import annotations

from winnow.situation_parser import parse_situation, parse_situation_text


def test_parse_launch_b2b_cto_ghana() -> None:
    s = parse_situation_text("B2B SaaS launch need CTO contacts in Ghana")
    assert s.situation_type == "launch"
    assert "b2b" in s.sector_hints
    assert "saas" in s.sector_hints
    assert "cto" in s.role_hints
    assert s.geography is not None
    assert "ghana" in s.geography.lower()


def test_parse_dict_round_trip() -> None:
    s = parse_situation(
        {
            "type": "fundraise",
            "sector_hints": ["fintech"],
            "role_hints": ["ceo"],
            "geography": "Kenya",
            "keywords": ["seed"],
        }
    )
    assert s.situation_type == "fundraise"
    assert s.sector_hints == ("fintech",)
    assert s.role_hints == ("ceo",)
    assert s.geography == "Kenya"
    assert s.keywords == ("seed",)