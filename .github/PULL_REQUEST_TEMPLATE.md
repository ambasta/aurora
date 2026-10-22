## Change

Describe the behavior changed and any intentionally retained limitations.

## Validation

- Final source revision and toolchain:
- Commands and results (link retained logs):
- Required checks not run, interrupted, or failed:

## Build and test cost

Compare the same configuration and workload; do not compare a clean build with
an incremental refresh or present estimates as measurements.

- Baseline revision/configuration and candidate revision/configuration:
- Build command, clean/incremental scope, and executed Ninja steps before/after:
- Configured graph targets and distinct kernel image producers before/after
  (exclude aliases; distinguish default products from test-only images):
- Full-suite test count and measured wall time before/after:
- Exhaustive checks run separately, if applicable:
- Actual CPU/job counts and memory policy (state if sizing is only an estimate):
- Reason for any increase in build steps, image count, or full-suite duration:

Use “not measured” when no comparable result exists. Historical results retain
their original source scope; interrupted runs do not establish full-suite time
or qualification.
