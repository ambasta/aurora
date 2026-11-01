import B.Model
namespace Aurora.B

def PhaseCoherent (s : State Agent) : Prop := ∀ ticket c, s.cursors ticket = some c →
  (c.phase = .done → c.copied = c.descriptor.count) ∧
  (c.phase = .running → c.copied < c.descriptor.count)

theorem initial_phase : PhaseCoherent (initial authority heap) := by
  intro ticket c found; cases found

theorem step_phase (h : PhaseCoherent s) (step : Step issuer subject config s event t) : PhaseCoherent t := by
  cases step with
  | protocol | write | control => exact h
  | beginCopy i d fresh empty valid admission =>
    intro j c found
    by_cases same : j = i
    · subst j
      simp only [start,putCursor,ite_true,Option.some.injEq] at found
      subst c
      exact ⟨(by intro bad; cases bad),fun _ => valid.1⟩
    · exact h j c (by simpa [start,putCursor,same] using found)
  | payload i old present running remaining =>
    intro j c found
    by_cases same : j = i
    · subst j
      simp only [copy,putCursor,ite_true,Option.some.injEq] at found
      subst c
      dsimp [advance]
      split
      · rename_i equal
        exact ⟨fun _ => equal,by intro bad; cases bad⟩
      · rename_i different
        exact ⟨(by intro bad; cases bad),fun _ => by omega⟩
    · exact h j c (by simpa [copy,putCursor,same] using found)
  | fault i old present running =>
    intro j c found
    by_cases same : j = i
    · subst j
      simp only [putCursor,ite_true,Option.some.injEq] at found
      subst c
      exact ⟨(by intro bad; cases bad),(by intro bad; cases bad)⟩
    · exact h j c (by simpa [putCursor,same] using found)
  | release i old present stopped =>
    intro j c found
    by_cases same : j = i
    · subst j; simp [putCursor] at found
    · exact h j c (by simpa [putCursor,same] using found)

theorem trace_phase (h : PhaseCoherent s) (trace : Trace issuer subject config s events t) : PhaseCoherent t := by
  induction trace with
  | nil => exact h
  | cons step tail ih => exact ih (step_phase h step)
end Aurora.B
