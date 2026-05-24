// The growing world (Section 6).
//
// READ-ONLY (Section 6.3, Principle 2.6). No view in this file may compute
// currency, streak, or unlocks. Everything is fetched from the backend, which
// derives it from VerifiedEvents.
//
// Four-level zoom is exposed as a TabView (Summit / Milestones / Habits /
// Today), with a Settings sheet for reset.

import SwiftUI

struct WorldView: View {
    @EnvironmentObject var sessionStore: SessionStore
    @StateObject private var model = WorldViewModel()
    @State private var showSettings = false

    var body: some View {
        TabView {
            summitTab.tabItem { Label("Summit", systemImage: "mountain.2.fill") }
            milestonesTab.tabItem { Label("Milestones", systemImage: "flag.fill") }
            habitsTab.tabItem { Label("Habits", systemImage: "leaf.fill") }
            todayTab.tabItem { Label("Today", systemImage: "sun.max.fill") }
        }
        .tabBarMinimizeBehavior(.onScrollDown)
        .task { await model.refreshAll() }
        .sheet(isPresented: $showSettings) {
            SettingsSheet()
                .environmentObject(sessionStore)
        }
    }

    // MARK: - Tabs

    private var summitTab: some View {
        NavigationStack {
            ScrollView {
                SummitContent(world: model.world,
                              identityStatement: sessionStore.identityStatement)
                    .padding(.horizontal)
            }
            .contentMargins(.bottom, 100, for: .scrollContent)
            .refreshable { await model.refreshWorld() }
            .navigationTitle("Your summit")
            .toolbar { settingsButton; currencyToolbar }
        }
    }

    private var milestonesTab: some View {
        NavigationStack {
            Group {
                switch model.milestonesState {
                case .loading:
                    ProgressView().controlSize(.large)
                case .ready(let ms):
                    MilestonesList(milestones: ms)
                case .failed(let msg):
                    ErrorView(title: "Couldn't load milestones",
                              message: msg,
                              retry: { await model.refreshMilestones() })
                }
            }
            .refreshable { await model.refreshMilestones() }
            .navigationTitle("Milestones")
            .toolbar { settingsButton; currencyToolbar }
        }
    }

    private var habitsTab: some View {
        NavigationStack {
            ScrollView {
                HabitsContent(world: model.world)
                    .padding(.horizontal)
            }
            .contentMargins(.bottom, 100, for: .scrollContent)
            .refreshable { await model.refreshWorld() }
            .navigationTitle("Habits")
            .toolbar { settingsButton; currencyToolbar }
        }
    }

    private var todayTab: some View {
        NavigationStack {
            Group {
                switch model.followupsState {
                case .loading:
                    ProgressView().controlSize(.large)
                case .ready(let f):
                    TodayContent(followups: f)
                case .failed(let msg):
                    ErrorView(title: "Couldn't load today",
                              message: msg,
                              retry: { await model.refreshFollowups() })
                }
            }
            .refreshable { await model.refreshFollowups() }
            .navigationTitle("Today")
            .toolbar { settingsButton; currencyToolbar }
        }
    }

    // MARK: - Toolbars

    @ToolbarContentBuilder
    private var settingsButton: some ToolbarContent {
        ToolbarItem(placement: .topBarLeading) {
            Button {
                showSettings = true
            } label: {
                Image(systemName: "gearshape")
            }
            .accessibilityLabel("Settings")
        }
    }

    @ToolbarContentBuilder
    private var currencyToolbar: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            CurrencyBadge(world: model.world)
        }
    }
}

// MARK: - View model

@MainActor
final class WorldViewModel: ObservableObject {
    enum AsyncState<T> {
        case loading
        case ready(T)
        case failed(String)
    }

    @Published var world: World?
    @Published var milestonesState: AsyncState<[Milestone]> = .loading
    @Published var followupsState: AsyncState<[FollowUp]> = .loading

    func refreshAll() async {
        async let w: Void = refreshWorld()
        async let m: Void = refreshMilestones()
        async let f: Void = refreshFollowups()
        _ = await (w, m, f)
    }

    func refreshWorld() async {
        world = try? await CoachAPI.shared.world()
    }

    func refreshMilestones() async {
        milestonesState = .loading
        do {
            milestonesState = .ready(try await CoachAPI.shared.milestones())
        } catch {
            milestonesState = .failed(error.localizedDescription)
        }
    }

    func refreshFollowups() async {
        followupsState = .loading
        do {
            followupsState = .ready(try await CoachAPI.shared.openFollowups())
        } catch {
            followupsState = .failed(error.localizedDescription)
        }
    }
}

// MARK: - Currency badge

private struct CurrencyBadge: View {
    let world: World?
    private var currency: Int { world?.currency ?? 0 }
    private var streak: Int { world?.streakDays ?? 0 }

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "flame.fill")
                .foregroundStyle(.orange)
            Text("\(currency)")
                .fontWeight(.semibold)
                .monospacedDigit()
            Text("·")
                .foregroundStyle(.secondary)
            Text("\(streak)d")
                .monospacedDigit()
                .foregroundStyle(.secondary)
        }
        .font(.callout)
        .padding(.horizontal, 10)
        .padding(.vertical, 4)
        .glassEffect(in: Capsule())
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(currency) effort, \(streak) day streak")
    }
}

