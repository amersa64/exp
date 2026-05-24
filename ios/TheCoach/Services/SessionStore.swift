import Foundation
import SwiftUI

@MainActor
final class SessionStore: ObservableObject {
    private enum Key {
        static let hasCompletedIntake = "TheCoach.hasCompletedIntake"
        static let identityStatement  = "TheCoach.identityStatement"
        static let userId             = "TheCoach.userId"
    }

    @Published var hasCompletedIntake: Bool {
        didSet { UserDefaults.standard.set(hasCompletedIntake, forKey: Key.hasCompletedIntake) }
    }

    @Published var identityStatement: String? {
        didSet { UserDefaults.standard.set(identityStatement, forKey: Key.identityStatement) }
    }

    @Published var userId: String {
        didSet { UserDefaults.standard.set(userId, forKey: Key.userId) }
    }

    init() {
        let defaults = UserDefaults.standard
        self.hasCompletedIntake = defaults.bool(forKey: Key.hasCompletedIntake)
        self.identityStatement  = defaults.string(forKey: Key.identityStatement)
        self.userId             = defaults.string(forKey: Key.userId) ?? "demo-user"
    }

    func reset() {
        hasCompletedIntake = false
        identityStatement = nil
    }
}
