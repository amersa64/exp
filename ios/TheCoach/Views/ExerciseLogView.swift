// One-exercise logger — the inner screen of the three-screen workout flow.
//
//   TrainView (entry)
//     -> ActiveSessionView (list of exercises)
//          -> ExerciseLogView         ← this file
//
// Shows the prescribed numbers up top, then a list of set rows the user
// fills in as they lift. After marking a set complete, a rest timer banner
// counts down from the prescription's restSeconds. Outcome (done/partial/
// skipped) defaults to .done and the user changes it explicitly if they
// cut the work short.
//
// All state writes go through the @Binding into ActiveSessionStore, so
// backgrounding the app between sets preserves exactly where the user was.

import SwiftUI

struct ExerciseLogView: View {
    let index: Int
    let exercise: ExercisePrescription
    @Binding var state: ExerciseState
    /// Called with the chosen replacement's catalog name when the user
    /// confirms a swap. The parent (ActiveSessionView) mutates the active
    /// session and the screen dismisses back to the list — there's nothing
    /// useful to do here after a swap, the row re-renders with the new
    /// prescription. Persistence + coach memory already happened server-side.
    var onSwap: ((String) -> Void)?

    @Environment(\.dismiss) private var dismiss
    @State private var showingSwap = false
    @State private var showingDemo = false
    /// `@FocusState` lets us auto-jump to the next field on "Done", which
    /// is how Strong / Hevy keep the lifter's hands off the screen.
    @FocusState private var focusedField: FieldID?

