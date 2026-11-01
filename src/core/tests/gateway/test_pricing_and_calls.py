# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse

from dexterhouse.apps.gateway.messages import Usage
from dexterhouse.apps.gateway.models import LLMCall
from dexterhouse.apps.gateway.pricing import DEFAULT_PRICES, get_prices, load_prices
from dexterhouse.apps.gateway.providers import FakeProvider, ProviderError
from dexterhouse.apps.gateway.providers.fake import FakeResponse
from dexterhouse.apps.gateway.services.complete import complete


def test_cost_formula_matches_pricing_doc():
    prices = load_prices(DEFAULT_PRICES)
    usage = Usage(input=1_000_000, output=1_000_000, cached_read=500_000, cached_write=100_000)
    # (0.5M*3 + 0.5M*0.30 + 0.1M*3.75 + 1M*15) USD per 1M = 17.025 USD * 0.92
    assert prices.cost_eur("anthropic", "claude-sonnet-5-5", usage) == Decimal("15.663000")


def test_wildcard_fallbacks_and_unpriced():
    prices = load_prices(DEFAULT_PRICES)
    assert prices.cost_eur("ollama", "qwen3:14b", Usage(input=10, output=10)) == 0
    gpt = prices.cost_eur("openai", "gpt-5", Usage(input=1_000_000, cached_write=1_000_000))
    assert gpt == Decimal("2.300000")  # cache_write falls back to the input price
    assert prices.cost_eur("anthropic", "unknown", Usage(input=1)) is None


def test_fx_override_and_prices_file(tmp_path: Path, settings):
    custom = tmp_path / "prices.yaml"
    custom.write_text(DEFAULT_PRICES.read_text().replace('"2026-11-01"', '"custom"'))
    settings.PRICES_FILE = str(custom)
    settings.FX_EUR_PER_USD = "1.0"
    prices = get_prices()
    assert prices.price_version == "custom"
    assert prices.eur_per_usd == Decimal("1.0")


@pytest.mark.django_db
def test_complete_records_llm_call_with_cost(organization, make_request):
    project_id = uuid.uuid4()
    provider = FakeProvider(
        [FakeResponse(text="done", usage=Usage(input=2000, output=500, cached_read=1000))]
    )
    result, call = complete(
        make_request(),
        provider=provider,
        organization_id=organization.id,
        project_id=project_id,
        trace_id="trace-1",
    )
    assert result.message.text() == "done"
    stored = LLMCall.objects.get(pk=call.pk)
    assert stored.status == "ok"
    assert (stored.input_tokens, stored.output_tokens, stored.cached_tokens) == (2000, 500, 1000)
    # (1000*1 + 1000*0.10 + 500*2) / 1M USD * 0.92 EUR/USD
    assert stored.cost == Decimal("0.001932")
    assert stored.price_version == "2026-11-01"
    assert stored.project_id == project_id
    assert str(stored) == "fake/fake-model ok"


@pytest.mark.django_db
def test_failed_call_is_recorded(organization, make_request):
    provider = FakeProvider([FakeResponse(error="rate_limited")])
    with pytest.raises(ProviderError):
        complete(
            make_request(),
            provider=provider,
            organization_id=organization.id,
            project_id=uuid.uuid4(),
        )
    call = LLMCall.objects.get()
    assert call.status == "rate_limited"
    assert call.cost is None


@pytest.mark.django_db
def test_unpriced_model_has_null_cost(organization, make_request):
    req = make_request().model_copy(update={"model": "not-in-table"})
    _, call = complete(
        req, provider=FakeProvider(), organization_id=organization.id, project_id=uuid.uuid4()
    )
    assert call.cost is None
    assert call.status == "ok"
    assert call.error_detail == ""


@pytest.mark.django_db
def test_gateway_command(organization):
    out = StringIO()
    call_command("gateway", "call", "hi", stdout=out)
    assert "fake: hi" in out.getvalue()
    assert LLMCall.objects.count() == 1
    with pytest.raises(CommandError, match="unknown provider"):
        call_command("gateway", "call", "hi", "--provider", "nope")
    with pytest.raises(CommandError, match="unknown organization"):
        call_command("gateway", "call", "hi", "--org", "nope")


@pytest.mark.django_db
def test_admin_is_read_only(admin_client, organization):
    call_command("gateway", "call", "hi", stdout=StringIO())
    assert admin_client.get(reverse("admin:gateway_llmcall_changelist")).status_code == 200
    assert admin_client.get(reverse("admin:gateway_llmcall_add")).status_code == 403
