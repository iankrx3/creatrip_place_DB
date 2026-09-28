import pytest

from normalize.procedure import match_procedure_keys
from normalize.text_rules import (
    days_in_sentence, mentioned_languages, parse_child_options, parse_duration_min, parse_price_line, strip_html,
)


@pytest.mark.parametrize("line,expected", [
    ("[50%] 103.09 USD", (103.09, True, "USD")),
    ("1,214.95 USD", (1214.95, False, "USD")),
    ("From 20,000₩", (20000.0, False, "KRW")),
    ("Deposit From 14.73 USD", (14.73, False, "USD")),
    ("Free", (0.0, False, "USD")),
    ("Lifting | HIFU Package", None),
])
def test_parse_price_line(line, expected):
    assert parse_price_line(line) == expected


@pytest.mark.parametrize("text,expected", [
    ("Art De La Peau Facial Care (60 minutes)", 60),
    ("毛孔・疤痕管理一日套餐｜30至40分鐘", 40),
    ("Head spa 1h 30m", 90),
    ("2 hours course", 120),
    ("Rejuran Healer 2cc", None),
])
def test_parse_duration(text, expected):
    assert parse_duration_min(text) == expected


def test_child_options_attach_sale_and_original_price():
    text = "\n".join([
        "Select an option", "Show with KRW", "HOT",
        "Free Reservation | Procedure Decided After Consultation", "Free", "SELECT",
        "[Package] Sagging", "Select Options",
        "Lifting | HIFU Package: 100 shots", "[50%] 103.09 USD", "206.17 USD",
        "Lifting | ONDA Package", "[57%] 404.98 USD", "942.5 USD",
        "Select Options", "SELECT",
    ])
    children = parse_child_options(text, {"[Package] Sagging"})
    assert children == [
        {"name": "Lifting | HIFU Package: 100 shots", "group": "[Package] Sagging", "price_usd": 103.09, "original_price_usd": 206.17},
        {"name": "Lifting | ONDA Package", "group": "[Package] Sagging", "price_usd": 404.98, "original_price_usd": 942.5},
    ]


def test_procedure_keywords_match_whole_words():
    assert "photo" not in match_procedure_keys("Special Bio Photon + Aroma Body Lymph Massage")
    assert "massage" in match_procedure_keys("Special Bio Photon + Aroma Body Lymph Massage")
    assert set(match_procedure_keys("Rejuran Healer 2cc + Juvederm Filler 1cc")) >= {"skin_booster", "filler"}


def test_downtime_days_from_sentence():
    assert days_in_sentence("Volnewmer — firmer, less pain, no downtime") == (0, 0)
    assert days_in_sentence("Scabs form and fall off within 5-7 days.") == (5, 7)
    assert days_in_sentence("Temporary redness may occur.") is None


def test_mentioned_languages_ignores_platform_support_line():
    body = "24/7 English/Chinese Support\nJapanese, Chinese, and English interpretation is available."
    assert sorted(set(mentioned_languages(body))) == ["Chinese", "English", "Japanese"]
    assert mentioned_languages("24/7 English/Chinese Support") == []


def test_strip_html():
    assert strip_html("<ul><li>Avoid sauna</li><li>No alcohol</li></ul>").split("\n")[0].strip() == "Avoid sauna"


@pytest.mark.parametrize("name,desc,expected", [
    ("Star Cut + Hair Styling | 60 min", "* Pre-service consultation: 10 minutes * Final check: 5–10 minutes", 60),
    ("InMode FX/FORMA 5min | 10 min", None, 10),
    ("Aquapeel + Premium LDM 6 min (MAD)ㅣ30 min", None, 30),
    ("Body Botox (Korean) 100U | 20-90 min", None, 90),
    ("Rejuran 2cc", "Takes about 40 minutes", 40),
])
def test_duration_prefers_option_name_tail(name, desc, expected):
    assert parse_duration_min(name, desc) == expected


def test_subtype_scoped_keywords():
    botox = "[Wrinkle Botox] Forehead / Glabella (between eyebrows) / Crow's Feet"
    assert "brow_tattoo" not in match_procedure_keys(botox, "dermatology")
    assert "brow_tattoo" in match_procedure_keys("Natural Eyebrow + Retouch", "permanent_makeup")
    assert "filler" not in match_procedure_keys("Cold Perm + filler care + hair cut", "hair_salon")
    assert "filler" in match_procedure_keys("Juvederm Filler 1cc", "dermatology")
    assert "lip_tattoo" not in match_procedure_keys("makeup pouch analysis + lip color test", "personal_color")
