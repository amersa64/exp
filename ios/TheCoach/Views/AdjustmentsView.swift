// "Things your coach remembers" — the coach memory surface.
//
// Lists every adjustment the user has ever requested (GET /adjustments):
// exercise swaps and program-level feedback, each with the user's own words
// and the coach's reply. This is what makes the app feel like a coach who
// knows you, not a tracker that forgets.

import SwiftUI

struct AdjustmentsView: View {
    @State private var loading = true
    @State private var adjustments: [ProgramAdjustment] = []
    @State private var errorText: String?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                AtmosphericBackground()
                Group {
                    if loading {
                        ProgressView().tint(Theme.ember)
                    } else if let err = errorText {
                        ErrorView(title: "Couldn't load",
                                  message: err,
                                  retry: { await load() })
                    } else if adjustments.isEmpty {
                        emptyState
                    } else {
                        list
                    }
                }
            }
            .navigationTitle("Coach memory")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                        .foregroundStyle(.white.opacity(0.85))
                }
            }
            .task { await load() }
        }
    }

    private var list: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Everything you've told your coach. These shape every "
                     + "program from here on.")
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.55))
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 4)
                // Newest first.
                ForEach(adjustments.reversed()) { adj in
                    AdjustmentCard(adjustment: adj)
                }
            }
            .padding(18)
        }
        .scrollContentBackground(.hidden)
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "brain.head.profile")
                .font(.system(size: 52))
                .foregroundStyle(Theme.emberGradient)
            Text("Nothing remembered yet")
                .font(.title3.weight(.semibold))
                .foregroundStyle(.white)
            Text("When you swap an exercise or give feedback, your coach "
                 + "remembers it here.")
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.6))
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(28)
        .frame(maxWidth: .infinity)
        .glassCard()
        .padding(18)
    }

    private func load() async {
        loading = true
        errorText = nil
        do {
            adjustments = try await CoachAPI.shared.adjustments()
        } catch {
            errorText = error.localizedDescription
        }
        loading = false
    }
}

private struct AdjustmentCard: View {
    let adjustment: ProgramAdjustment

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: adjustment.scope == "exercise"
                      ? "arrow.triangle.2.circlepath" : "slider.horizontal.3")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(Theme.gold)
                Text(scopeLabel)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(Theme.gold)
                Spacer()
                if !adjustment.active {
                    Text("RETIRED")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(.white.opacity(0.4))
                }
            }

            // The user's own words — the primary signal.
            Text("\u{201C}\(adjustment.userNote)\u{201D}")
                .font(.callout)
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)

            if let from = adjustment.targetExercise {
                HStack(spacing: 6) {
                    Text(from)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white.opacity(0.6))
                        .strikethrough()
                    if let to = adjustment.replacementExercise {
                        Image(systemName: "arrow.right")
                            .font(.caption2)
                            .foregroundStyle(.white.opacity(0.4))
                        Text(to)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Theme.emerald)
                    }
                }
            }

            Text(adjustment.coachResponse)
                .font(.footnote)
                .foregroundStyle(.white.opacity(0.7))
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }

    private var scopeLabel: String {
        adjustment.scope == "exercise" ? "EXERCISE SWAP" : "PROGRAM FEEDBACK"
    }
}
