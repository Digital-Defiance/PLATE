import json

from plate import pipeline, vlm
from plate.config import Config
from mock_vlm import serve


def test_vlm_names_and_groups(samples, tmp_path, monkeypatch):
    monkeypatch.setattr(vlm, "CACHE_DIR", tmp_path / "cache")

    def reply(text):
        if "Group shapes" in text:
            ids = [int(i) for i in __import__("re").findall(r'"id": (\d+)', text)][:2]
            return json.dumps({"groups": [{"name": "Test Group", "members": ids}]})
        return '```json\n{"name": "mock thing"}\n```'

    srv, url = serve(reply)
    try:
        r = pipeline.run(samples / "face.png", Config(vlm_url=url))
    finally:
        srv.shutdown()
    assert "Mock Thing" in r.svg and 'data-name="Test Group"' in r.svg


def test_vlm_unreachable_falls_back(samples):
    r = pipeline.run(samples / "face.png", Config(vlm_url="http://127.0.0.1:9/v1"))
    assert "Yellow" in r.svg or "circle" in r.svg      # classical names still produced


def test_json_extractor_handles_reasoning_output():
    """Qwen3-style replies: <think> blocks, fences, and trailing prose must not
    break JSON extraction (regression: 'no JSON in reply' on real LM Studio)."""
    # think block before the JSON
    assert vlm._json('<think>Let me look...</think>\n{"name": "Star"}')["name"] == "Star"
    # fenced JSON with reasoning preamble and trailing commentary
    r = vlm._json('<think>eye = ball+highlight</think>\n'
                  '```json\n{"groups": [{"name": "Left Eye", "members": [5, 1]}]}\n```\n'
                  'That groups the eye parts.')
    assert r["groups"][0]["members"] == [5, 1]
    # balanced extraction stops at the first complete object, ignoring trailing text
    assert vlm._json('{"name": "A"} and then some words {"name": "B"}')["name"] == "A"


def test_pick_model_skips_embeddings():
    assert vlm.pick_model(["text-embedding-nomic", "qwen/qwen3.8-27b"]) == "qwen/qwen3.8-27b"
    assert vlm.pick_model(["a", "b"], "b") == "b"          # explicit preference wins
    assert vlm.pick_model(["bge-embed"]) == "bge-embed"    # fallback when all look non-vision
    assert vlm.pick_model([]) == ""
