# backend/models.py
from django.db import models
from backend.models_managers import TradeAnalysisManager
from django.utils import timezone


# ------------------------------------------------------------
# MarketData — canonical OHLCV bars (013.1 added timeframe + idempotent key)
# ------------------------------------------------------------
class MarketData(models.Model):
    timestamp = models.DateTimeField(db_index=True)          # candle timestamp (UTC)
    symbol = models.CharField(max_length=20, db_index=True)  # e.g., EURUSD
    timeframe = models.CharField(max_length=10, db_index=True)  # '15m', '1h', etc.

    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()
    volume = models.FloatField()
    provider = models.CharField(max_length=50, default="AllTick")

    class Meta:
        # One bar per (symbol, timeframe, timestamp)
        unique_together = (("symbol", "timeframe", "timestamp"),)
        indexes = [
            models.Index(fields=["symbol", "timeframe", "timestamp"]),
        ]

    def __str__(self) -> str:
        return f"{self.symbol} {self.timeframe} @ {self.timestamp}"


# ------------------------------------------------------------
# MarketDataFeatures — engineered features per bar (Agent 010 baseline)
# ------------------------------------------------------------
class MarketDataFeatures(models.Model):
    market_data = models.OneToOneField(
        MarketData,
        on_delete=models.CASCADE,
        related_name="features",
    )

    # Core features (examples; extend as needed)
    atr_14 = models.FloatField(null=True, blank=True)
    ema_8 = models.FloatField(null=True, blank=True)
    ema_20 = models.FloatField(null=True, blank=True)
    ema_50 = models.FloatField(null=True, blank=True)
    rsi_14 = models.FloatField(null=True, blank=True)
    bb_bbm = models.FloatField(null=True, blank=True)
    bb_bbh = models.FloatField(null=True, blank=True)
    bb_bbl = models.FloatField(null=True, blank=True)
    bb_bandwidth = models.FloatField(null=True, blank=True)

    # Extended examples
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
# TradeAnalysis — rules + ML + composite + integrity (013.4)
# STEP 3: keys are STRICT (non-null) and uniqueness is enforced at DB level.
# ------------------------------------------------------------
class TradeAnalysis(models.Model):
    # Integrity keys (explicit; strict for hard idempotency)
    symbol = models.CharField(max_length=20, db_index=True)
    timeframe = models.CharField(max_length=10, db_index=True)
    bar_ts = models.DateTimeField(db_index=True)  # analyzed candle time

    # Optional link to the exact features row for explainability / joins
    market_data_feature = models.ForeignKey(
        MarketDataFeatures,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trade_analyses",
    )

    # 010 rule engine outputs
    final_decision = models.CharField(max_length=20, null=True, blank=True)  # LONG/SHORT/NO_TRADE
    rule_confidence_score = models.IntegerField(null=True, blank=True)       # 0..100
    sl = models.FloatField(null=True, blank=True)
    tp = models.FloatField(null=True, blank=True)

    # 011 ML outputs / explanation
    ml_signal = models.CharField(max_length=20, null=True, blank=True)
    ml_confidence = models.FloatField(null=True, blank=True)     # 0..100
    ml_prob_long = models.FloatField(null=True, blank=True)
    ml_prob_short = models.FloatField(null=True, blank=True)
    ml_prob_no_trade = models.FloatField(null=True, blank=True)
    ml_expected_rr = models.FloatField(null=True, blank=True)
    ml_model_version = models.CharField(max_length=50, null=True, blank=True)
    ml_model_hash_prefix = models.CharField(max_length=8, null=True, blank=True)
    top_features = models.JSONField(null=True, blank=True)

    # Composite score (rules ⊕ ML)
    composite_score = models.FloatField(null=True, blank=True)   # 0..100
    ml_skipped = models.BooleanField(default=False)

    # 013.2 state machine fields
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
    objects = TradeAnalysisManager()

    class Meta:
        unique_together = (("symbol", "timeframe", "bar_ts"),)
        indexes = [
            models.Index(fields=["symbol", "timeframe", "bar_ts"]),
            models.Index(fields=["final_decision"]),
            models.Index(fields=["ml_model_version"]),
            models.Index(fields=["status"]),
        ]

    def save(self, *args, **kwargs):
        # If linked to features but keys not set, align keys from MarketData
        if self.market_data_feature_id and (not self.symbol or not self.timeframe or not self.bar_ts):
            md = self.market_data_feature.market_data
            self.symbol = self.symbol or md.symbol
            self.timeframe = self.timeframe or md.timeframe
            self.bar_ts = self.bar_ts or md.timestamp
        super().save(*args, **kwargs)

    def finish_run_fail(self, exc: Exception):
        """
        Model-level helper (013.2.1) to persist failure details using the centralized taxonomy.
        """
        try:
            from backend.errors import map_exception  # local import to avoid circulars
            self.status = "FAILED"
            self.error_code = str(map_exception(exc).value)
            self.error_message = str(exc)
            self.finished_at = timezone.now()
            self.save(
                update_fields=[
                    "status",
                    "error_code",
                    "error_message",
                    "finished_at",
                    "updated_at",
                ]
            )
        except Exception:
            # Never raise from here; task will also log AnalysisLog failure.
            pass

    def __str__(self) -> str:
        return f"TA<{self.symbol} {self.timeframe} @ {self.bar_ts}> [{self.status}]"


