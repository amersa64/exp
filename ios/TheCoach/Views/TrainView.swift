// "Train" tab — the in-app path that closes the coaching loop without APNs.
//
// Without this view, a fresh user who finishes intake lands on a blank Summit
// with no way to act. The brain has already prescribed a session
// (`prepare_next_action`); this tab surfaces it and lets the user log the
// outcome, which feeds the same REPORT → ADAPT path a nudge reply would.
//
// Rubric C1 ("useful without opening") still rests on APNs. This tab is the
// in-app fallback so the loop is end-to-end exercisable.

import SwiftUI

struct TrainView: View {
    @StateObject private var model = TrainViewModel()
    @State private var showLogSheet = false
    @State private var lastResult: LogSessionResult?

    var body: some View {
        NavigationStack {
            Group {
                switch model.state {
                case .loading:
                    ProgressView().controlSize(.large)
                case .ready(let next):
                    ScrollView {
                        SessionContent(
                            next: next,
                            lastResult: lastResult,
                            onSchedule: { Task { await model.schedule(actionId: next.actionId) } },
                            onLog: { showLogSheet = true },
                            onLogMinimum: {
                                Task {
                                    let result = await model.log(
                                        actionId: next.actionId,
                                        outcome: .done,
                                        friction: "minimum dose — 2-min rule"
                                    )
                                    lastResult = result
                                    await model.refresh()
                                }
                            }
                        )
                        .padding(.horizontal)
                    }
                    .contentMargins(.bottom, 100, for: .scrollContent)
                    .refreshable { await model.refresh() }
                case .empty(let message):
                    ContentUnavailableView("Nothing prescribed yet",
                                           systemImage: "dumbbell.fill",
                                           description: Text(message))
                case .failed(let msg):
                    ErrorView(title: "Couldn't load your session",
                              message: msg,
                              retry: { await model.refresh() })
                }
            }
            .navigationTitle("Train")
            .navigationBarTitleDisplayMode(.inline)
            .task { await model.refresh() }
            .sheet(isPresented: $showLogSheet) {
                if case .ready(let next) = model.state {
                    LogSessionSheet(
                        sessionName: next.session.name,
                        onSubmit: { outcome, friction in
                            let result = await model.log(actionId: next.actionId,
                                                          outcome: outcome,
                                                          friction: friction)
                            lastResult = result
                            await model.refresh()
                        }
                    )
                    .presentationDetents([.medium, .large])
                }
            }
        }
    }
}

// MARK: - View model

@MainActor
final class TrainViewModel: ObservableObject {
    enum State {
        case loading
        case ready(NextSession)
        case empty(String)
        case failed(String)
    }

    @Published var state: State = .loading

    func refresh() async {
        state = .loading
        do {
            let next = try await CoachAPI.shared.nextSession()
            state = .ready(next)
        } catch let urlError as URLError {
            state = .failed(urlError.localizedDescription)
        } catch {
            // 409 from backend = no program yet (intake incomplete);
            // fall through to a friendly empty state.
            state = .empty("Finish intake and the coach will prescribe your first session.")
        }
    }

    func log(actionId: String, outcome: NudgeOutcome, friction: String?) async -> LogSessionResult? {
        try? await CoachAPI.shared.logSession(actionId: actionId, outcome: outcome, friction: friction)
    }

    func schedule(actionId: String) async {
        _ = try? await CoachAPI.shared.scheduleSession(actionId: actionId)
        await refresh()
    }
}

// MARK: - Session content

private struct SessionContent: View {
    let next: NextSession
    let lastResult: LogSessionResult?
    let onSchedule: () -> Void
    let onLog: () -> Void
    let onLogMinimum: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let result = lastResult, !result.ripples.isEmpty {
                RipplesBanner(ripples: result.ripples, adaptation: result.adaptation)
            }

            ImplementationIntentionCard(
                cue: next.cue,
                location: next.location,
                sessionName: next.session.name
            )

            VStack(alignment: .leading, spacing: 6) {
                Text("Up next").font(.caption).foregroundStyle(.secondary).textCase(.uppercase)
                Text(next.session.name).font(.title.bold())
                HStack(spacing: 8) {
                    Label("\(next.session.expectedMinutes) min", systemImage: "clock")
                    if let when = next.prescribedFor {
                        Text("·").foregroundStyle(.tertiary)
                        Label(when.formatted(date: .omitted, time: .shortened),
                              systemImage: "calendar")
                    }
                }
                .font(.subheadline)
                .foregroundStyle(.secondary)
            }

            VStack(spacing: 12) {
                ForEach(next.session.exercises) { ex in
                    ExerciseRow(exercise: ex)
                }
            }

