// "Train" tab — the in-app path that closes the coaching loop without APNs.
//
// Without this view, a fresh user who finishes intake lands on a blank Summit
// with no way to act. The brain has already prescribed a session
// (`prepare_next_action`); this tab surfaces it and lets the user log the
// outcome, which feeds the same REPORT → ADAPT path a nudge reply would.
//
// Rubric C1 ("useful without opening") still rests on APNs. This tab is the
// in-app fallback so the loop is end-to-end exercisable.

import SwiftUI

struct TrainView: View {
    @StateObject private var model = TrainViewModel()
    @StateObject private var sessionStore = ActiveSessionStore.shared
    /// Gym Radar (Feature 2) — observed so the "At the gym now" badge updates
    /// live when the geofence fires.
    @ObservedObject private var location = LocationManager.shared
    /// Navigation destination — set when the user taps Start/Resume so the
    /// NavigationStack pushes ActiveSessionView. Optional<NextSession> is the
    /// value driving navigationDestination(item:).
    @State private var pushedSession: NextSession?
    @State private var lastResult: LogSessionResult?
    @State private var autologResult: AutologResult?
    @State private var showingFeedback = false

    var body: some View {
        NavigationStack {
            ZStack {
                AtmosphericBackground()
                Group {
                    switch model.state {
                    case .loading:
                        ProgressView().controlSize(.large).tint(Theme.ember)
                    case .ready(let next):
                        ScrollView {
                            SessionContent(
                                next: next,
                                lastResult: lastResult,
                                autologResult: autologResult,
                                atGym: location.atGym,
                                gymCoachLine: location.lastCoachLine,
                                detectedWorkout: model.detectedWorkout,
                                autologging: model.autologging,
                                hasResumableSession: sessionStore.current(for: next.actionId) != nil,
                                onSchedule: { Task { await model.schedule(actionId: next.actionId) } },
                                onStart: {
                                    // Teach the brain where we train (Feature 2).
                                    location.observeTrainingLocation()
                                    pushedSession = next
                                },
                                onLogMinimum: {
                                    Task {
                                        let result = await model.logMinimumDose(next: next)
                                        lastResult = result
                                        await model.refresh()
                                    }
                                },
                                onAutolog: { workout in
                                    Task {
                                        autologResult = await model.autolog(actionId: next.actionId, workout: workout)
                                    }
                                }
                            )
                            .padding(.horizontal, 18)
                        }
                        .scrollContentBackground(.hidden)
                        .contentMargins(.bottom, 100, for: .scrollContent)
                        .refreshable { await model.refresh() }
                    case .empty(let message):
                        EmptyStateCard(
                            icon: "dumbbell.fill",
                            title: "Nothing prescribed yet",
                            message: message
                        )
                        .padding(.horizontal, 18)
                    case .failed(let msg):
                        ErrorView(title: "Couldn't load your session",
                                  message: msg,
                                  retry: { await model.refresh() })
                    }
                }
            }
            .navigationTitle("Train")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        showingFeedback = true
                    } label: {
                        Image(systemName: "quote.bubble")
                            .foregroundStyle(.white.opacity(0.85))
                    }
                    .accessibilityLabel("Talk to your coach")
                }
            }
            .task { await model.refresh() }
            .navigationDestination(item: $pushedSession) { next in
                ActiveSessionView(next: next) { result in
                    lastResult = result
                    await model.refresh()
                }
            }
            .sheet(isPresented: $showingFeedback) {
                CoachFeedbackSheet(onSubmitted: {
                    Task { await model.refresh() }
                })
                .presentationDetents([.large])
            }
        }
    }
}

private struct EmptyStateCard: View {
    let icon: String
    let title: String
    let message: String

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: icon)
                .font(.system(size: 56))
                .foregroundStyle(Theme.emberGradient)
                .shadow(color: Theme.ember.opacity(0.5), radius: 16)
            Text(title)
                .font(.title3.weight(.semibold))
                .foregroundStyle(.white)
            Text(message)
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.6))
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(28)
        .frame(maxWidth: .infinity)
        .glassCard()
    }
}

// MARK: - View model

@MainActor
final class TrainViewModel: ObservableObject {
    enum State {
        case loading
        case ready(NextSession)
        case empty(String)
        case failed(String)
    }

