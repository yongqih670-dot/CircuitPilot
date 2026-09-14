# Research Task 6 Hypotheses

Status: pre-registered before implementation and before cost profiling.

## H1: expensive-analysis reduction

Operating-point staged screening will reduce the number of logical expensive
AC analyses in the equal-candidate experiment. H1 is supported when the pooled
paired-seed median percentage of AC analyses saved is positive and its
pre-registered paired bootstrap 95% confidence interval excludes zero.

## H2: cost-normalized feasibility search

Under the equal expensive-AC budget and fixed candidate cap, screened
evaluation will improve cost-normalized discovery of truly Task 5-feasible
designs. H2 is fully supported when Screened has lower pooled restricted mean
time-to-feasible by expensive-AC count and no lower pooled success rate.
It is partially supported when exactly one endpoint improves, and unsupported
when neither improves. Candidate-count and wall-time endpoints remain required
secondary results.

## H3: optimizer-dependent benefit

The benefit of staged evaluation will differ among Random, DE, TPE, and BO
because their observed OP-rejection frequencies differ. H3 is supported
descriptively when the range of method-level paired median percentage AC saved
is at least 10 percentage points and the Spearman association between
method-level OP-rejection rate and percentage AC saved exceeds 0.5.

These hypotheses concern a deterministic physics-aware baseline. They do not
claim novelty for OP-first or multi-fidelity simulation and do not introduce
an LLM, learned classifier, or adaptive search space.

