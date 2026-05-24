// Intake = a conversation, not a form (Section 4.1.1, anti-pattern: "Pre-built
// goal templates the user picks from"). The questions stream from the persona;
// the user answers in free text; the LLM derives the structured profile.

import SwiftUI

struct IntakeView: View {
    @EnvironmentObject var session: SessionState
    @State private var questions: [IntakeQuestion] = []
    @State private var answers: [String: String] = [:]
    @State private var current: Int = 0
    @State private var draft: String = ""
    @State private var loading = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if questions.isEmpty {
                ProgressView("Calling the coach…")
            } else if current < questions.count {
                Text(questions[current].q).font(.title3).bold()
                TextEditor(text: $draft)
                    .frame(minHeight: 100)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(.secondary))
                Button("Next") {
                    answers[questions[current].key] = draft
                    draft = ""
                    current += 1
                }.buttonStyle(.borderedProminent)
                Text("\(current + 1) of \(questions.count)").font(.caption).foregroundStyle(.secondary)
            } else {
                ProgressView("Building your program…")
                    .task { await submit() }
            }
        }
        .padding()
        .task { await loadQuestions() }
    }

    private func loadQuestions() async {
        questions = (try? await CoachAPI.shared.intakeQuestions()) ?? []
    }

    private func submit() async {
        loading = true
        let result = try? await CoachAPI.shared.submitIntake(answers)
        loading = false
        if let handoff = result?.handoff {
            session.handoffMessage = handoff
        } else {
            session.hasCompletedIntake = true
        }
    }
}
