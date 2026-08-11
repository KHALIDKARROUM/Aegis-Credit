# Frontend Integration Contract

The templates render safely with the current view contexts. This contract lists
the context supplied by the operational views and the remaining optional
release-provenance hooks without putting business logic in templates.

## Shared shell

The following context processor is registered after Django’s authentication
processor:

```python
"app.context_processors.product_shell",
```

It supplies role-filtered `product_nav_items`, the workspace-mode badge,
contextual footer text, and the universal skip-link label. The base template
uses `product_shell_ready` to distinguish an intentionally empty anonymous
navigation from a legacy `pages` fallback.
It also exposes `batch_processing_inline` so upload copy accurately distinguishes
synchronous scoring from a durable queued job.

The canonical assessment route is `assessment` at `/`; `overview` is at
`/overview/`, and `/assessment/` is a legacy alias. Legal navigation exposes
only Cases and Monitoring. Route authorization must enforce the same boundary;
hiding a link is not an access control.

The root templates `403.html`, `404.html`, and `500.html` extend the shared
shell. Permission failures should render `403.html` with an optional safe
`error_message`; do not pass exception details to any of the error templates.

## Case queue

The case-list template supports:

- `page_obj`: a Django `Page` instance; when absent, the existing `cases`
  iterable remains supported;
- `assignee_choices`: `(value, label)` pairs;
- `selected_assignee`: the selected value as a string;
- `sla_choices`: `(value, label)` pairs;
- `selected_sla`: the selected SLA filter;
- `case_sla_enabled`: whether to display the review-timing column.

Each case additionally exposes `sla_label`, `sla_tone`, and `due_at`.
Supported tones are `success`, `warning`, `danger`, or `neutral`. Keep the
existing `assigned_to` relation selected to avoid per-row queries. Pagination
must occur before sensitive-access logging so only displayed records are logged.

## Batch detail

- `batch_warning_count`: number of scored rows with warnings;
- `batch_can_download`: whether a failed batch has a safe partial result export;
- `batch_progress_percent`: integer from 0 through 100 for asynchronous work;
- `batch_error_message`: sanitized operator guidance for a failed job.
- `batch_rows`: durable row records; the template also accepts legacy flat
  dictionaries from `batch.results`.

Every result row’s existing `warnings` list is rendered on screen. Do not put
stack traces, filesystem paths, or applicant values in `batch_error_message`.

## Monitoring

- `monitoring_status`: `fresh`, `stale`, `missing`, or `error`;
- `monitoring_message`: approved operator guidance;
- `drift_generated_at`: timezone-aware display value;
- `drift_model_version`: model version used for the baseline;
- `drift_sample_size`: count of incoming rows;
- `drift_alert_count`: count requiring investigation.
- `latest_monitoring_run`: persisted run metadata and alert status;
- `monitoring_acknowledgements`: immutable follow-up records;
- `model_versions` and `selected_model`: version-filter controls;
- `performance_table` and `mature_outcomes`: outcome-backed performance evidence.

Calculate freshness from a persisted monitoring run, not the report file’s
filesystem timestamp. Keep historical aggregates filterable by model version;
the template’s current totals remain backward compatible.

The acknowledgement form posts to `monitoring-acknowledge`. It is shown to
reviewer, legal, administrator, and local-workspace roles, matching the
dedicated monitoring permission.

## Business policy

- `policy_scenarios`: the latest versioned `PolicyScenario` records;
- `scenario_is_illustrative`: displays the non-deployment warning;
- `recommended_display`, `economics_table`, and `model_threshold`: calculated
  scenario evidence.

The calculator posts `form_action=calculate`; saving posts `form_action=save`.
Administrator decisions post `decision` plus a substantive `reason` to
`policy-scenario-decision`. A saved or approved scenario remains governance
evidence and must never mutate the deployed threshold directly.

Optional `policy_scenario_status`, `policy_scenario_status_tone`,
`policy_scenario_updated_at`, and `policy_scenario_export_url` values may be
provided for an external approval/export system. Only provide an export URL
after assumptions and the source model/report version have been durably
recorded.

## Reports

- `report_release_status`, `report_release_tone`, and `report_release_message`;
- `report_provenance`: ordered `{label, value}` rows.

Recommended provenance rows are report generation time, model version, model
artifact digest, data digest or approved dataset ID, validation cohort, and
release approval state. The template links allowlisted report artifacts but
keeps the model pickle marked as a restricted release asset.
