# VIREÁX GEM projection and Speed-Bump Invariant

**Status:** experimental optimisation primitive; not a truth detector or a claim
that semantic memory already has a calibrated gradient representation.

## Contract

For a current-task loss gradient \(g\) and selected protected-memory loss
gradients \(g_k\), choose the nearest update \(g^*\) satisfying

\[
\min_v \frac12\|v-g\|_2^2
\quad\text{subject to}\quad g_k^\top v\geq0\quad\forall k.
\]

Under gradient descent, this makes the first-order change in each protected
loss non-positive. It does **not** guarantee non-increasing loss for arbitrary
finite step sizes; evaluate the actual loss after an update if a strict
non-regression condition is required.

The new `qviraex.vireax.gem_projection.project_gradient` function implements
the projection using Dykstra's algorithm over half-spaces and returns diagnostics
including convergence, constraint violation, projection distance, and retained
gradient norm. It has no third-party runtime dependency.

## Collision behavior

- 0°, 45°: the original gradient satisfies the single constraint and passes through.
- 90°: the constraint is on its boundary; no projection is needed.
- 135°: the component opposed to the memory gradient is removed.
- 180°: exact opposition to a single memory gradient projects to zero.

With multiple constraints, the projection is onto their intersection; do not
apply the single-constraint formula independently and assume the result is
globally optimal.

## Epistemic and governance boundary

1. **Evidence/provenance gate:** choose which memories qualify for protection.
   Historical presence alone is not evidence of truth.
2. **Projection gate:** constrain the numerical update according to selected
   gradients.
3. **Policy/authorization gate:** separately enforce permissions, user consent,
   safety rules, and audit requirements.

This primitive does not authorize actions, validate claims, or decide that a
new claim is false because it conflicts with an old one. It is not wired into
the existing VIREÁX Center Node automatically; integration requires a real
trainable component with a defined loss and gradient source. Do not manufacture
gradient vectors from semantic disagreement and describe them as GEM.

## Verification

Run:

```bash
python -m pytest tests/test_gem_projection.py
```

Tests cover pass-through, orthogonality, 135° projection, exact opposition,
multiple constraints, dimensional validation, and zero memory gradients.