    var body: some View {
        ZStack {
            AtmosphericBackground()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    headerCard
                    setListCard
                    outcomeCard
                    noteCard
                }
                .padding(18)
            }
            .scrollContentBackground(.hidden)
        }
        .navigationTitle("\(index). \(exercise.name)")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(.hidden, for: .navigationBar)
        .toolbar {
            // Overflow menu for the "non-obvious" per-exercise actions. Swap
            // belongs here — common enough to need, rare enough not to deserve
            // dedicated screen space.
            if onSwap != nil {
                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        Button {
                            showingSwap = true
                        } label: {
                            Label("Replace exercise", systemImage: "arrow.triangle.2.circlepath")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                            .foregroundStyle(.white.opacity(0.85))
                    }
                }
            }
            ToolbarItem(placement: .confirmationAction) {
                Button("Done") { dismiss() }
                    .foregroundStyle(Theme.gold)
                    .font(.body.weight(.semibold))
            }
        }
        // Rest timer floats above the scroll content and survives pop /
        // push between exercises — RestTimer.shared is the source of truth.
        .safeAreaInset(edge: .bottom, spacing: 0) { RestTimerBar() }
        .sheet(isPresented: $showingSwap) {
            SwapSheet(original: exercise) { picked in
                showingSwap = false
                onSwap?(picked)
                // Pop back to the active-session list — the row will now show
                // the replacement, and the lifter can tap into it to start.
                dismiss()
            }
            .presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showingDemo) {
            ExerciseDetailSheet(exerciseName: exercise.name)
                .presentationDetents([.large])
        }
    }

    // MARK: - Header

    private var headerCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionEyebrow(text: "PRESCRIBED")
            Text(prescribedLine)
                .font(.system(.title2, design: .rounded, weight: .bold))
                .foregroundStyle(.white)
                .monospacedDigit()
            HStack(spacing: 14) {
                restPicker
                if let mins = exercise.durationMin {
                    Label("\(mins) min", systemImage: "clock")
                        .font(.subheadline)
                        .foregroundStyle(.white.opacity(0.6))
                }
            }
            if !exercise.notes.isEmpty {
                Text(exercise.notes)
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.55))
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 4)
            }
            Button { showingDemo = true } label: {
                Label("Show me how", systemImage: "play.rectangle.fill")
            }
            .buttonStyle(GhostButtonStyle())
            .padding(.top, 6)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }

    /// Effective rest period for this exercise: user override wins, then
    /// the prescription, then a safe fallback. Single source of truth used
    /// by both the header pill and the timer start path.
    private var effectiveRestSeconds: Int {
        state.restSecondsOverride ?? exercise.restSeconds
    }

    /// Common rest periods. Densely sampled in the typical lifting band
    /// (1-3 min) and looser at the extremes. The prescription value is
    /// added on the fly so it's always selectable even if it's "non-standard".
    private static let restPresets: [Int] = [30, 45, 60, 75, 90, 120, 150, 180, 210, 240, 300]

    /// Tap-to-edit rest pill — small, lives in the header next to the
    /// duration label (when present). Menu shows formatted presets +
    /// "Reset to prescribed" when the user has an override active.
    @ViewBuilder
    private var restPicker: some View {
        let presets = Self.restPresets.contains(exercise.restSeconds)
            ? Self.restPresets
            : (Self.restPresets + [exercise.restSeconds]).sorted()
        Menu {
            ForEach(presets, id: \.self) { seconds in
                Button {
                    // Tap of the prescribed value = no override (cleaner state).
                    state.restSecondsOverride =
                        seconds == exercise.restSeconds ? nil : seconds
                } label: {
                    let label = "\(Self.formatRest(seconds))"
                                + (seconds == exercise.restSeconds ? "  (prescribed)" : "")
                    if seconds == effectiveRestSeconds {
                        Label(label, systemImage: "checkmark")
                    } else {
                        Text(label)
                    }
                }
            }
            if state.restSecondsOverride != nil {
                Divider()
                Button("Reset to prescribed (\(Self.formatRest(exercise.restSeconds)))") {
                    state.restSecondsOverride = nil
                }
            }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "hourglass")
                Text("\(Self.formatRest(effectiveRestSeconds)) rest")
                if state.restSecondsOverride != nil {
                    Text("·").foregroundStyle(.white.opacity(0.4))
                    Text("custom")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(Theme.gold)
                }
                Image(systemName: "chevron.up.chevron.down")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.white.opacity(0.5))
            }
            .font(.subheadline)
            .foregroundStyle(.white.opacity(0.85))
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background {
                Capsule().fill(Color.white.opacity(0.08))
                    .overlay { Capsule().strokeBorder(Color.white.opacity(0.15), lineWidth: 1) }
            }
        }
        .accessibilityLabel("Rest period")
    }

    /// "90s" / "1:30" / "5:00" — concise. Sub-minute uses seconds; >=1 min
    /// uses M:SS so the lifter reads "2:30" the way they think about it.
    private static func formatRest(_ seconds: Int) -> String {
        if seconds < 60 { return "\(seconds)s" }
        return String(format: "%d:%02d", seconds / 60, seconds % 60)
    }

    private var prescribedLine: String {
        if let mins = exercise.durationMin {
            return exercise.sets > 1 ? "\(exercise.sets) × \(mins) min" : "\(mins) min"
        }
        if let load = exercise.loadLb {
            return "\(exercise.sets) × \(exercise.reps)  @  \(Int(load)) lb"
        }
        return "\(exercise.sets) × \(exercise.reps)"
    }

    // MARK: - Sets

    private var setListCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                SectionEyebrow(text: "SETS", icon: "list.bullet")
                Spacer()
                Text("\(loggedCount)/\(exercise.sets)")
                    .font(.caption.weight(.bold))
                    .monospacedDigit()
                    .foregroundStyle(.white.opacity(0.6))
            }
            // Row per set the user has touched. Strong shows N empty rows
            // matching the prescription; we follow that — fewer taps to
            // reach the common case of "did exactly what was prescribed".
            ForEach(Array(state.sets.enumerated()), id: \.element.id) { idx, _ in
                SetRow(
                    number: idx + 1,
                    set: $state.sets[idx],
                    prescribedReps: exercise.reps,
                    prescribedLoadLb: exercise.loadLb,
                    focused: $focusedField,
                    onComplete: { handleSetComplete(at: idx) }
                )
            }
            Button {
                state.sets.append(SetLog())
            } label: {
                Label("Add set", systemImage: "plus.circle")
            }
            .buttonStyle(GhostButtonStyle())
            .padding(.top, 4)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }

    private var loggedCount: Int {
        state.sets.filter { $0.isLogged }.count
    }

    /// Called when the user taps the checkmark on a set row. Starts the
    /// shared rest timer (using prescription.restSeconds) so the countdown
    /// survives if the user pops back to the active-session list, and
    /// auto-appends a new empty set row if they just filled the last one —
    /// keeps the flow moving without forcing them to tap "Add set".
    private func handleSetComplete(at index: Int) {
        // User-set override wins; falls back to the prescription. Zero/neg
        // means "no rest" — defensive guard for hypothetical edge cases.
        let rest = effectiveRestSeconds
        if rest > 0 {
            RestTimer.shared.start(seconds: rest, exerciseName: exercise.name)
        }
        if state.sets.allSatisfy(\.isLogged) {
            state.sets.append(SetLog())
        }
    }

    // MARK: - Outcome

    private var outcomeCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionEyebrow(text: "HOW IT WENT")
            Picker("Outcome", selection: $state.outcome) {
                Text("Done").tag(NudgeOutcome.done)
                Text("Partial").tag(NudgeOutcome.partial)
                Text("Skipped").tag(NudgeOutcome.skipped)
            }
            .pickerStyle(.segmented)
            Text(outcomeHint)
                .font(.caption)
                .foregroundStyle(.white.opacity(0.55))
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }

    private var outcomeHint: String {
        switch state.outcome {
        case .done: return "Cleared the prescribed work — the coach will progress next session."
        case .partial: return "Did some sets but cut it short — the coach will hold steady."
        case .skipped: return "Didn't lift this one — the coach will check in why."
        default: return ""
        }
    }

    // MARK: - Note

    private var noteCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionEyebrow(text: "NOTE")
            TextField("Form, pain, anything to flag (optional)",
                      text: $state.note, axis: .vertical)
                .lineLimit(2...4)
                .padding(12)
                .background {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(Color.white.opacity(0.06))
                        .overlay {
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .strokeBorder(Color.white.opacity(0.12), lineWidth: 1)
                        }
                }
                .foregroundStyle(.white)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }

    enum FieldID: Hashable { case reps(UUID), load(UUID) }
}

