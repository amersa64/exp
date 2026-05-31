// Gym Radar (Feature 2, Section 8.1) — the location half of the iPhone signals.
//
// The brain LEARNS where the user trains: every time a session starts we post
// the current coordinates and the backend folds them into a running centroid.
// Once that place is "monitorable" we register a CoreLocation geofence around
// it. Crossing the fence drives contextual coaching:
//
//   arrived  → "you're at the gym, today's session is ready" (+ surface it)
//   departed → "log it so it counts" if nothing's been logged today
//
// CoreLocation region monitoring keeps working when the app is backgrounded or
// killed, so the nudge lands at the door — the whole point.

import Foundation
import CoreLocation
import UserNotifications

@MainActor
final class LocationManager: NSObject, ObservableObject {
    static let shared = LocationManager()

    private let manager = CLLocationManager()
    private let regionId = "coach.training-place"

    /// True while the phone is inside the learned gym geofence — drives the
    /// "At the gym now" badge on the Train tab.
    @Published var atGym = false
    /// The most recent contextual line the coach returned for a crossing.
    @Published var lastCoachLine: String?
    /// Set true when an arrival says "surface today's session" so the Train
    /// tab can auto-present / highlight it.
    @Published var shouldSurfaceSession = false

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        manager.allowsBackgroundLocationUpdates = false  // region monitoring only
    }

    // MARK: - Lifecycle

    /// Ask for location permission and, if we already learned a place, start
    /// fencing it. Always-authorization is what lets the geofence fire in the
    /// background; we degrade gracefully to when-in-use.
    func start() {
        manager.requestAlwaysAuthorization()
        Task { await refreshGeofence() }
    }

    /// Post the current coordinates so the brain can learn / refine the place.
    /// Call when a session starts or is logged — that's the ground truth of
    /// "this is where I train". Then re-arm the geofence with the new centroid.
    func observeTrainingLocation() {
        manager.requestLocation()  // one-shot; delivered to didUpdateLocations
    }

    /// Pull the learned place from the backend and (re)register the geofence.
    func refreshGeofence() async {
        guard CLLocationManager.isMonitoringAvailable(for: CLCircularRegion.self) else { return }
        guard let place = try? await CoachAPI.shared.learnedPlace(),
              place.monitorable, let lat = place.lat, let lon = place.lon else {
            return
        }
        for region in manager.monitoredRegions where region.identifier == regionId {
            manager.stopMonitoring(for: region)
        }
        let region = CLCircularRegion(
            center: CLLocationCoordinate2D(latitude: lat, longitude: lon),
            radius: place.radiusM ?? 150,
            identifier: regionId
        )
        region.notifyOnEntry = true
        region.notifyOnExit = true
        manager.startMonitoring(for: region)
    }

    // MARK: - Crossing handling

    private func handleCrossing(_ event: String) {
        Task {
            guard let result = try? await CoachAPI.shared.locationEvent(event) else { return }
            await MainActor.run {
                self.atGym = (event == "arrived")
                self.lastCoachLine = result.coachLine
                self.shouldSurfaceSession = result.surfaceSession
            }
            if let line = result.coachLine {
                Self.notify(title: event == "arrived" ? "You're at the gym" : "On your way out?",
                            body: line)
            }
            NotificationCenter.default.post(name: .coachStateChanged, object: nil)
        }
    }

    private static func notify(title: String, body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        let req = UNNotificationRequest(
            identifier: UUID().uuidString, content: content, trigger: nil
        )
        UNUserNotificationCenter.current().add(req)
    }
}

extension LocationManager: CLLocationManagerDelegate {
    nonisolated func locationManager(_ manager: CLLocationManager, didEnterRegion region: CLRegion) {
        Task { @MainActor in handleCrossing("arrived") }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didExitRegion region: CLRegion) {
        Task { @MainActor in handleCrossing("departed") }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let loc = locations.last else { return }
        let lat = loc.coordinate.latitude, lon = loc.coordinate.longitude
        Task {
            // Teach the brain this location, then re-arm the fence with the
            // refined centroid.
            _ = try? await CoachAPI.shared.observePlace(lat: lat, lon: lon)
            await self.refreshGeofence()
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didChangeAuthorization status: CLAuthorizationStatus) {
        if status == .authorizedAlways || status == .authorizedWhenInUse {
            Task { @MainActor in await refreshGeofence() }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // One-shot requestLocation failures are non-fatal — we'll get the next
        // observation on the next session start.
    }
}
