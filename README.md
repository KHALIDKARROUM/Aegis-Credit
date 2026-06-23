# BankRisk Compass

BankRisk Compass is an end-to-end credit default risk project. It trains a machine learning model to estimate whether a loan applicant is likely to default, then packages the result into a Django dashboard for applicant-level risk scoring, model explanation, and business threshold analysis.

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
│   │       └── styles.css
│   ├── templates/
│   │   └── app/
│   ├── services.py
│   ├── urls.py
│   └── views.py
├── bankrisk_compass/
│   ├── settings.py
│   └── urls.py
├── data/
│   └── credit_risk.csv
├── manage.py
├── models/
│   └── credit_risk_model.pkl
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
│   └── train_model.py
├── README.md
└── requirements.txt
```

## Workflow

1. Load and inspect the credit-risk dataset.
2. Check missing values, class balance, and data quality issues.
3. Explore default patterns by income, loan amount, interest rate, grade, and loan intent.
4. Train models using a leakage-safe `Pipeline` and `ColumnTransformer`.
5. Compare Logistic Regression, Random Forest, and Gradient Boosting.
6. Tune the Random Forest model.
7. Tune a decision threshold using a 5:1 false-negative to false-positive cost ratio.
8. Save the model bundle with `joblib`.
9. Generate reports, charts, permutation importance, and a Django dashboard.

## Leakage Prevention

The notebook originally handled missing values and encoding before splitting the data. That can leak test-set information into training. The final project fixes this by placing preprocessing inside a scikit-learn pipeline:

- numeric features: median imputation and scaling
- categorical features: most-frequent imputation and one-hot encoding
- model: Random Forest classifier

Because preprocessing is fitted inside the pipeline, transformations are learned only from the training fold.

## Model Results

The final model is a tuned Random Forest.

| Model | Accuracy | Precision | Recall | F1-score | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| Random Forest | 0.934 | 0.974 | 0.715 | 0.825 | 0.931 |
| Gradient Boosting | 0.929 | 0.951 | 0.710 | 0.813 | 0.925 |
| Logistic Regression | 0.815 | 0.555 | 0.771 | 0.645 | 0.870 |

At the default `0.50` threshold, the Random Forest achieves about 93% accuracy and a 0.825 F1-score. The business threshold is `0.26`, which increases default recall from 0.715 to 0.784 by sending more borderline applicants to review.

## Dashboard

The Django dashboard includes:

- applicant risk prediction form
- probability of default
- Low / Medium / High risk category
- recommended action based on the business threshold
- top local factors influencing the applicant score
- model comparison chart
- threshold tradeoff chart
- confusion matrix
- permutation importance chart

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
- `reports/business_report.md`: concise final business interpretation.
- `manage.py`: Django command entry point.
- `bankrisk_compass/settings.py`: Django project settings.
- `app/views.py`: Django dashboard pages.
- `app/services.py`: model loading, scoring, report loading, and dashboard data helpers.

## Next Improvements

- Add calibration analysis to make probabilities more reliable.
- Add model monitoring for drift in applicant income, loan amount, and default rate.
- Add fairness checks across age groups or other legally appropriate protected attributes.
- Connect the dashboard to a database or API for real-time scoring.
