// The Coach — iOS client entry point.
//
// This is a thin client (Section 8.3). The brain runs server-side; this app
// renders the world, fires HealthKit signals back to the brain, and presents
// nudges + one-tap replies that land via APNs.

import BackgroundTasks
import SwiftUI
import UserNotifications

/// Background-refresh task id. Must match BGTaskSchedulerPermittedIdentifiers
/// in Info.plist (project.yml) or registration crashes at launch.
private let kRefreshTaskID = "ai.zaimler.TheCoach.refresh"

@main
struct TheCoachApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var sessionStore = SessionStore()
    @StateObject private var backendHealth = BackendHealth()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(sessionStore)
                .environmentObject(backendHealth)
                .preferredColorScheme(.dark)
                .tint(Theme.ember)
                .task { await backendHealth.probe() }
        }
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey : Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { _, _ in
            // Local notifications (the scheduled reminders) only need this
            // authorization. registerForRemoteNotifications additionally needs
            // the paid-account aps-environment entitlement; it fails harmlessly
            // on a free team and lights up once push is enabled.
            DispatchQueue.main.async { application.registerForRemoteNotifications() }
        }

        // Background refresh: periodically re-sync the local reminder schedule
        // so it tracks plan changes even when the app isn't opened.
        BGTaskScheduler.shared.register(forTaskWithIdentifier: kRefreshTaskID, using: nil) { task in
            self.handleAppRefresh(task as! BGAppRefreshTask)
        }
        scheduleAppRefresh()
        return true
    }

    func applicationDidBecomeActive(_ application: UIApplication) {
        // Refresh on every open so reminders reflect the latest plan, and pull
        // any reminders that fired while away into the log.
        Task {
            await NotificationScheduler.shared.refresh()
            await NotificationLog.shared.sweepDelivered()
        }
    }

    private func scheduleAppRefresh() {
        let request = BGAppRefreshTaskRequest(identifier: kRefreshTaskID)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 6 * 3600)  // ~6h
        try? BGTaskScheduler.shared.submit(request)
    }

    private func handleAppRefresh(_ task: BGAppRefreshTask) {
        scheduleAppRefresh()  // chain the next one
        let work = Task {
            await NotificationScheduler.shared.refresh()
            task.setTaskCompleted(success: true)
        }
        task.expirationHandler = { work.cancel() }
    }

    // Token goes to the backend so the JITAI scheduler can push at the right moment.
    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task { await CoachAPI.shared.registerPushToken(token) }
    }

    // Show nudges as a banner even when the app is foregrounded — otherwise iOS
    // drops them silently and a nudge that fires while you're in the app vanishes.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        let c = notification.request.content
        NotificationLog.shared.record(
            requestId: notification.request.identifier, date: notification.date,
            title: c.title, body: c.body, how: "shown")
        completionHandler([.banner, .sound])
    }

    // Tapping a nudge action opens the one-tap reply UI.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let note = response.notification
        let c = note.request.content
        NotificationLog.shared.record(
            requestId: note.request.identifier, date: note.date,
            title: c.title, body: c.body, how: "tapped")
        if let nudgeId = c.userInfo["nudge_id"] as? String {
            NudgeReplyRouter.shared.present(nudgeId: nudgeId, actionId: response.actionIdentifier)
        }
        completionHandler()
    }
}

struct RootView: View {
    @EnvironmentObject var sessionStore: SessionStore
    @EnvironmentObject var backendHealth: BackendHealth
    @StateObject private var router = NudgeReplyRouter.shared

    var body: some View {
        Group {
            switch backendHealth.status {
            case .checking:
                BackendLoadingView()
            case .unreachable(let message):
                ErrorView(
                    title: "Can't reach the coach",
                    message: message,
                    retry: { await backendHealth.probe() }
                )
            case .reachable:
                if sessionStore.hasCompletedIntake {
                    WorldView()
                        .task { await bootstrapSignals() }
                } else {
                    IntakeView()
                }
            }
        }
        .sheet(item: $router.presented) { reply in
            NudgeReplyView(nudgeId: reply.nudgeId, defaultOutcome: reply.actionId)
        }
    }

    /// Bring the three iPhone-signal features online once we're onboarded and
    /// connected (Section 8.1). Permission prompts only appear here, after the
    /// user has a reason to grant them — not cold on first launch.
    @MainActor
    private func bootstrapSignals() async {
        #if canImport(HealthKit)
        await HealthKitService.shared.requestAuthorization()
        // Broad ingestion — post the rolling history of everything Health
        // grants (body weight, sleep, steps, …) so trends are ready to read.
        await HealthKitService.shared.collectAndReportVitals()
        // Feature 1 — post this morning's readiness so /session/next can shape
        // today's ask before the user even opens the Train tab. Runs AFTER
        // vitals so the multi-day sleep-debt history is already in place.
        await HealthKitService.shared.computeAndReportReadiness()
        // Feature 3 — watch for completed workouts to offer auto-log.
        HealthKitService.shared.observeWorkouts()
        #endif
        // Feature 2 — learn the gym + arm the geofence.
        LocationManager.shared.start()
        // Schedule the weekly local-notification reminders from the brain's plan
        // (the free, no-APNs path to push). Re-synced on every app open too.
        await NotificationScheduler.shared.refresh()
    }
}

private struct BackendLoadingView: View {
    @State private var pulse = false

    var body: some View {
        ZStack {
            AtmosphericBackground()
            VStack(spacing: 24) {
                ZStack {
                    Circle()
                        .fill(Theme.emberGradient)
                        .frame(width: 14, height: 14)
                        .shadow(color: Theme.ember.opacity(0.9), radius: pulse ? 28 : 10)
                        .scaleEffect(pulse ? 1.15 : 1.0)
                }
                .frame(width: 80, height: 80)
                Text("Connecting")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(.white.opacity(0.9))
                Text("Reaching the brain on the wire.")
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.5))
            }
        }
        .onAppear {
            withAnimation(.easeInOut(duration: 1.2).repeatForever(autoreverses: true)) {
                pulse = true
            }
        }
    }
}