    @Published var state: State = .loading
    /// Feature 3 — a HealthKit workout we detected that the user can one-tap
    /// auto-log. Nil when there's nothing fresh to offer.
    @Published var detectedWorkout: DetectedWorkout?
    /// Set while an auto-log round-trip is in flight (drives the card spinner).
    @Published var autologging = false

    /// Observer for cross-VM refresh signals. Without this, the Train tab
    /// stays stuck on whatever state was set when the view first appeared
    /// (e.g. .empty before intake) and doesn't refresh after a dev-seed,
    /// a log, or anything else that mutates server state from elsewhere
    /// in the app.
    private var observer: NSObjectProtocol?
    private var workoutObserver: NSObjectProtocol?

    init() {
        observer = NotificationCenter.default.addObserver(
            forName: .coachStateChanged,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor [weak self] in await self?.refresh() }
        }
        #if canImport(HealthKit)
        workoutObserver = NotificationCenter.default.addObserver(
            forName: HealthKitService.workoutDetected,
            object: nil,
            queue: .main
        ) { [weak self] note in
            let workout = note.userInfo?["workout"] as? DetectedWorkout
            Task { @MainActor [weak self] in self?.detectedWorkout = workout }
        }
        #endif
    }

    deinit {
        if let observer { NotificationCenter.default.removeObserver(observer) }
        if let workoutObserver { NotificationCenter.default.removeObserver(workoutObserver) }
    }

    /// Feature 3 — log the prescribed session from the detected HealthKit
    /// workout. The backend records a SENSOR verification (the strongest kind)
    /// enriched with the real duration / calories / heart rate.
    func autolog(actionId: String, workout: DetectedWorkout) async -> AutologResult? {
        autologging = true
        defer { autologging = false }
        let result = try? await CoachAPI.shared.autolog(actionId: actionId, workout: workout)
        detectedWorkout = nil
        await refresh()
        return result
    }

    func refresh() async {
        state = .loading
        do {
            let next = try await CoachAPI.shared.nextSession()
            state = .ready(next)
        } catch let urlError as URLError {
            state = .failed(urlError.localizedDescription)
        } catch {
            // 409 from backend = no program yet (intake incomplete);
            // fall through to a friendly empty state.
            state = .empty("Finish intake and the coach will prescribe your first session.")
        }
    }

    /// 2-minute-rule fallback (Atomic Habits ch.13). Bad day → "I showed up
    /// at all" still counts as a vote. We synthesize a `done` outcome for
    /// every prescribed exercise so the server rolls up to `done`, and
    /// label the session note so the coach sees what happened.
    func logMinimumDose(next: NextSession) async -> LogSessionResult? {
        let exercises = Dictionary(uniqueKeysWithValues:
            next.session.exercises.map { ex in
                (ex.name, CoachAPI.ExerciseLogPayload(
                    outcome: .done,
                    calibrationSlot: ex.calibrationSlot
                ))
            }
        )
        return try? await CoachAPI.shared.logSession(
            actionId: next.actionId,
            friction: "minimum dose — 2-min rule",
            exercises: exercises
        )
    }

    func schedule(actionId: String) async {
        _ = try? await CoachAPI.shared.scheduleSession(actionId: actionId)
        await refresh()
    }
}

// MARK: - Session content

private struct SessionContent: View {
    let next: NextSession
    let lastResult: LogSessionResult?
    let autologResult: AutologResult?
    /// Gym Radar (Feature 2).
    let atGym: Bool
    let gymCoachLine: String?
    /// Workout auto-log (Feature 3).
    let detectedWorkout: DetectedWorkout?
    let autologging: Bool
    /// True when ActiveSessionStore has an in-progress workout matching this
    /// prescription — drives the "Resume workout" CTA over "Start workout".
    let hasResumableSession: Bool
    let onSchedule: () -> Void
    let onStart: () -> Void
    let onLogMinimum: () -> Void
    let onAutolog: (DetectedWorkout) -> Void

