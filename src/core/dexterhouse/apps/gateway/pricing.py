# SPDX-License-Identifier: AGPL-3.0-or-later
"""Versioned price table: USD prices, costs stored in EUR (CD-024, infra/pricing)."""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml
from django.conf import settings
from pydantic import BaseModel, ConfigDict, Field

from dexterhouse.apps.gateway.messages import Usage

DEFAULT_PRICES = Path(__file__).with_name("prices.yaml")
MILLION = Decimal(1_000_000)
QUANTUM = Decimal("0.000001")


class ModelPrice(BaseModel):
    """USD per 1M tokens; missing cache prices fall back to the input price."""

    model_config = ConfigDict(extra="allow")
    input: Decimal
    output: Decimal
    cache_read: Decimal | None = None
    cache_write: Decimal | None = None


class PriceTable(BaseModel):
    model_config = ConfigDict(extra="ignore")
    price_version: str
    currency: str = "USD"
    fx: dict[str, Decimal] = Field(default_factory=dict)
    models: dict[str, dict[str, ModelPrice]]

    @property
    def eur_per_usd(self) -> Decimal:
        return self.fx["EUR_per_USD"]

    def price(self, provider: str, model: str) -> ModelPrice | None:
        table = self.models.get(provider, {})
        return table.get(model) or table.get("*")

    def cost_eur(self, provider: str, model: str, usage: Usage) -> Decimal | None:
        """EUR cost of a call, or None when the model is not priced."""
        price = self.price(provider, model)
        if price is None:
            return None
        cache_read = price.cache_read if price.cache_read is not None else price.input
        cache_write = price.cache_write if price.cache_write is not None else price.input
        usd = (
            (usage.input - usage.cached_read) * price.input
            + usage.cached_read * cache_read
            + usage.cached_write * cache_write
            + usage.output * price.output
        ) / MILLION
        return (usd * self.eur_per_usd).quantize(QUANTUM)


def load_prices(path: Path, fx_override: str = "") -> PriceTable:
    table = PriceTable.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if fx_override:
        table.fx["EUR_per_USD"] = Decimal(fx_override)
    return table


@lru_cache(maxsize=4)
def _cached(path: str, fx_override: str) -> PriceTable:
    return load_prices(Path(path), fx_override)


def get_prices() -> PriceTable:
    """Current table from PRICES_FILE (or the bundled one) with FX_EUR_PER_USD applied."""
    path = settings.PRICES_FILE or str(DEFAULT_PRICES)
    return _cached(path, settings.FX_EUR_PER_USD)
