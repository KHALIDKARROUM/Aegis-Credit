# Dataset Provenance Gate

The exact upstream source, owner, collection period, geography, consent basis,
field definitions, and redistribution license for `data/credit_risk.csv` have
not been verified in this repository.

The field names resemble a commonly circulated public credit-risk dataset, but
similarity is not sufficient evidence of provenance or permission.

Before redistribution or operational use, record:

- authoritative source URL and publisher;
- original file hash and retrieval date;
- license text and redistribution permission;
- population, product, geography, and collection period;
- outcome definition and performance window;
- missing-value, exclusion, and sampling rules;
- de-identification and privacy assessment;
- comparison of the source file with the included SHA-256 hash.
- units, currency, source system, observation time, and permissible use for
  every input field;
- application/approval policy that created the observed population, including
  rejected-applicant and survivorship bias;
- target event, observation horizon, maturity/censoring rules, and label owner;
- an approved decision on whether repository history containing the file and
  derived artifacts must be rewritten or access-restricted.

Current project data SHA-256:

```text
f56c566de00c25e0979a402afc57442fd20e1f4763cf16afc818bf35040df9ef
```

Until the gate is completed, treat the file as demonstration data that is
excluded from the project MIT license. It must not be loaded for scoring,
training, validation, reporting, or any other operational purpose. The
application enforces this with `DATA_PROVENANCE_VERIFIED=False` by default;
approval must be documented before that deployment setting can be changed.

`DATA_PROVENANCE_VERIFIED=True` is an attestation, not a workaround. A signed
release must repeat the attestation and bind the exact dataset digest. If the
evidence cannot be obtained, remove the CSV, model pickle, notebook outputs,
and derived reports from distributable builds and assess whether they must also
be removed from Git history.
