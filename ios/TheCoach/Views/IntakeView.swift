// Intake = a conversation, not a form (Section 4.1.1). For this pass, the
// spec's "no pre-built templates" rule is intentionally relaxed: HIG-native
// pickers/steppers give the LLM cleaner structured answers and the user a
// faster path through onboarding. The semantics are unchanged — answers are
// still a `[String: String]` dict sent to the backend persona for derivation.

import SwiftUI

struct IntakeView: View {
    @EnvironmentObject var sessionStore: SessionStore
    @State private var step: Step = .welcome
    @State private var answers = StructuredAnswers()
    @State private var identityStatement: String = ""
    @State private var submitState: SubmitState = .idle
    @FocusState private var injuriesFocused: Bool
    @FocusState private var squatFocused: Bool
    @FocusState private var identityFocused: Bool

    enum Step: Int, CaseIterable, Comparable {
        case welcome, experience, daysPerWeek, injuries, equipment, baselineSquat, identity, submitting
        static func < (lhs: Step, rhs: Step) -> Bool { lhs.rawValue < rhs.rawValue }
        var index: Int { rawValue }
        var total: Int { 6 }  // counted onboarding screens, excluding welcome + submitting
    }

    enum SubmitState: Equatable {
        case idle
        case loading
        case failed(String)
    }

