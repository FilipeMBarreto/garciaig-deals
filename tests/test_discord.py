import json
import re
from datetime import date
import pytest
import requests
from garciaig import discord
from garciaig.models import Game, Week


def game(i, name, price, preorder=False):
    return Game(i, name, f"slug-{i}", price, price, 0, 1791244800, preorder, False, True, 5, 0)


def make_week():
    return Week(
        "2026-W41", date(2026, 10, 5), date(2026, 10, 11),
        game(1, "Star [Wars]", 39.99, True), game(2, "Zoo", 38.49, True),
        {"20": [game(3, "A", 15)], "10": [], "5": [], "2": []},
    )


def test_payload_links_all_affiliate_and_markdown_safe():
    p = discord.build_payload(make_week(), "https://garcia.example/")
    text = json.dumps(p, ensure_ascii=False)
    links = re.findall(r"\((https://www\.instant-gaming\.com[^)]*)\)", text)
    assert len(links) == 3
    assert all(l.endswith("?igr=garciap") for l in links)
    assert "Star \\[Wars\\]" in p["embeds"][0]["description"]
    assert "https://garcia.example/" in p["content"]
    assert 1 <= len(p["embeds"]) <= 10
    assert all(len(e["description"]) <= 4096 for e in p["embeds"])
    assert len(p["content"]) <= 2000


def test_empty_blocks_are_omitted():
    titles = [e["title"] for e in discord.build_payload(make_week())["embeds"]]
    assert any("Destaque" in t for t in titles) and any("20" in t for t in titles)
    assert not any("até 2 €" in t.lower() for t in titles)


def test_send_posts_json_and_raises_on_error():
    seen = {}

    class R:
        def __init__(self, ok): self.ok = ok
        def raise_for_status(self):
            if not self.ok: raise RuntimeError("boom")

    def post(url, json, timeout):
        seen.update(url=url, json=json)
        return R(True)

    discord.send({"content": "x"}, "https://hook", post=post)
    assert seen == {"url": "https://hook", "json": {"content": "x"}}
    with pytest.raises(RuntimeError):
        discord.send({}, "https://hook", post=lambda url, json, timeout: R(False))


def test_main_without_webhook_is_noop(tmp_path, monkeypatch):
    f = tmp_path / "p.json"
    f.write_text("{}")
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    assert discord.main([str(f)]) == 0


def test_main_hides_webhook_secret_in_error(tmp_path, monkeypatch, capsys):
    webhook_url = "https://discord.com/api/webhooks/123/SECRET_TOKEN"

    class FakeResponse:
        status_code = 404

    def mock_send(payload, url, post=None):
        raise requests.HTTPError(f"404 for url: {webhook_url}", response=FakeResponse())

    f = tmp_path / "p.json"
    f.write_text("{}")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", webhook_url)
    monkeypatch.setattr(discord, "send", mock_send)

    assert discord.main([str(f)]) == 1
    captured = capsys.readouterr()
    assert "SECRET_TOKEN" not in captured.out
    assert "SECRET_TOKEN" not in captured.err
    assert "404" in captured.out or "404" in captured.err


def test_tier_title_singular_for_one_game():
    p = discord.build_payload(make_week())
    assert any(e["title"] == "🎮 1 jogo até 20 €" for e in p["embeds"])


def test_payload_disables_mentions():
    assert discord.build_payload(make_week())["allowed_mentions"] == {"parse": []}
