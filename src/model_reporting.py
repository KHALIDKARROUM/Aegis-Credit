from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import confusion_matrix, f1_score, recall_score, roc_auc_score


def save_calibration_report(
    y_true: pd.Series,
    probabilities: np.ndarray,
    reports_dir: Path,
) -> pd.DataFrame:
    observed, predicted = calibration_curve(
        y_true,
        probabilities,
        n_bins=10,
        strategy="quantile",
    )
    frame = pd.DataFrame(
        {
            "mean_predicted_probability": predicted,
            "observed_default_rate": observed,
            "absolute_gap": np.abs(predicted - observed),
        }
    )
    frame.to_csv(reports_dir / "calibration_analysis.csv", index=False)

    plt.figure(figsize=(7, 6))
    plt.plot([0, 1], [0, 1], linestyle="--", color="#60708d", label="Perfect calibration")
    plt.plot(predicted, observed, marker="o", color="#0b63ce", label="Calibrated model")
    plt.xlabel("Mean predicted probability")
    plt.ylabel("Observed default rate")
    plt.title("Probability Calibration on Final Test Set")
    plt.legend()
    plt.tight_layout()
    plt.savefig(reports_dir / "calibration_curve.png", dpi=160)
    plt.close()
    return frame


def save_age_fairness_report(
    data: pd.DataFrame,
    y_true: pd.Series,
    probabilities: np.ndarray,
    threshold: float,
    reports_dir: Path,
) -> pd.DataFrame:
    evaluation = data.loc[y_true.index, ["person_age"]].copy()
    evaluation["actual_default"] = y_true
    evaluation["predicted_default"] = (probabilities >= threshold).astype(int)
    evaluation["probability"] = probabilities
    evaluation["age_group"] = pd.cut(
        evaluation["person_age"],
        bins=[0, 24, 34, 49, 61, np.inf],
        labels=["20-24", "25-34", "35-49", "50-61", "62+"],
    )

    rows = []
    for group, values in evaluation.groupby("age_group", observed=True):
        tn, fp, fn, tp = confusion_matrix(
            values["actual_default"],
            values["predicted_default"],
            labels=[0, 1],
        ).ravel()
        rows.append(
            {
                "age_group": str(group),
                "applicants": len(values),
                "observed_default_rate": values["actual_default"].mean(),
                "predicted_high_risk_rate": values["predicted_default"].mean(),
                "average_predicted_probability": values["probability"].mean(),
                "true_positive_rate": tp / (tp + fn) if tp + fn else 0.0,
                "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0,
            }
        )

    frame = pd.DataFrame(rows)
    frame.to_csv(reports_dir / "fairness_age_groups.csv", index=False)
    return frame


def save_bootstrap_intervals(
    y_true: pd.Series,
    probabilities: np.ndarray,
    threshold: float,
    reports_dir: Path,
    iterations: int = 400,
) -> pd.DataFrame:
    truth = y_true.to_numpy()
    predictions = (probabilities >= threshold).astype(int)
    random = np.random.default_rng(42)
    samples: dict[str, list[float]] = {"roc_auc": [], "recall": [], "f1_score": []}

    for _ in range(iterations):
        indices = random.integers(0, len(truth), len(truth))
        sampled_truth = truth[indices]
        if len(np.unique(sampled_truth)) < 2:
            continue
        sampled_probability = probabilities[indices]
        sampled_prediction = predictions[indices]
        samples["roc_auc"].append(roc_auc_score(sampled_truth, sampled_probability))
        samples["recall"].append(recall_score(sampled_truth, sampled_prediction, zero_division=0))
        samples["f1_score"].append(f1_score(sampled_truth, sampled_prediction, zero_division=0))

    rows = []
    for metric, values in samples.items():
        rows.append(
            {
                "metric": metric,
                "estimate": float(np.median(values)),
                "lower_95": float(np.quantile(values, 0.025)),
                "upper_95": float(np.quantile(values, 0.975)),
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(reports_dir / "metric_confidence_intervals.csv", index=False)
    return frame
