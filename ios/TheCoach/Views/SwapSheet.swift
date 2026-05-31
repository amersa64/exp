// Swap-exercise modal — pick a default alternative, or tell your coach.
//
// Two paths, defaults-first (the user shouldn't have to write an essay just to
// trade one lift for another):
//
//   1) DEFAULT PICKS — on open we fetch the equipment-matched alternates (same
//      primary muscle + movement pattern) and show them as tappable rows. One
//      tap swaps and the coach remembers it (no LLM round-trip needed — the
//      decision's already made).
//   2) CUSTOM — "Something specific?" reveals a note field; the coach reads the
//      free-form request against the catalog and recommends a fit. This is the
//      path for "this hurts my knee, give me something gentler".
//
//   TrainView -> ActiveSessionView -> ExerciseLogView -> [this sheet]
//
// On confirm, `onPick(replacementName)` hands the chosen catalog name back so
// the active session mutates locally; persistence + memory already happened
// server-side in the /exercise/swap call.

import SwiftUI

struct SwapSheet: View {
    let original: ExercisePrescription
    /// Called with the chosen replacement's catalog name once the user
    /// confirms. The swap is already persisted + remembered server-side.
    let onPick: (String) -> Void

    @State private var note: String = ""
    @State private var phase: Phase = .choices
    @State private var alternates: [ExerciseAlternate] = []
    @State private var loadingAlternates = true
    @State private var applyingPick: String?       // name being applied (spinner)
    @State private var result: ExerciseSwapResult?
    @State private var errorText: String?
    @FocusState private var noteFocused: Bool
    @Environment(\.dismiss) private var dismiss

    private enum Phase { case choices, input, loading, result }

