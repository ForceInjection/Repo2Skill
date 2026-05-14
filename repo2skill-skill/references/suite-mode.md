# Suite Mode Detection

Apply these 4 criteria from `analysis.json` and the selected candidates:

1. **Candidate count > 1** AND combined Level 2 body estimate > 4,000 tokens
2. **Multiple entry points**: different `policy.type` values across candidates (e.g., both "script" and "function")
3. **Disconnected clusters**: `dependency_graph` contains independent subgraphs (use `find_disconnected_clusters` in suite.py)
4. **Divergent tools**: different `allowed-tools` sets across candidates

If any criterion is met, propose suite mode. When assembling, validate that inter-skill relations form a DAG — no cycles in `depends-on` and `requires-output-from` relations.
