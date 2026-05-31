// Client-side mirror of the four-level hierarchy (Section 5).
// READ-ONLY DTOs. Mutating these from the client must never grow the world.

import Foundation

struct Identity: Codable, Identifiable {
    let id: String
    let statement: String
    let domain: String
}

struct Milestone: Codable, Identifiable {
    let id: String
    let title: String
    let description: String
    let achievedAt: Date?
}

struct Habit: Codable, Identifiable {
    let id: String
    let title: String
    let cadence: String
    let active: Bool
}

struct AtomicAction: Codable, Identifiable {
    let id: String
    let title: String
    let description: String
    let cue: String?
    let expectedMinutes: Int
    let prescribedFor: Date?
}

enum TrackingKind: String, Codable {
    case binary, count, duration, scale
}

/// Read-only reflection of the world (Section 6.3, Principle 2.6).
struct World: Codable {
    let theme: String
    let currency: Int
    let streakDays: Int
    let longestStreak: Int
    let unlocked: [String]
    let livingSystems: [String: Double]
    // Atomic Habits ch.2 — votes cast for the user's identity statement.
    // Defaults to 0 for older backends that don't return the field.
    var identityVotes: Int = 0

    enum CodingKeys: String, CodingKey {
        case theme, currency, streakDays, longestStreak, unlocked, livingSystems, identityVotes
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        theme = try c.decode(String.self, forKey: .theme)
        currency = try c.decode(Int.self, forKey: .currency)
        streakDays = try c.decode(Int.self, forKey: .streakDays)
        longestStreak = try c.decode(Int.self, forKey: .longestStreak)
        unlocked = try c.decode([String].self, forKey: .unlocked)
        livingSystems = try c.decode([String: Double].self, forKey: .livingSystems)
        identityVotes = (try? c.decode(Int.self, forKey: .identityVotes)) ?? 0
    }
}

enum NudgeOutcome: String, Codable {
    case done, partial, skipped, not_now, busy
}

struct ExercisePrescription: Codable, Hashable, Identifiable {
    let name: String
    let sets: Int
    let reps: Int
    let loadLb: Double?
    let restSeconds: Int
    let notes: String
    /// Optional. When set, this is a duration-based exercise (cardio / plank /
    /// carry). iOS renders the duration in place of "Nx{reps}".
    let durationMin: Int?
    /// When set, this exercise is a calibration probe for the named lift
    /// slot (e.g. "squat", "bench", "pullup"). The log sheet shows a "top
    /// clean set" input (reps + lb) for it, keyed by this slot.
    let calibrationSlot: String?

    var id: String { name }
}

struct PrescribedSession: Codable, Hashable {
    let name: String
    let summary: String?
    let expectedMinutes: Int
    let progressionRule: String
    let exercises: [ExercisePrescription]
}

/// Conforms to `Hashable` so it can drive `NavigationStack`'s
/// `navigationDestination(item:)` — the Train tab pushes the active workout
/// screen by setting an optional NextSession to non-nil.
struct NextSession: Codable, Hashable {
    let actionId: String
    let actionTitle: String
    let prescribedFor: Date?
    let expectedMinutes: Int
    let cue: String?
    let location: String?
    let minimumDose: String?
    /// The goal the user picked during intake (e.g. "lose_weight").
    /// Used by the iOS app to render a fallback banner when the user's
    /// requested template isn't shipped yet.
    let goal: String?
    /// True when the user's goal didn't have a real template and they were
    /// routed to the strength template as a fallback.
    let isFallback: Bool?
    /// Program phase — "calibration" during week 1 assessment, "active"
    /// once we know the user's numbers and have prescribed the real program.
    /// Older backends omit this field; default to "active" on the client
    /// so the calibration banner stays hidden for legacy responses.
    let phase: String?
    /// Calibration progress — how many calibration sessions logged so far,
    /// out of the total expected. Drives the "Session 3 of 5" indicator.
    let calibrationIndex: Int?
    let calibrationLength: Int?
    /// Once the program transitions to active phase, the persona picks the
    /// user's weakest lift as the emphasis slot (extra volume for 4 weeks).
    let emphasisSlot: String?
    /// Feature 1 — this morning's readiness, present only when the user posted
    /// HealthKit recovery signals today. Nil → train as planned, no banner.
    let readiness: Readiness?
    let session: PrescribedSession

