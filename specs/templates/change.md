# <ID>: <Feature or change name>

State: draft | implementing | implemented; awaiting verification | verified

Related spec: <relative link, if extending an existing feature>

## Problem and scope

<What the user wants and the observable improvement. List non-goals.>

## Contract

<Inputs/defaults, outputs/result variants, preconditions, failure reasons,
side effects, state preserved, and which interfaces expose the operation.>

| Requirement ID | Observable requirement | Acceptance scenario | Test or check |
| --- | --- | --- | --- |
| <ID>-001 | <Behavior> | Given … when … then … | <Test name or planned check> |

## Design and compatibility

<Affected files, dependencies, constants, concurrency concerns, and why the
chosen approach satisfies the contract. Describe any API/format migration.
Record assumptions and unresolved questions separately from requirements.>

## Implementation tasks

- [ ] Update the relevant contract/spec.
- [ ] Implement domain behavior and specified adapters.
- [ ] Add or update commented behavioral tests.
- [ ] Update help, usage documentation, and dependency locks if affected.
- [ ] Execute relevant verification and record evidence below.

Remove inapplicable tasks; add concrete steps specific to the change.

## Verification evidence

| Date / environment | Working directory and exact command | Result | Limitation / next action |
| --- | --- | --- | --- |
| <Date, Python/Node/Git versions when relevant> | <Command> | Not run / pass / fail / blocked | <Evidence or limitation> |

<List criteria not yet covered or verified. A planned test is not a passing test.
Do not mark verified while required checks remain unresolved.>
