// Local notifications — the free path to reminders (no APNs / paid account).
//
// The brain returns a weekly plan (/notifications/plan); we schedule each entry
// as a repeating local calendar notification in the device's LOCAL time. Because
// they're calendar triggers with repeats=true, they keep firing without the app
// running or any push server. We just re-sync the set whenever the app opens (or
// on background refresh) so it tracks the latest plan.

import Foundation
import UserNotifications

@MainActor
final class NotificationScheduler {
    static let shared = NotificationScheduler()

    // Identifier prefix for the reminders we own, so refresh only clears ours
    // and never stomps on anything else (e.g. one-off local notifications).
    private let prefix = "coach-"

    /// Fetch the plan and (re)schedule it. Idempotent: clears our previously
    /// scheduled reminders first, so the live set always matches the latest plan.
    /// No-ops quietly when offline, not onboarded, or notifications aren't allowed.
    func refresh() async {
        let specs: [ReminderSpec]
        do {
            specs = try await CoachAPI.shared.notificationPlan()
        } catch {
            return  // offline / pre-onboarding — keep whatever's already scheduled
        }

        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        guard settings.authorizationStatus == .authorized
                || settings.authorizationStatus == .provisional else { return }

        let pending = await center.pendingNotificationRequests()
        let ours = pending.map(\.identifier).filter { $0.hasPrefix(prefix) }
        center.removePendingNotificationRequests(withIdentifiers: ours)

        for s in specs {
            guard let weekday = Self.iosWeekday(s.weekday) else { continue }
            let content = UNMutableNotificationContent()
            content.title = s.title
            content.body = s.body
            content.sound = .default

            var when = DateComponents()
            when.weekday = weekday
            when.hour = s.hour
            when.minute = s.minute
            let trigger = UNCalendarNotificationTrigger(dateMatching: when, repeats: true)

            let request = UNNotificationRequest(
                identifier: prefix + s.id, content: content, trigger: trigger
            )
            try? await center.add(request)
        }
    }

    /// Backend 3-letter codes → iOS weekday ints (1 = Sunday … 7 = Saturday).
    private static func iosWeekday(_ code: String) -> Int? {
        ["sun": 1, "mon": 2, "tue": 3, "wed": 4, "thu": 5, "fri": 6, "sat": 7][code.lowercased()]
    }

    /// Fire a one-off reminder a few seconds out so the user can feel a real
    /// notification now instead of waiting for a scheduled slot. Uses a distinct
    /// "coachtest-" id so a routine refresh() (which only clears "coach-") won't
    /// cancel it before it fires. Returns a short status for the UI.
    func scheduleTest(after seconds: TimeInterval = 10) async -> String {
        if let problem = await authorizationProblem() { return problem }
        let center = UNUserNotificationCenter.current()
        let content = UNMutableNotificationContent()
        content.title = "Test reminder"
        content.body = "If you can read this, your reminders work. The scheduled ones fire the same way — even with the app closed."
        content.sound = .default
        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: max(1, seconds), repeats: false)
        let request = UNNotificationRequest(
            identifier: "coachtest-\(UUID().uuidString)", content: content, trigger: trigger
        )
        try? await center.add(request)
        return "Test set for \(Int(seconds))s out — lock your phone to feel it land."
    }

    /// Stress test: fire `count` one-off notifications spaced `intervalSeconds`
    /// apart. One-off time-interval triggers fire regardless of app state —
    /// foreground, backgrounded, or fully closed — so this verifies the wire end
    /// to end. (iOS blocks *repeating* triggers under 60s, hence a finite burst.)
    /// Ids use the "coachtest-" prefix so a routine refresh() won't cancel them.
    func scheduleBurst(count: Int, intervalSeconds: Double = 2) async -> String {
        if let problem = await authorizationProblem() { return problem }
        let n = max(1, min(count, 60))  // keep the burst sane
        let center = UNUserNotificationCenter.current()
        for i in 1...n {
            let content = UNMutableNotificationContent()
            content.title = "Stress test \(i)/\(n)"
            content.body = "Fired at +\(Int(Double(i) * intervalSeconds))s after you tapped."
            content.sound = .default
            let trigger = UNTimeIntervalNotificationTrigger(
                timeInterval: Double(i) * intervalSeconds, repeats: false
            )
            let request = UNNotificationRequest(
                identifier: "coachtest-burst-\(i)-\(UUID().uuidString)",
                content: content, trigger: trigger
            )
            try? await center.add(request)
        }
        return "Scheduled \(n) notifications, one every \(Int(intervalSeconds))s. Lock your phone and watch them roll in."
    }

    /// Cancel any pending test notifications (the test + burst ones), so a long
    /// burst can be stopped. Leaves the real weekly reminders ("coach-") intact.
    func cancelTests() async -> String {
        let center = UNUserNotificationCenter.current()
        let pending = await center.pendingNotificationRequests()
        let testIds = pending.map(\.identifier).filter { $0.hasPrefix("coachtest") }
        center.removePendingNotificationRequests(withIdentifiers: testIds)
        return "Cleared \(testIds.count) pending test notification(s)."
    }

    /// nil when notifications can be delivered; otherwise a user-facing reason.
    private func authorizationProblem() async -> String? {
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral:
            return nil
        case .notDetermined:
            let granted = (try? await center.requestAuthorization(options: [.alert, .badge, .sound])) ?? false
            return granted ? nil : "Notifications weren't allowed."
        case .denied:
            return "Notifications are off — enable them in Settings › The Coach."
        @unknown default:
            return "Notifications unavailable."
        }
    }
}

// One recorded notification event, so the user can see WHEN reminders fired.
struct NotificationEvent: Codable, Identifiable {
    let id: String        // requestId@epoch — dedupes the same fire across sources
    let date: Date
    let title: String
    let body: String
    let how: String       // "shown" (foreground) | "tapped" | "delivered"
}

/// Persistent log of coach notifications that have fired, surfaced in the Dev
/// sheet. Fed from foreground presentation + taps (AppDelegate) and, on app
/// open, by sweeping anything still sitting in Notification Center.
@MainActor
final class NotificationLog: ObservableObject {
    static let shared = NotificationLog()

    @Published private(set) var events: [NotificationEvent] = []
    private let key = "coach.notificationLog"
    private let maxEntries = 30

    init() {
        if let data = UserDefaults.standard.data(forKey: key),
           let decoded = try? JSONDecoder().decode([NotificationEvent].self, from: data) {
            events = decoded
        }
    }

    func record(requestId: String, date: Date, title: String, body: String, how: String) {
        let id = "\(requestId)@\(Int(date.timeIntervalSince1970))"
        guard !events.contains(where: { $0.id == id }) else { return }
        events.insert(NotificationEvent(id: id, date: date, title: title, body: body, how: how), at: 0)
        if events.count > maxEntries { events = Array(events.prefix(maxEntries)) }
        if let data = try? JSONEncoder().encode(events) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    /// Pull anything still in Notification Center (e.g. a reminder that fired
    /// while the app was closed) into the log when the user reopens the app.
    func sweepDelivered() async {
        let delivered = await UNUserNotificationCenter.current().deliveredNotifications()
        for n in delivered where n.request.identifier.hasPrefix("coach") {
            record(requestId: n.request.identifier, date: n.date,
                   title: n.request.content.title, body: n.request.content.body, how: "delivered")
        }
    }
}
