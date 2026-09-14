# Task 6 Cost-Profile Pilot Protocol

Status: pre-registered before pilot implementation and execution.

The pilot contains 32 candidates sampled independently from the unchanged
Task 5 seven-dimensional search space by NumPy default_rng seed 6001.
Sampling uses the same linear/log decoding rules as the optimizers. Candidate
order and a canonical candidate-design SHA-256 are saved before simulation.

Every pilot candidate receives both an OP-only process and the frozen Task 5
full process, regardless of OP validity. To reduce order bias, even-indexed
candidates run Full then OP-only and odd-indexed candidates run OP-only then
Full. There is no warm-up deletion, retry, candidate replacement, feedback,
or optimizer.

The pilot reports paired raw wall times, mean, median, quartiles, distribution,
process status, and OP-physics status. Pilot candidates are excluded from
smoke and formal runs and are never passed to an optimizer.

The formal budget values are defined independently in COST_MODEL.md. Pilot
results validate whether wall time should remain a secondary measured outcome;
they cannot change the search space, hypotheses, physics rules, objective,
candidate caps, or expensive-AC budget.

