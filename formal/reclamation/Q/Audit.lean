import Q.Witnesses
import Q.Mutants

#print axioms Aurora.Q.initial_invariant
#print axioms Aurora.Q.step_preserves_invariant
#print axioms Aurora.Q.reachable_invariant
#print axioms Aurora.Q.quiescent_no_possibility
#print axioms Aurora.Q.after_reuse_no_old_access
#print axioms Aurora.Q.finite_cpu_safe_reuse
#print axioms Aurora.Q.retirement_preserves_other_obligations
#print axioms Aurora.Q.stale_ack_inert
#print axioms Aurora.Q.duplicate_ack_inert
#print axioms Aurora.Q.Witness.successful_reuse
#print axioms Aurora.Q.Witness.closing_activation
#print axioms Aurora.Q.Witness.authority_before_drain
#print axioms Aurora.Q.Witness.old_ack_after_reuse_inert
#print axioms Aurora.Q.Mutants.uncovered_publication_counterexample
#print axioms Aurora.Q.Mutants.premature_fence_ack_counterexample
#print axioms Aurora.Q.Mutants.premature_drain_ack_counterexample
#print axioms Aurora.Q.Mutants.lost_transfer_counterexample
#print axioms Aurora.Q.Mutants.duplicate_subtraction_counterexample
#print axioms Aurora.Q.Mutants.replay_after_reuse_counterexample
#print axioms Aurora.Q.Mutants.epoch_only_reuse_counterexample
#print axioms Aurora.Q.acknowledged_gate_cannot_admit
#print axioms Aurora.Q.receiveAck_step
#print axioms Aurora.Q.Witness.resolved_transfer_cannot_activate
#print axioms Aurora.Q.Mutants.false_receipt_reuse_counterexample
