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
    @State private var result: LocalResult?
    @Environment(\.dismiss) var dismiss

    enum LocalResult: Equatable {
        case sent(ripples: [String], adaptation: String?, coachResponse: String?)
        case failed(String)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                AtmosphericBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        outcomeCard
                        frictionCard
                        resultCards
                        sendButton
                    }
                    .padding(18)
                }
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("Quick reply")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(result == nil ? "Cancel" : "Done") { dismiss() }
                        .foregroundStyle(.white.opacity(0.85))
                }
            }
        }
        .onAppear { outcome = NudgeOutcome(rawValue: defaultOutcome.lowercased()) ?? .done }
    }

    private var outcomeCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionEyebrow(text: "HOW DID IT GO?")
            Picker("Outcome", selection: $outcome) {
                Text("Done").tag(NudgeOutcome.done)
                Text("Partial").tag(NudgeOutcome.partial)
                Text("Not now").tag(NudgeOutcome.not_now)
                Text("Busy").tag(NudgeOutcome.busy)
                Text("Skipped").tag(NudgeOutcome.skipped)
            }
            .pickerStyle(.segmented)
            Text(footerForOutcome)
                .font(.caption)
                .foregroundStyle(.white.opacity(0.55))
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }

    private var frictionCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionEyebrow(text: "FRICTION NOTE")
            TextField("What got in the way? (optional)",
                      text: $friction, axis: .vertical)
                .lineLimit(2...5)
                .foregroundStyle(.white)
                .tint(Theme.ember)
                .padding(12)
                .background {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(Color.white.opacity(0.06))
                        .overlay {
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .strokeBorder(Color.white.opacity(0.12), lineWidth: 1)
                        }
                }
            Text("Feeds adaptation. Specific beats polite — 'kids meltdown at 6pm' is more useful than 'busy'.")
                .font(.caption)
                .foregroundStyle(.white.opacity(0.5))
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }

    @ViewBuilder
    private var resultCards: some View {
        if case .sent(let ripples, let adaptation, let coachResponse) = result {
            if let cr = coachResponse, !cr.isEmpty {
                // The coach's voice — distinct treatment from the world ripples.
                VStack(alignment: .leading, spacing: 12) {
                    SectionEyebrow(text: "FROM YOUR COACH", icon: "quote.opening")
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "person.fill.questionmark")
                            .font(.title3)
                            .foregroundStyle(Theme.emberGradient)
                            .shadow(color: Theme.ember.opacity(0.5), radius: 6)
                        Text(cr)
                            .font(.system(.callout, design: .serif))
                            .foregroundStyle(.white)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(18)
                .frame(maxWidth: .infinity, alignment: .leading)
                .glassCardTinted(Theme.ember)
            }

            VStack(alignment: .leading, spacing: 12) {
                SectionEyebrow(text: "REFLECTED IN YOUR WORLD", icon: "sparkles")
                ForEach(ripples, id: \.self) { ripple in
                    HStack(spacing: 10) {
                        Image(systemName: "sparkles")
                            .foregroundStyle(Theme.gold)
                        Text(ripple)
                            .foregroundStyle(.white.opacity(0.92))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                if let a = adaptation, !a.isEmpty {
                    Text(a)
                        .font(.footnote)
                        .foregroundStyle(.white.opacity(0.55))
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 4)
                }
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .glassCard()
        }

        if case .failed(let msg) = result {
            HStack(spacing: 10) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(Theme.rose)
                Text(msg)
                    .foregroundStyle(.white)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .glassCardTinted(Theme.rose)
        }
    }

    private var sendButton: some View {
        Button {
            Task { await send() }
        } label: {
            HStack {
                if sending { ProgressView().tint(.black) }
                Text(sending ? "Sending…" : "Send")
            }
        }
        .buttonStyle(EmberButtonStyle())
        .disabled(sending || result != nil)
        .opacity(result != nil ? 0.4 : 1.0)
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
            // The reply now returns the brain's whole response: ripples,
            // adaptation rationale, AND the coach's spoken acknowledgment.
            // We render all three — the coach's voice goes first.
            let resp = try await CoachAPI.shared.reply(
                nudgeId: nudgeId,
                outcome: outcome,
                friction: friction.isEmpty ? nil : friction
            )
            result = .sent(
                ripples: resp.ripples,
                adaptation: resp.adaptation,
                coachResponse: resp.coachResponse
            )
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
