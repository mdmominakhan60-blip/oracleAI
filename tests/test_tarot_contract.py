from __future__ import annotations

import pytest

from app.core import tarot


def test_tarot_deck_has_78_unique_cards_and_four_minor_suits():
    deck = tarot.full_deck()
    assert len(deck) == 78
    assert len({card["img"] for card in deck}) == 78
    assert sum(card["arcana"] == "major" for card in deck) == 22
    assert sum(card["arcana"] == "minor" for card in deck) == 56
    assert {card["suit"] for card in deck if card["arcana"] == "minor"} == set(tarot.SUITS)


def test_seeded_draw_is_replayable_but_reversal_is_part_of_evidence():
    first = tarot.draw(10, seed="synthetic-seed")
    second = tarot.draw(10, seed="synthetic-seed")
    assert first == second
    assert len({card["img"] for card in first}) == 10
    ledger = tarot.reading_ledger(first, "three")
    assert ledger["deck_id"] == "rws-78-v1"
    assert all(entry["orientation"] in {"upright", "reversed"} for entry in ledger["entries"])
    flipped = [dict(card, reversed=not card["reversed"]) for card in first]
    assert tarot.reading_ledger(flipped, "three")["checksum"] != ledger["checksum"]


def test_unknown_lenormand_is_not_silently_promised_as_tarot():
    assert "lenormand" not in tarot.SPREADS
    fallback = tarot.spread("lenormand")
    assert fallback["code"] == tarot.DEFAULT_SPREAD
    assert fallback["title"] == tarot.SPREADS[tarot.DEFAULT_SPREAD]["title"]




def test_tarot_draw_rejects_impossible_sizes():
    with pytest.raises(ValueError, match="between 1 and 78"):
        tarot.draw(0)
    with pytest.raises(ValueError, match="between 1 and 78"):
        tarot.draw(79)


def test_tarot_ledger_rejects_duplicate_and_unknown_evidence():
    card = dict(tarot.DECK[0], reversed=False)
    with pytest.raises(ValueError, match="duplicate"):
        tarot.reading_ledger([card, dict(card)], "one")
    with pytest.raises(ValueError, match="unknown"):
        tarot.reading_ledger([{"img": "not-a-card", "name": "Подделка", "reversed": False}], "one")


def test_tarot_ledger_canonicalizes_unknown_spread_code():
    ledger = tarot.reading_ledger(tarot.draw(1, seed="canonical-spread"), "unknown")
    assert ledger["spread"] == tarot.DEFAULT_SPREAD
    assert ledger["replay"]["checksum"] == ledger["checksum"]


@pytest.mark.parametrize("legacy_name", ["The Star", "Ace of Cups", "King of Wands"])
def test_legacy_english_rws_names_normalize_without_redraw(legacy_name):
    ledger = tarot.reading_ledger([{"name": legacy_name, "reversed": False}], "one")
    assert ledger["entries"][0]["card_id"] in {card["img"] for card in tarot.DECK}
    assert ledger["entries"][0]["orientation"] == "upright"