    var isCalibration: Bool { (phase ?? "active") == "calibration" }
}

/// The Readiness Engine's verdict for today (Feature 1). `directive` ∈
/// {full, reduced, rest} tells the UI how the coach is shaping the ask.
struct Readiness: Codable, Hashable {
    let score: Int
    let band: String          // rest | easy | ready | primed
    let directive: String     // full | reduced | rest
    let note: String?
    let sleepHours: Double?
    let restingHr: Double?
    let hrvMs: Double?
}

// MARK: - iPhone signal inputs + results (Section 8.1)

/// The recovery numbers the client reads off HealthKit and posts each morning.
struct ReadinessInput {
    var sleepHours: Double?
    var restingHr: Double?
    var hrvMs: Double?
    var restingHrBaseline: Double?
    var hrvBaseline: Double?
}

struct ReadinessResult: Codable {
    let ok: Bool
    let score: Int
    let band: String
    let directive: String
    let note: String?
}

/// The learned training geofence (Feature 2). `monitorable` gates whether the
/// client should actually start region-monitoring.
struct LearnedPlace: Codable {
    let lat: Double?
    let lon: Double?
    let radiusM: Double?
    let label: String?
    let confidence: Double?
    let monitorable: Bool
}

struct LocationEventResult: Codable {
    let ok: Bool?
    let surfaceSession: Bool
    let coachLine: String?
}

/// A HealthKit workout the app detected (Feature 3).
struct DetectedWorkout {
    var durationMin: Double?
    var activeKcal: Double?
    var avgHr: Double?
    var workoutType: String?
    var endedAt: Date?
}

struct AutologResult: Codable {
    let ok: Bool
    let ripples: [String]
    let adaptation: String?
    let outcome: String
    let coachResponse: String?
}

// MARK: - Broad vitals ingestion + dashboard

/// One HealthKit reading the client posts. `metric` is a canonical backend key
/// (coach.vitals.METRICS); `at` defaults to now server-side when nil.
struct VitalSampleInput {
    let metric: String
    let value: Double
    let unit: String
    let at: Date?
}

/// The Vitals dashboard payload — per-metric trend summaries + insights.
struct VitalsSummary: Codable {
    let metrics: [VitalMetricSummary]
    let insights: [VitalsInsight]
}

struct VitalMetricSummary: Codable, Identifiable {
    let metric: String
    let label: String
    let unit: String
    let tier: String           // body | sleep | core | optional
    let current: Double
    let n: Int
    let change: Double
    let slopePerWeek: Double?
    let directionGood: Bool?   // nil = neutral / no change
    let firstAt: String?
    let lastAt: String?

    var id: String { metric }
}

struct VitalsInsight: Codable, Identifiable {
    let kind: String           // weight_trajectory | relative_strength
    let title: String
    let detail: String
    let direction: String?     // up | down

    var id: String { kind + title }
}

struct VitalsSeries: Codable {
    let metric: String
    let label: String
    let unit: String
    let points: [VitalPoint]
}

struct VitalPoint: Codable {
    let at: Date
    let value: Double
}

// NOTE: the backend's /session/next response also includes a
// `calibration_results` dict — full benchmark verdicts per lift slot,
// used by the Becoming-tab summary card. iOS doesn't decode it yet
// (Codable ignores unknown JSON keys), and a typed model that survives
// the `1rm` field is fiddly under `.convertFromSnakeCase`. Will revisit
// when the summary card lands.

// MARK: - Exercise swap

/// Returned by GET /exercises/alternates — 3 viable alternates for the user's
/// equipment, all matching the original's primary muscle + movement pattern.
struct ExerciseAlternatesResponse: Codable {
    let original: String
    let alternates: [ExerciseAlternate]
}

struct ExerciseAlternate: Codable, Identifiable {
    let name: String
    let primaryMuscles: [String]
    let equipment: String?
    let level: String?
    let firstInstruction: String?

    var id: String { name }
}

/// Returned by POST /exercise/swap — the adaptive-coach response to a
/// free-form swap request. `replacement` is the coach's top pick (a catalog
/// name), `alternatives` are other viable choices, `coachResponse` is the
/// human-voice reply, `applied` is whether the live program was patched.
struct ExerciseSwapResult: Codable {
    let ok: Bool
    let replacement: String?
    let alternatives: [String]
    let coachResponse: String
    let constraint: String
    let applied: Bool
}

