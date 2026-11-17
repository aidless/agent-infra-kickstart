# 幂等键盘点（静态初判）

扫描 589 个脚本；红项 **227** 个。

| 判定 | 数量 | 含义 |
|---|---|---|
| VOLATILE_ARTIFACT | 202 | 红：产物路径带时间戳/随机 |
| OVERWRITE_IDEMPOTENT | 175 | 绿：固定路径覆盖写 |
| NO_SIDE_EFFECT | 164 | 未命中副作用原语 |
| APPEND_NO_KEY | 15 | 红：追加写且无去重键 |
| APPEND_GUARDED | 9 | 追加写，有去重/锁证据 |
| DELETE_UNGUARDED | 6 | 红：删除无存在性判断 |
| LOG_APPEND | 6 |  |
| REMOTE_NO_KEY | 4 | 红：远端/服务/DB 副作用且答不出键 |
| REMOTE_STATELESS | 3 | 黄：无状态推理端点（本地 Ollama 等） |
| REMOTE_GUARDED | 3 | 远端副作用，有幂等证据 |
| TEST_INJECTOR | 2 |  |

## 分级

| 档 | 判定 | 含义 | 数量 |
|---|---|---|---|
| P0 | REMOTE_NO_KEY | 远端/服务副作用，重跑会真的再做一次 | 4 |
| P1 | APPEND_NO_KEY | 追加写，重跑多一条记录 | 15 |
| P2 | DELETE_UNGUARDED | 删除无存在性判断，第二遍报错 | 6 |
| P3 | VOLATILE_ARTIFACT | 产物路径带时间戳，重跑多一份文件（仅当被当唯一记录消费时才有害） | 202 |

## P0（4）

| 脚本 | 判定 | 依据 |
|---|---|---|
| `scripts/dsh-restart-preflight.sh` | REMOTE_NO_KEY | 远端/服务/DB 副作用且无任何幂等证据 |
| `scripts/verify_relay_model.py` | REMOTE_NO_KEY | 远端/服务/DB 副作用且无任何幂等证据 |
| `scripts/zotero_import_wiki.py` | REMOTE_NO_KEY | 远端/服务/DB 副作用且无任何幂等证据 |
| `tools/fetch_nexa_models.py` | REMOTE_NO_KEY | 远端/服务/DB 副作用且无任何幂等证据 |

## P1（15）

| 脚本 | 判定 | 依据 |
|---|---|---|
| `scripts/kagg_absorption.py` | APPEND_NO_KEY | 追加写且无去重/锁 → 每跑多一条 |
| `scripts/kagg_b5_price.py` | APPEND_NO_KEY | 追加写且无去重/锁 → 每跑多一条 |
| `scripts/kagg_corpus_build.py` | APPEND_NO_KEY | 追加写且无去重/锁 → 每跑多一条 |
| `scripts/kagg_handicap_ladder.py` | APPEND_NO_KEY | 追加写且无去重/锁 → 每跑多一条 |
| `scripts/kagg_handon_ladder.py` | APPEND_NO_KEY | 追加写且无去重/锁 → 每跑多一条 |
| `scripts/kagg_ladder_by_submission.py` | APPEND_NO_KEY | 追加写且无去重/锁 → 每跑多一条 |
| `scripts/kagg_our_eps_fetch.py` | APPEND_NO_KEY | 追加写且无去重/锁 → 每跑多一条 |
| `scripts/kagg_package_head_screen.py` | APPEND_NO_KEY | 追加写且无去重/锁 → 每跑多一条 |
| `scripts/kagg_public_ladder.py` | APPEND_NO_KEY | 追加写且无去重/锁 → 每跑多一条 |
| `scripts/kagg_public_ladder_refill.py` | APPEND_NO_KEY | 追加写且无去重/锁 → 每跑多一条 |
| `scripts/kagg_seat_work_distribution.py` | APPEND_NO_KEY | 追加写且无去重/锁 → 每跑多一条 |
| `scripts/kagg_top10_eps_fetch.py` | APPEND_NO_KEY | 追加写且无去重/锁 → 每跑多一条 |
| `scripts/kagg_top10_windows.py` | APPEND_NO_KEY | 追加写且无去重/锁 → 每跑多一条 |
| `scripts/make_diag_n1a_probe.py` | APPEND_NO_KEY | 追加写且无去重/锁 → 每跑多一条 |
| `scripts/make_diag_n1b_probe.py` | APPEND_NO_KEY | 追加写且无去重/锁 → 每跑多一条 |

## P2（6）

| 脚本 | 判定 | 依据 |
|---|---|---|
| `scripts/d1_ceiling_audit.py` | DELETE_UNGUARDED | 删除无存在性判断 → 第二遍报错 |
| `scripts/kagg_seat_money_split.py` | DELETE_UNGUARDED | 删除无存在性判断 → 第二遍报错 |
| `scripts/kagg_top10_game_index.py` | DELETE_UNGUARDED | 删除无存在性判断 → 第二遍报错 |
| `tools/bench-noise-floor/followup_ec56_permutation_null.py` | DELETE_UNGUARDED | 删除无存在性判断 → 第二遍报错 |
| `tools/bench-noise-floor/selftest_ds.py` | DELETE_UNGUARDED | 删除无存在性判断 → 第二遍报错 |
| `tools/bench-noise-floor/tests/test_revision_round2.py` | DELETE_UNGUARDED | 删除无存在性判断 → 第二遍报错 |

## P3（202）

