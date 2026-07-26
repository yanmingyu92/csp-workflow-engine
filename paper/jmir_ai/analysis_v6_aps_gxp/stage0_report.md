# APS-GxP v6 Stage-0 Report

Network calls: **0**
Context cells/builds: **40 / 120**
Overall: **PASS**

## Gates

| Gate | Result | Actual | Expected |
|---|---|---|---|
| `frozen_v5_parity` | PASS | `{"checkpoint_sha256": "e337862a974fd2bb5cd1bd691875f1e6483b8acca5687cbe4e758f5fcb587ed8", "expected_checkpoint_sha256": "e337862a974fd2bb5cd1bd691875f1e6483b8acca5687cbe4e758f5fcb587ed8", "stored_framework_rows": 30, "task_parity": {"task-01-sap-parse": true, "task-02-protocol-setup": true, "task-06-sdtm-dm": true, "task-07-sdtm-ae": true, "task-10-p21-sdtm": true, "task-13-adam-adsl": true, "task-14-adam-adae": true, "task-17-tfl-demographics": true, "task-20-tfl-ae": true, "task-21-define-sdtm": true}}` | all 10 task projections match the hashed v5 checkpoint |
| `context_cardinality` | PASS | `40` | 40 |
| `budgets` | PASS | `7998` | maximum <= 8000 |
| `relevance_score_variation` | PASS | `true` | at least one same-node task pair varies |
| `current_protection` | PASS | `{"task-01-sap-parse": true, "task-02-protocol-setup": true, "task-06-sdtm-dm": true, "task-07-sdtm-ae": true, "task-10-p21-sdtm": true, "task-13-adam-adsl": true, "task-14-adam-adae": true, "task-17-tfl-demographics": true, "task-20-tfl-ae": true, "task-21-define-sdtm": true}` | optimized CURRENT names/statuses/tokens equal frozen CURRENT |
| `optimized_median_context` | PASS | `6283.0` | [4000, 7200] |
| `optimized_max_context` | PASS | `6852` | <= 8000 |
| `optimized_15_percent_reduction` | PASS | `9` | at least 6 of 10 tasks |
| `tfl_noncurrent_selection_difference` | PASS | `true` | the two fixed TFL tasks differ |
| `provenance_completeness` | PASS | `100.0` | 100% |
| `manifest_reproducibility` | PASS | `100.0` | 100% across three builds |
| `random_token_matching` | PASS | `0` | <= 1 estimated token |
| `change_impact_determinism` | PASS | `true` | True |
| `no_secrets_or_absolute_paths` | PASS | `[]` | [] |

## Source Hashes

- `runner`: `304238a34de570f6dcb1d920d68eb25d2e0e3009848a21571dc5e77cac82a232`
- `v6_context`: `452cd46ff7d1cb6b067fc54e28314d9deab33e2b7154512603d94ba9e947f617`
- `v5_runner`: `ee717d96f0343eac759742491a70493bd353a7606ec44f7c6f9ee60cb5622efd`
- `analyzer`: `56e08f177aed773b845c3200a6a38a664fbf83bd0c8db0693d3076652592336d`
- `scheduler`: `ed0125d6db267d7456df58b53d0687b9ead076d5ffae484380916c582d88154f`
- `invocation`: `f3fc2a7e0c5a6d5c5b3e2e4892042dbf2917d483f626dcc93101a9e7c59074fd`
- `graph`: `6c0b6e45ea47008021cea4cdc10286ee2322211d7551228f17b13247dbdcb4b5`
- `regulatory_patterns`: `14d7b9dce5af789d9c18b81f12de0272c275e9c5ae2d641cfd3e0d31537fda4f`
- `design`: `4bc55199fef7c37a8d38cf504aff19529a77ed6ac1b0be7917ba7ba7a95e715b`
- `system_prompt`: `323fa149855bd915cee6dbdf776d3f02d3d0aa7a2820c8766cdbe103427f1139`
- `task_panel`: `4f198f1b7e76094de4fe8e549e2cc22c65c7ce94f45ffff1c54b0c11618a044b`
- `judge_prompt`: `3ca4589e764f6673230255b122fbd453a06aea7805114e31e058b775eef4113d`
- `relevance_rule`: `b28b762b3a9a9b9210f616a2b255679dc7cfc6c8e7e865d8a8d03c0582df943b`
- `optimization_policy`: `e35d70b449d9a7450da2201ec65d3d67bc16f1a522892fa284873ed44481e34f`
- `skill_manifest`: `0cead079089d226d3f35fc9257320bdabafc7f0e35b9f684e97863ec53b11247`

These are deterministic GxP-oriented governance proxies; they do not establish operational GxP compliance.
