// One-tap reply (Section 7.3, Rubric D5).
//
// This is NOT a dashboard. Default outcome is pre-selected from the
// notification action; an optional friction note feeds adaptation.

import SwiftUI
import Combine

struct NudgeReplyView: View {
    let nudgeId: String
    var defaultOutcome: String

    @State private var outcome: NudgeOutcome = .done
    @State private var friction: String = ""
    @State private var sending = false
    @Environment(\.dismiss) var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Quick reply").font(.title2).bold()
            Picker("Outcome", selection: $outcome) {
                Text("Done").tag(NudgeOutcome.done)
                Text("Partial").tag(NudgeOutcome.partial)
                Text("Not now").tag(NudgeOutcome.not_now)
                Text("Busy").tag(NudgeOutcome.busy)
                Text("Skipped").tag(NudgeOutcome.skipped)
            }.pickerStyle(.segmented)
            TextField("What got in the way? (optional)", text: $friction, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(2...4)
            Button(sending ? "Sending…" : "Send") { Task { await send() } }
                .buttonStyle(.borderedProminent)
                .disabled(sending)
            Spacer()
        }
        .padding()
        .onAppear { outcome = NudgeOutcome(rawValue: defaultOutcome.lowercased()) ?? .done }
    }

    private func send() async {
        sending = true
        try? await CoachAPI.shared.reply(nudgeId: nudgeId, outcome: outcome, friction: friction.isEmpty ? nil : friction)
        sending = false
        dismiss()
    }
}

/// Routes APNs taps → sheet presentation.
final class NudgeReplyRouter: ObservableObject {
    static let shared = NudgeReplyRouter()
    struct Presented: Identifiable { let nudgeId: String; let actionId: String; var id: String { nudgeId } }
    @Published var presented: Presented?
    func present(nudgeId: String, actionId: String) {
        presented = Presented(nudgeId: nudgeId, actionId: actionId)
    }
}

final class SessionState: ObservableObject {
    @Published var hasCompletedIntake: Bool = false
    @Published var handoffMessage: String?
}
