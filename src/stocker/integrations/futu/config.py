"""Futu-specific configuration model.

Parses and validates STOCKER_FUTU_* environment variables into a typed config.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FutuConfig(BaseModel):
    """Typed configuration for the Futu Open API integration."""

    host: str = Field(default="127.0.0.1", description="OpenD gateway host")
    port: int = Field(default=11111, description="OpenD gateway port")
    trd_env: str = Field(
        default="simulate",
        description="Trading environment: 'simulate' or 'real'",
    )
    market: str = Field(
        default="HK",
        description="Default market: HK / US / CN / SG / JP / AU",
    )
    trade_password: str = Field(
        default="",
        description="Trade unlock password (empty = skip unlock, fine for simulate)",
    )
    quote_enabled: bool = Field(
        default=True,
        description="Whether to enable Futu quote context on startup",
    )
    subscribe_codes: list[str] = Field(
        default_factory=list,
        description="Codes to subscribe on startup, e.g. ['HK.00700', 'US.AAPL']",
    )

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def to_futu_trd_env(self):
        """Convert string config to ``futu.TrdEnv`` enum."""
        from futu import TrdEnv

        return TrdEnv.REAL if self.trd_env.lower() == "real" else TrdEnv.SIMULATE

    def to_futu_market(self):
        """Convert market string to ``futu.TrdMarket`` enum."""
        from futu import TrdMarket

        mapping = {
            "HK": TrdMarket.HK,
            "US": TrdMarket.US,
            "CN": TrdMarket.CN,
            "SG": TrdMarket.SG,
            "JP": TrdMarket.JP,
            "AU": TrdMarket.AU,
        }
        return mapping.get(self.market.upper(), TrdMarket.HK)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_stocker_config(cls, config: dict) -> FutuConfig:
        """Build ``FutuConfig`` from the main stocker config dict.

        Reads keys prefixed with ``futu_`` (e.g. ``futu_host``, ``futu_port``).
        """
        codes_raw = config.get("futu_subscribe_codes", "")
        codes = [c.strip() for c in codes_raw.split(",") if c.strip()] if isinstance(codes_raw, str) else codes_raw

        return cls(
            host=config.get("futu_host", cls.model_fields["host"].default),
            port=int(config.get("futu_port", cls.model_fields["port"].default)),
            trd_env=config.get("futu_trd_env", cls.model_fields["trd_env"].default),
            market=config.get("futu_market", cls.model_fields["market"].default),
            trade_password=config.get("futu_trade_pwd", ""),
            quote_enabled=str(config.get("futu_quote_enabled", "true")).lower() in ("true", "1", "yes"),
            subscribe_codes=codes,
        )
