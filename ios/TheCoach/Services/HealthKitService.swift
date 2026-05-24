// Reads HealthKit for two purposes (Section 8.1):
//   1) Timing fuel for the JITAI scheduler (steps, recent activity, sleep).
//   2) Verification of real-world behavior so the world grows honestly.
//
// SCAFFOLD: needs HealthKit capability + Info.plist usage strings to compile.

import Foundation
#if canImport(HealthKit)
import HealthKit

final class HealthKitService {
    static let shared = HealthKitService()
    private let store = HKHealthStore()

    func requestAuthorization() async throws {
        let types: Set = [
            HKObjectType.workoutType(),
            HKObjectType.quantityType(forIdentifier: .stepCount)!,
            HKObjectType.quantityType(forIdentifier: .activeEnergyBurned)!,
            HKObjectType.categoryType(forIdentifier: .sleepAnalysis)!,
        ]
        try await store.requestAuthorization(toShare: [], read: types)
    }

    /// Stream workouts as they happen; forward to backend as verification signals.
    func observeWorkouts() {
        let workoutType = HKObjectType.workoutType()
        let query = HKObserverQuery(sampleType: workoutType, predicate: nil) { _, _, error in
            guard error == nil else { return }
            Task { await self.forwardLatestWorkout() }
        }
        store.execute(query)
        store.enableBackgroundDelivery(for: workoutType, frequency: .immediate) { _, _ in }
    }

    private func forwardLatestWorkout() async {
        // Read the latest workout and POST it as a sensor verification.
        // The backend `record_sensor_verification` will grow the world iff it
        // matches an active prescribed action (Section 9.1).
    }
}
#endif
