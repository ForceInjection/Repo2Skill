# Trust Level Computation

| Level | Condition                                                                          |
| ----- | ---------------------------------------------------------------------------------- |
| L0    | Unverified — no security checks passed                                             |
| L1    | G1 static scan passed (no high-severity findings)                                  |
| L2    | L1 + G2 aggregate score >= 0.8, AND no dimension scored below 0.5 ("questionable") |

A score of 0.85 where hallucination is 0.95, injection is 0.90, but consistency is 0.40 → L1 (consistency is questionable despite aggregate >= 0.8).

L3 (G3 sandbox) and L4 (G4 permission audit) require Phase 3+ infrastructure.
