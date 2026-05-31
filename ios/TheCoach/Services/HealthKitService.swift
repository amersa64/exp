// HealthKit — the body-sensing half of the iPhone-signal features (Section 8.1).
//
// Two magical jobs, both reading-only:
//   1) Readiness Engine (Feature 1): each morning read last night's sleep,
//      resting heart rate, and HRV — plus the user's own 14-day baselines —
//      and post them so the brain can dial today's ask up or down.
//   2) Workout auto-log (Feature 3): detect a completed workout that overlaps
//      the prescribed window so the Train tab can offer a one-tap auto-log
//      enriched with the real duration / calories / heart rate.
//
// Nothing here grows the world directly — it posts raw signals to the backend,
// which owns scoring and verification. The phone senses; the brain decides.

import Foundation
#if canImport(HealthKit)
import HealthKit

final class HealthKitService {
    static let shared = HealthKitService()
    private let store = HKHealthStore()

    /// Fired (on the main actor) when a fresh workout is detected so the UI can
    /// offer to auto-log it. Carries the detected workout in `userInfo["workout"]`.
    static let workoutDetected = Notification.Name("HealthKitWorkoutDetected")

    var isAvailable: Bool { HKHealthStore.isHealthDataAvailable() }

    // MARK: - Authorization

    private var readTypes: Set<HKObjectType> {
        var types: Set<HKObjectType> = [HKObjectType.workoutType()]
        if let t = HKObjectType.quantityType(forIdentifier: .stepCount) { types.insert(t) }
        if let t = HKObjectType.quantityType(forIdentifier: .activeEnergyBurned) { types.insert(t) }
        if let t = HKObjectType.quantityType(forIdentifier: .restingHeartRate) { types.insert(t) }
        if let t = HKObjectType.quantityType(forIdentifier: .heartRateVariabilitySDNN) { types.insert(t) }
        if let t = HKObjectType.quantityType(forIdentifier: .heartRate) { types.insert(t) }
        if let t = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) { types.insert(t) }
        return types
    }

    @discardableResult
    func requestAuthorization() async -> Bool {
        guard isAvailable else { return false }
        do {
            try await store.requestAuthorization(toShare: [], read: readTypes)
            return true
        } catch {
            return false
        }
    }

    // MARK: - Feature 1: Readiness

    /// Read the morning recovery picture and post it. Safe to call on every
    /// foreground — the backend keeps only the latest snapshot per day.
    @discardableResult
    func computeAndReportReadiness() async -> ReadinessResult? {
        guard isAvailable else { return nil }

        async let sleep = lastNightSleepHours()
        async let rhr = mostRecentQuantity(.restingHeartRate, unit: .count().unitDivided(by: .minute()))
        async let hrv = mostRecentQuantity(.heartRateVariabilitySDNN, unit: .secondUnit(with: .milli))
        async let rhrBase = medianQuantity(.restingHeartRate, unit: .count().unitDivided(by: .minute()), days: 14)
        async let hrvBase = medianQuantity(.heartRateVariabilitySDNN, unit: .secondUnit(with: .milli), days: 14)

        let input = ReadinessInput(
            sleepHours: await sleep,
            restingHr: await rhr,
            hrvMs: await hrv,
            restingHrBaseline: await rhrBase,
            hrvBaseline: await hrvBase
        )

        // Nothing granted / nothing recorded → don't post a hollow snapshot.
        guard input.sleepHours != nil || input.restingHr != nil || input.hrvMs != nil else {
            return nil
        }
        return try? await CoachAPI.shared.reportReadiness(input)
    }

    // MARK: - Broad vitals ingestion

    /// Read everything Health will grant and post it as a batch. iPhone-native
    /// metrics (steps, distance, flights, body composition, sleep duration) are
    /// the backbone; Watch-derived metrics (resting HR, HRV, VO2max, …) ride
    /// along only if some device wrote them — never required.
    func collectAndReportVitals() async {
        guard isAvailable else { return }
        var batch: [VitalSampleInput] = []

        // --- Body composition (smart scale / manual) — trailing history so
        //     the weight trajectory is real, not a single point.
        batch += await quantitySeries(.bodyMass, key: "body_mass_kg",
                                       unit: .gramUnit(with: .kilo), days: 90)
        batch += await quantitySeries(.bodyFatPercentage, key: "body_fat_pct",
                                       unit: .percent(), days: 90, scale: 100)
        batch += await quantitySeries(.leanBodyMass, key: "lean_mass_kg",
                                       unit: .gramUnit(with: .kilo), days: 90)
        batch += await quantitySeries(.bodyMassIndex, key: "bmi",
                                       unit: .count(), days: 90)
        if let h = await mostRecentQuantity(.height, unit: .meterUnit(with: .centi)) {
            batch.append(VitalSampleInput(metric: "height_cm", value: h, unit: "cm", at: nil))
        }

        // --- iPhone-native daily activity — per-day sums.
        batch += await dailySums(.stepCount, key: "steps", unit: .count(), days: 30)
        batch += await dailySums(.distanceWalkingRunning, key: "distance_km",
                                 unit: .meterUnit(with: .kilo), days: 30)
        batch += await dailySums(.flightsClimbed, key: "flights_climbed",
                                 unit: .count(), days: 30)
        batch += await dailySums(.activeEnergyBurned, key: "active_energy_kcal",
                                 unit: .kilocalorie(), days: 30)
        batch += await dailySums(.appleExerciseTime, key: "exercise_min",
                                 unit: .minute(), days: 30)

        // --- Sleep per night (iPhone sleep schedule / sleep apps).
        batch += await sleepByNight(days: 8)

        // --- Optional Watch enrichment — latest only, never gates anything.
        if let v = await mostRecentQuantity(.restingHeartRate, unit: .count().unitDivided(by: .minute())) {
            batch.append(VitalSampleInput(metric: "resting_hr", value: v, unit: "bpm", at: nil))
        }
        if let v = await mostRecentQuantity(.heartRateVariabilitySDNN, unit: .secondUnit(with: .milli)) {
            batch.append(VitalSampleInput(metric: "hrv_ms", value: v, unit: "ms", at: nil))
        }
        if let v = await mostRecentQuantity(.vo2Max, unit: HKUnit(from: "ml/kg*min")) {
            batch.append(VitalSampleInput(metric: "vo2max", value: v, unit: "mL/kg·min", at: nil))
        }
        if let v = await mostRecentQuantity(.respiratoryRate, unit: .count().unitDivided(by: .minute())) {
            batch.append(VitalSampleInput(metric: "respiratory_rate", value: v, unit: "br/min", at: nil))
        }

        _ = try? await CoachAPI.shared.reportVitals(batch)
    }

    /// All samples of a quantity over the last `days`, mapped to vitals inputs
    /// with their real timestamps. `scale` multiplies the raw value (e.g. body
    /// fat fraction → percent).
    private func quantitySeries(
        _ id: HKQuantityTypeIdentifier, key: String, unit: HKUnit, days: Int, scale: Double = 1
    ) async -> [VitalSampleInput] {
        guard let type = HKQuantityType.quantityType(forIdentifier: id) else { return [] }
        let predicate = HKQuery.predicateForSamples(
            withStart: Date().addingTimeInterval(-Double(days) * 86400), end: Date(), options: []
        )
        return await withCheckedContinuation { cont in
            let q = HKSampleQuery(sampleType: type, predicate: predicate,
                                  limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, _ in
                let out = (samples as? [HKQuantitySample])?.map {
                    VitalSampleInput(metric: key,
                                     value: $0.quantity.doubleValue(for: unit) * scale,
                                     unit: "", at: $0.startDate)
                } ?? []
                cont.resume(returning: out)
            }
            store.execute(q)
        }
    }

    /// Per-calendar-day sums of a cumulative quantity (steps, distance, …).
    private func dailySums(
        _ id: HKQuantityTypeIdentifier, key: String, unit: HKUnit, days: Int
    ) async -> [VitalSampleInput] {
        guard let type = HKQuantityType.quantityType(forIdentifier: id) else { return [] }
        let cal = Calendar.current
        let start = cal.startOfDay(for: Date().addingTimeInterval(-Double(days) * 86400))
        var comps = DateComponents(); comps.day = 1
        return await withCheckedContinuation { cont in
            let q = HKStatisticsCollectionQuery(
                quantityType: type,
                quantitySamplePredicate: nil,
                options: .cumulativeSum,
                anchorDate: start,
                intervalComponents: comps
            )
            q.initialResultsHandler = { _, results, _ in
                var out: [VitalSampleInput] = []
                results?.enumerateStatistics(from: start, to: Date()) { stat, _ in
                    if let sum = stat.sumQuantity()?.doubleValue(for: unit), sum > 0 {
                        out.append(VitalSampleInput(metric: key, value: sum, unit: "",
                                                    at: stat.startDate))
                    }
                }
                cont.resume(returning: out)
            }
            store.execute(q)
        }
    }

    /// Total asleep hours per night over the last `days`, keyed by wake day —
    /// gives the multi-day sleep-debt signal an instant history.
    private func sleepByNight(days: Int) async -> [VitalSampleInput] {
        guard let type = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) else { return [] }
        let predicate = HKQuery.predicateForSamples(
            withStart: Date().addingTimeInterval(-Double(days) * 86400), end: Date(), options: []
        )
        let asleepValues: Set<Int> = [
            HKCategoryValueSleepAnalysis.asleepUnspecified.rawValue,
            HKCategoryValueSleepAnalysis.asleepCore.rawValue,
            HKCategoryValueSleepAnalysis.asleepDeep.rawValue,
            HKCategoryValueSleepAnalysis.asleepREM.rawValue,
        ]
        return await withCheckedContinuation { cont in
            let q = HKSampleQuery(sampleType: type, predicate: predicate,
                                  limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, _ in
                let cal = Calendar.current
                var perDay: [Date: Double] = [:]
                for s in (samples as? [HKCategorySample] ?? []) where asleepValues.contains(s.value) {
                    // Attribute the sleep to the wake day (endDate).
                    let day = cal.startOfDay(for: s.endDate)
                    perDay[day, default: 0] += s.endDate.timeIntervalSince(s.startDate)
                }
                let out = perDay.map { (day, seconds) in
                    VitalSampleInput(metric: "sleep_asleep_h", value: seconds / 3600.0,
                                     unit: "h", at: day.addingTimeInterval(8 * 3600))
                }
                cont.resume(returning: out)
            }
            store.execute(q)
        }
    }

    // MARK: - Feature 3: Workout detection + auto-log

    /// Begin observing for new workouts. On each one we look up the latest and
    /// broadcast it so the Train tab can offer a one-tap auto-log.
    func observeWorkouts() {
        guard isAvailable else { return }
        let workoutType = HKObjectType.workoutType()
        let query = HKObserverQuery(sampleType: workoutType, predicate: nil) { [weak self] _, completion, error in
            defer { completion() }
            guard error == nil else { return }
            Task { await self?.broadcastLatestWorkout() }
        }
        store.execute(query)
        store.enableBackgroundDelivery(for: workoutType, frequency: .immediate) { _, _ in }
    }

    private func broadcastLatestWorkout() async {
        guard let workout = await latestWorkout(within: 6 * 3600) else { return }
        await MainActor.run {
            NotificationCenter.default.post(
                name: Self.workoutDetected, object: nil, userInfo: ["workout": workout]
            )
        }
    }

    /// The most recent workout that ended within `seconds` of now, with its
    /// real duration / active energy / average heart rate filled in.
    func latestWorkout(within seconds: TimeInterval) async -> DetectedWorkout? {
        guard isAvailable else { return nil }
        let predicate = HKQuery.predicateForSamples(
            withStart: Date().addingTimeInterval(-seconds), end: Date(), options: []
        )
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)
        let workout: HKWorkout? = await withCheckedContinuation { cont in
            let q = HKSampleQuery(sampleType: .workoutType(), predicate: predicate,
                                  limit: 1, sortDescriptors: [sort]) { _, samples, _ in
                cont.resume(returning: samples?.first as? HKWorkout)
            }
            store.execute(q)
        }
        guard let workout else { return nil }

        let kcal = workout.statistics(for: HKQuantityType(.activeEnergyBurned))?
            .sumQuantity()?.doubleValue(for: .kilocalorie())
        let avgHr = await averageHeartRate(for: workout)

        return DetectedWorkout(
            durationMin: workout.duration / 60.0,
            activeKcal: kcal,
            avgHr: avgHr,
            workoutType: workout.workoutActivityType.coachName,
            endedAt: workout.endDate
        )
    }

    private func averageHeartRate(for workout: HKWorkout) async -> Double? {
        guard let hrType = HKQuantityType.quantityType(forIdentifier: .heartRate) else { return nil }
        let predicate = HKQuery.predicateForSamples(
            withStart: workout.startDate, end: workout.endDate, options: []
        )
        return await withCheckedContinuation { cont in
            let q = HKStatisticsQuery(quantityType: hrType, quantitySamplePredicate: predicate,
                                      options: .discreteAverage) { _, stats, _ in
                let bpm = stats?.averageQuantity()?
                    .doubleValue(for: .count().unitDivided(by: .minute()))
                cont.resume(returning: bpm)
            }
            store.execute(q)
        }
    }

    // MARK: - Query helpers

    /// Total asleep hours in the last 24h (sums all "asleep" category samples).
    private func lastNightSleepHours() async -> Double? {
        guard let type = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) else { return nil }
        let predicate = HKQuery.predicateForSamples(
            withStart: Date().addingTimeInterval(-24 * 3600), end: Date(), options: []
        )
        let asleepValues: Set<Int> = [
            HKCategoryValueSleepAnalysis.asleepUnspecified.rawValue,
            HKCategoryValueSleepAnalysis.asleepCore.rawValue,
            HKCategoryValueSleepAnalysis.asleepDeep.rawValue,
            HKCategoryValueSleepAnalysis.asleepREM.rawValue,
        ]
        return await withCheckedContinuation { cont in
            let q = HKSampleQuery(sampleType: type, predicate: predicate,
                                  limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, _ in
                let seconds = (samples as? [HKCategorySample])?
                    .filter { asleepValues.contains($0.value) }
                    .reduce(0.0) { $0 + $1.endDate.timeIntervalSince($1.startDate) } ?? 0
                cont.resume(returning: seconds > 0 ? seconds / 3600.0 : nil)
            }
            store.execute(q)
        }
    }

    private func mostRecentQuantity(_ id: HKQuantityTypeIdentifier, unit: HKUnit) async -> Double? {
        guard let type = HKQuantityType.quantityType(forIdentifier: id) else { return nil }
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)
        return await withCheckedContinuation { cont in
            let q = HKSampleQuery(sampleType: type, predicate: nil, limit: 1,
                                  sortDescriptors: [sort]) { _, samples, _ in
                let v = (samples?.first as? HKQuantitySample)?.quantity.doubleValue(for: unit)
                cont.resume(returning: v)
            }
            store.execute(q)
        }
    }

    /// Median of the daily samples over the last `days` — the user's own normal.
    private func medianQuantity(_ id: HKQuantityTypeIdentifier, unit: HKUnit, days: Int) async -> Double? {
        guard let type = HKQuantityType.quantityType(forIdentifier: id) else { return nil }
        let predicate = HKQuery.predicateForSamples(
            withStart: Date().addingTimeInterval(-Double(days) * 24 * 3600), end: Date(), options: []
        )
        return await withCheckedContinuation { cont in
            let q = HKSampleQuery(sampleType: type, predicate: predicate,
                                  limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, _ in
                let values = (samples as? [HKQuantitySample])?
                    .map { $0.quantity.doubleValue(for: unit) }
                    .sorted() ?? []
                guard !values.isEmpty else { cont.resume(returning: nil); return }
                cont.resume(returning: values[values.count / 2])
            }
            store.execute(q)
        }
    }
}

private extension HKWorkoutActivityType {
    /// A short, backend-friendly label for the workout kind.
    var coachName: String {
        switch self {
        case .traditionalStrengthTraining: return "traditionalStrengthTraining"
        case .functionalStrengthTraining:  return "functionalStrengthTraining"
        case .highIntensityIntervalTraining: return "hiit"
        case .running: return "running"
        case .cycling: return "cycling"
        case .walking: return "walking"
        case .coreTraining: return "coreTraining"
        case .crossTraining: return "crossTraining"
        case .mixedCardio: return "mixedCardio"
        default: return "other"
        }
    }
}
#endif
