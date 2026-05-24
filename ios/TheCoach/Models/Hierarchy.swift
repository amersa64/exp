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
}

enum NudgeOutcome: String, Codable {
    case done, partial, skipped, not_now, busy
}