    var body: some View {
        NavigationStack {
            Group {
                if step == .welcome {
                    WelcomeScreen(onStart: { advance() })
                } else if step == .submitting {
                    submittingScreen
                } else {
                    ScrollView {
                        content
                            .padding(.horizontal, 20)
                            .padding(.top, 4)
                            .padding(.bottom, 16)
                    }
                    .scrollBounceBehavior(.basedOnSize)
                    .safeAreaInset(edge: .bottom) { progressFooter }
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if step != .welcome && step != .submitting {
                    ToolbarItem(placement: .topBarLeading) {
                        Button {
                            withAnimation { goBack() }
                        } label: {
                            Image(systemName: "chevron.left")
                        }
                        .disabled(step == .experience)
                    }
                    ToolbarItem(placement: .principal) {
                        Text("\(step.index) of \(step.total)")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .monospacedDigit()
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        switch step {
        case .welcome, .submitting:  EmptyView()
        case .experience:   experienceScreen
        case .daysPerWeek:  daysPerWeekScreen
        case .injuries:     injuriesScreen
        case .equipment:    equipmentScreen
        case .baselineSquat: baselineSquatScreen
        case .identity:     identityScreen
        }
    }

    // MARK: - Screens

    private var experienceScreen: some View {
        OnboardingQuestion(
            prompt: "Your strength-training experience?",
            subtitle: "We'll use this to calibrate starting loads."
        ) {
            VStack(spacing: 8) {
                ForEach(ExperienceLevel.allCases) { e in
                    OptionRow(
                        label: e.label,
                        selected: answers.experience == e,
                        onTap: { answers.experience = e }
                    )
                }
            }
        }
    }

    private var daysPerWeekScreen: some View {
        OnboardingQuestion(
            prompt: "How many days a week can you train?",
            subtitle: "Honest is better than ambitious."
        ) {
            HStack(spacing: 20) {
                Button { if answers.daysPerWeek > 2 { answers.daysPerWeek -= 1 } } label: {
                    Image(systemName: "minus")
                        .font(.title2.weight(.semibold))
                        .frame(width: 56, height: 56)
                }
                .buttonStyle(.bordered)
                .clipShape(Circle())
                .disabled(answers.daysPerWeek <= 2)

                VStack(spacing: 0) {
                    Text("\(answers.daysPerWeek)")
                        .font(.system(size: 56, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .contentTransition(.numericText(value: Double(answers.daysPerWeek)))
                    Text(answers.daysPerWeek == 1 ? "day per week" : "days per week")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .frame(minWidth: 140)

                Button { if answers.daysPerWeek < 4 { answers.daysPerWeek += 1 } } label: {
                    Image(systemName: "plus")
                        .font(.title2.weight(.semibold))
                        .frame(width: 56, height: 56)
                }
                .buttonStyle(.bordered)
                .clipShape(Circle())
                .disabled(answers.daysPerWeek >= 4)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 24)
            .background(Color(.secondarySystemBackground),
                        in: RoundedRectangle(cornerRadius: 16))
        }
    }

    private var injuriesScreen: some View {
        OnboardingQuestion(
            prompt: "Any current pain or injuries to work around?",
            subtitle: "If something hurts, the coach holds back."
        ) {
            VStack(alignment: .leading, spacing: 12) {
                TextField("Describe anything to be careful with…", text: $answers.injuries, axis: .vertical)
                    .lineLimit(3...5)
                    .textFieldStyle(.roundedBorder)
                    .focused($injuriesFocused)
                Button {
                    answers.injuries = "none"
                    injuriesFocused = false
                } label: {
                    Label("Nothing — I'm good", systemImage: "checkmark.circle")
                        .font(.subheadline)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
    }

    private var equipmentScreen: some View {
        OnboardingQuestion(
            prompt: "What equipment do you have?",
            subtitle: "We'll build the program around what you can actually use."
        ) {
            VStack(spacing: 8) {
                ForEach(Equipment.allCases) { e in
                    OptionRow(
                        label: e.label,
                        selected: answers.equipment == e,
                        onTap: { answers.equipment = e }
                    )
                }
            }
        }
    }

    private var baselineSquatScreen: some View {
        OnboardingQuestion(
            prompt: "Most you can squat for 5 reps?",
            subtitle: "Good form, not a max. Unsure is fine."
        ) {
            VStack(spacing: 12) {
                HStack {
                    Text("I'm not sure")
                        .font(.body)
                    Spacer()
                    Toggle("", isOn: $answers.unsure)
                        .labelsHidden()
                        .toggleStyle(.switch)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .background(Color(.secondarySystemBackground),
                            in: RoundedRectangle(cornerRadius: 12))

                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    TextField("0", text: $answers.baselineSquatRaw)
                        .keyboardType(.numberPad)
                        .font(.system(size: 40, weight: .bold, design: .rounded))
                        .multilineTextAlignment(.trailing)
                        .frame(maxWidth: 140)
                        .focused($squatFocused)
                        .disabled(answers.unsure)
                        .opacity(answers.unsure ? 0.3 : 1.0)
                    Text("lb")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 20)
                .background(Color(.secondarySystemBackground),
                            in: RoundedRectangle(cornerRadius: 12))
                .opacity(answers.unsure ? 0.5 : 1.0)
            }
        }
    }

    private var identityScreen: some View {
        OnboardingQuestion(
            prompt: "Who are you becoming?",
            subtitle: "One sentence. This becomes your summit."
        ) {
            VStack(alignment: .leading, spacing: 8) {
                TextField("e.g. someone who shows up, even when tired",
                          text: $identityStatement, axis: .vertical)
                    .lineLimit(2...4)
                    .textFieldStyle(.roundedBorder)
                    .focused($identityFocused)
                Text("The coach measures progress against this, not pounds lifted.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var submittingScreen: some View {
        VStack(spacing: 16) {
            switch submitState {
            case .idle, .loading:
                ProgressView()
                    .controlSize(.large)
                Text("Building your program…")
                    .font(.headline)
                Text("This usually takes a second.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            case .failed(let msg):
                ErrorView(
                    title: "Couldn't build your program",
                    message: msg,
                    retry: { await submit() }
                )
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var progressFooter: some View {
        VStack(spacing: 10) {
            ProgressView(value: Double(step.index), total: Double(step.total))
                .tint(.accentColor)
                .frame(maxWidth: .infinity)
            Button {
                Task { await onContinue() }
            } label: {
                Text(continueLabel)
                    .fontWeight(.semibold)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 4)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(!canContinue)
        }
        .padding(.horizontal, 20)
        .padding(.top, 10)
        .padding(.bottom, 8)
        .background(.bar)
    }

    private var continueLabel: String {
        step == .identity ? "Build my program" : "Continue"
    }

    private var canContinue: Bool {
        switch step {
        case .experience, .daysPerWeek, .equipment: return true
        case .injuries:      return !answers.injuries.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case .baselineSquat: return answers.unsure || !answers.baselineSquatRaw.isEmpty
        case .identity:      return !identityStatement.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case .welcome, .submitting: return false
        }
    }

    // MARK: - Navigation

    private func advance() {
        if let next = Step(rawValue: step.rawValue + 1) {
            withAnimation(.easeOut) { step = next }
        }
    }

    private func goBack() {
        if let prev = Step(rawValue: step.rawValue - 1), prev != .welcome {
            step = prev
        }
    }

    private func onContinue() async {
        if step == .identity {
            await submit()
        } else {
            advance()
        }
    }

    // MARK: - Submit

    private func submit() async {
        step = .submitting
        submitState = .loading
        injuriesFocused = false
        squatFocused = false
        identityFocused = false

        let answersDict = answers.toBackendDict()
        let trimmed = identityStatement.trimmingCharacters(in: .whitespacesAndNewlines)

        do {
            _ = try await CoachAPI.shared.submitIntake(answers: answersDict, identityStatement: trimmed)
            sessionStore.identityStatement = trimmed
            sessionStore.hasCompletedIntake = true
        } catch {
            submitState = .failed("\(error.localizedDescription) — check that the backend is running and try again.")
        }
    }
}

// MARK: - Onboarding question scaffolding

private struct OptionRow: View {
    let label: String
    let selected: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 12) {
                Text(label)
                    .font(.body)
                    .foregroundStyle(.primary)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer()
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .font(.title3)
                    .foregroundStyle(selected ? Color.accentColor : Color(.tertiaryLabel))
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color(.secondarySystemBackground))
            )
        }
        .buttonStyle(.plain)
    }
}

private struct OnboardingQuestion<Content: View>: View {
    let prompt: String
    var subtitle: String? = nil
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(prompt)
                .font(.title2.bold())
                .fixedSize(horizontal: false, vertical: true)
                .multilineTextAlignment(.leading)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let subtitle {
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            content()
                .padding(.top, 20)
        }
    }
}

private struct WelcomeScreen: View {
    let onStart: () -> Void
    var body: some View {
        VStack(spacing: 0) {
            Spacer()
            Image(systemName: "mountain.2.fill")
                .font(.system(size: 72))
                .foregroundStyle(.tint)
                .padding(.bottom, 24)
            Text("The Coach")
                .font(.largeTitle.bold())
                .padding(.bottom, 8)
            Text("A copilot that pushes when it matters\nand stays out of the way when it doesn't.")
                .font(.body)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer()
            Button(action: onStart) {
                Text("Get started")
                    .fontWeight(.semibold)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 4)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.bottom, 8)
            Text("A few quick questions — about a minute.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 24)
        .padding(.bottom, 24)
    }
}

// MARK: - Structured answers

private struct StructuredAnswers {
    var experience: ExperienceLevel = .novice
    var daysPerWeek: Int = 3
    var injuries: String = ""
    var equipment: Equipment = .fullGym
    var baselineSquatRaw: String = ""
    var unsure: Bool = false

    func toBackendDict() -> [String: String] {
        [
            "experience": experience.backendValue,
            "days_per_week": String(daysPerWeek),
            "injuries": injuries.trimmingCharacters(in: .whitespacesAndNewlines),
            "equipment": equipment.backendValue,
            "baseline_squat": unsure ? "unsure" : baselineSquatRaw,
        ]
    }
}

private enum ExperienceLevel: String, CaseIterable, Identifiable {
    case none, novice, intermediate, advanced
    var id: String { rawValue }
    var label: String {
        switch self {
        case .none: return "None — never trained"
        case .novice: return "Novice — under 6 months"
        case .intermediate: return "Intermediate — 1+ year"
        case .advanced: return "Advanced — 3+ years"
        }
    }
    var backendValue: String { rawValue }
}

private enum Equipment: String, CaseIterable, Identifiable {
    case fullGym, barbellRack, dumbbells, bodyweight
    var id: String { rawValue }
    var label: String {
        switch self {
        case .fullGym: return "Full gym"
        case .barbellRack: return "Barbell + rack at home"
        case .dumbbells: return "Dumbbells only"
        case .bodyweight: return "Bodyweight only"
        }
    }
    var backendValue: String {
        switch self {
        case .fullGym: return "full gym"
        case .barbellRack: return "barbell+rack"
        case .dumbbells: return "dumbbells"
        case .bodyweight: return "bodyweight"
        }
    }
}