# ------------------------------------------------------------
# AnalysisLog — every analysis attempt (013.2)
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
# IngestionStatus — freshness & KPIs per (symbol, timeframe) (013.2/013.3/013.4 heartbeat)
# ------------------------------------------------------------
class IngestionStatus(models.Model):
    FRESHNESS_CHOICES = [
        ("GREEN", "GREEN"),
        ("AMBER", "AMBER"),
        ("RED", "RED"),
    ]
    ESCALATION_CHOICES = [
        ("INFO", "INFO"),
        ("WARN", "WARN"),
        ("ERROR", "ERROR"),
        ("CRITICAL", "CRITICAL"),
    ]
    PROVIDER_CHOICES = [
        ("AllTick", "AllTick"),
        ("TwelveData", "TwelveData"),
    ]

    symbol = models.CharField(max_length=20, db_index=True)
    timeframe = models.CharField(max_length=10, db_index=True)

    # Freshness + provider
    last_bar_ts = models.DateTimeField(null=True, blank=True)
    last_ingest_ts = models.DateTimeField(null=True, blank=True)
    data_freshness_sec = models.IntegerField(null=True, blank=True)
    freshness_state = models.CharField(max_length=10, choices=FRESHNESS_CHOICES, default="GREEN")
    provider = models.CharField(max_length=50, choices=PROVIDER_CHOICES, default="AllTick")
    key_age_days = models.IntegerField(null=True, blank=True)
    fallback_active = models.BooleanField(default=False)

    # KPIs
    analyses_ok_5m = models.IntegerField(default=0)
    analyses_fail_5m = models.IntegerField(default=0)
    median_latency_ms = models.IntegerField(null=True, blank=True)

    # Escalation & Resilience (013.3)
    escalation_level = models.CharField(max_length=10, choices=ESCALATION_CHOICES, default="INFO")
    breaker_open = models.BooleanField(default=False)
    last_notify_at = models.DateTimeField(null=True, blank=True)
    last_signal_bar_ts = models.DateTimeField(null=True, blank=True)

    # 013.4 Heartbeat — successful poll/WS ping time even if bar didn’t advance
    last_seen_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = TradeAnalysisManager()

    class Meta:
        unique_together = (("symbol", "timeframe"),)
        indexes = [
            models.Index(fields=["symbol", "timeframe"]),
            models.Index(fields=["freshness_state"]),
            models.Index(fields=["escalation_level"]),
        ]

    def __str__(self) -> str:
        return (
            f"IngestionStatus<{self.symbol} {self.timeframe} "
            f"freshness={self.freshness_state} provider={self.provider}>"
        )


# ------------------------------------------------------------
# NotificationChannel — channel configs (013.3)
# ------------------------------------------------------------
class NotificationChannel(models.Model):
    TYPE_CHOICES = (
        ("EMAIL", "EMAIL"),
        ("WEBHOOK", "WEBHOOK"),
        ("SLACK", "SLACK"),
    )
    name = models.CharField(max_length=64, unique=True)
    channel_type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    enabled = models.BooleanField(default=False)
    min_severity = models.CharField(max_length=10, default="INFO")
    config = models.JSONField(default=dict)  # smtp/webhook/slack specifics
    events = models.JSONField(default=dict)  # {"signal": true, "failure": true, "freshness": true}
    dedupe_window_sec = models.IntegerField(default=900)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Notify<{self.name}:{self.channel_type}{' enabled' if self.enabled else ''}>"


# ------------------------------------------------------------
# MlModelRegistry — track model versions & hashes (Agent 011.2)
# ------------------------------------------------------------
class MlModelRegistry(models.Model):
    model_name = models.CharField(max_length=100, db_index=True)
    version = models.CharField(max_length=50)
    hash_prefix = models.CharField(max_length=8)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("model_name", "version"),)
        indexes = [
            models.Index(fields=["model_name", "version"]),
        ]

    def __str__(self) -> str:
        return f"{self.model_name} v{self.version}"


# ------------------------------------------------------------
# MlPreference — model weight overrides (Agent 011.3)
# ------------------------------------------------------------
class MlPreference(models.Model):
    key = models.CharField(max_length=100, unique=True)
    float_value = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)
    objects = TradeAnalysisManager()

    def __str__(self) -> str:
        return f"{self.key}={self.float_value}"

from django.db import models
from backend.models_managers import TradeAnalysisManager

class ProviderTelemetry(models.Model):
    provider = models.CharField(max_length=64, unique=True)
    quota_usage_pct = models.FloatField(null=True, blank=True)
    key_age_days = models.IntegerField(null=True, blank=True)
    fallback_active = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    objects = TradeAnalysisManager()
    class Meta:
        verbose_name = "Provider Telemetry"
        verbose_name_plural = "Provider Telemetries"

    def __str__(self) -> str:
        return f"{self.provider} telemetry"

