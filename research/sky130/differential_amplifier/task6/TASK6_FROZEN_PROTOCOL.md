# Frozen Task 6 Physics-Aware Evaluation Protocol

Status: frozen after the pre-registered pilot and before the production staged
evaluator, smoke, or formal optimization.

The circuit, search space, hard constraints, physical metrics, feasibility
definition, and full-evaluation objective are exactly Task 5, whose benchmark
hash is:

57d2183621ecf37e5ca22e012452c43fce6459be7d347a5cfc93d0b394c14378

The only experimental variable is evaluation policy:

- Full uses the unchanged Task 5 one-process OP plus combined dual-AC path.
- OP-screened runs an explicit OP-only process, applies the frozen transparent
  rules, and runs a second combined dual-AC process only when physics is valid.

The Full evaluation-policy hash is:

a07ea20ee7f16598602fa7f05218b45439e4bb87ac34c786d9881125372de0f0

The OP-screened evaluation-policy hash is:

28110a5127748f185c35f038b2a4dcf333356ae54e676391042cebeff0cfe065

The complete Task 6 policy-family hash is:

53b1eb73160b4d069135f406613cd1249fcdd002bfd6cb2b0c8892da1c3b4867

Supporting semantic hashes are:

| Definition | Version | SHA-256 |
|---|---|---|
| Physics rules | task6_op_physics_rules_v1 | 704634265dcbc3e0e8a7dd56eb4bd07c385bf26b0ad4ce0f306bdc43401ce052 |
| OP feedback | task6_normalized_op_violation_feedback_v1 | 2890448082b38377353526406abcd78cdca7b23f86d8a6765bbfb9f26bce3d27 |
| Cost model | task6_logical_ac_primary_cost_v1 | 1ddf380b35fa8f5628c10e1f6e25cf87a32ef336a4ce229d071a7b4d796d7726 |
| Statistical plan | task6_paired_survival_effects_v1 | recorded in family hash |

Smoke is four methods by two policies by seeds 0-2 with candidate cap 25.
Formal A is four methods by two policies by seeds 0-9 with exactly 100
candidates. Formal B is the same 80 method-policy-seed combinations with at
most 200 logical expensive AC calls and hard candidate cap 300. Wall time is
measured_not_stopping_v1.

The pilot confirms that OP-only is only modestly faster on this host. It does
not alter any frozen choice. Any later semantics defect requires a new policy
hash and complete restart; accepted results cannot be reinterpreted.