    var body: some View {
        NavigationStack {
            ZStack {
                AtmosphericBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        originalCard
                        switch phase {
                        case .choices: choicesSection
                        case .input:   inputSection
                        case .loading: loadingSection
                        case .result:  resultSection
                        }
                    }
                    .padding(18)
                }
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("Swap exercise")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .foregroundStyle(.white.opacity(0.85))
                }
            }
            .task { await loadAlternates() }
        }
    }

    // MARK: - Original

    private var originalCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            SectionEyebrow(text: "SWAPPING")
            Text(original.name)
                .font(.title3.weight(.bold))
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }

    // MARK: - Default picks phase

    private var choicesSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            if loadingAlternates {
                HStack(spacing: 10) {
                    ProgressView().tint(Theme.ember)
                    Text("Finding good swaps…")
                        .font(.footnote)
                        .foregroundStyle(.white.opacity(0.6))
                }
                .frame(maxWidth: .infinity)
                .padding(24)
            } else if alternates.isEmpty {
                // No equipment-matched defaults — go straight to the note path.
                Text("No quick swaps for your equipment — tell your coach what you need instead.")
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.6))
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Text("PICK A SWAP")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(Theme.gold)
                Text("Same muscles, your equipment. One tap and your coach remembers it.")
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.55))
                    .fixedSize(horizontal: false, vertical: true)
                ForEach(alternates) { alt in
                    Button {
                        Task { await applyPick(alt.name) }
                    } label: {
                        alternateRow(alt)
                    }
                    .buttonStyle(.plain)
                    .disabled(applyingPick != nil)
                }
            }

            if let err = errorText { errorCard(err) }

            Button {
                phase = .input
            } label: {
                Label("Something specific? Tell your coach", systemImage: "quote.bubble")
            }
            .buttonStyle(GhostButtonStyle())
            .padding(.top, 2)
        }
    }

    private func alternateRow(_ alt: ExerciseAlternate) -> some View {
        HStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 4) {
                Text(alt.name)
                    .font(.headline)
                    .foregroundStyle(.white)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                if let muscles = alt.primaryMuscles.first {
                    Text([muscles, alt.equipment, alt.level]
                            .compactMap { $0 }
                            .joined(separator: " · "))
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.5))
                }
            }
            Spacer(minLength: 0)
            if applyingPick == alt.name {
                ProgressView().controlSize(.small).tint(Theme.gold)
            } else {
                Image(systemName: "arrow.left.arrow.right.circle.fill")
                    .font(.title3)
                    .foregroundStyle(Theme.gold)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }

    // MARK: - Custom-note input phase

    private var inputSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 8) {
                Text("What's wrong with it?")
                    .font(.headline)
                    .foregroundStyle(.white)
                Text("Tell your coach why — pain, equipment, you just hate it. "
                     + "The more you say, the better the swap. We'll remember it.")
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.55))
                    .fixedSize(horizontal: false, vertical: true)

                ZStack(alignment: .topLeading) {
                    if note.isEmpty {
                        Text("e.g. \"this flares up my lower back — want something safer that still hits hamstrings\"")
                            .font(.callout)
                            .foregroundStyle(.white.opacity(0.3))
                            .padding(.horizontal, 12)
                            .padding(.vertical, 12)
                    }
                    TextEditor(text: $note)
                        .font(.callout)
                        .foregroundStyle(.white)
                        .scrollContentBackground(.hidden)
                        .frame(minHeight: 110)
                        .padding(6)
                        .focused($noteFocused)
                }
                .background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(.white.opacity(0.1)))
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .glassCard()

            if let err = errorText {
                errorCard(err)
            }

            Button {
                Task { await requestSwap() }
            } label: {
                Label("Find me an alternative", systemImage: "sparkles")
            }
            .buttonStyle(EmberButtonStyle())
            .disabled(note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

            if !alternates.isEmpty {
                Button { phase = .choices } label: {
                    Label("Back to quick swaps", systemImage: "chevron.left")
                }
                .buttonStyle(GhostButtonStyle())
            }
        }
        .onAppear { noteFocused = true }
    }

    // MARK: - Loading phase

    private var loadingSection: some View {
        VStack(spacing: 12) {
            ProgressView().tint(Theme.ember)
            Text("Your coach is thinking it through…")
                .font(.footnote)
                .foregroundStyle(.white.opacity(0.6))
        }
        .frame(maxWidth: .infinity)
        .padding(28)
    }

    // MARK: - Result phase (custom-note path)

    @ViewBuilder
    private var resultSection: some View {
        if let r = result {
            VStack(alignment: .leading, spacing: 16) {
                // Coach's voice reply.
                VStack(alignment: .leading, spacing: 8) {
                    SectionEyebrow(text: "YOUR COACH", icon: "quote.bubble.fill")
                    Text(r.coachResponse)
                        .font(.callout)
                        .foregroundStyle(.white)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(18)
                .frame(maxWidth: .infinity, alignment: .leading)
                .glassCardTinted(Theme.ember)

                if let replacement = r.replacement {
                    Text("RECOMMENDED")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(Theme.gold)
                    Button {
                        onPick(replacement)
                        dismiss()
                    } label: {
                        pickRow(name: replacement, highlighted: true)
                    }
                    .buttonStyle(.plain)
                }

                if !r.alternatives.isEmpty {
                    Text("OR TRY")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.white.opacity(0.45))
                        .padding(.top, 4)
                    ForEach(r.alternatives, id: \.self) { alt in
                        Button {
                            onPick(alt)
                            dismiss()
                        } label: {
                            pickRow(name: alt, highlighted: false)
                        }
                        .buttonStyle(.plain)
                    }
                }

                if r.replacement == nil && r.alternatives.isEmpty {
                    Text("I couldn't find a clean equipment-matched alternative, "
                         + "but I've noted this and will rebalance your program around it.")
                        .font(.footnote)
                        .foregroundStyle(.white.opacity(0.6))
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(18)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .glassCard()
                    Button("Done") { dismiss() }
                        .buttonStyle(GhostButtonStyle())
                }
            }
        }
    }

    private func pickRow(name: String, highlighted: Bool) -> some View {
        HStack(spacing: 14) {
            Text(name)
                .font(.headline)
                .foregroundStyle(.white)
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            Image(systemName: highlighted ? "checkmark.circle.fill" : "chevron.right")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(highlighted ? Theme.gold : .white.opacity(0.35))
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(PickRowBackground(highlighted: highlighted))
    }

    private func errorCard(_ text: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label {
                Text("Couldn't reach your coach").foregroundStyle(.white)
            } icon: {
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(Theme.amber)
            }
            .font(.subheadline.weight(.semibold))
            Text(text).font(.caption).foregroundStyle(.white.opacity(0.6))
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCardTinted(Theme.amber)
    }

    // MARK: - Networking

    private func loadAlternates() async {
        loadingAlternates = true
        defer { loadingAlternates = false }
        do {
            let resp = try await CoachAPI.shared.exerciseAlternates(name: original.name)
            alternates = resp.alternates
        } catch {
            // Non-fatal: fall back to the note path silently.
            alternates = []
        }
    }

    /// Default-pick path: apply the chosen alternate directly. The coach
    /// remembers it (standing constraint) without an LLM call.
    private func applyPick(_ name: String) async {
        errorText = nil
        applyingPick = name
        defer { applyingPick = nil }
        do {
            _ = try await CoachAPI.shared.exerciseSwap(name: original.name, note: "", chosen: name)
            onPick(name)
            dismiss()
        } catch {
            errorText = error.localizedDescription
        }
    }

    /// Custom-note path: the LLM reads the note and recommends a fit.
    private func requestSwap() async {
        errorText = nil
        phase = .loading
        do {
            let r = try await CoachAPI.shared.exerciseSwap(
                name: original.name,
                note: note.trimmingCharacters(in: .whitespacesAndNewlines)
            )
            result = r
            phase = .result
        } catch {
            errorText = error.localizedDescription
            phase = .input
        }
    }
}

/// Ember-tinted background for the recommended pick, plain glass otherwise.
private struct PickRowBackground: ViewModifier {
    let highlighted: Bool
    func body(content: Content) -> some View {
        if highlighted {
            content.glassCardTinted(Theme.ember)
        } else {
            content.glassCard()
        }
    }
}
