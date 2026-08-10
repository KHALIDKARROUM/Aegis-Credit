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

Current project data SHA-256:

```text
f56c566de00c25e0979a402afc57442fd20e1f4763cf16afc818bf35040df9ef
```

Until the gate is completed, treat the file as demonstration data that is
excluded from the project MIT license. It must not be loaded for scoring,
training, validation, reporting, or any other operational purpose. The
application enforces this with `DATA_PROVENANCE_VERIFIED=False` by default;
approval must be documented before that deployment setting can be changed.
