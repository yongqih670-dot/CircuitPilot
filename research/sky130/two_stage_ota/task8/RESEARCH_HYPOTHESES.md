# Task 8 Research Hypotheses

Status: pre-registered before replay, implementation, or new simulation.

Version: task8_hypotheses_decision_rules_v1

## H1: analysis reduction

Under the equal-candidate design, Hierarchical reduces both AC calls and
transient calls relative to paired Full runs.

H1 is supported only if, over the 40 paired method/seed cells:

- the paired median Full-minus-Hierarchical AC count is positive;
- the paired median Full-minus-Hierarchical transient count is positive; and
- the percentile 95% bootstrap confidence interval for each paired mean
  Full-minus-Hierarchical difference has a lower bound above zero.

## H2: accumulated simulator-time reduction

Under the equal-candidate design, analysis reduction translates into a
meaningful reduction in accumulated ngspice subprocess time.

H2 is supported only if the pooled paired Full-minus-Hierarchical accumulated
ngspice-time difference has a 95% bootstrap lower bound above zero and the
paired median percentage reduction is at least 20%.

## H3: equal simulation-cost efficiency

Under the equal-simulation-time design, Hierarchical finds feasible designs
more efficiently than Full.

H3 is supported only if Hierarchical has both:

- a strictly higher pooled run success rate than Full; and
- a lower pooled accumulated-ngspice-time RMST to first feasible design at
  the shared restricted horizon.

Candidate-count, AC-count, and transient-count survival are reported as
secondary explanations. H3 is not supported from candidate throughput alone.

## H4: zero false rejection

H4 requires exactly zero false rejections in both gates:

1. offline replay of all 2,000 frozen Task 7 formal candidates; and
2. smoke shadow-Full validation of every hierarchical early rejection.

A false rejection is a candidate rejected before transient completion that
is feasible under the unchanged Task 7 Full evaluator. Any false rejection
halts formal execution. It cannot be removed by excluding the candidate,
changing Task 7 feasibility, or changing the decision rule after observation.

## Statistical conventions

All policy comparisons use paired method and seed cells. Bootstrap intervals
use 10,000 paired resamples with deterministic RNG seed 82008. Per-method
effects use ten seed pairs; pooled effects use all 40 method/seed pairs and
are explicitly descriptive rather than independent-sample inference.
