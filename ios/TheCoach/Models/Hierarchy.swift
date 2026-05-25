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

struct ExercisePrescription: Codable, Identifiable {
    let name: String
    let sets: Int
    let reps: Int
    let loadLb: Double?
    let restSeconds: Int
    let notes: String

    var id: String { name }
}

struct PrescribedSession: Codable {
    let name: String
    let expectedMinutes: Int
    let progressionRule: String
    let exercises: [ExercisePrescription]
}

struct NextSession: Codable {
    let actionId: String
    let actionTitle: String
    let prescribedFor: Date?
    let expectedMinutes: Int
    let cue: String?
    let location: String?
    let minimumDose: String?
    let session: PrescribedSession
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
