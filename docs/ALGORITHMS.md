# Algorithms, uncertainty and evaluation

## Definition of graph

The persisted network is an undirected graph `G=(V,E)`. Each edge stores `distance_m`, `stairs` (nullable), `slope_pct` (nullable), `surface` (nullable), `curb` (nullable), `crossing`, `verification` (`verified`, `community`, `unverified`), `surveyed_at`, and moderated community reports. Every demo node, coordinate, verification state and obstacle is **synthetic**.

## Hard feasibility constraints

A verified blocked or temporary-obstruction report blocks all profiles. Stairs and severe curbs block wheelchair, walker and step-free profiles. Wheelchairs have a maximum known slope of 8%, walkers 12%, step-free preference 14%; pedestrians have no known slope limit. A severe (`3`) verified damaged-surface report blocks wheelchairs and walkers. **Unknown observations are allowed to be considered but never described as verified passable**; users must inspect warnings. The profile's constraints are implemented in `routing.active_barriers()`.

## Evidence confidence score

For each edge:

- `completeness = present(stairs, slope_pct, surface, curb) / 4`
- `verification_weight = 0.99 verified; 0.75 community; 0.48 unverified`
- `freshness = max(0.35, exp(-age_days/180))`; if undated, `0.35`
- `pending_count = number of pending or reviewed obstacle reports`
- `corroboration = 0.025` if a verified obstacle report is present, otherwise 0

Then the heuristic evidence score is:

```text
p_edge = clamp(0.55 + 0.18*verification_weight + 0.16*completeness
               + 0.10*freshness + corroboration
               - min(0.22, 0.11*pending_count), 0.30, 0.985)
p_route = product(p_edge for edge in path)
```

`p_route` is not a field-calibrated passability probability. The multiplicative form intentionally penalizes paths that accumulate more uncertain evidence. A verified physical barrier is **never** made traversable by having high evidence confidence; it is rejected before cost calculation.

## Personalized edge cost

For an allowed edge, define `r = risk_aversion / 100`, `p = p_edge`:

```text
weight(edge) = distance_m * [
    1 + (1-p)*2.1*r
      + slope_penalty(profile, slope)
      + surface_penalty(profile, surface)
      + missing_curb_penalty(r)
      + unknown_slope_penalty(r)
      + unverified_crossing_penalty(r)
]
```

All penalties are nonnegative; the base is always the edge distance. A hard barrier gives the edge infinite cost. Lower `risk_aversion` prioritizes shorter feasible routes; higher values prioritize complete, recent, verified observations. The distance-only baseline ignores barriers **only for comparison**, not as a recommendation.

## Dijkstra and admissible A*

Both algorithms use a binary min-heap and relax graph neighbors with the same exact custom edge costs. Dijkstra uses `h=0` and A* uses the great-circle (`haversine`) distance to the destination times `min(1, min(distance_m/haversine_m over all edges))`. This ensures the heuristic never overestimates remaining accumulated cost when edges are traversed by straight segments and edge weight is at least their stored distance. Search returns optimal paths for the cost model. Tests assert Dijkstra/A* cost equality across **all 20×19 directed node-pairs × 4 mobility profiles** in the demo network.

## Alternatives

Yen's algorithm computes loopless K-shortest simple paths. For each accepted path, it iterates over spur nodes, removes prior prefixes by banning edges and bans root-prefix nodes to avoid cycles. Candidate paths are ranked by their **actual** accessibility cost. This produces distinct feasible paths (not painted duplicates). `alternatives` defaults to 3 and supports 1 to 5 through the API.

## Dynamic report states

`pending → reviewed → verified → resolved` is one lifecycle. `pending/reviewed → rejected` and `pending/reviewed/verified → expired` are also allowed. Reports expire automatically at the specified ISO 8601 timestamp when the network is next loaded. Expiration and moderation bump `network_revision`, which the frontend uses to requery. Submitted reports are **not** hard constraints until verified, though pending evidence lowers confidence. Reporter identification is intentionally not stored in the prototype.

## Evaluation: actual computed metrics, synthetic truth

`calculate_evaluation()` runs **12 predefined origin–destination pairs across four profiles** on the live seeded graph, comparing accessible routes to distance-only Dijkstra. Reported measurements include:

- count of baseline and chosen unsuitable edges
- route distance overhead (%)
- confirmed barriers avoided (sum over cases)
- verified-edge coverage weighted by distance
- actual elapsed search time in milliseconds (environment dependent)
- synthetic Brier score and expected calibration error (ECE)

For calibration only, a **separate hypothetical synthetic truth model** assigns probabilities of edge passability from the edge's category, missing metadata, freshness, reports and surface. With a deterministic PRNG seed, it draws 50 independent outcome sets for each feasible route, and compares the heuristic `p_route` with the outcome that **all edges in that route remain passable**. Brier score is mean `(p_route - outcome)^2`. ECE bins routes by predicted score and sums weighted `abs(mean_prediction - observed_frequency)` across five equal-width confidence bins. These measurements are *not evidence of calibrated real-world mobility safety*. Route-level samples are correlated within a route; they are simulations, not independent field observations.

**Important restrictions:** no longitudinal real-user validation, no uncertainty quantification based on measured accessibility outcomes, no real street coverage, no trustworthy verified field reports, no protection against fake/malicious community reports, and no production-grade moderator authentication. Deploying this as a true assistance product would require all of those plus appropriate audits and standards review.
