from __future__ import annotations

from django.db import models


class PredictionAudit(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    feature_digest = models.CharField(max_length=64)
    probability = models.FloatField()
    threshold = models.FloatField()
    risk_category = models.CharField(max_length=16)
    decision = models.CharField(max_length=80)
    model_version = models.CharField(max_length=32)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.model_version}: {self.risk_category} ({self.probability:.3f})"