/// Returned by POST /program/feedback — coach's response to whole-program
/// feedback, plus whether it triggered a regeneration.
struct ProgramFeedbackResult: Codable {
    let ok: Bool
    let coachResponse: String
    let changeSummary: String
    let constraint: String
    let regenerated: Bool
}

/// One remembered decision — the coach's memory of a change the user asked
/// for. Returned by GET /adjustments.
struct ProgramAdjustment: Codable, Identifiable {
    let id: String
    let at: String
    let scope: String                  // "exercise" | "program"
    let userNote: String
    let targetExercise: String?
    let replacementExercise: String?
    let constraint: String
    let coachResponse: String
    let active: Bool
}

struct AdjustmentsResponse: Codable {
    let adjustments: [ProgramAdjustment]
}

/// Returned by GET /exercise?name=... — the visual + instructional payload
/// the ExerciseDetailSheet needs to teach the lift. Images are absolute URLs
/// to free-exercise-db on GitHub's raw CDN (vendored metadata only, not bytes).
struct ExerciseDetail: Codable {
    let name: String
    let instructions: [String]
    let primaryMuscles: [String]
    let secondaryMuscles: [String]
    let equipment: String?
    let level: String?
    let mechanic: String?
    let category: String?
    let imageUrls: [URL]
}

/// Snapshot of what the brain is currently thinking — dev pane + status.
struct CoachState: Codable {
    let hasProfile: Bool
    let hasProgram: Bool
    let identityStatement: String?
    let identityAnchor: String?
    let programName: String?
    let sessionIndex: Int
    let lastNudge: NudgeSnapshot?
    let openFollowups: [FollowupSnapshot]
    /// Most recent surface-worthy observation from the coach's journal —
    /// drives the "From your coach" card on Today. May be nil.
    let latestObservation: JournalEntrySnapshot?
    /// Most recent journal entry of any kind — for the debug pane.
    let latestJournalEntry: JournalEntrySnapshot?
}

/// One entry from the coach's narrative memory.
struct JournalEntrySnapshot: Codable, Identifiable {
    let id: String
    let at: Date
    let kind: String
    let text: String
    let surface: Bool
    let reasonForSurface: String?
}

struct NudgeSnapshot: Codable, Identifiable {
    let id: String
    let headline: String
    let body: String
    let implementationIntention: String?
    let firedAt: Date
    let firedBecause: String
    let outcome: String
}

struct FollowupSnapshot: Codable, Identifiable {
    let nudgeId: String
    let title: String
    let prompt: String
    var id: String { nudgeId }
}

/// The v2 Coach-tab payload — the single shape the brain wants shown now,
/// with the Marcus-voiced line and the data its CTAs need.
/// `shape` ∈ quiet | prescription | slip | return | pause.
struct CoachToday: Codable {
    let shape: String
    let coachLine: String
    let votes: Int
    let followups: [FollowupSnapshot]
    let actionId: String?
    let sessionName: String?
    let minimumDose: String?
    let daysAway: Int?
    let resumeOn: String?
}

struct DevTickResult: Codable {
    let fired: Bool
    let nudge: NudgeSnapshot?
}

struct LogSessionResult: Codable {
    let ok: Bool
    let ripples: [String]
    let handoff: String?
    let adaptation: String?
    let outcome: String
    /// LLM-authored acknowledgment from the coach — what makes a log feel
    /// like a conversation rather than a button tap. Nil for clean "done"
    /// with no friction note (the ripples speak for themselves there).
    let coachResponse: String?
}

/// Mirror of `/nudge/{id}/reply`'s JSON response — same fields as the
/// session log result; reused so the reply sheet can show the same
/// post-send acknowledgment + ripples as the Train log sheet.
struct ReplyResult: Codable {
    let ok: Bool
    let ripples: [String]
    let handoff: String?
    let adaptation: String?
    let outcome: String
    let coachResponse: String?
}

struct ScheduleResult: Codable {
    let blocked: Bool
    let reason: String?
    let calendarEventId: String?
    let start: String?
    let end: String?
}
