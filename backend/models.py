from django.db import models

# ------------------------------------------------------------
# MarketData — (kept from Agent 010.1 baseline)
# ------------------------------------------------------------
class MarketData(models.Model):
    timestamp = models.DateTimeField()
    symbol = models.CharField(max_length=20)
    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()
    volume = models.FloatField()
    provider = models.CharField(max_length=50)

    class Meta:
        unique_together = ("timestamp", "symbol")
        indexes = [
            models.Index(fields=["symbol", "timestamp"]),
        ]


# ------------------------------------------------------------
# MarketDataFeatures — (kept from Agent 010.1 baseline)
# ------------------------------------------------------------
class MarketDataFeatures(models.Model):
    market_data = models.OneToOneField(
        MarketData,
        on_delete=models.CASCADE,
        related_name="features",
    )

    # Core features
    atr_14 = models.FloatField(null=True, blank=True)
    ema_8 = models.FloatField(null=True, blank=True)
    ema_20 = models.FloatField(null=True, blank=True)
    ema_50 = models.FloatField(null=True, blank=True)
    rsi_14 = models.FloatField(null=True, blank=True)
    bb_bbm = models.FloatField(null=True, blank=True)
    bb_bbh = models.FloatField(null=True, blank=True)
    bb_bbl = models.FloatField(null=True, blank=True)
    bb_bandwidth = models.FloatField(null=True, blank=True)

    # Extended features present in baseline
    vwap = models.FloatField(null=True, blank=True)
    vwap_dist = models.FloatField(null=True, blank=True)
    volume_zscore = models.FloatField(null=True, blank=True)
    range_atr_ratio = models.FloatField(null=True, blank=True)

    # Confluence flags
    ema_bull_cross = models.BooleanField(default=False)
    ema_bear_cross = models.BooleanField(default=False)
    rsi_overbought = models.BooleanField(default=False)
    rsi_oversold = models.BooleanField(default=False)
    bb_squeeze = models.BooleanField(default=False)

    class Meta:
        unique_together = ("market_data",)
        indexes = [
            models.Index(fields=["market_data"]),
        ]


# ------------------------------------------------------------
# TradeAnalysis — 010 fields preserved + 011.2 fields appended
# ------------------------------------------------------------
class TradeAnalysis(models.Model):
    market_data_feature = models.ForeignKey(
        MarketDataFeatures,
        on_delete=models.CASCADE,
        related_name="trade_analysis",
    )

    # Align TA to the market bar time (Agent 011.2)
    timestamp = models.DateTimeField(db_index=True, null=True, blank=True)

    # --------------------
    # Rule-based engine outputs (Agent 010)
    # --------------------
    rule_confidence = models.IntegerField(null=True, blank=True)
    final_decision = models.CharField(max_length=20, null=True, blank=True)
    volume_support = models.BooleanField(default=False)
    proximity_to_sr = models.BooleanField(default=False)
    candlestick_pattern = models.CharField(max_length=50, null=True, blank=True)
    pattern_location_sr = models.BooleanField(default=False)
    pattern_confirmed = models.BooleanField(default=False)
    indicator_confluence = models.BooleanField(default=False)
    confluence_ok = models.BooleanField(default=False)

    # Trade execution details (persisted by 010)
    entry_price = models.FloatField(null=True, blank=True)
    stop_loss = models.FloatField(null=True, blank=True)
    take_profit = models.FloatField(null=True, blank=True)

    # --------------------
    # ML outputs (legacy + new Agent 011.2 fields)
    # --------------------
    ml_signal = models.CharField(max_length=20, null=True, blank=True)
    ml_prob_long = models.FloatField(null=True, blank=True)
    ml_prob_short = models.FloatField(null=True, blank=True)
    ml_prob_no_trade = models.FloatField(null=True, blank=True)
    ml_expected_rr = models.FloatField(null=True, blank=True)
    ml_model_version = models.CharField(max_length=50, null=True, blank=True)
    ml_model_hash_prefix = models.CharField(max_length=8, null=True, blank=True)
    feature_importances = models.JSONField(null=True, blank=True)

    # New 011.2 ML fields
    ml_confidence = models.FloatField(null=True, blank=True)  # 0..100
    composite_score = models.FloatField(null=True, blank=True)  # 0..100
    top_features = models.JSONField(null=True, blank=True)  # explanation (Agent 011.3)

    # System bookkeeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["ml_signal"]),
            models.Index(fields=["ml_model_version"]),
            models.Index(fields=["final_decision"]),
            models.Index(fields=["timestamp"]),
        ]

    def save(self, *args, **kwargs):
        if self.timestamp is None and self.market_data_feature_id:
            try:
                md = self.market_data_feature.market_data
                self.timestamp = getattr(md, "timestamp", None)
            except Exception:
                pass
        super().save(*args, **kwargs)


# ------------------------------------------------------------
# ModelMetadata — keep existing (baseline)
# ------------------------------------------------------------
class ModelMetadata(models.Model):
    model_name = models.CharField(max_length=255)
    version = models.CharField(max_length=50)
    training_date = models.DateTimeField(auto_now_add=True)
    parameters = models.JSONField()
    metrics = models.JSONField()

    def __str__(self) -> str:
        return f"{self.model_name} v{self.version}"


# ------------------------------------------------------------
# MlPreference — for user-configurable weight overrides (Agent 011.3)
# ------------------------------------------------------------
class MlPreference(models.Model):
    key = models.CharField(max_length=100, unique=True)
    float_value = models.FloatField()

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.key}={self.float_value}"