// MARK: - One set row

/// Two numeric fields + a checkmark. Strong / Hevy nailed this minimal
/// layout — there's a reason every fitness app uses it. Tap reps, tap load,
/// tap check → next set.
private struct SetRow: View {
    let number: Int
    @Binding var set: SetLog
    let prescribedReps: Int
    let prescribedLoadLb: Double?
    var focused: FocusState<ExerciseLogView.FieldID?>.Binding
    let onComplete: () -> Void

    @State private var repsText: String = ""
    @State private var loadText: String = ""

    var body: some View {
        HStack(spacing: 8) {
            // Set number tile
            Text("\(number)")
                .font(.system(.body, design: .rounded, weight: .heavy))
                .monospacedDigit()
                .foregroundStyle(set.isLogged ? .white : .white.opacity(0.55))
                .frame(width: 28, height: 28)
                .background {
                    Circle().fill(set.isLogged ? Theme.emerald.opacity(0.30) : Color.white.opacity(0.08))
                        .overlay { Circle().strokeBorder(Color.white.opacity(0.15), lineWidth: 1) }
                }

            // Reps: ±1 steppers flanking the keyboard-editable field.
            // Lifter can type a value OR tap to bump without unlocking the
            // phone — the "sliding dial" affordance the keyboard alone lacks.
            stepperCluster(
                text: $repsText,
                placeholder: "\(prescribedReps)",
                id: .reps(set.id),
                width: 54,
                onMinus: { bumpReps(-1) },
                onPlus: { bumpReps(+1) },
                accessibilityName: "reps"
            )

            Text("×")
                .font(.title3.weight(.bold))
                .foregroundStyle(.white.opacity(0.40))

            // Load: ±5 lb steppers — standard "two 2.5s per side" plate jump.
            stepperCluster(
                text: $loadText,
                placeholder: prescribedLoadLb.map { "\(Int($0))" } ?? "bw",
                id: .load(set.id),
                width: 64,
                isDecimal: true,
                onMinus: { bumpLoad(-5) },
                onPlus: { bumpLoad(+5) },
                accessibilityName: "load in pounds"
            )

            // Checkmark — the one tap that says "this set happened"
            Button(action: completeTapped) {
                Image(systemName: set.isLogged ? "checkmark.circle.fill" : "circle")
                    .font(.title2)
                    .foregroundStyle(set.isLogged ? Theme.emerald : .white.opacity(0.30))
            }
            .buttonStyle(.plain)
            .accessibilityLabel(set.isLogged ? "Set \(number) complete" : "Mark set \(number) complete")
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 4)
        .onAppear { syncTextFromSet() }
    }

