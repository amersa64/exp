// HTTP client for the backend brain.
//
// SCAFFOLD: backend HTTP layer is not yet wired in this repo — the Python brain
// in /backend exposes the same shape as a library. Once the HTTP layer is up,
// point `baseURL` at it. Keep the client dumb; never re-derive world state.

import Foundation

actor CoachAPI {
    static let shared = CoachAPI()
    // Backend brain — see backend/api/app.py.
    // Override the URL per-environment by setting `CoachBackendURL` in Info.plist
    // (e.g. http://192.168.x.y:8765 when running on a real device against a Mac
    // on the same Wi-Fi). Falls back to localhost for the simulator.
    private let baseURL: URL = {
        if let s = Bundle.main.object(forInfoDictionaryKey: "CoachBackendURL") as? String,
           let url = URL(string: s) {
            return url
        }
        return URL(string: "http://127.0.0.1:8765")!
    }()
    private let userId = "demo-user"  // single-user v1 (Section 10)
    private let session: URLSession = .shared

    func registerPushToken(_ token: String) async {
        try? await send("/push/register", body: ["token": token])
    }

    func intakeQuestions() async throws -> [IntakeQuestion] {
        let wrapper: IntakeQuestionsResponse = try await get("/intake/questions")
        return wrapper.questions
    }

    func submitIntake(answers: [String: String], identityStatement: String) async throws -> IntakeResult {
        try await post("/intake/submit", body: [
            "answers": answers,
            "identity_statement": identityStatement,
        ])
    }

    func world() async throws -> World {
        try await get("/world")
    }

    func identity() async throws -> Identity {
        try await get("/identity")
    }

    func milestones() async throws -> [Milestone] {
        let wrapper: MilestonesResponse = try await get("/milestones")
        return wrapper.milestones
    }

    func openFollowups() async throws -> [FollowUp] {
        let wrapper: FollowupsResponse = try await get("/followups")
        return wrapper.followups
    }

    func nextSession() async throws -> NextSession {
        try await get("/session/next")
    }

    func logSession(actionId: String, outcome: NudgeOutcome, friction: String?) async throws -> LogSessionResult {
        let result: LogSessionResult = try await post("/session/\(actionId)/log", body: [
            "outcome": outcome.rawValue,
            "friction": friction ?? "",
        ])
        // Broadcast so other VMs (WorldViewModel) refresh their derived state.
        await MainActor.run {
            NotificationCenter.default.post(name: .coachStateChanged, object: nil)
        }
        return result
    }

    func scheduleSession(actionId: String) async throws -> ScheduleResult {
        try await post("/session/\(actionId)/schedule", body: [:])
    }

    func coachState() async throws -> CoachState {
        try await get("/coach/state")
    }

    /// Dev-only: ask the brain to evaluate one tick now and tell us what it
    /// decided (fire/silence). Backstops not having APNs in local dev.
    func devTick() async throws -> DevTickResult {
        let result: DevTickResult = try await post("/dev/tick", body: [:])
        await MainActor.run {
            NotificationCenter.default.post(name: .coachStateChanged, object: nil)
        }
        return result
    }

    func reply(nudgeId: String, outcome: NudgeOutcome, friction: String?) async throws {
        try await send("/nudge/\(nudgeId)/reply", body: [
            "outcome": outcome.rawValue,
            "friction": friction ?? "",
        ])
        await MainActor.run {
            NotificationCenter.default.post(name: .coachStateChanged, object: nil)
        }
    }

    // HealthKit signals — used for BOTH timing context AND verification (Section 8.1).
    func reportHealthSignal(kind: String, value: Double, at: Date) async {
        try? await send("/healthkit/signal", body: [
            "kind": kind, "value": value, "at": ISO8601DateFormatter().string(from: at)
        ])
    }

    // -- plumbing --

    private func get<T: Decodable>(_ path: String) async throws -> T {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.addValue(userId, forHTTPHeaderField: "X-User-Id")
        let (data, _) = try await session.data(for: req)
        return try JSONDecoder.coach.decode(T.self, from: data)
    }

    private func post<T: Decodable>(_ path: String, body: [String: Any]) async throws -> T {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.addValue("application/json", forHTTPHeaderField: "Content-Type")
        req.addValue(userId, forHTTPHeaderField: "X-User-Id")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, _) = try await session.data(for: req)
        return try JSONDecoder.coach.decode(T.self, from: data)
    }

    private func send(_ path: String, body: [String: Any]) async throws {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.addValue("application/json", forHTTPHeaderField: "Content-Type")
        req.addValue(userId, forHTTPHeaderField: "X-User-Id")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        _ = try await session.data(for: req)
    }
}

extension Notification.Name {
    /// Fired after any client-driven action that may have changed coach state
    /// (logs, replies, dev ticks). Listeners refresh their derived views.
    static let coachStateChanged = Notification.Name("CoachStateChanged")
}

struct IntakeQuestion: Codable, Identifiable {
    let key: String
    let q: String
    var id: String { key }
}

struct IntakeResult: Codable {
    let summary: String
    let handoff: String?
}

struct FollowUp: Codable, Identifiable {
    let nudgeId: String
    let actionTitle: String
    let prompt: String
    var id: String { nudgeId }
}

private struct IntakeQuestionsResponse: Codable {
    let questions: [IntakeQuestion]
}

private struct FollowupsResponse: Codable {
    let followups: [FollowUp]
}

private struct MilestonesResponse: Codable {
    let milestones: [Milestone]
}

private extension JSONDecoder {
    static let coach: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        d.dateDecodingStrategy = .iso8601
        return d
    }()
}
