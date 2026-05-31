// Dev affordance — jump the app to any pre-built state without manually
// going through onboarding + 5 calibration sessions. Pairs with the
// /dev/seed backend endpoint in api/app.py.
//
// Surfaced via a small "Dev" button in WorldView's debug area. Not for
// production; the backend endpoint bypasses LLM-driven derivation and
// world mirror integrity.

import SwiftUI
import UserNotifications

struct DevScenarioSheet: View {
    @StateObject private var model = DevScenarioViewModel()
    @ObservedObject private var notifLog = NotificationLog.shared
    @State private var selectedGoal: String = "get_stronger"
    @State private var selectedScenario: String?
    @State private var applying = false
    @State private var lastApplied: String?
    @State private var notifStatus: String?
    @State private var authStatus: String?
    @State private var pendingCount: Int = 0
    @State private var burstCount: Int = 10
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                AtmosphericBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        notificationTools
                        intro
                        goalPicker
                        scenarioList
                        if let last = lastApplied {
                            appliedBanner(message: last)
                        }
                    }
                    .padding(18)
                }
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("Dev — seed state")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                        .foregroundStyle(.white.opacity(0.85))
                }
            }
            .task { await model.load() }
        }
    }

    // MARK: - Subviews

    /// Try local notifications without waiting for a scheduled slot, and see
    /// when reminders have actually fired.
    private var notificationTools: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionEyebrow(text: "REMINDERS", icon: "bell.fill")
            Text("Local notifications")
                .font(.title3.weight(.bold))
                .foregroundStyle(.white)
            Text("Send a test now (lock your phone to feel it land), or re-pull the weekly schedule from the coach.")
                .font(.footnote)
                .foregroundStyle(.white.opacity(0.65))
                .fixedSize(horizontal: false, vertical: true)

            // Live diagnostic: the actual permission state + how many reminders
            // are currently scheduled. If permission isn't "authorized", nothing
            // will ever fire — fix it in Settings › The Coach › Notifications.
            HStack(spacing: 6) {
                Image(systemName: authStatus == "authorized" ? "checkmark.shield.fill" : "exclamationmark.shield.fill")
                    .foregroundStyle(authStatus == "authorized" ? Theme.emerald : Theme.amber)
                Text("Permission: \(authStatus ?? "checking…")   ·   scheduled: \(pendingCount)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white.opacity(0.85))
            }
            .task { await loadNotifStatus() }

            HStack(spacing: 10) {
                Button {
                    Task {
                        notifStatus = await NotificationScheduler.shared.scheduleTest()
                        await loadNotifStatus()
                    }
                } label: {
                    Label("Test in 10s", systemImage: "bell.badge")
                        .font(.footnote.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(Theme.ember.opacity(0.22)))
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.ember)

                Button {
                    Task {
                        await NotificationScheduler.shared.refresh()
                        notifStatus = "Re-synced the weekly schedule."
                        await loadNotifStatus()
                    }
                } label: {
                    Label("Re-sync", systemImage: "arrow.clockwise")
                        .font(.footnote.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(Color.white.opacity(0.08)))
                }
                .buttonStyle(.plain)
                .foregroundStyle(.white.opacity(0.85))
            }

            // Stress test: fire a burst of notifications 2s apart, regardless of
            // app state. Lock the phone after tapping and watch them roll in.
            Divider().overlay(Color.white.opacity(0.12))
            Stepper(value: $burstCount, in: 1...60) {
                Text("Burst size: \(burstCount)")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.white.opacity(0.85))
            }
            .tint(Theme.ember)

            HStack(spacing: 10) {
                Button {
                    Task {
                        notifStatus = await NotificationScheduler.shared.scheduleBurst(count: burstCount, intervalSeconds: 2)
                        await loadNotifStatus()
                    }
                } label: {
                    Label("Stress: \(burstCount) × 2s", systemImage: "waveform.path")
                        .font(.footnote.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(Theme.ember.opacity(0.22)))
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.ember)

                Button {
                    Task {
                        notifStatus = await NotificationScheduler.shared.cancelTests()
                        await loadNotifStatus()
                    }
                } label: {
                    Label("Clear tests", systemImage: "xmark.circle")
                        .font(.footnote.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(Color.white.opacity(0.08)))
                }
                .buttonStyle(.plain)
                .foregroundStyle(.white.opacity(0.85))
            }

            if let status = notifStatus {
                Text(status)
                    .font(.caption)
                    .foregroundStyle(Theme.gold)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if !notifLog.events.isEmpty {
                Divider().overlay(Color.white.opacity(0.12))
                Text("Recent fires")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white.opacity(0.5))
                ForEach(notifLog.events.prefix(8)) { e in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(e.date, format: .dateTime.weekday().hour().minute())
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.white.opacity(0.85))
                        Text(e.title)
                            .font(.caption)
                            .foregroundStyle(.white.opacity(0.6))
                            .lineLimit(1)
                        Spacer(minLength: 0)
                        Text(e.how)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(Theme.emerald)
                    }
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCardTinted(Theme.ember)
    }

    private var intro: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionEyebrow(text: "ITERATE FAST", icon: "bolt.fill")
            Text("Skip onboarding")
                .font(.title3.weight(.bold))
                .foregroundStyle(.white)
            Text("Pick a goal + a canned state. Wipes the current user and seeds it directly — no clicking through calibration.")
                .font(.footnote)
                .foregroundStyle(.white.opacity(0.65))
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCardTinted(Theme.amber)
    }

    private var goalPicker: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionEyebrow(text: "GOAL")
            Picker("Goal", selection: $selectedGoal) {
                ForEach(model.goals, id: \.value) { g in
                    Text(g.label).tag(g.value)
                }
            }
            .pickerStyle(.segmented)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }

    private var scenarioList: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionEyebrow(text: "SCENARIO")
            if model.loading {
                HStack {
                    Spacer()
                    ProgressView().tint(Theme.ember)
                    Spacer()
                }
                .padding()
            } else if let err = model.loadError {
                Text("Couldn't load scenarios: \(err)")
                    .font(.footnote)
                    .foregroundStyle(Theme.amber)
            } else {
                VStack(spacing: 10) {
                    ForEach(model.scenarios, id: \.name) { s in
                        scenarioRow(s)
                    }
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }

    private func scenarioRow(_ s: DevScenario) -> some View {
        Button {
            Task { await apply(scenario: s) }
        } label: {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(s.label)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(s.description)
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.55))
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
                if applying && selectedScenario == s.name {
                    ProgressView().tint(Theme.ember)
                } else {
                    Image(systemName: "arrow.right.circle.fill")
                        .font(.title3)
                        .foregroundStyle(Theme.ember)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(Color.white.opacity(0.06))
                    .overlay {
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .strokeBorder(Color.white.opacity(0.12), lineWidth: 1)
                    }
            }
        }
        .buttonStyle(.plain)
        .disabled(applying)
    }

    private func appliedBanner(message: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "checkmark.seal.fill")
                .foregroundStyle(Theme.emerald)
            Text(message)
                .font(.footnote.weight(.semibold))
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCardTinted(Theme.emerald)
    }

    // MARK: - Notifications

    private func loadNotifStatus() async {
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        switch settings.authorizationStatus {
        case .authorized: authStatus = "authorized"
        case .denied: authStatus = "DENIED — turn on in Settings"
        case .notDetermined: authStatus = "not asked yet"
        case .provisional: authStatus = "provisional (quiet)"
        case .ephemeral: authStatus = "ephemeral"
        @unknown default: authStatus = "unknown"
        }
        pendingCount = await center.pendingNotificationRequests().count
    }

    // MARK: - Apply

    private func apply(scenario: DevScenario) async {
        selectedScenario = scenario.name
        applying = true
        defer { applying = false }
        do {
            let result = try await CoachAPI.shared.seedScenario(
                goal: selectedGoal, scenario: scenario.name
            )
            lastApplied = result.summary
            // Broadcast so all view models re-fetch — same hook used by
            // log/reply/tick paths.
            await MainActor.run {
                NotificationCenter.default.post(name: .coachStateChanged, object: nil)
            }
        } catch {
            lastApplied = "Failed: \(error.localizedDescription)"
        }
    }
}

// MARK: - View model

@MainActor
final class DevScenarioViewModel: ObservableObject {
    @Published var goals: [DevGoal] = []
    @Published var scenarios: [DevScenario] = []
    @Published var loading = false
    @Published var loadError: String?

    func load() async {
        loading = true
        defer { loading = false }
        do {
            let listing = try await CoachAPI.shared.devScenarios()
            self.goals = listing.goals
            self.scenarios = listing.scenarios
        } catch {
            self.loadError = error.localizedDescription
        }
    }
}

// MARK: - DTOs

struct DevGoal: Codable {
    let value: String
    let label: String
}

struct DevScenario: Codable {
    let name: String
    let label: String
    let description: String
    let phase: String
    let votes: Int
    let streakDays: Int
}

struct DevScenarioListing: Codable {
    let goals: [DevGoal]
    let scenarios: [DevScenario]
}

struct DevSeedResult {
    let summary: String
}