    // MARK: - Stepper cluster (numeric field with -/+ buttons)

    /// `[-] [number field] [+]` — the keyboard still works on tap, the
    /// buttons let the lifter nudge values without the keyboard.
    private func stepperCluster(
        text: Binding<String>,
        placeholder: String,
        id: ExerciseLogView.FieldID,
        width: CGFloat,
        isDecimal: Bool = false,
        onMinus: @escaping () -> Void,
        onPlus: @escaping () -> Void,
        accessibilityName: String
    ) -> some View {
        HStack(spacing: 4) {
            stepperButton(systemImage: "minus", action: onMinus)
                .accessibilityLabel("Decrease \(accessibilityName)")
            numericField(text: text, placeholder: placeholder,
                         id: id, width: width, isDecimal: isDecimal)
            stepperButton(systemImage: "plus", action: onPlus)
                .accessibilityLabel("Increase \(accessibilityName)")
        }
    }

    private func stepperButton(systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.footnote.weight(.bold))
                .foregroundStyle(.white.opacity(0.85))
                .frame(width: 28, height: 28)
                .background {
                    Circle().fill(Color.white.opacity(0.10))
                        .overlay { Circle().strokeBorder(Color.white.opacity(0.18), lineWidth: 1) }
                }
        }
        .buttonStyle(.plain)
    }

    private func bumpReps(_ delta: Int) {
        let current = Int(repsText) ?? prescribedReps
        let next = max(0, current + delta)
        repsText = "\(next)"
    }

    private func bumpLoad(_ delta: Double) {
        let current = Double(loadText) ?? (prescribedLoadLb ?? 0)
        let next = max(0, current + delta)
        loadText = formatLoad(next)
    }

    /// Apply the text-field values to the SetLog and start the rest timer.
    /// "Empty reps" is the only blocker — load is optional (bodyweight).
    private func completeTapped() {
        // Toggle off if it was already logged — lets the user undo.
        if set.isLogged {
            set.completed = false
            return
        }
        let parsedReps = Int(repsText) ?? prescribedReps
        let parsedLoad = Double(loadText) ?? prescribedLoadLb
        set.reps = parsedReps
        set.loadLb = parsedLoad
        set.completed = true
        focused.wrappedValue = nil
        onComplete()
    }

    private func syncTextFromSet() {
        if let r = set.reps { repsText = "\(r)" }
        if let lb = set.loadLb { loadText = formatLoad(lb) }
    }

    /// Strip the trailing `.0` so "135" doesn't display as "135.0".
    private func formatLoad(_ lb: Double) -> String {
        lb.rounded() == lb ? "\(Int(lb))" : "\(lb)"
    }

    private func numericField(text: Binding<String>, placeholder: String,
                              id: ExerciseLogView.FieldID, width: CGFloat,
                              isDecimal: Bool = false) -> some View {
        TextField(placeholder, text: text)
            .keyboardType(isDecimal ? .decimalPad : .numberPad)
            .multilineTextAlignment(.center)
            .focused(focused, equals: id)
            .frame(width: width)
            .padding(.vertical, 8)
            .background {
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(Color.white.opacity(0.08))
                    .overlay {
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .strokeBorder(Color.white.opacity(0.15), lineWidth: 1)
                    }
            }
            .foregroundStyle(.white)
    }
}