    /// Entry-screen rule: shape only, never details. The lifter sees the
    /// session name, what it costs (time, exercise count), and the script.
    /// Per-exercise prescription numbers + swap + progression rule belong
    /// inside the workout, not on the "tap to start" surface.
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if let result = autologResult, !result.ripples.isEmpty {
                RipplesBanner(ripples: result.ripples, adaptation: result.adaptation)
            } else if let result = lastResult, !result.ripples.isEmpty {
                RipplesBanner(ripples: result.ripples, adaptation: result.adaptation)
            }

            // Feature 2 — "you're at the gym" badge, when the geofence says so.
            if atGym {
                GymRadarBadge(coachLine: gymCoachLine)
            }

            // Feature 3 — Apple Health saw a workout; offer one-tap auto-log.
            if let workout = detectedWorkout {
                DetectedWorkoutCard(workout: workout, busy: autologging,
                                    onAutolog: { onAutolog(workout) })
            }

            // Feature 1 — readiness banner: how the coach is shaping today.
            if let readiness = next.readiness {
                ReadinessBanner(readiness: readiness)
            }

            if next.isFallback == true, let goal = next.goal {
                FallbackBanner(requestedGoal: goal)
            }

            if next.isCalibration {
                CalibrationBanner(
                    index: next.calibrationIndex ?? 0,
                    length: next.calibrationLength ?? 5
                )
            }

            ImplementationIntentionCard(
                cue: next.cue,
                location: next.location,
                sessionName: next.session.name
            )

            SessionHeader(session: next.session, prescribedFor: next.prescribedFor)

            VStack(spacing: 12) {
                Button(action: onStart) {
                    Label(
                        hasResumableSession ? "Resume workout" : "Start workout",
                        systemImage: hasResumableSession ? "play.circle.fill" : "flame.fill"
                    )
                }
                .buttonStyle(EmberButtonStyle())

                Button(action: onSchedule) {
                    Label(next.prescribedFor == nil ? "Schedule on calendar"
                                                    : "Reschedule on calendar",
                          systemImage: "calendar.badge.plus")
                }
                .buttonStyle(GhostButtonStyle())
            }
            .padding(.top, 4)

            if let dose = next.minimumDose, !dose.isEmpty {
                MinimumDoseCard(dose: dose, onLogMinimum: onLogMinimum)
            }
        }
        .padding(.vertical, 16)
    }
}

private struct SessionHeader: View {
    let session: PrescribedSession
    let prescribedFor: Date?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionEyebrow(text: "UP NEXT", icon: "flame.fill")
            Text(session.name)
                .font(.system(.largeTitle, design: .rounded, weight: .heavy))
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)
            if let summary = session.summary, !summary.isEmpty {
                Text(summary)
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.65))
                    .fixedSize(horizontal: false, vertical: true)
            }
            // Pills convey shape without details — "5 exercises · 45 min".
            // Per-set/load specifics live inside the workout, on purpose.
            HStack(spacing: 10) {
                metaPill(icon: "list.bullet",
                         text: "\(session.exercises.count) exercise\(session.exercises.count == 1 ? "" : "s")")
                metaPill(icon: "clock", text: "\(session.expectedMinutes) min")
                if let when = prescribedFor {
                    metaPill(icon: "calendar",
                             text: when.formatted(date: .omitted, time: .shortened))
                }
            }
        }
    }

    private func metaPill(icon: String, text: String) -> some View {
        Label(text, systemImage: icon)
            .font(.footnote.weight(.semibold))
            .foregroundStyle(.white.opacity(0.85))
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background {
                Capsule().fill(Color.white.opacity(0.08))
                    .overlay { Capsule().strokeBorder(Color.white.opacity(0.12), lineWidth: 1) }
            }
    }
}

/// "When CUE, I will TRAIN at LOCATION" — Atomic Habits ch.5.
/// Shown prominently because the script is the friction-reducer.
private struct ImplementationIntentionCard: View {
    let cue: String?
    let location: String?
    let sessionName: String

