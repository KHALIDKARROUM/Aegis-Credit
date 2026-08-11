# Production Governance Checklist

This checklist records controls that require organizational evidence rather than code alone. It is not legal advice.

## Data approval

- [ ] Authoritative dataset owner, source, license, and extraction date recorded
- [ ] Product, geography, applicant population, and outcome window documented
- [ ] Training population compared with the intended production population
- [ ] Missingness, exclusions, duplicates, outliers, and label maturity approved
- [ ] Retention, privacy, access, and deletion requirements approved

## Business policy

- [ ] Exposure at default, loss given default, margin, funding, and review costs approved
- [ ] Review capacity and service-level targets tested against expected routing volume
- [ ] Threshold and risk-band decision memo signed by business and risk owners
- [ ] Human override authority, reason taxonomy, and escalation path documented

## Independent validation

- [ ] Development code and artifacts independently reproduced
- [ ] Out-of-time and representative external validation completed
- [ ] Calibration, discrimination, uncertainty, stability, and sensitivity reviewed
- [ ] Challenger models and simpler alternatives assessed
- [ ] Limitations, compensating controls, and validation findings closed or accepted

Federal Reserve model-risk guidance was revised on April 17, 2026 in
[SR 26-2](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf).
Applicability depends on the institution and use case.

## Fair lending and adverse action

- [ ] Legally appropriate protected-class analysis completed
- [ ] Proxy, interaction, geography, and subgroup risks reviewed
- [ ] Small-sample uncertainty and multiple-testing concerns addressed
- [ ] Specific adverse-action reason mapping validated against actual model behavior
- [ ] Applicant notices reviewed by qualified legal/compliance staff

The primary U.S. reference listed here is the binding adverse-action provision
in [12 CFR 1002.9](https://www.ecfr.gov/current/title-12/chapter-X/part-1002/subpart-A/section-1002.9).
CFPB Circular 2022-03 was withdrawn in May 2025 and must not be represented as
current primary authority; see the CFPB's
[withdrawn-guidance register](https://www.consumerfinance.gov/compliance/guidance/withdrawn-guidance/).

For an EU use case, determine whether the system is a high-risk
creditworthiness/credit-scoring system under the
[EU AI Act](https://eur-lex.europa.eu/eli/reg/2024/1689/oj?locale=en) and apply
the relevant [EBA loan-origination and monitoring guidelines](https://www.eba.europa.eu/activities/single-rulebook/regulatory-activities/credit-risk/guidelines-loan-origination-and-monitoring?version=2020).
Applicability, dates, and required controls depend on the institution,
jurisdiction, and actual use and require qualified legal advice.

## Technology and operations

- [ ] Authentication, least privilege, joiner/mover/leaver, and key rotation tested
- [ ] PostgreSQL backups and restoration tested
- [ ] Penetration test and dependency/security review completed
- [ ] Monitoring owners, alert thresholds, and incident runbooks approved
- [ ] Rollback tested with application, database, and model versions together
- [ ] Retention purge and legal-hold procedures tested
- [ ] Immutable review/outcome/monitoring events and concurrency controls tested
- [ ] Batch worker crash recovery, cancellation, retry, and reconciliation tested
- [ ] Every release report hash verified against the signed release manifest
- [ ] Dataset/model serialization supply-chain risk accepted or replaced with a constrained format

## Release approval

| Role | Name | Decision | Date |
|---|---|---|---|
| Business owner |  |  |  |
| Model owner |  |  |  |
| Independent validation |  |  |  |
| Fair lending/compliance |  |  |  |
| Information security |  |  |  |
| Production operations |  |  |  |
