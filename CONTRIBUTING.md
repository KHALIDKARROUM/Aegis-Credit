# Contributing

1. Create a focused branch.
2. Install `requirements.txt`.
3. Run migrations with `python manage.py migrate`.
4. Run `python manage.py check`.
5. Run `python manage.py test`.
6. Run `python -m compileall -q app bankrisk_compass src`.
7. If model behavior changes, regenerate artifacts with
   `python -m src.train_model --quick` and update the model/data cards.

Do not commit raw applicant data, local databases, `.env` files, or credentials.
Changes to features, thresholds, costs, or decision language require explicit
model-governance review.