    var body: some View {
        let cueText = (cue?.isEmpty == false) ? cue! : "when the moment opens"
        let locText = (location?.isEmpty == false) ? location! : "wherever you train"
        VStack(alignment: .leading, spacing: 10) {
            SectionEyebrow(text: "THE SCRIPT", icon: "scroll.fill")
            Text("\(Text(cueText.capitalized + ", ").foregroundStyle(.white))\(Text("I will start ").foregroundStyle(.white.opacity(0.65)))\(Text(sessionName).fontWeight(.bold).foregroundStyle(Theme.gold))\(Text(" at ").foregroundStyle(.white.opacity(0.65)))\(Text(locText).foregroundStyle(.white))")
                .font(.system(.title3, design: .serif))
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCardTinted(Theme.ember)
    }
}

/// 2-minute-rule fallback (Atomic Habits ch.13). Showing up at all > nothing.
private struct MinimumDoseCard: View {
    let dose: String
    let onLogMinimum: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "bolt.heart.fill")
                    .foregroundStyle(Theme.amber)
                Text("Bad day?")
                    .font(.headline)
                    .foregroundStyle(.white)
            }
            Text(dose)
                .font(.body)
                .foregroundStyle(.white.opacity(0.85))
                .fixedSize(horizontal: false, vertical: true)
            Text("Two-minute rule. Showing up beats skipping — and it still counts as a vote.")
                .font(.caption)
                .foregroundStyle(.white.opacity(0.5))
                .fixedSize(horizontal: false, vertical: true)
            Button(action: onLogMinimum) {
                Label("I did the minimum", systemImage: "checkmark")
            }
            .buttonStyle(GhostButtonStyle())
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCardTinted(Theme.amber)
    }
}

private struct RipplesBanner: View {
    let ripples: [String]
    let adaptation: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label {
                Text("Logged").foregroundStyle(.white)
            } icon: {
                Image(systemName: "checkmark.seal.fill").foregroundStyle(Theme.emerald)
            }
            .font(.subheadline.weight(.bold))
            Text(ripples.joined(separator: "  ·  "))
                .font(.body)
                .foregroundStyle(.white.opacity(0.85))
                .fixedSize(horizontal: false, vertical: true)
            if let a = adaptation, !a.isEmpty {
                Text(a)
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.55))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCardTinted(Theme.emerald)
    }
}

// MARK: - Feature 1: Readiness banner

/// Shows this morning's HealthKit-derived readiness and how the coach is
/// shaping today's ask. The color + ring track the band so a wrecked night
/// reads as amber/rose at a glance, a primed morning as emerald.
private struct ReadinessBanner: View {
    let readiness: Readiness

    private var tint: Color {
        switch readiness.band {
        case "primed": return Theme.emerald
        case "ready":  return Theme.gold
        case "easy":   return Theme.amber
        case "rest":   return Theme.rose
        default:       return Theme.gold
        }
    }

    private var directiveLabel: String {
        switch readiness.directive {
        case "rest":    return "Recovery day"
        case "reduced": return "Dialed back"
        default:        return "Full session"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 14) {
                ReadinessRing(score: readiness.score, tint: tint)
                    .frame(width: 56, height: 56)
                VStack(alignment: .leading, spacing: 3) {
                    SectionEyebrow(text: "READINESS", icon: "heart.fill", tint: tint)
                    Text(directiveLabel)
                        .font(.headline)
                        .foregroundStyle(.white)
                    Text(readiness.band.capitalized)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(tint)
                }
                Spacer()
            }
            if let note = readiness.note, !note.isEmpty {
                Text(note)
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.8))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCardTinted(tint)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Readiness \(readiness.score), \(readiness.band). \(directiveLabel). \(readiness.note ?? "")")
    }
}

private struct ReadinessRing: View {
    let score: Int
    let tint: Color

    var body: some View {
        ZStack {
            Circle().stroke(Color.white.opacity(0.10), lineWidth: 6)
            Circle()
                .trim(from: 0, to: max(0.02, Double(score) / 100.0))
                .stroke(tint.gradient, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .shadow(color: tint.opacity(0.6), radius: 5)
            Text("\(score)")
                .font(.system(.headline, design: .rounded, weight: .heavy))
                .monospacedDigit()
                .foregroundStyle(.white)
        }
    }
}

// MARK: - Feature 2: Gym Radar badge

/// Appears when the learned geofence says the user is at the gym — the
/// "your phone knows where you train" moment. Tapping Start (above) is the
/// natural next action; this just confirms the coach noticed.
private struct GymRadarBadge: View {
    let coachLine: String?

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "location.fill")
                .font(.title3)
                .foregroundStyle(Theme.emerald)
                .shadow(color: Theme.emerald.opacity(0.6), radius: 6)
            VStack(alignment: .leading, spacing: 2) {
                Text("At the gym now")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.white)
                Text(coachLine ?? "Your session is loaded and ready.")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.7))
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCardTinted(Theme.emerald)
    }
}

