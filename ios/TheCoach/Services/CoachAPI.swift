// HTTP client for the backend brain.
//
// SCAFFOLD: backend HTTP layer is not yet wired in this repo — the Python brain
// in /backend exposes the same shape as a library. Once the HTTP layer is up,
// point `baseURL` at it. Keep the client dumb; never re-derive world state.

import Foundation

actor CoachAPI {
    static let shared = CoachAPI()
    // Backend brain — see backend/api/app.py. Override per-environment via Info.plist.
    private let baseURL = URL(string: "http://127.0.0.1:8765")!
    private let userId = "demo-user"  // single-user v1 (Section 10)
    private let session: URLSession = .shared

    func registerPushToken(_ token: String) async {
        _ = try? await post("/push/register", body: ["token": token])
    }

    func intakeQuestions() async throws -> [IntakeQuestion] {
        try await get("/intake/questions")
    }

    func submitIntake(_ answers: [String: String]) async throws -> IntakeResult {
        try await post("/intake/submit", body: ["answers": answers])
    }

    func world() async throws -> World {
        try await get("/world")
    }

    func openFollowups() async throws -> [FollowUp] {
        try await get("/followups")
    }

    func reply(nudgeId: String, outcome: NudgeOutcome, friction: String?) async throws {
        _ = try await post("/nudge/\(nudgeId)/reply", body: [
            "outcome": outcome.rawValue,
            "friction": friction ?? ""
        ])
    }

    // HealthKit signals — used for BOTH timing context AND verification (Section 8.1).
    func reportHealthSignal(kind: String, value: Double, at: Date) async {
        _ = try? await post("/healthkit/signal", body: [
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

private extension JSONDecoder {
    static let coach: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        d.dateDecodingStrategy = .iso8601
        return d
    }()
}
