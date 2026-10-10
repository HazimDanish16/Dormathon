"""Provider adapters, grounding enforcement, and fixture alert composition."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from mymarket.config import Settings
from mymarket.llm.explain import Explainer, template
from mymarket.llm.schema import Explanation, validate_grounding
from mymarket.service import MarketService
from mymarket.store.db import Article, ArticleStore
from scripts.generate_fixtures import generate

ROOT = Path(__file__).resolve().parents[1]
FACTS = {"article": {"title": "Chicken shortage", "source": "Test"},
         "prediction": {"product": "chicken", "direction": "UP", "confidence": .8}, "price_context": {"change_7d_pct": 1.2}}


@pytest.mark.parametrize("lang", ["en", "ms"])
def test_templates_and_provider_failure(lang):
    explainer = Explainer(Settings(ROOT, ROOT / "config"))
    calls = []
    def bad_provider(*args):
        calls.append(1)
        return '{"invalid":true}'
    explainer.provider = bad_provider
    output = explainer.explain(FACTS, lang)
    assert output["explanation_source"] == "template"
    assert len(calls) == 2


@pytest.mark.parametrize("field, text", [("headline", "Prices rise 99 percent"), ("domain_impact", "Thailand controls supply")])
def test_grounding_rejects_invented_numbers_and_names(field, text):
    data = template(FACTS)
    data.pop("explanation_source")
    data[field] = text
    with pytest.raises(ValueError):
        validate_grounding(Explanation.model_validate(data), FACTS, "en")


@pytest.mark.parametrize("provider", ["gemini", "groq", "ollama"])
def test_provider_adapters(provider, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    data = template(FACTS)
    data.pop("explanation_source")
    data["confidence_note"] = "This prediction is uncertain."
    data["domain_impact"] = "Prices may rise."
    data["product_impacts"][0]["why"] = "News suggests higher price pressure."
    def handler(request):
        payload = json.loads(request.content)
        if provider == "gemini":
            assert request.headers["x-goog-api-key"] == "test-key"
            assert payload["generationConfig"]["responseMimeType"] == "application/json"
            response = {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}
        elif provider == "groq":
            assert payload["response_format"]["type"] == "json_object"
            response = {"choices": [{"message": {"content": json.dumps(data)}}]}
        else:
            assert payload["stream"] is False
            response = {"response": json.dumps(data)}
        return httpx.Response(200, json=response)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = Explainer(Settings(ROOT, ROOT / "config"), client).explain(FACTS)
    assert result["explanation_source"] == "provider"


def test_fixture_alerts_and_confidence_filter(tmp_path):
    generate(tmp_path)
    settings = Settings(ROOT, ROOT / "config", data_mode="fixture", data_dir=tmp_path, database_path=tmp_path / "FAKE.sqlite3")
    now = datetime.now(timezone.utc)
    ArticleStore(settings.sqlite_path).insert(Article("https://example.com/FAKE", "Chicken shortage", "FAKE", now, "", "", "en", now))
    service = MarketService(settings)
    result = service.scan_alerts(lang="ms")
    assert result["synthetic"]
    assert len(result["alerts"]) == 1
    assert result["alerts"][0]["explanation"]["explanation_source"] == "template"
    assert service.scan_alerts(min_confidence=.9)["alerts"] == []
    assert service.forward_validation()["logged"] == 1
