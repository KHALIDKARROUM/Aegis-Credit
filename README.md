# BankRisk Compass

BankRisk Compass is an end-to-end credit default risk decision-support project. It trains and calibrates a machine learning model, evaluates it on an untouched test set, and packages it in a Django dashboard with validated applicant scoring, local explanations, threshold analysis, calibration diagnostics, and governance metadata.

## Business Problem

Banks need to approve profitable borrowers while controlling default risk. A model that only maximizes accuracy is not enough because the two main mistakes have different business costs:

- False negative: a risky borrower is approved.
- False positive: a safer borrower is rejected or sent to manual review.

This project uses a business threshold that treats false negatives as more expensive than false positives, which is closer to how credit-risk decisions work in practice.

## Dataset

The project uses `data/credit_risk.csv`, which contains borrower, loan, and credit-history fields:

- borrower profile: age, income, employment length, home ownership
- loan profile: amount, interest rate, loan grade, loan intent, loan-to-income ratio
- credit history: previous default flag, credit history length
- target: `loan_status`, where `1` means default and `0` means non-default

The dataset has 32,581 rows and 12 columns. The target is imbalanced, with about 22% default cases.

## Project Structure

```text
BankRisk-Compass/
├── app/
│   ├── static/
│   │   └── app/
│   │       ├── app.js
│   │       └── styles.css
│   ├── templates/
│   │   └── app/
│   ├── forms.py
│   ├── models.py
│   ├── services.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py
├── bankrisk_compass/
│   ├── settings.py
│   └── urls.py
├── data/
│   └── credit_risk.csv
├── manage.py
├── models/
│   ├── credit_risk_model.pkl
│   └── model_manifest.json
├── notebooks/
│   └── bank.ipynb
├── reports/
│   ├── business_report.md
│   ├── classification_report.txt
│   ├── confusion_matrix.png
│   ├── final_model_metrics.csv
│   ├── model_comparison.csv
│   ├── model_comparison.png
│   ├── permutation_importance.csv
│   ├── permutation_importance.png
│   ├── threshold_analysis.csv
│   └── threshold_tradeoff.png
├── src/
│   ├── __init__.py
│   ├── model_reporting.py
│   ├── monitor_model.py
│   └── train_model.py
├── DATA_CARD.md
├── MODEL_CARD.md
├── README.md
├── requirements.txt
└── requirements-prod.txt
```

## Workflow

1. Load and inspect the credit-risk dataset.
2. Check missing values, class balance, and data quality issues.
3. Explore default patterns by income, loan amount, interest rate, grade, and loan intent.
4. Train models using a leakage-safe `Pipeline` and `ColumnTransformer`.
5. Split data into training, validation/calibration, and final test sets.
6. Compare Logistic Regression, Random Forest, and Gradient Boosting on validation data.
7. Tune and calibrate the Random Forest model.
8. Select a decision threshold on validation data using a 5:1 false-negative to false-positive cost ratio.
9. Evaluate once on the untouched final test set.
10. Save a versioned model bundle and integrity manifest.
11. Generate reports, calibration, subgroup diagnostics, explanations, and the Django dashboard.

## Leakage Prevention

The notebook originally handled missing values and encoding before splitting the data. That can leak test-set information into training. The final project fixes this by placing preprocessing inside a scikit-learn pipeline:

- numeric features: median imputation and scaling
- categorical features: most-frequent imputation and one-hot encoding
- model: Random Forest classifier

Because preprocessing is fitted inside the pipeline, transformations are learned only from the training fold.

## Model Results

The final model is a calibrated Random Forest using application-time features. Loan grade and interest rate are excluded because they may be lender-assigned after underwriting begins. Age is used for input consistency checks and monitoring, but is excluded from the score itself.

| Model | Accuracy | Precision | Recall | F1-score | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| Random Forest | 0.880 | 0.847 | 0.551 | 0.668 | 0.870 |

At the default `0.50` threshold, the final-test accuracy is 0.880 and ROC-AUC is 0.870. The validation-selected business threshold is `0.19`; on the final test set it increases default recall from 0.551 to 0.724 while routing more applicants to review. See `reports/final_model_metrics.csv` for the complete results.

## Dashboard

The Django dashboard includes:

- applicant risk prediction form
- probability of default
- Low / Medium / High risk category
- recommended action based on the business threshold
- top local factors influencing the applicant score
- validated input errors and out-of-distribution warnings
- model comparison chart
- threshold tradeoff chart
- confusion matrix
- permutation importance chart
- probability calibration and age-group monitoring diagnostics

Run it with:

```bash
python manage.py runserver
```

## How to Run

### One-click Windows launch

For non-technical Windows users:

1. Install Python 3.13 and select **Add Python to PATH** during installation.
2. Download or copy the complete project folder.
3. Double-click `Start BankRisk Compass.bat`.

The launcher creates a private Python environment, installs the required packages,
opens the dashboard in the default browser, and starts the local server. The first
launch takes longer because dependencies are installed. Keep the launcher window
open while using the application; close it or press `Ctrl+C` to stop the app.
It uses the smaller `requirements-app.txt` runtime dependency list; notebook,
training, and deployment tools are not installed for end users.

### Developer launch

Install dependencies with the Python already available on your machine:

```bash
python -m pip install -r requirements.txt
```

The saved model bundle is already included, so training is optional before starting the dashboard.

Train the model and regenerate reports:

```bash
python -m src.train_model
```

For faster local iteration, use the smaller tuning grid:

```bash
python -m src.train_model --quick
```

Open the notebook:

```bash
jupyter notebook notebooks/bank.ipynb
```

Start the dashboard:

```bash
python manage.py runserver
```

Open the dashboard at:

```text
http://127.0.0.1:8000/
```

## Key Files

- `notebooks/bank.ipynb`: polished analysis notebook with EDA, modeling workflow, and final report.
- `src/train_model.py`: reusable training script with leakage-safe preprocessing, model tuning, threshold tuning, report generation, and model saving.
- `models/credit_risk_model.pkl`: compressed model bundle used by the dashboard.
- `models/model_manifest.json`: model/data hashes and reproducibility metadata.
- `reports/business_report.md`: concise final business interpretation.
- `MODEL_CARD.md` and `DATA_CARD.md`: intended use, limitations, provenance, and controls.
- `manage.py`: Django command entry point.
- `bankrisk_compass/settings.py`: Django project settings.
- `app/views.py`: Django dashboard pages.
- `app/services.py`: model loading, scoring, report loading, and dashboard data helpers.

## Validation

```bash
python manage.py migrate
python manage.py check
python manage.py test
python -m compileall -q app bankrisk_compass src
```

The GitHub Actions workflow runs these checks for pushes and pull requests.

Compare a new batch with the training distribution:

```bash
python -m src.monitor_model --data path/to/new_applicants.csv
```

The command writes PSI/total-variation diagnostics to `reports/drift_monitoring.csv`.

## Scoring API

Set `SCORING_API_KEY`, then send validated JSON to `POST /api/v1/score/` with
either `X-API-Key` or `Authorization: Bearer <key>`. The API returns a versioned
probability and screening recommendation without performing the slower SHAP step.
If no API key is configured, the endpoint remains disabled.

## Important limitation

This is a demonstration and decision-support project, not a production credit decision engine. Operational use requires independent validation, representative data, authenticated access, durable monitoring, fair-lending review, and compliant adverse-action procedures.
