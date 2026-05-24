// The Coach — iOS client entry point.
//
// This is a thin client (Section 8.3). The brain runs server-side; this app
// renders the world, fires HealthKit signals back to the brain, and presents
// nudges + one-tap replies that land via APNs.
//
// SCAFFOLD: needs an Xcode project + APNs key + HealthKit capability to build.

import SwiftUI
import UserNotifications

@main
struct TheCoachApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var delegate

    var body: some Scene {
        WindowGroup {
            RootView()
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
            DispatchQueue.main.async { application.registerForRemoteNotifications() }
        }
        return true
    }

    // Token goes to the backend so the JITAI scheduler can push at the right moment.
    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task { await CoachAPI.shared.registerPushToken(token) }
    }

    // Tapping a nudge action opens the one-tap reply UI.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo
        if let nudgeId = userInfo["nudge_id"] as? String {
            NudgeReplyRouter.shared.present(nudgeId: nudgeId, actionId: response.actionIdentifier)
        }
        completionHandler()
    }
}

struct RootView: View {
    @StateObject private var router = NudgeReplyRouter.shared
    @StateObject private var session = SessionState()

    var body: some View {
        Group {
            if session.hasCompletedIntake {
                WorldView()
            } else {
                IntakeView()
            }
        }
        .sheet(item: $router.presented) { reply in
            NudgeReplyView(nudgeId: reply.nudgeId, defaultOutcome: reply.actionId)
        }
        .environmentObject(session)
    }
}
