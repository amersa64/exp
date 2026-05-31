// In-progress workout screen — the middle layer of the three-screen flow.
//
//   TrainView (entry)
//     -> ActiveSessionView      ← this file
//          -> ExerciseLogView   (push, per-exercise)
//
// Shows the prescribed exercises as a list with per-row status — same
// pattern as Strong / Hevy: tap an exercise to log its sets, then come
// back here to pick the next one. Header shows elapsed workout time. The
// "Finish workout" button rolls up the per-exercise outcomes and fires
// the existing /session/{id}/log endpoint.
//
// State lives in ActiveSessionStore (UserDefaults-backed), so backgrounding
// the app or force-quitting it preserves where the user was.

import SwiftUI

struct ActiveSessionView: View {
    let next: NextSession
    /// Called with the finish result so the parent (TrainView) can show the
    /// ripples banner and refresh the next prescription.
    let onFinished: (LogSessionResult?) async -> Void

    @StateObject private var store = ActiveSessionStore.shared
    @State private var session: ActiveSession
    @State private var elapsed: TimeInterval = 0
    @State private var submitting = false
    /// Drives the .confirmationDialog so an accidental tap on Cancel doesn't
    /// destroy the lifter's local set/rep state.
    @State private var confirmingCancel = false
    @Environment(\.dismiss) private var dismiss

    /// Ticks the elapsed-time pill once per second. Cheap; no Combine sink.
    private let ticker = Timer.publish(every: 1.0, on: .main, in: .common).autoconnect()

    init(next: NextSession, onFinished: @escaping (LogSessionResult?) async -> Void) {
        self.next = next
        self.onFinished = onFinished
        // Resume if the store has a session for this prescription, otherwise
        // start fresh. The resume branch is what gives us "you closed the
        // app between sets and came back" continuity.
        let existing = ActiveSessionStore.shared.current(for: next.actionId)
        _session = State(initialValue: existing ?? ActiveSessionStore.shared.start(next))
    }

