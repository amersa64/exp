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

    // Shared bearer token. Injected at build time via the `CoachAPIToken`
    // Info.plist key (project.yml: `CoachAPIToken: ${COACH_API_TOKEN}`). When
    // absent — empty, or an un-substituted `${...}` literal because the env var
    // wasn't set — we send no Authorization header, which matches an open
    // (token-less) backend for simulator/local dev.
    private let apiToken: String? = {
        guard let raw = Bundle.main.object(forInfoDictionaryKey: "CoachAPIToken") as? String else {
            return nil
        }
        let t = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty, !t.hasPrefix("${") else { return nil }
        return t
    }()

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

    /// The weekly local-notification plan the brain wants scheduled on-device
    /// (the free alternative to APNs push). See NotificationScheduler.
    func notificationPlan() async throws -> [ReminderSpec] {
        let wrapper: ReminderPlanResponse = try await get("/notifications/plan")
        return wrapper.reminders
    }

    func nextSession() async throws -> NextSession {
        try await get("/session/next")
    }

    /// Fetch up to 3 alternates for an exercise (same primary muscle, same
    /// movement pattern, filtered by user's equipment).
    func exerciseAlternates(name: String) async throws -> ExerciseAlternatesResponse {
        try await get("/exercises/alternates", query: ["name": name])
    }

    /// Adaptive swap — the user explains in their own words why an exercise
    /// isn't working and what they'd prefer. The coach reads the note against
    /// equipment-matched alternatives, recommends a replacement, AND records a
    /// standing constraint so the vetoed exercise never silently returns.
    /// When `apply` is true the live program is patched immediately.
    /// `chosen` short-circuits the LLM: when the user taps a default alternate
    /// the UI already offered, we send it directly and the backend just records
    /// + applies the swap. `note` carries the free-form custom-request path.
    func exerciseSwap(name: String, note: String, chosen: String? = nil, apply: Bool = true) async throws -> ExerciseSwapResult {
        var body: [String: Any] = [
            "exercise_name": name,
            "note": note,
            "apply": apply,
        ]
        if let chosen { body["chosen"] = chosen }
        let result: ExerciseSwapResult = try await post("/exercise/swap", body: body)
        await MainActor.run {
            NotificationCenter.default.post(name: .coachStateChanged, object: nil)
        }
        return result
    }

    /// Free-form feedback about the program as a whole ("too much volume",
    /// "I can only do 3 days now"). The coach interprets it, remembers it, and
    /// regenerates the program when the feedback changes its shape.
    func programFeedback(note: String) async throws -> ProgramFeedbackResult {
        let result: ProgramFeedbackResult = try await post("/program/feedback", body: [
            "note": note,
        ])
        await MainActor.run {
            NotificationCenter.default.post(name: .coachStateChanged, object: nil)
        }
        return result
    }

    /// The coach's memory — every change this user has requested.
    func adjustments() async throws -> [ProgramAdjustment] {
        let wrapper: AdjustmentsResponse = try await get("/adjustments")
        return wrapper.adjustments
    }

    /// Visual + step-by-step instructions for one prescribed exercise. Powers
    /// the "Show me how" sheet in ExerciseLogView. Throws on 404 (catalog miss).
    func exerciseDetail(name: String) async throws -> ExerciseDetail {
        try await get("/exercise", query: ["name": name])
    }

    /// Per-exercise session log. The backend derives the rolled-up session
    /// outcome (all done → done, all skipped → skipped, mixed → partial) and
    /// pulls calibration top-set data out of any exercise whose payload
    /// carries a `calibrationSlot`. `friction` is a session-level free-text
    /// note for things that aren't pinned to one lift.
    func logSession(actionId: String, friction: String?,
                    exercises: [String: ExerciseLogPayload]) async throws -> LogSessionResult {
        let body: [String: Any] = [
            "exercises": exercises.mapValues { $0.toDict() },
            "friction": friction ?? "",
        ]
        let result: LogSessionResult = try await post("/session/\(actionId)/log", body: body)
        // Broadcast so other VMs (WorldViewModel) refresh their derived state.
        await MainActor.run {
            NotificationCenter.default.post(name: .coachStateChanged, object: nil)
        }
        return result
    }

    /// One completed set's wire shape — reps required, load nil for
    /// bodyweight lifts (pullups, planks).
    struct SetPayload {
        let reps: Int
        let loadLb: Double?

        func toDict() -> [String: Any] {
            var d: [String: Any] = ["reps": reps]
            if let lb = loadLb { d["load_lb"] = lb }
            return d
        }
    }

    /// Per-exercise outcome captured by the active-session flow.
    ///
    /// `outcome` is done/partial/skipped for this one lift. `sets` is the
    /// per-set history (Strong / Hevy style). `actualReps` / `actualLoadLb`
    /// are the top-set rollup — we send them too so the server doesn't have
    /// to re-derive them, but it will fall back to `sets` if we don't.
    /// `calibrationSlot` is echoed from the prescription so the backend can
    /// derive the legacy top_sets dict (keyed by lift slot) without
    /// re-running the persona.
    struct ExerciseLogPayload {
        let outcome: NudgeOutcome
        let actualReps: Int?
        let actualLoadLb: Double?
        let actualSets: Int?
        let note: String?
        let calibrationSlot: String?
        let sets: [SetPayload]

        init(outcome: NudgeOutcome,
             actualReps: Int? = nil,
             actualLoadLb: Double? = nil,
             actualSets: Int? = nil,
             note: String? = nil,
             calibrationSlot: String? = nil,
             sets: [SetPayload] = []) {
            self.outcome = outcome
            self.actualReps = actualReps
            self.actualLoadLb = actualLoadLb
            self.actualSets = actualSets
            self.note = note
            self.calibrationSlot = calibrationSlot
            self.sets = sets
        }

        func toDict() -> [String: Any] {
            var d: [String: Any] = ["outcome": outcome.rawValue]
            if let r = actualReps { d["actual_reps"] = r }
            if let lb = actualLoadLb { d["actual_load_lb"] = lb }
            if let s = actualSets { d["actual_sets"] = s }
            if let n = note, !n.isEmpty { d["note"] = n }
            if let slot = calibrationSlot { d["calibration_slot"] = slot }
            if !sets.isEmpty { d["sets"] = sets.map { $0.toDict() } }
            return d
        }
    }

    func scheduleSession(actionId: String) async throws -> ScheduleResult {
        try await post("/session/\(actionId)/schedule", body: [:])
    }

    func coachState() async throws -> CoachState {
        try await get("/coach/state")
    }

    /// The v2 Coach-tab shape the brain wants shown right now.
    func coachToday() async throws -> CoachToday {
        try await get("/coach/today")
    }

    /// Pause the program for N days (Shape D "give me a week" / Settings).
    func pauseProgram(days: Int) async throws {
        try await send("/program/pause", body: ["days": days])
        await MainActor.run { NotificationCenter.default.post(name: .coachStateChanged, object: nil) }
    }

    func resumeProgram() async throws {
        try await send("/program/resume", body: [:])
        await MainActor.run { NotificationCenter.default.post(name: .coachStateChanged, object: nil) }
    }

    // -- dev affordances --

    /// Fetch the catalog of seedable scenarios + selectable goals so the
    /// Dev sheet can render its pickers.
    func devScenarios() async throws -> DevScenarioListing {
        try await get("/dev/scenarios")
    }

    /// Wipe the current user and apply a pre-built scenario. Pairs with
    /// the /dev/seed backend endpoint — see backend/coach/dev_scenarios.py.
    func seedScenario(goal: String, scenario: String) async throws -> DevSeedResult {
        let body: [String: Any] = ["goal": goal, "scenario": scenario]
        let raw: [String: Any] = try await postRaw("/dev/seed", body: body)
        let applied = raw["applied"] as? String ?? scenario
        let phase = raw["phase"] as? String ?? "?"
        let votes = raw["votes"] as? Int ?? 0
        let streak = raw["streak_days"] as? Int ?? 0
        let summary = "Applied: \(applied) → phase=\(phase), \(votes) votes, \(streak)-day streak"
        return DevSeedResult(summary: summary)
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

    func reply(nudgeId: String, outcome: NudgeOutcome, friction: String?) async throws -> ReplyResult {
        let result: ReplyResult = try await post("/nudge/\(nudgeId)/reply", body: [
            "outcome": outcome.rawValue,
            "friction": friction ?? "",
        ])
        await MainActor.run {
            NotificationCenter.default.post(name: .coachStateChanged, object: nil)
        }
        return result
    }

    // HealthKit signals — used for BOTH timing context AND verification (Section 8.1).
    func reportHealthSignal(kind: String, value: Double, at: Date) async {
        try? await send("/healthkit/signal", body: [
            "kind": kind, "value": value, "at": ISO8601DateFormatter().string(from: at)
        ])
    }

    // MARK: - iPhone signals (Section 8.1)

    /// Feature 1 — post this morning's HealthKit recovery picture. The backend
    /// scores it and returns the band + the directive it will apply to today.
    func reportReadiness(_ input: ReadinessInput) async throws -> ReadinessResult {
        var body: [String: Any] = [:]
        if let v = input.sleepHours { body["sleep_hours"] = v }
        if let v = input.restingHr { body["resting_hr"] = v }
        if let v = input.hrvMs { body["hrv_ms"] = v }
        if let v = input.restingHrBaseline { body["resting_hr_baseline"] = v }
        if let v = input.hrvBaseline { body["hrv_baseline"] = v }
        let result: ReadinessResult = try await post("/signals/readiness", body: body)
        await MainActor.run {
            NotificationCenter.default.post(name: .coachStateChanged, object: nil)
        }
        return result
    }

    /// Feature 2 — post current coordinates so the brain can learn where the
    /// user trains. Called when a session starts or is logged.
    @discardableResult
    func observePlace(lat: Double, lon: Double) async throws -> LearnedPlace {
        try await post("/signals/place/observe", body: ["lat": lat, "lon": lon])
    }

    /// The learned training geofence to region-monitor (or monitorable=false).
    func learnedPlace() async throws -> LearnedPlace {
        try await get("/signals/place")
    }

    /// The phone crossed the gym geofence — arrived or departed.
    func locationEvent(_ event: String, lat: Double? = nil, lon: Double? = nil) async throws -> LocationEventResult {
        var body: [String: Any] = ["event": event]
        if let lat { body["lat"] = lat }
        if let lon { body["lon"] = lon }
        return try await post("/signals/location-event", body: body)
    }

    /// Broad ingestion — post a batch of HealthKit readings (any metrics).
    /// Idempotent server-side on (metric, timestamp), so re-posting overlapping
    /// windows is safe.
    @discardableResult
    func reportVitals(_ samples: [VitalSampleInput]) async throws -> Int {
        guard !samples.isEmpty else { return 0 }
        let iso = ISO8601DateFormatter()
        let body: [String: Any] = [
            "samples": samples.map { s -> [String: Any] in
                var d: [String: Any] = ["metric": s.metric, "value": s.value, "unit": s.unit]
                if let at = s.at { d["at"] = iso.string(from: at) }
                return d
            }
        ]
        struct StoredResult: Codable { let ok: Bool; let stored: Int }
        let result: StoredResult = try await post("/signals/vitals", body: body)
        return result.stored
    }

    /// The Vitals dashboard payload: per-metric trends + cross-metric insights.
    func vitalsSummary() async throws -> VitalsSummary {
        try await get("/vitals/summary")
    }

    /// Raw points for one metric — for charting.
    func vitalsSeries(metric: String, days: Int = 90) async throws -> VitalsSeries {
        try await get("/vitals/series", query: ["metric": metric, "days": String(days)])
    }

    /// Feature 3 — auto-log the prescribed session from a HealthKit workout.
    func autolog(actionId: String, workout: DetectedWorkout) async throws -> AutologResult {
        var body: [String: Any] = [:]
        if let v = workout.durationMin { body["duration_min"] = v }
        if let v = workout.activeKcal { body["active_kcal"] = v }
        if let v = workout.avgHr { body["avg_hr"] = v }
        if let v = workout.workoutType { body["workout_type"] = v }
        if let v = workout.endedAt { body["ended_at"] = ISO8601DateFormatter().string(from: v) }
        let result: AutologResult = try await post("/session/\(actionId)/autolog", body: body)
        await MainActor.run {
            NotificationCenter.default.post(name: .coachStateChanged, object: nil)
        }
        return result
    }

    // -- plumbing --

    /// Apply the headers every request needs: the identity header and, when a
    /// token is configured, the shared bearer credential the hardened backend
    /// requires (see _auth_gate in backend/api/app.py).
    private func authorize(_ req: inout URLRequest) {
        req.addValue(userId, forHTTPHeaderField: "X-User-Id")
        if let apiToken {
            req.addValue("Bearer \(apiToken)", forHTTPHeaderField: "Authorization")
        }
    }

    private func get<T: Decodable>(_ path: String, query: [String: String] = [:]) async throws -> T {
        var comps = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty {
            comps.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        var req = URLRequest(url: comps.url!)
        authorize(&req)
        let (data, _) = try await session.data(for: req)
        return try JSONDecoder.coach.decode(T.self, from: data)
    }

    private func post<T: Decodable>(_ path: String, body: [String: Any]) async throws -> T {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.addValue("application/json", forHTTPHeaderField: "Content-Type")
        authorize(&req)
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, _) = try await session.data(for: req)
        return try JSONDecoder.coach.decode(T.self, from: data)
    }

    /// POST helper that returns the raw JSON dict — used for endpoints
    /// whose response shape we want to read field-by-field without a
    /// dedicated Codable struct (e.g. the dev seed summary).
    fileprivate func postRaw(_ path: String, body: [String: Any]) async throws -> [String: Any] {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.addValue("application/json", forHTTPHeaderField: "Content-Type")
        authorize(&req)
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, _) = try await session.data(for: req)
        return (try JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    private func send(_ path: String, body: [String: Any]) async throws {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.addValue("application/json", forHTTPHeaderField: "Content-Type")
        authorize(&req)
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

/// One weekly recurring reminder, scheduled locally on the device.
struct ReminderSpec: Codable, Identifiable {
    let id: String          // stable per slot (e.g. "pre-mon") — used to de-dupe
    let weekday: String     // "mon".."sun"
    let hour: Int           // local wall-clock
    let minute: Int
    let title: String
    let body: String
}

private struct ReminderPlanResponse: Codable {
    let reminders: [ReminderSpec]
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