// MARK: - Summit tab

private struct SummitContent: View {
    let world: World?
    let identityStatement: String?

    var body: some View {
        // `identityStatement` is always set by IntakeView's submit handler before
        // WorldView becomes reachable (SessionStore.hasCompletedIntake gates this).
        // The empty-string check is defensive only.
        let statement = (identityStatement?.isEmpty == false)
            ? identityStatement!
            : "Your summit."

        VStack(spacing: 20) {
            // Identity — most important, lives high in the visual hierarchy.
            VStack(spacing: 10) {
                Text(statement)
                    .font(.title2.bold())
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                Text("The summit grows with every verified session.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 8)
            .padding(.top, 8)

            // Visual — decorative, OK if partially behind glass on small screens.
            Image(systemName: "mountain.2.fill")
                .font(.system(size: 84))
                .foregroundStyle(.tint)
                .symbolEffect(.pulse, options: .repeating, value: world?.currency)
                .padding(.vertical, 8)

            // Numbers — already in the toolbar badge, so overlap with the tab
            // bar's glass effect is acceptable.
            StatsCard(world: world)
        }
    }
}

private struct StatsCard: View {
    let world: World?
    var body: some View {
        HStack(spacing: 16) {
            stat(value: "\(world?.currency ?? 0)", label: "Effort")
            Divider().frame(height: 40)
            stat(value: "\(world?.streakDays ?? 0)", label: "Streak (days)")
            Divider().frame(height: 40)
            stat(value: "\(world?.longestStreak ?? 0)", label: "Longest")
        }
        .padding()
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
    }

    private func stat(value: String, label: String) -> some View {
        VStack(spacing: 4) {
            Text(value).font(.title2.bold()).monospacedDigit()
            Text(label).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}

// MARK: - Milestones tab

private struct MilestonesList: View {
    let milestones: [Milestone]
    var body: some View {
        if milestones.isEmpty {
            ContentUnavailableView(
                "No milestones yet",
                systemImage: "flag",
                description: Text("Once your program is built, you'll see waypoints here.")
            )
        } else {
            List(milestones) { m in
                HStack(spacing: 12) {
                    Image(systemName: m.achievedAt != nil ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(m.achievedAt != nil ? .green : .secondary)
                        .font(.title3)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(m.title).fontWeight(.semibold)
                        Text(m.description)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(.vertical, 4)
            }
            .listStyle(.insetGrouped)
        }
    }
}

// MARK: - Habits tab

private struct HabitsContent: View {
    let world: World?

    var body: some View {
        if let systems = world?.livingSystems, !systems.isEmpty {
            VStack(spacing: 12) {
                ForEach(Array(systems.keys.sorted()), id: \.self) { id in
                    let vitality = systems[id] ?? 0
                    HabitCard(name: "Strength training", vitality: vitality)
                }
                Text("A living system thrives while you sustain it.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.top, 4)
            }
            .padding(.top, 8)
        } else {
            ContentUnavailableView(
                "Habits aren't growing yet",
                systemImage: "leaf",
                description: Text("A living system thrives once you start reporting verified sessions.")
            )
        }
    }
}

private struct HabitCard: View {
    let name: String
    let vitality: Double
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "leaf.fill")
                    .foregroundStyle(vitalityColor)
                Text(name).font(.headline)
                Spacer()
                Text("\(Int(vitality * 100))%")
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            ProgressView(value: vitality)
                .tint(vitalityColor)
        }
        .padding()
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
    }

    private var vitalityColor: Color {
        if vitality > 0.7 { return .green }
        if vitality > 0.4 { return .yellow }
        return .orange
    }
}

// MARK: - Today tab

private struct TodayContent: View {
    let followups: [FollowUp]
    var body: some View {
        if followups.isEmpty {
            ContentUnavailableView(
                "Nothing owed",
                systemImage: "sun.max",
                description: Text("No open nudges. The coach will reach out when the moment fits.")
            )
        } else {
            List(followups) { f in
                VStack(alignment: .leading, spacing: 8) {
                    Text(f.actionTitle).font(.headline)
                    Text(f.prompt)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.vertical, 6)
            }
            .listStyle(.insetGrouped)
        }
    }
}

// MARK: - Settings sheet

private struct SettingsSheet: View {
    @EnvironmentObject var sessionStore: SessionStore
    @Environment(\.dismiss) var dismiss
    @State private var confirmReset = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Backend") {
                    LabeledContent("URL", value: "http://127.0.0.1:8765")
                        .font(.callout)
                }
                Section("Identity") {
                    LabeledContent("Statement",
                                   value: sessionStore.identityStatement ?? "(not set)")
                        .lineLimit(3)
                    LabeledContent("User", value: sessionStore.userId)
                }
                Section {
                    Button(role: .destructive) {
                        confirmReset = true
                    } label: {
                        Label("Reset onboarding", systemImage: "arrow.counterclockwise")
                    }
                } footer: {
                    Text("Clears your identity statement and intake completion locally. The backend still remembers your program until you reset its database.")
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .confirmationDialog("Reset onboarding?", isPresented: $confirmReset) {
                Button("Reset", role: .destructive) {
                    sessionStore.reset()
                    dismiss()
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("You'll go back through intake. Your verified history on the backend is unaffected.")
            }
        }
    }
}