// MARK: - Feature 3: Detected-workout auto-log card

/// Apple Health recorded a workout; offer to close the loop with one tap,
/// enriched with the real numbers off the watch.
private struct DetectedWorkoutCard: View {
    let workout: DetectedWorkout
    let busy: Bool
    let onAutolog: () -> Void

    private var metrics: [String] {
        var out: [String] = []
        if let m = workout.durationMin { out.append("\(Int(m.rounded())) min") }
        if let k = workout.activeKcal { out.append("\(Int(k.rounded())) kcal") }
        if let hr = workout.avgHr { out.append("avg HR \(Int(hr.rounded()))") }
        return out
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "applewatch")
                    .foregroundStyle(Theme.gold)
                Text("We saw your workout")
                    .font(.headline)
                    .foregroundStyle(.white)
            }
            if !metrics.isEmpty {
                Text(metrics.joined(separator: "  ·  "))
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(.white.opacity(0.85))
            }
            Text("Apple Health logged a session. Want me to count it? It'll log as done with the real numbers.")
                .font(.caption)
                .foregroundStyle(.white.opacity(0.6))
                .fixedSize(horizontal: false, vertical: true)
            Button(action: onAutolog) {
                HStack {
                    if busy { ProgressView().controlSize(.small).tint(.black) }
                    Text(busy ? "Logging…" : "Auto-log from Apple Health")
                }
            }
            .buttonStyle(EmberButtonStyle())
            .disabled(busy)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCardTinted(Theme.gold)
    }
}

// MARK: - Calibration banner (week 1 assessment)

/// Surfaces during the calibration phase so the user understands week 1 is
/// data collection, not the real program. The "N of 5" progress is the
/// thing that turns calibration from confusion ("why does this only have
/// one exercise?") into anticipation ("two more and the real plan starts").
private struct CalibrationBanner: View {
    let index: Int
    let length: Int

    private var sessionsLeft: Int { max(0, length - index) }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "target")
                    .font(.headline)
                    .foregroundStyle(Theme.gold)
                Text("Week 1 — calibration")
                    .font(.headline)
                    .foregroundStyle(.white)
                Spacer()
                Text("Session \(index + 1) of \(length)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white.opacity(0.7))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background {
                        Capsule().fill(Color.white.opacity(0.10))
                            .overlay { Capsule().strokeBorder(Color.white.opacity(0.15), lineWidth: 1) }
                    }
            }
            Text("Five short sessions to learn where you are. \(sessionsLeft > 0 ? "\(sessionsLeft) to go." : "Last one — the real program starts next.") No grinding, no hero sets.")
                .font(.footnote)
                .foregroundStyle(.white.opacity(0.75))
                .fixedSize(horizontal: false, vertical: true)
            ProgressView(value: Double(index), total: Double(length))
                .tint(Theme.gold)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCardTinted(Theme.gold)
    }
}

// MARK: - Fallback banner (when user's goal isn't fully implemented yet)

/// Honest message: tells the user their picked goal doesn't have a real
/// template shipped yet, and they're on the strength template until it does.
/// Beats the alternative of silently giving them the wrong program.
private struct FallbackBanner: View {
    let requestedGoal: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label {
                Text("Heads up").foregroundStyle(.white)
            } icon: {
                Image(systemName: "info.circle.fill")
                    .foregroundStyle(Theme.amber)
            }
            .font(.subheadline.weight(.bold))
            Text("Your \(goalDisplayName) program isn't built yet. You're on the strength template until it ships.")
                .font(.footnote)
                .foregroundStyle(.white.opacity(0.75))
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCardTinted(Theme.amber)
    }

    private var goalDisplayName: String {
        // All five canonical goals (get_stronger, build_muscle, lose_weight,
        // age_well, discipline) now have real templates and won't surface here.
        // Anything that lands here is an unknown/custom goal — rare path.
        return "custom"
    }
}

