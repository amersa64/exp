// In-progress workout state — what the user is doing RIGHT NOW.
//
// This is the substrate for the multi-screen workout flow (Strong / Hevy
// pattern): entry → in-progress session → per-exercise loggers. The user
// can pop out of the app mid-set; we persist this to UserDefaults so a
// resume restores the exact set/rep history they were partway through.
//
// Keyed by `actionId` so it ties back to the prescribed session the brain
// handed us. If the brain prescribes a different action (calibration ticks
// forward, persona regenerates), `ActiveSessionStore.current(for:)` returns
// nil and the Train tab shows "Start" instead of "Resume" — no stale state.

import Foundation
import Combine
import UIKit  // UINotificationFeedbackGenerator for the rest-timer chime

// MARK: - Codable wire / persistence types

/// One completed set the user logged. Reps required; load nil for bodyweight.
struct SetLog: Codable, Identifiable, Equatable {
    var id: UUID = UUID()
    var reps: Int?
    var loadLb: Double?
    var completed: Bool = false

    /// True when the user has filled in reps AND tapped the check — the only
    /// state that should fire a rest-timer countdown.
    var isLogged: Bool { completed && (reps ?? 0) > 0 }
}

/// Per-exercise rollup the user is building up inside the active session.
struct ExerciseState: Codable, Equatable {
    var outcome: NudgeOutcome = .done
    var sets: [SetLog] = []
    var note: String = ""
    /// User-set override for the rest-period countdown on this exercise.
    /// When nil, the prescription's `restSeconds` is used. Persisted so
    /// "I always rest 2:30 on squats" sticks across backgrounding.
    var restSecondsOverride: Int? = nil

    /// Used by the active-session list to color rows and to compute the
    /// session rollup at finish time. Mirrors the backend rule: any logged
    /// set counts as "in progress"; outcome stays at the user's choice.
    var hasLoggedSet: Bool { sets.contains(where: { $0.isLogged }) }

    enum CodingKeys: String, CodingKey {
        case outcome, sets, note, restSecondsOverride
    }

    init(outcome: NudgeOutcome = .done,
         sets: [SetLog] = [],
         note: String = "",
         restSecondsOverride: Int? = nil) {
        self.outcome = outcome
        self.sets = sets
        self.note = note
        self.restSecondsOverride = restSecondsOverride
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        outcome = try c.decode(NudgeOutcome.self, forKey: .outcome)
        sets = try c.decode([SetLog].self, forKey: .sets)
        note = try c.decode(String.self, forKey: .note)
        // Optional decode — sessions persisted before this field existed
        // don't carry the key. Same backward-compat pattern as World.
        restSecondsOverride = try? c.decode(Int.self, forKey: .restSecondsOverride)
    }
}

/// The in-progress workout itself. `actionId` pins this to the prescribed
/// session — if /session/next returns a different one, we discard.
struct ActiveSession: Codable, Equatable {
    let actionId: String
    let sessionName: String
    let startedAt: Date
    /// Exercise states keyed by *original* exercise name. After a swap, the
    /// state for the swapped exercise lives under the original name so the
    /// list position is stable — `swaps[originalName]` resolves to the new
    /// prescription for display.
    var exercises: [String: ExerciseState]

    /// Order the user sees in the active-session list — mirrors the order
    /// in the prescription, keyed by *original* names. Stored explicitly so
    /// dictionary key ordering doesn't shuffle the UI between launches.
    var exerciseOrder: [String]

    /// Per-workout exercise swaps, keyed by the original name. When set,
    /// the row + per-exercise screen render this replacement prescription
    /// instead of the brain's original. Cleared on workout finish/cancel.
    /// Defaults to empty so sessions persisted before this field existed
    /// still decode cleanly.
    var swaps: [String: ExercisePrescription] = [:]

    enum CodingKeys: String, CodingKey {
        case actionId, sessionName, startedAt, exercises, exerciseOrder, swaps
    }

    init(actionId: String, sessionName: String, startedAt: Date,
         exercises: [String: ExerciseState], exerciseOrder: [String],
         swaps: [String: ExercisePrescription] = [:]) {
        self.actionId = actionId
        self.sessionName = sessionName
        self.startedAt = startedAt
        self.exercises = exercises
        self.exerciseOrder = exerciseOrder
        self.swaps = swaps
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        actionId = try c.decode(String.self, forKey: .actionId)
        sessionName = try c.decode(String.self, forKey: .sessionName)
        startedAt = try c.decode(Date.self, forKey: .startedAt)
        exercises = try c.decode([String: ExerciseState].self, forKey: .exercises)
        exerciseOrder = try c.decode([String].self, forKey: .exerciseOrder)
        // Optional decode — older persisted sessions don't carry this key.
        swaps = (try? c.decode([String: ExercisePrescription].self, forKey: .swaps)) ?? [:]
    }

