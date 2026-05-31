// "Talk to your coach" — free-form feedback about the program as a whole.
//
// Distinct from SwapSheet (which is about ONE exercise). This is where the
// user says "I'm wiped, it's too much" / "I can only train 3 days now" /
// "more upper body please". The coach interprets the feedback, remembers it,
// and regenerates the program when the feedback changes its shape.
//
// Entry point: a button on the Train tab. Reachable any time, but most useful
// after the first week once the user has felt the program.

import SwiftUI

struct CoachFeedbackSheet: View {
    /// Called after a successful submission so the parent can refresh the
    /// session (a regeneration changes what /session/next returns).
    let onSubmitted: () -> Void

    @State private var note: String = ""
    @State private var phase: Phase = .input
    @State private var result: ProgramFeedbackResult?
    @State private var errorText: String?
    @State private var showingMemory = false
    @FocusState private var noteFocused: Bool
    @Environment(\.dismiss) private var dismiss

    private enum Phase { case input, loading, result }

    var body: some View {
        NavigationStack {
            ZStack {
                AtmosphericBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        switch phase {
                        case .input:   inputSection
                        case .loading: loadingSection
                        case .result:  resultSection
                        }
                    }
                    .padding(18)
                }
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("Talk to your coach")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(phase == .result ? "Done" : "Cancel") { dismiss() }
                        .foregroundStyle(.white.opacity(0.85))
                }
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        showingMemory = true
                    } label: {
                        Image(systemName: "brain.head.profile")
                            .foregroundStyle(.white.opacity(0.85))
                    }
                }
            }
            .sheet(isPresented: $showingMemory) {
                AdjustmentsView()
                    .presentationDetents([.medium, .large])
            }
        }
    }

    // MARK: - Input

    private var inputSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 8) {
                SectionEyebrow(text: "HOW'S IT GOING?", icon: "quote.bubble.fill")
                Text("Tell me what's working and what isn't")
                    .font(.headline)
                    .foregroundStyle(.white)
                Text("Too much? Too little? Schedule changed? Something hurts? "
                     + "Say it however you like — I'll adjust your program and "
                     + "remember it going forward.")
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.55))
                    .fixedSize(horizontal: false, vertical: true)

                ZStack(alignment: .topLeading) {
                    if note.isEmpty {
                        Text("e.g. \"these sessions leave me totally wiped, I think it's too much volume\"")
                            .font(.callout)
                            .foregroundStyle(.white.opacity(0.3))
                            .padding(.horizontal, 12)
                            .padding(.vertical, 12)
                    }
                    TextEditor(text: $note)
                        .font(.callout)
                        .foregroundStyle(.white)
                        .scrollContentBackground(.hidden)
                        .frame(minHeight: 130)
                        .padding(6)
                        .focused($noteFocused)
                }
                .background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(.white.opacity(0.1)))
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .glassCard()

            if let err = errorText { errorCard(err) }

            Button {
                Task { await submit() }
            } label: {
                Label("Send to coach", systemImage: "paperplane.fill")
            }
            .buttonStyle(EmberButtonStyle())
            .disabled(note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .onAppear { noteFocused = true }
    }

    // MARK: - Loading

    private var loadingSection: some View {
        VStack(spacing: 12) {
            ProgressView().tint(Theme.ember)
            Text("Your coach is reworking your plan…")
                .font(.footnote)
                .foregroundStyle(.white.opacity(0.6))
        }
        .frame(maxWidth: .infinity)
        .padding(28)
    }

    // MARK: - Result

    @ViewBuilder
    private var resultSection: some View {
        if let r = result {
            VStack(alignment: .leading, spacing: 16) {
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

                VStack(alignment: .leading, spacing: 8) {
                    Label {
                        Text(r.regenerated ? "Program updated" : "Noted for next time")
                            .foregroundStyle(.white)
                    } icon: {
                        Image(systemName: r.regenerated ? "arrow.triangle.2.circlepath" : "bookmark.fill")
                            .foregroundStyle(Theme.gold)
                    }
                    .font(.subheadline.weight(.semibold))
                    Text(r.changeSummary)
                        .font(.footnote)
                        .foregroundStyle(.white.opacity(0.7))
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(18)
                .frame(maxWidth: .infinity, alignment: .leading)
                .glassCard()

                Button("Done") {
                    onSubmitted()
                    dismiss()
                }
                .buttonStyle(EmberButtonStyle())
            }
        }
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

    private func submit() async {
        errorText = nil
        phase = .loading
        do {
            result = try await CoachAPI.shared.programFeedback(
                note: note.trimmingCharacters(in: .whitespacesAndNewlines)
            )
            phase = .result
        } catch {
            errorText = error.localizedDescription
            phase = .input
        }
    }
}