    var body: some View {
        ZStack {
            AtmosphericBackground()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header
                    exerciseList
                    finishButton
                    cancelButton
                }
                .padding(18)
            }
            .scrollContentBackground(.hidden)
        }
        .navigationTitle(session.sessionName)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(.hidden, for: .navigationBar)
        .onReceive(ticker) { _ in
            elapsed = Date().timeIntervalSince(session.startedAt)
        }
        .onAppear {
            elapsed = Date().timeIntervalSince(session.startedAt)
        }
        // Rest timer floats above the scroll content so the lifter sees the
        // countdown even when they pop back from an individual exercise.
        .safeAreaInset(edge: .bottom, spacing: 0) { RestTimerBar() }
        .confirmationDialog(
            "Cancel this workout?",
            isPresented: $confirmingCancel,
            titleVisibility: .visible
        ) {
            Button("Cancel workout", role: .destructive) {
                store.clear()
                dismiss()
            }
            Button("Keep going", role: .cancel) {}
        } message: {
            Text("Your sets and notes for this workout will be discarded.")
        }
    }

    // MARK: - Subviews

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionEyebrow(text: "IN PROGRESS", icon: "flame.fill")
            Text(session.sessionName)
                .font(.system(.title, design: .rounded, weight: .heavy))
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 10) {
                Label(formatElapsed(elapsed), systemImage: "stopwatch")
                    .font(.subheadline.weight(.semibold))
                    .monospacedDigit()
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background {
                        Capsule().fill(Color.white.opacity(0.10))
                            .overlay { Capsule().strokeBorder(Color.white.opacity(0.18), lineWidth: 1) }
                    }
                Text(rollupSummary)
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.65))
                Spacer()
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCardTinted(Theme.ember)
    }

    private var exerciseList: some View {
        VStack(spacing: 12) {
            // Render in the order stored on the session — which mirrors the
            // brain's original prescription order. Each row resolves through
            // `session.swaps` so an in-workout swap shows the new name without
            // reordering the list.
            ForEach(Array(session.exerciseOrder.enumerated()), id: \.element) { idx, originalName in
                let resolved = session.resolvedPrescription(
                    for: originalName,
                    base: next.session.exercises
                ) ?? placeholderPrescription(originalName)
                NavigationLink {
                    ExerciseLogView(
                        index: idx + 1,
                        exercise: resolved,
                        state: bindingFor(originalName),
                        onSwap: { replacementName in
                            performSwap(originalName: originalName,
                                        prescription: resolved,
                                        replacementName: replacementName)
                        }
                    )
                } label: {
                    ExerciseProgressRow(
                        index: idx + 1,
                        exercise: resolved,
                        state: session.exercises[originalName] ?? ExerciseState()
                    )
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var finishButton: some View {
        Button {
            Task { await finish() }
        } label: {
            HStack {
                if submitting { ProgressView().tint(.black) }
                Text(submitting ? "Sending…" : "Finish workout")
            }
        }
        .buttonStyle(EmberButtonStyle())
        .disabled(submitting)
        .padding(.top, 4)
    }

    private var cancelButton: some View {
        Button(role: .destructive) {
            confirmingCancel = true
        } label: {
            Label("Cancel workout", systemImage: "xmark.circle")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(Theme.rose.opacity(0.75))
        }
        .buttonStyle(.plain)
        .padding(.top, 8)
        .frame(maxWidth: .infinity)
    }

    // MARK: - Logic

    /// Two-way binding that writes through ActiveSessionStore so the
    /// ExerciseLogView push gets persistence + cross-screen sync for free.
    private func bindingFor(_ name: String) -> Binding<ExerciseState> {
        Binding(
            get: { session.exercises[name] ?? ExerciseState() },
            set: { newValue in
                session.exercises[name] = newValue
                // Persist on the next runloop tick: updateExercise mutates the
                // store's @Published `current`, and doing that synchronously
                // inside a binding flush trips "Publishing changes from within
                // view updates". The local @State write above is what drives
                // this view; the store write is just persistence + sync.
                DispatchQueue.main.async { store.updateExercise(name, state: newValue) }
            }
        )
    }

    /// Mutate the active session when the user picks an alternate from the
    /// SwapSheet inside ExerciseLogView. We keep the row position stable by
    /// keying everything on the *original* name, then `swaps[originalName]`
    /// resolves to the replacement prescription on render.
    private func performSwap(originalName: String,
                             prescription: ExercisePrescription,
                             replacementName: String) {
        // Build a new prescription preserving the prescribed sets/reps/load —
        // only the name changes. (The brain decided how heavy this slot should
        // be; the swap is "different exercise, same volume.") The coach's
        // reasoning + memory were already recorded server-side in /exercise/swap.
        let replacement = ExercisePrescription(
            name: replacementName,
            sets: prescription.sets,
            reps: prescription.reps,
            loadLb: prescription.loadLb,
            restSeconds: prescription.restSeconds,
            notes: prescription.notes,
            durationMin: prescription.durationMin,
            calibrationSlot: prescription.calibrationSlot
        )
        store.swap(originalName: originalName, with: replacement)
        // Reflect the store change into the local @State copy so the list
        // re-renders without waiting for the next view appearance.
        if let updated = store.current(for: next.actionId) {
            session = updated
        }
    }

    /// Fallback prescription when an exercise no longer exists in the
    /// brain's response — shouldn't happen mid-workout but a defensive
    /// placeholder keeps the list from crashing if it does.
    private func placeholderPrescription(_ name: String) -> ExercisePrescription {
        ExercisePrescription(
            name: name, sets: 0, reps: 0, loadLb: nil,
            restSeconds: 60, notes: "", durationMin: nil, calibrationSlot: nil
        )
    }

    /// Build the per-exercise payload + fire the log POST. On success, clear
    /// local state and pop back to Train so the user sees the ripples banner.
    ///
    /// We key the payload by the *resolved* name so the backend records what
    /// the user actually did (the swap target), not the brain's original
    /// prescription. The `calibration_slot` echo still flows through.
    @MainActor
    private func finish() async {
        submitting = true
        var payload: [String: CoachAPI.ExerciseLogPayload] = [:]
        for originalName in session.exerciseOrder {
            let resolved = session.resolvedPrescription(
                for: originalName,
                base: next.session.exercises
            ) ?? placeholderPrescription(originalName)
            let state = session.exercises[originalName] ?? ExerciseState()
            payload[resolved.name] = state.toPayload(calibrationSlot: resolved.calibrationSlot)
        }
        let result = try? await CoachAPI.shared.logSession(
            actionId: next.actionId,
            friction: nil,
            exercises: payload
        )
        submitting = false
        store.clear()
        await onFinished(result)
        dismiss()
    }

    /// "3 done · 1 partial" — same shape as the old single-sheet rollup,
    /// surfaced live so the user knows what Finish will record.
    private var rollupSummary: String {
        let outcomes = session.exerciseOrder.map {
            session.exercises[$0]?.outcome ?? .done
        }
        let done = outcomes.filter { $0 == .done }.count
        let partial = outcomes.filter { $0 == .partial }.count
        let skipped = outcomes.filter { $0 == .skipped }.count
        var parts: [String] = []
        if done > 0 { parts.append("\(done) done") }
        if partial > 0 { parts.append("\(partial) partial") }
        if skipped > 0 { parts.append("\(skipped) skipped") }
        return parts.joined(separator: " · ")
    }

    /// "12:34" / "1:02:34" — drops the hours segment when unnecessary so
    /// the chip stays tight on the most common (sub-hour) case.
    private func formatElapsed(_ t: TimeInterval) -> String {
        let total = Int(t)
        let h = total / 3600
        let m = (total % 3600) / 60
        let s = total % 60
        if h > 0 {
            return String(format: "%d:%02d:%02d", h, m, s)
        }
        return String(format: "%02d:%02d", m, s)
    }
}

// MARK: - Row in the exercise list

/// One exercise tile on the active-session list. Mirrors TrainView's
/// `ExerciseRow` but adds a per-state color band (green when all sets are
/// done, amber when partial, dim when skipped) and a checkmark indicator.
private struct ExerciseProgressRow: View {
    let index: Int
    let exercise: ExercisePrescription
    let state: ExerciseState

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text("\(index)")
                .font(.system(.title3, design: .rounded, weight: .heavy))
                .monospacedDigit()
                .foregroundStyle(Theme.gold)
                .frame(width: 24, alignment: .leading)
            VStack(alignment: .leading, spacing: 4) {
                Text(exercise.name)
                    .font(.headline)
                    .foregroundStyle(.white)
                Text(progressLabel)
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.6))
                    .monospacedDigit()
            }
            Spacer()
            statusIcon
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color.white.opacity(0.05))
                .overlay {
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .strokeBorder(accent, lineWidth: 1)
                }
        }
    }

    /// "2/3 sets · 135 lb" when the user's started, "3×5 @ 135 lb" prescribed
    /// when they haven't. Matches the Strong / Hevy row layout: prescribed
    /// numbers in faint, actual numbers in bright once they exist.
    private var progressLabel: String {
        let logged = state.sets.filter { $0.isLogged }
        if logged.isEmpty {
            if let mins = exercise.durationMin {
                return exercise.sets > 1 ? "\(exercise.sets)×\(mins) min" : "\(mins) min"
            }
            if let load = exercise.loadLb {
                return "\(exercise.sets)×\(exercise.reps) @ \(Int(load)) lb"
            }
            return "\(exercise.sets)×\(exercise.reps)"
        }
        let setLabel = "\(logged.count)/\(exercise.sets) sets"
        if let top = logged.max(by: { ($0.loadLb ?? 0) < ($1.loadLb ?? 0) }),
           let load = top.loadLb {
            return "\(setLabel) · top \(Int(load)) lb"
        }
        if let top = logged.max(by: { ($0.reps ?? 0) < ($1.reps ?? 0) }),
           let reps = top.reps {
            return "\(setLabel) · \(reps) reps"
        }
        return setLabel
    }

    @ViewBuilder
    private var statusIcon: some View {
        switch state.outcome {
        case .done where allSetsLogged:
            Image(systemName: "checkmark.circle.fill")
                .font(.title3)
                .foregroundStyle(Theme.emerald)
        case .partial:
            Image(systemName: "circle.lefthalf.filled")
                .font(.title3)
                .foregroundStyle(Theme.amber)
        case .skipped:
            Image(systemName: "minus.circle")
                .font(.title3)
                .foregroundStyle(.white.opacity(0.35))
        default:
            // Default outcome is .done but user hasn't logged anything yet —
            // show an empty circle so the row reads as "todo".
            Image(systemName: "circle")
                .font(.title3)
                .foregroundStyle(.white.opacity(0.35))
        }
    }

    private var allSetsLogged: Bool {
        let logged = state.sets.filter { $0.isLogged }.count
        return logged >= exercise.sets
    }

    /// Border color = at-a-glance status. Subtle to avoid a noisy list.
    private var accent: Color {
        switch state.outcome {
        case .done where allSetsLogged: return Theme.emerald.opacity(0.40)
        case .done where state.hasLoggedSet: return Theme.gold.opacity(0.35)
        case .partial: return Theme.amber.opacity(0.40)
        case .skipped: return Color.white.opacity(0.08)
        default: return Color.white.opacity(0.10)
        }
    }
}