    /// Resolve the prescription for a given original exercise name: returns
    /// the swap if one was made, otherwise the original.
    func resolvedPrescription(for originalName: String,
                              base: [ExercisePrescription]) -> ExercisePrescription? {
        if let swapped = swaps[originalName] { return swapped }
        return base.first { $0.name == originalName }
    }
}

// MARK: - Local persistence

/// Thin wrapper around UserDefaults so the active workout survives an app
/// kill / background-past-the-OS-limit. Single-user v1 → single slot.
///
/// Why UserDefaults and not the keychain or SQLite: the data is small (a
/// few KB max), non-sensitive, and we want synchronous reads on view
/// appear. UserDefaults is exactly that.
@MainActor
final class ActiveSessionStore: ObservableObject {
    static let shared = ActiveSessionStore()

    private let key = "active_session_v1"
    private let defaults: UserDefaults

    @Published private(set) var current: ActiveSession?

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.current = Self.load(from: defaults, key: key)
    }

    // MARK: Reads

    /// Returns the stored session only if it matches the prescribed action.
    /// Anything else is stale — the brain has moved on, drop it silently.
    func current(for actionId: String) -> ActiveSession? {
        guard let s = current, s.actionId == actionId else { return nil }
        return s
    }

    // MARK: Writes

    /// Begin a workout for the prescribed session. Pre-creates one empty
    /// set row per *prescribed* set — so a 4×5 exercise shows 4 rows up
    /// front, ready to check off. The user can still tap "Add set" to
    /// log extras.
    func start(_ next: NextSession) -> ActiveSession {
        let order = next.session.exercises.map(\.name)
        let states = Dictionary(uniqueKeysWithValues:
            next.session.exercises.map { ex in
                (ex.name, ExerciseState(sets: Self.seedSets(count: ex.sets)))
            }
        )
        let session = ActiveSession(
            actionId: next.actionId,
            sessionName: next.session.name,
            startedAt: Date(),
            exercises: states,
            exerciseOrder: order
        )
        save(session)
        return session
    }

    /// Build N fresh, distinct SetLog rows. Using `.map` (not
    /// `Array(repeating:)`) is deliberate — `Array(repeating:)` would
    /// share the same SetLog instance N times, meaning every row would
    /// carry the *same* UUID and SwiftUI's ForEach would alias them.
    private static func seedSets(count: Int) -> [SetLog] {
        // At least one row even if the prescription says zero — a duration
        // exercise (cardio, plank) still wants a checkbox to log "done".
        let n = max(1, count)
        return (0..<n).map { _ in SetLog() }
    }

    /// Replace the state for one exercise (called whenever the
    /// ExerciseLogView's @State changes). Idempotent — no-op if no active
    /// session is loaded.
    func updateExercise(_ name: String, state: ExerciseState) {
        guard var s = current else { return }
        s.exercises[name] = state
        save(s)
    }

    /// Swap an exercise for an alternate. Resets the per-exercise state
    /// (different load/reps make the previously-logged sets meaningless)
    /// and persists the replacement prescription so the active-session
    /// list shows the new name on the same row. Seeds N empty rows from
    /// the replacement's prescription so the new exercise behaves the
    /// same as a fresh `start()`.
    func swap(originalName: String, with replacement: ExercisePrescription) {
        guard var s = current else { return }
        s.swaps[originalName] = replacement
        s.exercises[originalName] = ExerciseState(
            sets: Self.seedSets(count: replacement.sets)
        )
        save(s)
    }

    /// Clear the active session — call after a successful log POST or on
    /// explicit "Cancel workout". Also kills any running rest timer because
    /// resting between sets of a finished workout makes no sense.
    func clear() {
        defaults.removeObject(forKey: key)
        current = nil
        RestTimer.shared.stop()
    }

    // MARK: Plumbing

    private func save(_ session: ActiveSession) {
        guard let data = try? JSONEncoder().encode(session) else { return }
        defaults.set(data, forKey: key)
        current = session
    }

    private static func load(from defaults: UserDefaults, key: String) -> ActiveSession? {
        guard let data = defaults.data(forKey: key) else { return nil }
        return try? JSONDecoder().decode(ActiveSession.self, from: data)
    }
}

