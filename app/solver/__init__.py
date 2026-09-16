"""Bounded, controlled autonomous problem-solving loop.

This package orchestrates the existing problem-solving abstractions
(``ProblemSolver``, research, ``Planner``, ``AgentRouter``, ``Predictor``,
``Critic``, ``Verifier``, memory and agents) into a single execution loop
with a strict iteration budget, explicit session lifecycle and a concise
observable trace.  It deliberately provides **no** unrestricted computer
control: every action and observation goes through injectable, faked-by-
default providers.
"""