| 脚本 | 判定 | 依据 |
|---|---|---|
| `ai-radar/radar.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `dots-agent/run.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `dots-agent/tests/test_agent_gates.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `dots-agent/tests/test_daemon_counterfactual.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `dots-agent/tests/test_proposal_sink_gates.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `dots-agent/tests/test_supervisor_gates.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/_mutcheck_d10.sh` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/add_mimir_server.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/add_two_fixed_papers.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/arc_d10_r5_read.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/arc_submit_guard.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/batch_import_mimir.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/compaction_health.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/create_project_record.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/enterprise_report.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/eval_run.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/fix_mimir_titles.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/foreign_agent_config_gate.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/harvest_1000.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/hooks/run-gates.sh` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_arm_ladder.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_arm_price_table.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_arm_win_axis.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_b4_carrier_probe.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_b4_replay_probe.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_b_prime_surface.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_batch_verify.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_birth_track.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_board_position.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_bt_window_projection.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_build_plan.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_cand_L_adjudicate.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_cand_M_adjudicate.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_cand_t_bridge.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_cap_utilisation.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_capacity_model.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_channel_rate.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_claim_manifest.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_consistency_check.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_corpus_build_mix.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_corpus_swap_price.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_d0_census.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_daily_package_probe.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_deid_scan.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_display_economics.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_display_landing.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_dose_ceiling_scan.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_entry_position_attribution.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_episode_config_fidelity.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_episode_presence.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_extraction_split_scan.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_fallback_audit.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_fert_allocation_probe.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_fert_mass_balance.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_fert_reserve_probe.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_fetch_episode_lists.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_floor_ledger.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_flywheel_is_live.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_freshness_vs_rank.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_frozen_domain_request.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_frozen_joint.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_frozen_menu.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_frozen_rungs_measured.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_gap_by_good.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_gap_win_curve.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_gate_bias_correction.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_guard_hole_sweep.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_h50_compare.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_h50_read.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_handon_pairwise.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_headstart_within_game.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_idle_attribution.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_idle_cap_cause.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_inwindow_wl.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_iter_ledger.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_k_transfer.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_ladder_monotony_audit.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_leader_pace.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_ledger_hygiene.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_locality_probe.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_lock_slot_price.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_lockdown_check.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_machine_time_sizing.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_margin_flip_and_ruler_power.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_margin_validity.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_mech_water.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_mix_response_probe.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_mo1_market_cap.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_money_rating_exchange.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_network_connectivity.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_opening_pass.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_ops_lab_audit.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_order_budget_seeds.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_our_wins_above_expectation.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_outcome_gap_resolution.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_package_manifest.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_package_parse_cost.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_pair_gap_ruler.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_pair_snapshot.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_paired_within_game.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_pickup_realized.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_plant_funnel_probe.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_plant_gate.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_plant_pipeline_split.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_pool_profile.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_price_war_headroom.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_quantile_map_calibration.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_rate_second_path.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_rating_score_tie.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_rating_semantics.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_rebuild_ledger_coverage.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_reconstructed_rating_uwe.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_required_p_given_lifetime.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_rival_cell_rate.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_roster_identity_check.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_row_age_mix.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_row_capacity_ceiling.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_row_inheritance.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_row_life.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_row_throughput.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_score_aggregation_probe.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_screen.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_seat_paired_work.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_second_look.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_segment_win_map.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_sell_px_quantity_weighted.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_sell_selfcrash.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_species_economics.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_spine_feasibility.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_spine_true_event.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_sum_pair_check.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_sweep_gate.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_table_identity_of_currency.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_table_increment_calibration.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_thin4_profile.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_top10_cross_line_gap.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_top10_gap_drift.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_top10_reachability.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_top10_rotation.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_toprank_win_rates.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_town_drain_census.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_unfrozen_adjudicate.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_vacant_cell_cause.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_verdict_recheck.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_walk_economics.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_water_gap.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_water_weed_ledger.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_wheat_buy_composition.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_wheat_cohort_fate.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_wheat_fert_funnel.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_wheat_flow_rec.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_wheat_mass_balance.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_wheat_water_window.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_wheatcap_priced.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_winner_goal_differential.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_winrate_premise.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_wl_event_check.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_young_row_population.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kagg_zero_game_noise.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/kernel_audit.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/line_next_48h.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/link_slm_papers.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/lint_debt.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/loop_step.sh` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/make_kernel_v355.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/make_kernel_v356_endgamewheat.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/make_kernel_v357_wheatline.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/mimir_build_import.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/paper_tier_board.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/register_mimir_projects.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/restore_ledger_append_only.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/rotate-magpie-token.sh` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/schema_rent_audit.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/sync_slm_wiki.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/top3_board_facts.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `scripts/top3_tfb_queue_observer.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/analyze_nexa.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/anonymize_log.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/check_selfdeclared_counts.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/ds_case_bootstrap.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/followup_ec32_tie_break.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/followup_ec37_bootstrap_coverage.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/followup_ec39_macro_micro.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/followup_ec41_minority.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/followup_ec63_kfold.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/followup_ec64_resources.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/make_floor_aggregation.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/make_m25_selfbias.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/make_m25_summary.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/make_mutation_ds_summary.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/make_mutation_summary.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/make_panel_summary.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/make_panel_votes.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/mutation_check.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/mutation_check_ds.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/normalize_evidence_paths.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/probe_hf_panel.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/bench-noise-floor/tests/test_revision_round4.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/claude_residential_relay.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/tests/test_consume_shortlist.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/tests/test_filelock.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |
| `tools/tests/test_probe_fallback.py` | VOLATILE_ARTIFACT | 产物路径含时间戳/随机 → 每跑多一份 |

判据：本表是**静态初判**。每条红项要人回答一句「重复跑两次，世界会变成什么样」。
答得出稳定键（内容哈希 / 稳定业务 id / upsert / 去重集合）→ 改判绿；答不出 → 它只能配 unknown-outcome 语义，不许进 at-least-once 路径。
