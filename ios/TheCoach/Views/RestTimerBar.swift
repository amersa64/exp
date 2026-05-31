// Sticky countdown banner — the one piece of UI that has to be everywhere
// inside a workout so the lifter sees their rest period regardless of
// which screen they're on (active-session list, individual exercise).
//
// Observes RestTimer.shared so both ActiveSessionView and ExerciseLogView
// see the same countdown without prop-drilling.

import SwiftUI

struct RestTimerBar: View {
    @ObservedObject private var timer = RestTimer.shared

    var body: some View {
        // Hidden when no rest is in progress — let .safeAreaInset collapse
        // to zero height rather than leaving an empty bar around.
        if timer.isRunning {
            bar
                .transition(.move(edge: .bottom).combined(with: .opacity))
        }
    }

    private var bar: some View {
        HStack(spacing: 14) {
            ZStack {
                Circle()
                    .stroke(Color.white.opacity(0.18), lineWidth: 4)
                Circle()
                    .trim(from: 0, to: timer.progress)
                    .stroke(Theme.gold, style: .init(lineWidth: 4, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                Text("\(timer.secondsRemaining)")
                    .font(.system(.title3, design: .rounded, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(.white)
            }
            .frame(width: 50, height: 50)
            VStack(alignment: .leading, spacing: 2) {
                Text("REST")
                    .font(.caption2.weight(.bold))
                    .tracking(1.5)
                    .foregroundStyle(.white.opacity(0.6))
                Text(label)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.white)
            }
            Spacer()
            Button { timer.skip() } label: {
                Text("Skip")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background {
                        Capsule().fill(Color.white.opacity(0.12))
                            .overlay { Capsule().strokeBorder(Color.white.opacity(0.20), lineWidth: 1) }
                    }
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Theme.gold.opacity(0.18))
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .strokeBorder(Theme.gold.opacity(0.35), lineWidth: 1)
                }
        }
        .padding(.horizontal, 14)
        .padding(.bottom, 8)
    }

    /// "Resume in 90s" while counting, "Resting between sets" when the timer
    /// is mid-period. Lifter context, not implementation detail.
    private var label: String {
        if let name = timer.exerciseName, !name.isEmpty {
            return "Between sets of \(name)"
        }
        return "Between sets"
    }
}
