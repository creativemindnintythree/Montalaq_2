from django.db import models

# ------------------------------------------------------------
# MarketData — baseline + 013.1 extension (timeframe + idempotent key)
# ------------------------------------------------------------
class MarketData(models.Model):
    timestamp = models.DateTimeField(db_index=True)          # candle timestamp
    symbol = models.CharField(max_length=20, db_index=True)  # e.g., EURUSD
    timeframe = models.CharField(                            # e.g., '15m', '1h'
        max_length=10,
        default="1m",                                        # default to avoid nulls on existing rows
        db_index=True
    )

    open = models.FloatField()
    high = models.FloatField()
    low  = models.FloatField()
    close= models.FloatField()
    volume = models.FloatField()
    provider = models.CharField(max_length=50)

    class Meta:
        # 013.1 idempotence: one bar per (symbol, timeframe, timestamp)
        unique_together = ("symbol", "timeframe", "timestamp")
        indexes = [
            models.Index(fields=["symbol", "timeframe", "timestamp"]),
        ]

    def __str__(self) -> str:
        return f"{self.symbol} {self.timeframe} @ {self.timestamp}"


# ------------------------------------------------------------
# MarketDataFeatures — (kept from Agent 010.1 baseline)
# One-to-one with a specific MarketData candle
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
        indexes = [
            models.Index(fields=["market_data"]),
        ]

    def __str__(self) -> str:
        md = self.market_data
        return f"Features<{md.symbol} {md.timeframe} @ {md.timestamp}>"


# ------------------------------------------------------------
# TradeAnalysis — 010 fields preserved + 011.2 fields appended
# 013.1: enforce one analysis per bar via (market_data_feature, timestamp)
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
    rule_confidence = models.IntegerField(null=True, blank=True)   # legacy name
    rule_confidence_score = models.IntegerField(null=True, blank=True)  # 013.1 alias (0..100)
    final_decision = models.CharField(max_length=20, null=True, blank=True)  # LONG/SHORT/NO_TRADE
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

    # New 011.2 / 011.3 fields
    ml_confidence = models.FloatField(null=True, blank=True)     # 0..100
    composite_score = models.FloatField(null=True, blank=True)   # 0..100
    top_features = models.JSONField(null=True, blank=True)       # explanation (Agent 011.3)
    ml_skipped = models.BooleanField(default=False)              # 013.1 gate bookkeeping

    # --------------------
    # New 013.2 fields for persistent task states
    # --------------------
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("COMPLETE", "Complete"),
        ("FAILED", "Failed"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    error_code = models.CharField(max_length=100, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    # System bookkeeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # 013.1 idempotence at analysis layer: one TA per bar/features row
        unique_together = (("market_data_feature", "timestamp"),)
        indexes = [
            models.Index(fields=["timestamp"]),
            models.Index(fields=["final_decision"]),
            models.Index(fields=["ml_model_version"]),
            models.Index(fields=["status"]),
        ]

    def save(self, *args, **kwargs):
        # Auto-align timestamp to the underlying MarketData if missing
        if self.timestamp is None and self.market_data_feature_id:
            try:
                md = self.market_data_feature.market_data
                self.timestamp = getattr(md, "timestamp", None)
            except Exception:
                pass
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        try:
            md = self.market_data_feature.market_data
            return f"TA<{md.symbol} {md.timeframe} @ {self.timestamp}> [{self.status}]"
        except Exception:
            return f"TA<timestamp={self.timestamp}, status={self.status}>"


# ------------------------------------------------------------
# AnalysisLog — tracks every run (013.2)
# ------------------------------------------------------------
class AnalysisLog(models.Model):
    STATE_CHOICES = [
        ("PENDING", "Pending"),
        ("COMPLETE", "Complete"),
        ("FAILED", "Failed"),
    ]

    symbol = models.CharField(max_length=20, db_index=True)
    timeframe = models.CharField(max_length=10, db_index=True)
    bar_ts = models.DateTimeField(db_index=True)

    state = models.CharField(max_length=20, choices=STATE_CHOICES, default="PENDING")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    error_code = models.CharField(max_length=100, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    latency_ms = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["symbol", "timeframe", "bar_ts"]),
            models.Index(fields=["state"]),
        ]

    def __str__(self) -> str:
        return f"AnalysisLog<{self.symbol} {self.timeframe} @ {self.bar_ts} state={self.state}>"


# ------------------------------------------------------------
# IngestionStatus — tracks provider freshness & KPIs (013.2)
# ------------------------------------------------------------
class IngestionStatus(models.Model):
    FRESHNESS_CHOICES = [
        ("GREEN", "Green"),
        ("AMBER", "Amber"),
        ("RED", "Red"),
    ]

    symbol = models.CharField(max_length=20, db_index=True)
    timeframe = models.CharField(max_length=10, db_index=True)

    last_bar_ts = models.DateTimeField(null=True, blank=True)
    last_ingest_ts = models.DateTimeField(null=True, blank=True)

    freshness_state = models.CharField(
        max_length=10, choices=FRESHNESS_CHOICES, default="RED"
    )
    data_freshness_sec = models.IntegerField(null=True, blank=True)

    provider = models.CharField(max_length=50, null=True, blank=True)
    key_age_days = models.IntegerField(null=True, blank=True)
    fallback_active = models.BooleanField(default=False)

    analyses_ok_5m = models.IntegerField(default=0)
    analyses_fail_5m = models.IntegerField(default=0)
    median_latency_ms = models.IntegerField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["symbol", "timeframe"]),
            models.Index(fields=["freshness_state"]),
        ]

    def __str__(self) -> str:
        return (
            f"IngestionStatus<{self.symbol} {self.timeframe} "
            f"freshness={self.freshness_state}>"
        )


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
