# Research Task 6: Related-Method Positioning

Status: literature positioning for the frozen Task 6 study. Sources were
checked on 2026-09-14. This document does not alter the pre-registered protocol.

## What Task 6 is

Task 6 is an optimizer-agnostic, deterministic two-stage evaluation policy for
one frozen SKY130 differential-amplifier sizing benchmark. A candidate first
receives an explicit SPICE operating-point analysis. Transparent, versioned
device-region and headroom rules either reject it with a normalized constraint
violation or promote it to the unchanged Task 5 differential/common-mode AC
evaluation. Random, DE, TPE, and BO are held fixed across Full and Screened
policies so the experiment isolates evaluation policy rather than claiming a
new optimizer.

## Closest method families and the boundary of the claim

| Method family | Representative primary source | Relation to Task 6 | Important distinction |
|---|---|---|---|
| Constrained Bayesian optimization | Gelbart, Snoek, and Adams, [Bayesian Optimization with Unknown Constraints](https://arxiv.org/abs/1403.5607) | Models expensive black-box constraints and can allow objective and constraint evaluations to be scheduled independently. | Task 6 does not learn a probabilistic constraint model or alter acquisition. Its OP rules are fixed, deterministic, and applied identically to every optimizer. |
| Multi-fidelity Bayesian optimization | Kandasamy et al., [Multi-fidelity Bayesian Optimisation with Continuous Approximations](https://proceedings.mlr.press/v70/kandasamy17a.html) | Uses cheaper approximations to reduce costly high-fidelity evaluations. | Task 6 has one fixed binary gate, not a learned fidelity model, continuous fidelity space, or regret-minimizing fidelity-selection algorithm. A rejected OP result is not treated as an approximate AC objective. |
| Local/trust-region Bayesian optimization | Eriksson et al., [Scalable Global Optimization via Local Bayesian Optimization](https://papers.nips.cc/paper_files/paper/2019/hash/6c990b7aca7bc7058f5e98ea909e924b-Abstract.html) | TuRBO changes how BO allocates samples by fitting local models in adaptive trust regions. | Task 6 changes evaluation cost after a candidate is proposed; it does not introduce trust regions or claim high-dimensional BO scalability. The BO baseline remains the Task 5 implementation. |
| Simulation-efficient analog sizing with BO | Lyu et al., [An Efficient Bayesian Optimization Approach for Automated Optimization of Analog Circuits](https://ieeexplore.ieee.org/document/8116661) | Uses Gaussian-process surrogates and a weighted expected-improvement strategy to reduce costly circuit simulations. | Task 6 compares four existing search methods under matched seeds and budgets; its contribution is the audited OP-first evaluation policy and accounting, not a new BO acquisition rule. |
| Learned analog sizing policy | Settaluri et al., [AutoCkt: Deep Reinforcement Learning of Analog Circuit Designs](https://arxiv.org/abs/2001.01808) | Learns a reinforcement-learning policy intended to generalize across target specifications. | Task 6 trains no policy, uses no neural surrogate, and makes no cross-specification generalization claim. Every accepted metric remains a direct frozen SPICE measurement. |
| Post-layout simulation-driven sizing | Gao et al., [Post-Layout Simulation Driven Analog Circuit Sizing](https://arxiv.org/abs/2310.14049) | Couples layout generation, post-layout simulation, and Bayesian optimization. | Task 6 is a schematic-level TT-corner study of one frozen topology. It does not include layout parasitics, PVT, or mismatch. |

## Claim discipline

The defensible Task 6 claim is narrow: on this frozen benchmark and under the
pre-registered budgets, measure whether an explicit, interpretable OP gate can
avoid logical AC analyses and change time-to-feasible outcomes without changing
the search algorithm or Task 5 feasibility definition. OP-first screening is
not claimed as a novel general idea. No result should be described as evidence
for an LLM agent, a learned failure predictor, general multi-fidelity Bayesian
optimization, post-layout robustness, PVT closure, or mismatch yield.
