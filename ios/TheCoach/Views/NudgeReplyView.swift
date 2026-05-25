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
    @State private var result: ReplyResult?
    @Environment(\.dismiss) var dismiss

    enum ReplyResult: Equatable {
        case sent(ripples: [String], adaptation: String?)
        case failed(String)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker("Outcome", selection: $outcome) {
                        Text("Done").tag(NudgeOutcome.done)
                        Text("Partial").tag(NudgeOutcome.partial)
                        Text("Not now").tag(NudgeOutcome.not_now)
                        Text("Busy").tag(NudgeOutcome.busy)
                        Text("Skipped").tag(NudgeOutcome.skipped)
                    }
                    .pickerStyle(.segmented)
                } header: {
                    Text("How did it go?")
                } footer: {
                    Text(footerForOutcome)
                }

                Section {
                    TextField("What got in the way? (optional)",
                              text: $friction, axis: .vertical)
                        .lineLimit(2...5)
                } header: {
                    Text("Friction note")
                } footer: {
                    Text("Feeds adaptation. Specific beats polite — 'kids meltdown at 6pm' is more useful than 'busy'.")
                }

                if case .sent(let ripples, let adaptation) = result {
                    Section {
                        ForEach(ripples, id: \.self) { ripple in
                            Label(ripple, systemImage: "sparkles")
                                .foregroundStyle(.primary)
                        }
                        if let a = adaptation, !a.isEmpty {
                            Text(a).font(.footnote).foregroundStyle(.secondary)
                        }
                    } header: {
                        Text("Reflected in your world")
                    }
                }

                if case .failed(let msg) = result {
                    Section {
                        Text(msg).foregroundStyle(.red)
                    }
                }

                Section {
                    Button {
                        Task { await send() }
                    } label: {
                        HStack {
                            if sending { ProgressView() }
                            Text(sending ? "Sending…" : "Send")
                                .fontWeight(.semibold)
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .disabled(sending || result != nil)
                }
            }
            .navigationTitle("Quick reply")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(result == nil ? "Cancel" : "Done") { dismiss() }
                }
            }
        }
        .onAppear { outcome = NudgeOutcome(rawValue: defaultOutcome.lowercased()) ?? .done }
    }

    private var footerForOutcome: String {
        switch outcome {
        case .done:     return "Counts as a verified vote. The world grows."
        case .partial:  return "Holds the load — no progression, no punishment."
        case .not_now:  return "Coach will back off and try again later."
        case .busy:     return "Acknowledged. No retry today."
        case .skipped:  return "Logged. No judgement — life happens."
        }
    }

    private func send() async {
        sending = true
        do {
            try await CoachAPI.shared.reply(
                nudgeId: nudgeId,
                outcome: outcome,
                friction: friction.isEmpty ? nil : friction
            )
            // Pull a fresh world to show the ripples that resulted.
            let world = try? await CoachAPI.shared.world()
            let ripples: [String] = {
                guard outcome == .done else { return [] }
                var out: [String] = []
                if let w = world {
                    out.append("+\(w.currency) total effort")
                    if w.streakDays > 0 { out.append("\(w.streakDays)-day streak") }
                    if w.identityVotes > 0 { out.append("\(w.identityVotes) votes cast") }
                }
                return out
            }()
            result = .sent(ripples: ripples, adaptation: nil)
        } catch {
            result = .failed(error.localizedDescription)
        }
        sending = false
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