            if !next.session.progressionRule.isEmpty {
                Text(next.session.progressionRule)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 4)
            }

            VStack(spacing: 8) {
                Button(action: onLog) {
                    Label("Log this session", systemImage: "checkmark.circle.fill")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 4)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)

                Button(action: onSchedule) {
                    Label(next.prescribedFor == nil ? "Schedule on calendar"
                                                    : "Reschedule on calendar",
                          systemImage: "calendar.badge.plus")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 4)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
            }
            .padding(.top, 4)

            if let dose = next.minimumDose, !dose.isEmpty {
                MinimumDoseCard(dose: dose, onLogMinimum: onLogMinimum)
            }
        }
        .padding(.vertical, 12)
    }
}

/// "When CUE, I will TRAIN at LOCATION" — Atomic Habits ch.5.
/// Shown prominently because the script is the friction-reducer.
private struct ImplementationIntentionCard: View {
    let cue: String?
    let location: String?
    let sessionName: String

    var body: some View {
        let cueText = (cue?.isEmpty == false) ? cue! : "when the moment opens"
        let locText = (location?.isEmpty == false) ? location! : "wherever you train"
        VStack(alignment: .leading, spacing: 4) {
            Text("THE SCRIPT")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            (Text(cueText.capitalized + ", ")
                .foregroundStyle(.primary)
             + Text("I will start ")
                .foregroundStyle(.secondary)
             + Text(sessionName)
                .fontWeight(.semibold)
                .foregroundStyle(.primary)
             + Text(" at ")
                .foregroundStyle(.secondary)
             + Text(locText)
                .foregroundStyle(.primary))
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.accentColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 16))
    }
}

/// 2-minute-rule fallback (Atomic Habits ch.13). Showing up at all > nothing.
private struct MinimumDoseCard: View {
    let dose: String
    let onLogMinimum: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "bolt.heart")
                    .foregroundStyle(.orange)
                Text("Bad day?")
                    .font(.subheadline.weight(.semibold))
            }
            Text(dose)
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)
            Text("Two-minute rule. Showing up beats skipping — and it still counts as a vote.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Button(action: onLogMinimum) {
                Label("I did the minimum", systemImage: "checkmark")
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 2)
            }
            .buttonStyle(.bordered)
            .controlSize(.regular)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 16))
    }
}

private struct ExerciseRow: View {
    let exercise: ExercisePrescription

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(exercise.name)
                    .font(.headline)
                Spacer()
                Text(volumeLabel)
                    .font(.body.weight(.semibold).monospacedDigit())
                    .foregroundStyle(.primary)
            }
            HStack(spacing: 12) {
                if let load = exercise.loadLb {
                    Label("\(Int(load)) lb", systemImage: "scalemass")
                }
                Label("\(exercise.restSeconds)s rest", systemImage: "hourglass")
            }
            .font(.subheadline)
            .foregroundStyle(.secondary)

            if !exercise.notes.isEmpty {
                Text(exercise.notes)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
        .accessibilityElement(children: .combine)
    }

    private var volumeLabel: String { "\(exercise.sets)×\(exercise.reps)" }
}

private struct RipplesBanner: View {
    let ripples: [String]
    let adaptation: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Logged", systemImage: "checkmark.seal.fill")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.green)
            Text(ripples.joined(separator: " · "))
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)
            if let a = adaptation, !a.isEmpty {
                Text(a)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.green.opacity(0.10), in: RoundedRectangle(cornerRadius: 16))
    }
}

// MARK: - Log sheet

private struct LogSessionSheet: View {
    let sessionName: String
    let onSubmit: (NudgeOutcome, String?) async -> Void

    @State private var outcome: NudgeOutcome = .done
    @State private var friction: String = ""
    @State private var submitting = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker("Outcome", selection: $outcome) {
                        Text("Done").tag(NudgeOutcome.done)
                        Text("Partial").tag(NudgeOutcome.partial)
                        Text("Skipped").tag(NudgeOutcome.skipped)
                    }
                    .pickerStyle(.segmented)
                } header: {
                    Text(sessionName)
                }

                Section {
                    TextField("What got in the way? (optional)",
                              text: $friction, axis: .vertical)
                        .lineLimit(2...5)
                } header: {
                    Text("Friction note")
                } footer: {
                    Text("This feeds adaptation — the next session changes based on what you report.")
                }

                Section {
                    Button {
                        Task {
                            submitting = true
                            await onSubmit(outcome, friction.isEmpty ? nil : friction)
                            submitting = false
                            dismiss()
                        }
                    } label: {
                        HStack {
                            if submitting { ProgressView() }
                            Text(submitting ? "Sending…" : "Send")
                                .frame(maxWidth: .infinity)
                                .fontWeight(.semibold)
                        }
                    }
                    .disabled(submitting)
                }
            }
            .navigationTitle("Log session")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
}
