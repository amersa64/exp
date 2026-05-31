// "How to do it" sheet — opened from the header of ExerciseLogView when the
// lifter wants a refresher on form before working through a lift.
//
// Loads on appear from GET /exercise?name=... (free-exercise-db metadata,
// vendored in backend/data/exercises.json). Images are static JPGs hosted
// on GitHub's raw CDN — usually a start and end position. A TabView with
// page dots lets the user swipe between them so the two positions read as
// "from here, to here" rather than as a wall of images.
//
// Fails gracefully: if the catalog doesn't have the prescribed name (rare —
// the persona pulls names from the same catalog), the sheet shows a one-line
// placeholder rather than blocking the workout.

import SwiftUI

struct ExerciseDetailSheet: View {
    let exerciseName: String

    @Environment(\.dismiss) private var dismiss
    @State private var state: LoadState = .loading

    enum LoadState {
        case loading
        case loaded(ExerciseDetail)
        case failed(String)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                AtmosphericBackground()
                Group {
                    switch state {
                    case .loading:
                        ProgressView().controlSize(.large).tint(Theme.ember)
                    case .loaded(let detail):
                        ScrollView {
                            content(detail)
                                .padding(18)
                        }
                        .scrollContentBackground(.hidden)
                    case .failed(let message):
                        VStack(spacing: 12) {
                            Image(systemName: "questionmark.circle")
                                .font(.system(size: 44))
                                .foregroundStyle(.white.opacity(0.5))
                            Text("No demo found for this exercise.")
                                .font(.headline)
                                .foregroundStyle(.white)
                            Text(message)
                                .font(.footnote)
                                .foregroundStyle(.white.opacity(0.55))
                                .multilineTextAlignment(.center)
                        }
                        .padding(32)
                    }
                }
            }
            .navigationTitle(exerciseName)
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                        .foregroundStyle(Theme.gold)
                        .font(.body.weight(.semibold))
                }
            }
        }
        .task { await load() }
    }

    // MARK: - Loaded content

    @ViewBuilder
    private func content(_ detail: ExerciseDetail) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            imagesCard(detail)
            metaCard(detail)
            instructionsCard(detail)
        }
    }

    private func imagesCard(_ detail: ExerciseDetail) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionEyebrow(text: "DEMO", icon: "photo.on.rectangle")
            if detail.imageUrls.isEmpty {
                Text("No reference image for this exercise.")
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.55))
            } else {
                // TabView with page dots reads as "swipe between positions" —
                // start → end is the natural mental model for a static demo.
                TabView {
                    ForEach(detail.imageUrls, id: \.self) { url in
                        AsyncImage(url: url) { phase in
                            switch phase {
                            case .empty:
                                ProgressView().tint(Theme.ember)
                            case .success(let image):
                                image.resizable().scaledToFit()
                            case .failure:
                                Image(systemName: "photo")
                                    .font(.system(size: 32))
                                    .foregroundStyle(.white.opacity(0.4))
                            @unknown default:
                                EmptyView()
                            }
                        }
                        .frame(maxWidth: .infinity)
                        .padding(8)
                    }
                }
                .tabViewStyle(.page(indexDisplayMode: .always))
                .indexViewStyle(.page(backgroundDisplayMode: .always))
                .frame(height: 280)
                .background {
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(Color.white.opacity(0.06))
                }
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }

    private func metaCard(_ detail: ExerciseDetail) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionEyebrow(text: "AT A GLANCE", icon: "target")
            FlexibleChips(items: chips(for: detail))
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }

    private func chips(for detail: ExerciseDetail) -> [Chip] {
        var out: [Chip] = []
        if let eq = detail.equipment, !eq.isEmpty {
            out.append(Chip(icon: "dumbbell.fill", text: eq.capitalized, tint: Theme.ember))
        }
        if let level = detail.level, !level.isEmpty {
            out.append(Chip(icon: "chart.bar.fill", text: level.capitalized, tint: Theme.gold))
        }
        if let mechanic = detail.mechanic, !mechanic.isEmpty {
            out.append(Chip(icon: "link", text: mechanic.capitalized, tint: Theme.amber))
        }
        for muscle in detail.primaryMuscles {
            out.append(Chip(icon: "figure.strengthtraining.traditional",
                            text: muscle.capitalized, tint: Theme.emerald))
        }
        for muscle in detail.secondaryMuscles {
            out.append(Chip(icon: "circle.dotted",
                            text: muscle.capitalized, tint: .white.opacity(0.5)))
        }
        return out
    }

    private func instructionsCard(_ detail: ExerciseDetail) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionEyebrow(text: "STEP BY STEP", icon: "list.number")
            if detail.instructions.isEmpty {
                Text("No written instructions available.")
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.55))
            } else {
                ForEach(Array(detail.instructions.enumerated()), id: \.offset) { idx, step in
                    HStack(alignment: .top, spacing: 12) {
                        Text("\(idx + 1)")
                            .font(.system(.subheadline, design: .rounded, weight: .heavy))
                            .monospacedDigit()
                            .foregroundStyle(.white)
                            .frame(width: 26, height: 26)
                            .background {
                                Circle().fill(Theme.ember.opacity(0.30))
                                    .overlay {
                                        Circle().strokeBorder(Color.white.opacity(0.15), lineWidth: 1)
                                    }
                            }
                        Text(step)
                            .font(.subheadline)
                            .foregroundStyle(.white.opacity(0.85))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }

    // MARK: - Loading

    private func load() async {
        do {
            let detail = try await CoachAPI.shared.exerciseDetail(name: exerciseName)
            state = .loaded(detail)
        } catch {
            state = .failed(error.localizedDescription)
        }
    }
}

// MARK: - Chip layout

private struct Chip: Identifiable {
    let id = UUID()
    let icon: String
    let text: String
    let tint: Color
}

/// Wrapping HStack — fills the row, then breaks onto the next line. SwiftUI
/// doesn't ship this out of the box; the implementation is a small Layout
/// that does one-pass left-to-right placement with row wrapping.
private struct FlexibleChips: View {
    let items: [Chip]

    var body: some View {
        ChipFlow(spacing: 6) {
            ForEach(items) { chip in
                Label(chip.text, systemImage: chip.icon)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background {
                        Capsule().fill(chip.tint.opacity(0.20))
                            .overlay {
                                Capsule().strokeBorder(chip.tint.opacity(0.45), lineWidth: 1)
                            }
                    }
            }
        }
    }
}

private struct ChipFlow: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        var rowWidth: CGFloat = 0
        var rowHeight: CGFloat = 0
        var totalHeight: CGFloat = 0
        var totalWidth: CGFloat = 0

        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if rowWidth + size.width > maxWidth, rowWidth > 0 {
                totalHeight += rowHeight + spacing
                totalWidth = max(totalWidth, rowWidth - spacing)
                rowWidth = 0
                rowHeight = 0
            }
            rowWidth += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        totalHeight += rowHeight
        totalWidth = max(totalWidth, rowWidth - spacing)
        return CGSize(width: totalWidth, height: totalHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0

        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX, x > bounds.minX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            view.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
