"""Picture cards: they draw, they're attached to the right cards, and Discord shows them inside the embed."""
from squadbot import cards, images
from squadbot.adapters.discord_bot import embed, image_file
from squadbot.store import Game, Question

PNG = b"\x89PNG"


def game(**kw):
    qs = [Question("What is a cache hit?", ["Data found", "Data lost", "A crash", "A loop"], 0, "") for _ in range(3)]
    return Game("g", "s", "caches", qs, course="CSE 230", **kw)


def test_battle_results_profile_draw():
    assert images.battle(game(hp=60), "The Caches Boss", "CRIT!").startswith(PNG)
    assert images.battle(game(hp=0, outcome="victory"), "The Caches Boss").startswith(PNG)
    board = [("1", "Malaika 🔥", 300), ("2", "Dhanush", 200)]
    assert images.results(game(hp=0, outcome="victory"), "The Caches Boss", board, ["caches"]).startswith(PNG)
    assert images.results(game(hp=40, outcome="survived"), "Boss", [], []).startswith(PNG)
    p = {"name": "Malaika Khan", "xp": 420, "accuracy": None, "games": 2, "daily": 0, "badges": []}
    assert images.profile(p).startswith(PNG)


def test_cards_carry_images_and_discord_shows_them():
    card = cards.intro(game())
    assert card.image and card.image.startswith(PNG)
    e = embed(card)
    assert e.image.url == "attachment://card.png"
    assert image_file(card).filename == "card.png"
    assert cards.question(game(), 0).image is None


def test_images_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(images.config, "IMAGES", False)
    assert cards.intro(game()).image is None


def test_a_broken_image_never_breaks_the_card(monkeypatch):
    monkeypatch.setattr(images, "Canvas", None)  # drawing will crash
    card = cards.intro(game())
    assert card.image is None and card.title