// MARK: - Wire payload conversion

extension ExerciseState {
    /// Convert to the backend payload. Empty / un-logged sets are dropped —
    /// the user added a row but never filled it in.
    func toPayload(calibrationSlot: String?) -> CoachAPI.ExerciseLogPayload {
        let logged = sets.filter { $0.isLogged }
        let setPayloads = logged.map { set in
            CoachAPI.SetPayload(reps: set.reps ?? 0, loadLb: set.loadLb)
        }
        // Top set: heaviest load, reps as tiebreaker. Bodyweight lifts use
        // reps alone. Lets the backend's calibration top_sets derivation
        // keep working without server-side re-derivation logic.
        let top = logged.max { a, b in
            (a.loadLb ?? 0, a.reps ?? 0) < (b.loadLb ?? 0, b.reps ?? 0)
        }
        return CoachAPI.ExerciseLogPayload(
            outcome: outcome,
            actualReps: top?.reps,
            actualLoadLb: top?.loadLb,
            actualSets: logged.isEmpty ? nil : logged.count,
            note: note.isEmpty ? nil : note,
            calibrationSlot: calibrationSlot,
            sets: setPayloads
        )
    }
}

// MARK: - Rest timer (shared across the active-session flow)

/// Workout-scoped rest-period countdown.
///
/// Singleton so that walking back from `ExerciseLogView` to
/// `ActiveSessionView` (or sideways into a different exercise) does NOT
/// stop the timer — the lifter is still resting, regardless of which screen
/// is on top. Both screens render the same banner observing this instance,
/// so the countdown is visible everywhere inside the workout.
///
/// Backgrounding the app pauses the wall-clock — Foundation Timers don't
/// fire when the app isn't foreground. That's the same compromise every
/// fitness app makes without a local-notification fallback; calling it
/// out so future-us doesn't think the bug is here.
@MainActor
final class RestTimer: ObservableObject {
    static let shared = RestTimer()

    @Published private(set) var secondsRemaining: Int = 0
    @Published private(set) var totalSeconds: Int = 0
    @Published private(set) var isRunning: Bool = false
    /// Set transiently when the timer hits zero on its own (vs Skip). UI can
    /// observe this to flash the banner / show a "ready" state. Cleared on
    /// the next `start()`.
    @Published private(set) var didJustComplete: Bool = false
    /// Exercise the timer was started from — lets the active-session list
    /// highlight the corresponding row. Nil when no rest is in progress.
    @Published private(set) var exerciseName: String?

    private var cancellable: AnyCancellable?

    var progress: CGFloat {
        guard totalSeconds > 0 else { return 0 }
        return CGFloat(secondsRemaining) / CGFloat(totalSeconds)
    }

    /// Begin a rest period from `seconds`. `exerciseName` is just metadata
    /// for the UI — the timer doesn't care which exercise you came from.
    func start(seconds: Int, exerciseName: String? = nil) {
        totalSeconds = seconds
        secondsRemaining = seconds
        isRunning = true
        didJustComplete = false
        self.exerciseName = exerciseName
        cancellable?.cancel()
        cancellable = Timer.publish(every: 1.0, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                guard let self else { return }
                if self.secondsRemaining <= 1 {
                    self.complete()
                } else {
                    self.secondsRemaining -= 1
                }
            }
    }

    /// User tapped "Skip" — silent stop, no haptic.
    func skip() { stop(natural: false) }

    /// Cleared because the workout ended / was cancelled. Also silent.
    func stop() { stop(natural: false) }

    /// Timer ran to zero on its own — fire the success haptic so the user
    /// knows rest is over without looking at the screen. This is the
    /// "between-set chime" every fitness app has.
    private func complete() {
        stop(natural: true)
    }

    private func stop(natural: Bool) {
        isRunning = false
        secondsRemaining = 0
        exerciseName = nil
        cancellable?.cancel()
        cancellable = nil
        if natural {
            didJustComplete = true
            let generator = UINotificationFeedbackGenerator()
            generator.notificationOccurred(.success)
            // Briefly hold `didJustComplete = true` so a banner that wants
            // to render a "ready" state has a window to do so. Half a
            // second is enough for SwiftUI's transition to start.
            Task { @MainActor [weak self] in
                try? await Task.sleep(nanoseconds: 1_500_000_000)
                self?.didJustComplete = false
            }
        }
    }
}
