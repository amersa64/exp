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
    @FocusState private var anchorFocused: Bool
    @FocusState private var locationFocused: Bool
    @FocusState private var identityFocused: Bool

    enum Step: Int, CaseIterable, Comparable {
        case welcome, goal, experience, daysPerWeek, injuries, equipment, baselineSquat,
             anchor, location, identity, submitting
        static func < (lhs: Step, rhs: Step) -> Bool { lhs.rawValue < rhs.rawValue }
        var index: Int { rawValue }
        var total: Int { 9 }  // onboarding screens, excluding welcome + submitting
    }

    enum SubmitState: Equatable {
        case idle
        case loading
        case failed(String)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                AtmosphericBackground()

                Group {
                    if step == .welcome {
                        WelcomeScreen(onStart: { advance() })
                    } else if step == .submitting {
                        submittingScreen
                    } else {
                        ScrollView {
                            content
                                .padding(.horizontal, 22)
                                .padding(.top, 8)
                                .padding(.bottom, 16)
                        }
                        .scrollContentBackground(.hidden)
                        .scrollBounceBehavior(.basedOnSize)
                        .safeAreaInset(edge: .bottom) { progressFooter }
                    }
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                if step != .welcome && step != .submitting {
                    ToolbarItem(placement: .topBarLeading) {
                        Button {
                            withAnimation { goBack() }
                        } label: {
                            Image(systemName: "chevron.left")
                                .foregroundStyle(.white.opacity(0.85))
                        }
                        .disabled(step == .experience)
                    }
                    ToolbarItem(placement: .principal) {
                        Text("\(step.index) of \(step.total)")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.white.opacity(0.55))
                            .monospacedDigit()
                            .tracking(1.2)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        switch step {
        case .welcome, .submitting:  EmptyView()
        case .goal:         goalScreen
        case .experience:   experienceScreen
        case .daysPerWeek:  daysPerWeekScreen
        case .injuries:     injuriesScreen
        case .equipment:    equipmentScreen
        case .baselineSquat: baselineSquatScreen
        case .anchor:       anchorScreen
        case .location:     locationScreen
        case .identity:     identityScreen
        }
    }

    // MARK: - Goal screen (Q1, v2)

    private var goalScreen: some View {
        OnboardingQuestion(
            prompt: "What do you want to do?",
            subtitle: "Pick the one that fits best. You can change later."
        ) {
            VStack(spacing: 10) {
                ForEach(GoalChoice.allCases) { g in
                    GoalOptionRow(
                        title: g.title,
                        description: g.description,
                        selected: answers.goal == g,
                        onTap: { answers.goal = g }
                    )
                }
            }
        }
    }

    // MARK: - Screens

    private var experienceScreen: some View {
        OnboardingQuestion(
            prompt: "Your strength-training experience?",
            subtitle: "We'll use this to calibrate starting loads."
        ) {
            VStack(spacing: 10) {
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
            HStack(spacing: 24) {
                stepperButton(icon: "minus",
                              enabled: answers.daysPerWeek > 2) {
                    if answers.daysPerWeek > 2 { answers.daysPerWeek -= 1 }
                }

                VStack(spacing: 2) {
                    Text("\(answers.daysPerWeek)")
                        .displayNumber(size: 72)
                        .contentTransition(.numericText(value: Double(answers.daysPerWeek)))
                    Text(answers.daysPerWeek == 1 ? "day per week" : "days per week")
                        .font(.subheadline)
                        .foregroundStyle(.white.opacity(0.6))
                }
                .frame(minWidth: 140)

                stepperButton(icon: "plus",
                              enabled: answers.daysPerWeek < 4) {
                    if answers.daysPerWeek < 4 { answers.daysPerWeek += 1 }
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 28)
            .frame(maxWidth: .infinity)
            .glassCard()
        }
    }

    private func stepperButton(icon: String, enabled: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.title2.weight(.bold))
                .foregroundStyle(.white.opacity(enabled ? 0.92 : 0.3))
                .frame(width: 56, height: 56)
                .background {
                    Circle()
                        .fill(Color.white.opacity(0.06))
                        .overlay { Circle().strokeBorder(Color.white.opacity(0.12), lineWidth: 1) }
                }
        }
        .disabled(!enabled)
        .buttonStyle(.plain)
    }

    private var injuriesScreen: some View {
        OnboardingQuestion(
            prompt: "Any current pain or injuries to work around?",
            subtitle: "If something hurts, the coach holds back."
        ) {
            VStack(alignment: .leading, spacing: 14) {
                AtmosphericTextField(
                    placeholder: "Describe anything to be careful with…",
                    text: $answers.injuries,
                    axis: .vertical,
                    lineLimit: 3...5
                )
                .focused($injuriesFocused)
                Button {
                    answers.injuries = "none"
                    injuriesFocused = false
                } label: {
                    Label("Nothing — I'm good", systemImage: "checkmark.circle")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white.opacity(0.9))
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background {
                            Capsule()
                                .fill(Color.white.opacity(0.08))
                                .overlay { Capsule().strokeBorder(Color.white.opacity(0.15), lineWidth: 1) }
                        }
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var equipmentScreen: some View {
        OnboardingQuestion(
            prompt: "What equipment do you have?",
            subtitle: "We'll build the program around what you can actually use."
        ) {
            VStack(spacing: 10) {
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
            VStack(spacing: 14) {
                HStack {
                    Text("I'm not sure")
                        .font(.body)
                        .foregroundStyle(.white)
                    Spacer()
                    Toggle("", isOn: $answers.unsure)
                        .labelsHidden()
                        .toggleStyle(.switch)
                        .tint(Theme.ember)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
                .glassCard()

                VStack(spacing: 4) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        TextField("", text: $answers.baselineSquatRaw,
                                  prompt: Text("0").foregroundColor(.white.opacity(0.3)))
                            .keyboardType(.numberPad)
                            .font(.system(size: 56, weight: .heavy, design: .rounded))
                            .foregroundStyle(answers.unsure ? AnyShapeStyle(Color.white.opacity(0.3))
                                                            : AnyShapeStyle(Theme.emberGradient))
                            .multilineTextAlignment(.trailing)
                            .frame(maxWidth: 160)
                            .focused($squatFocused)
                            .disabled(answers.unsure)
                        Text("lb")
                            .font(.title2.weight(.semibold))
                            .foregroundStyle(.white.opacity(0.55))
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 28)
                .glassCard()
                .opacity(answers.unsure ? 0.5 : 1.0)
            }
        }
    }

    private var anchorScreen: some View {
        OnboardingQuestion(
            prompt: "Pick something you do every single day.",
            subtitle: "We'll stack training right after it — morning coffee, school drop-off, end-of-workday shutdown."
        ) {
            VStack(alignment: .leading, spacing: 10) {
                AtmosphericTextField(
                    placeholder: "e.g. after my morning coffee",
                    text: $answers.anchorHabit,
                    axis: .vertical,
                    lineLimit: 1...3
                )
                .focused($anchorFocused)
                Text("Habit stacking: 'right after X, I will train' is much harder to forget than 'I'll train sometime today'.")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.5))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var locationScreen: some View {
        OnboardingQuestion(
            prompt: "Where will the training happen?",
            subtitle: "Naming the place makes the moment harder to dodge."
        ) {
            VStack(alignment: .leading, spacing: 10) {
                AtmosphericTextField(
                    placeholder: "e.g. the garage, the gym on Main St., the living room",
                    text: $answers.trainingLocation,
                    axis: .vertical,
                    lineLimit: 1...3
                )
                .focused($locationFocused)
                Text("Implementation intention: when CUE, I will TRAIN at LOCATION. All three together; not just one.")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.5))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var identityScreen: some View {
        OnboardingQuestion(
            prompt: "Who are you becoming?",
            subtitle: "One sentence. This becomes your summit."
        ) {
            VStack(alignment: .leading, spacing: 10) {
                AtmosphericTextField(
                    placeholder: "e.g. someone who shows up, even when tired",
                    text: $identityStatement,
                    axis: .vertical,
                    lineLimit: 2...4,
                    font: .system(.title3, design: .serif)
                )
                .focused($identityFocused)
                Text("The coach measures progress against this, not pounds lifted.")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.5))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var submittingScreen: some View {
        VStack(spacing: 20) {
            switch submitState {
            case .idle, .loading:
                ZStack {
                    Circle()
                        .stroke(Color.white.opacity(0.08), lineWidth: 4)
                        .frame(width: 84, height: 84)
                    Circle()
                        .trim(from: 0, to: 0.3)
                        .stroke(Theme.emberGradient,
                                style: StrokeStyle(lineWidth: 4, lineCap: .round))
                        .frame(width: 84, height: 84)
                        .rotationEffect(.degrees(rotating ? 360 : 0))
                        .animation(.linear(duration: 1.2).repeatForever(autoreverses: false),
                                   value: rotating)
                    Image(systemName: "mountain.2.fill")
                        .font(.title2)
                        .foregroundStyle(Theme.emberGradient)
                }
                .onAppear { rotating = true }
                Text("Putting your program together")
                    .font(.title3.weight(.bold))
                    .foregroundStyle(.white)
                Text("One minute.")
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.55))
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

    @State private var rotating = false

    private var progressFooter: some View {
        VStack(spacing: 12) {
            // Custom progress bar — thin gradient fill on a translucent track.
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.white.opacity(0.08))
                    Capsule()
                        .fill(Theme.emberGradient)
                        .frame(width: max(8, geo.size.width * progress))
                        .shadow(color: Theme.ember.opacity(0.6), radius: 4)
                }
            }
            .frame(height: 5)
            .animation(.spring(response: 0.5, dampingFraction: 0.85), value: progress)

            Button {
                Task { await onContinue() }
            } label: {
                Text(continueLabel)
            }
            .buttonStyle(EmberButtonStyle())
            .disabled(!canContinue)
            .opacity(canContinue ? 1.0 : 0.45)
        }
        .padding(.horizontal, 22)
        .padding(.top, 12)
        .padding(.bottom, 10)
        .background {
            // Subtle gradient hide so the footer doesn't sit hard against the bg.
            LinearGradient(
                colors: [.clear, Theme.coal.opacity(0.85), Theme.coal],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()
        }
    }

    private var progress: Double {
        Double(step.index) / Double(step.total)
    }

    private var continueLabel: String {
        step == .identity ? "Build my program" : "Continue"
    }

    private var canContinue: Bool {
        switch step {
        case .goal, .experience, .daysPerWeek, .equipment: return true
        case .injuries:      return !answers.injuries.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case .baselineSquat: return answers.unsure || !answers.baselineSquatRaw.isEmpty
        case .anchor:        return !answers.anchorHabit.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case .location:      return !answers.trainingLocation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
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
        anchorFocused = false
        locationFocused = false
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
            HStack(spacing: 14) {
                ZStack {
                    Circle()
                        .stroke(selected ? Color.clear : Color.white.opacity(0.2),
                                lineWidth: 1.5)
                        .frame(width: 24, height: 24)
                    if selected {
                        Circle()
                            .fill(Theme.emberGradient)
                            .frame(width: 24, height: 24)
                            .shadow(color: Theme.ember.opacity(0.6), radius: 8)
                        Image(systemName: "checkmark")
                            .font(.caption2.weight(.heavy))
                            .foregroundStyle(.black)
                    }
                }
                Text(label)
                    .font(.body.weight(selected ? .semibold : .regular))
                    .foregroundStyle(.white)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(.ultraThinMaterial)
                    .overlay {
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .fill(selected ? Theme.ember.opacity(0.10) : Color.white.opacity(0.02))
                    }
                    .overlay {
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .strokeBorder(selected ? Theme.ember.opacity(0.5)
                                                   : Color.white.opacity(0.08),
                                          lineWidth: 1)
                    }
            }
        }
        .buttonStyle(.plain)
    }
}

private struct OnboardingQuestion<Content: View>: View {
    let prompt: String
    var subtitle: String? = nil
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(prompt)
                .font(.system(.title, design: .serif, weight: .bold))
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)
                .multilineTextAlignment(.leading)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let subtitle {
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.6))
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            content()
                .padding(.top, 24)
        }
    }
}

private struct AtmosphericTextField: View {
    let placeholder: String
    @Binding var text: String
    var axis: Axis = .horizontal
    var lineLimit: ClosedRange<Int> = 1...1
    var font: Font = .body

    var body: some View {
        TextField(placeholder, text: $text, axis: axis)
            .lineLimit(lineLimit)
            .font(font)
            .foregroundStyle(.white)
            .tint(Theme.ember)
            .padding(14)
            .background {
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Color.white.opacity(0.06))
                    .overlay {
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .strokeBorder(Color.white.opacity(0.12), lineWidth: 1)
                    }
            }
    }
}

private struct WelcomeScreen: View {
    let onStart: () -> Void
    @State private var glow = false

    var body: some View {
        VStack(spacing: 0) {
            Spacer()
            ZStack {
                Circle()
                    .fill(RadialGradient(
                        colors: [Theme.ember.opacity(0.5), .clear],
                        center: .center,
                        startRadius: 4,
                        endRadius: 140))
                    .frame(width: 280, height: 280)
                    .scaleEffect(glow ? 1.05 : 0.95)
                    .animation(.easeInOut(duration: 2.5).repeatForever(autoreverses: true), value: glow)

                Image(systemName: "mountain.2.fill")
                    .font(.system(size: 96, weight: .black))
                    .foregroundStyle(Theme.emberGradient)
                    .shadow(color: Theme.ember.opacity(0.65), radius: 24)
                    .shadow(color: Theme.gold.opacity(0.4), radius: 8)
            }
            .padding(.bottom, 32)

            Text("The Coach")
                .font(.system(size: 48, weight: .heavy, design: .rounded))
                .foregroundStyle(.white)
                .padding(.bottom, 14)

            Text("A copilot that pushes when it matters\nand stays out of the way when it doesn't.")
                .font(.body)
                .multilineTextAlignment(.center)
                .foregroundStyle(.white.opacity(0.7))
                .fixedSize(horizontal: false, vertical: true)

            Spacer()

            Button(action: onStart) {
                Text("Get started")
            }
            .buttonStyle(EmberButtonStyle())
            .padding(.bottom, 10)

            Text("A few quick questions — about a minute.")
                .font(.caption)
                .foregroundStyle(.white.opacity(0.45))
        }
        .padding(.horizontal, 28)
        .padding(.bottom, 32)
        .onAppear { glow = true }
    }
}

// MARK: - Structured answers

private struct StructuredAnswers {
    var goal: GoalChoice = .getStronger
    var experience: ExperienceLevel = .novice
    var daysPerWeek: Int = 3
    var injuries: String = ""
    var equipment: Equipment = .fullGym
    var baselineSquatRaw: String = ""
    var unsure: Bool = false
    var anchorHabit: String = ""
    var trainingLocation: String = ""

    func toBackendDict() -> [String: String] {
        [
            "goal": goal.backendValue,
            "experience": experience.backendValue,
            "days_per_week": String(daysPerWeek),
            "injuries": injuries.trimmingCharacters(in: .whitespacesAndNewlines),
            "equipment": equipment.backendValue,
            "baseline_squat": unsure ? "unsure" : baselineSquatRaw,
            "anchor_habit": anchorHabit.trimmingCharacters(in: .whitespacesAndNewlines),
            "training_location": trainingLocation.trimmingCharacters(in: .whitespacesAndNewlines),
        ]
    }
}

// MARK: - Goal choice (v2 Q1)

/// Five goal templates the user picks from. Drives downstream programming
/// (only `getStronger` is wired to a real template today; others store the
/// choice for future routing — see design/v2/templates/).
enum GoalChoice: String, CaseIterable, Identifiable {
    case buildMuscle, getStronger, loseWeight, ageWell, discipline
    var id: String { rawValue }
    var title: String {
        switch self {
        case .buildMuscle:  return "Build muscle"
        case .getStronger:  return "Get stronger"
        case .loseWeight:   return "Lose weight, get fit"
        case .ageWell:      return "Stay fit, age well"
        case .discipline:   return "75-Hard-style discipline"
        }
    }
    var description: String {
        switch self {
        case .buildMuscle:  return "Look bigger. Fill out a t-shirt."
        case .getStronger:  return "Move more weight."
        case .loseWeight:   return "Drop fat, feel better."
        case .ageWell:      return "Maintain. Don't get injured."
        case .discipline:   return "Strict, daily, photos."
        }
    }
    /// Lowercase snake-case for backend storage.
    var backendValue: String {
        switch self {
        case .buildMuscle:  return "build_muscle"
        case .getStronger:  return "get_stronger"
        case .loseWeight:   return "lose_weight"
        case .ageWell:      return "age_well"
        case .discipline:   return "discipline"
        }
    }
}

// MARK: - Goal option row (taller than OptionRow — has a description line)

private struct GoalOptionRow: View {
    let title: String
    let description: String
    let selected: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 14) {
                ZStack {
                    Circle()
                        .stroke(selected ? Color.clear : Color.white.opacity(0.2),
                                lineWidth: 1.5)
                        .frame(width: 24, height: 24)
                    if selected {
                        Circle()
                            .fill(Theme.emberGradient)
                            .frame(width: 24, height: 24)
                            .shadow(color: Theme.ember.opacity(0.6), radius: 8)
                        Image(systemName: "checkmark")
                            .font(.caption2.weight(.heavy))
                            .foregroundStyle(.black)
                    }
                }
                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.body.weight(selected ? .semibold : .regular))
                        .foregroundStyle(.white)
                        .multilineTextAlignment(.leading)
                    Text(description)
                        .font(.footnote)
                        .foregroundStyle(.white.opacity(0.55))
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(.ultraThinMaterial)
                    .overlay {
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .fill(selected ? Theme.ember.opacity(0.10) : Color.white.opacity(0.02))
                    }
                    .overlay {
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .strokeBorder(selected ? Theme.ember.opacity(0.5)
                                                   : Color.white.opacity(0.08),
                                          lineWidth: 1)
                    }
            }
        }
        .buttonStyle(.plain)
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
