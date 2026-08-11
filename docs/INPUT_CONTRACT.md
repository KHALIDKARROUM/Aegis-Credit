# Application Input Contract

This document describes the interface enforced by the current web form, batch
loader, and scoring API. It is a technical validation contract, not evidence
that the bundled demonstration fields are sufficient, lawful, or suitable for
credit underwriting. Dataset units, currency, collection timing, source-system
ownership, and permissible use remain unresolved in `DATA_PROVENANCE.md`.

## Field contract

| Field | Type and accepted values | Meaning and handling |
|---|---|---|
| `applicant_reference` | String, at most 80 characters; value optional | Internal application/case reference. Do not send a name, account number, government identifier, email address, or other direct identifier. The batch header must be present even when every value is blank. |
| `person_age` | Integer, 18 through 100 | Age in completed years at application time. Used for plausibility checks, excluded from the model, and not retained in the saved case input. |
| `person_income` | Integer, 1 through 2,000,000 | Annual income in one deployment-approved currency and definition. The bundled data does not establish that currency or whether the amount is gross, net, individual, or household income. |
| `person_emp_length` | Number, 0 through 60 | Completed years in the employment definition approved for the deployment. It cannot exceed `person_age - 14`. |
| `person_home_ownership` | `MORTGAGE`, `OTHER`, `OWN`, or `RENT` | Housing status at the approved observation time. Values are case-sensitive. |
| `loan_amnt` | Integer, 500 through 500,000 | Requested principal in the same approved currency as income. |
| `loan_intent` | `DEBTCONSOLIDATION`, `EDUCATION`, `HOMEIMPROVEMENT`, `MEDICAL`, `PERSONAL`, or `VENTURE` | Declared purpose using the deployment's approved mapping. Values are case-sensitive. |
| `cb_person_cred_hist_length` | Integer, 0 through 50 | Completed years of credit history at application time. It cannot exceed `person_age - 16`. |
| `cb_person_default_on_file` | `N` or `Y` | Prior-default indicator from the deployment's approved source and lookback definition. Values are case-sensitive. |

The interface uses neutral “monetary units” unless `CURRENCY_CODE` is set.
That presentation does not establish the source dataset's currency. Configure
and validate product/currency semantics before any non-demo use.

## Derived and excluded fields

`loan_percent_income` must not be supplied. The service always computes
`loan_amnt / person_income` from the accepted raw values and rounds it to four
decimal places for the model frame. Any similarly named source column is
overwritten during training and offline validation.

`loan_grade` and `loan_int_rate` are not accepted because they may be assigned
after underwriting begins. `person_age` is accepted only for plausibility
validation and does not enter the probability model. Adding fields or changing
units, category mappings, derivations, or observation timing requires a new
feature-contract version, model version, validation, and signed release.

## Cross-field and model-domain behavior

- A loan greater than 150% of annual income fails ordinary validation.
- A loan greater than annual income is outside the supported scoring domain;
  the API returns HTTP 422, the batch row is invalid, and the web workflow does
  not create a score.
- Values outside the development reference range can produce a verification
  warning. Materially out-of-domain values are withheld from scoring.
- Passing these checks only means the payload satisfies this software
  contract. It does not establish affordability, eligibility, identity,
  product compliance, or data accuracy.

## Web and API requests

The web form uses the labels shown in the interface but enforces the same
values. The API accepts a JSON object containing exactly the fields above;
unknown properties are rejected. `applicant_reference` is optional in JSON and
all other fields are required. See `/api/v1/openapi.json` for the machine-readable
schema.

API clients should send a UUID in `Idempotency-Key` for every logical
application. Reusing the same key with the same normalized request returns the
stored result. Reusing it with different content returns HTTP 409. A key is a
retry identifier, not an applicant identifier, and must not contain personal
data.

## Batch files

CSV and `.xlsx` uploads use one header row and these exact columns, in any
order:

```text
applicant_reference
person_age
person_income
person_emp_length
person_home_ownership
loan_amnt
loan_intent
cb_person_cred_hist_length
cb_person_default_on_file
```

All headers are required and unknown columns are rejected. Individual
`applicant_reference` cells may be blank. For `.xlsx`, only the first worksheet
is read. Use UTF-8 for CSV files. The configured defaults permit at most 1,000
rows and a 10 MiB upload; operators may lower or raise those limits through
`MAX_BATCH_ROWS` and `MAX_UPLOAD_BYTES` after capacity review. XLSX archive
member count, expanded size, path safety, and compression ratio are checked
before parsing.

Each row is validated independently after the file-level schema passes. Valid
rows can be scored while invalid rows retain errors for reconciliation. A
downloaded result is spreadsheet-injection escaped, but it still contains
sensitive workflow data and must use approved storage and transfer controls.

Download the canonical template from `/batch/template.csv` rather than copying
an old spreadsheet.

## Changes and ownership still required

Before operational use, the organization must assign owners and approve:

- currency, units, definitions, observation time, source, and permissible use
  for every field;
- product, geography, applicant population, and authoritative category maps;
- data-quality rejection and manual no-score procedures;
- whether each field is necessary and whether it introduces proxy or
  discrimination risk;
- a versioned schema-change, client-migration, and backward-compatibility
  process.

Those decisions cannot be inferred from the included CSV or completed by code
alone.
