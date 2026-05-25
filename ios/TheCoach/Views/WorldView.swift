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
            TrainView().tabItem { Label("Train", systemImage: "dumbbell.fill") }
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
            .navigationBarTitleDisplayMode(.inline)
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
            ScrollView {
                TodayContent(
                    followupsState: model.followupsState,
                    coachState: model.coachState,
                    isTicking: model.isTicking,
                    onTick: { await model.runTickAndRefresh() },
                    refresh: { await model.refreshAll() }
                )
                .padding(.horizontal)
            }
            .contentMargins(.bottom, 100, for: .scrollContent)
            .refreshable { await model.refreshAll() }
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
    @Published var coachState: CoachState?
    @Published var isTicking: Bool = false
    @Published var lastTick: DevTickResult?

    private var observer: NSObjectProtocol?

    init() {
        observer = NotificationCenter.default.addObserver(
            forName: .coachStateChanged,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            // Hop to MainActor — closure is nominally any-actor.
            Task { @MainActor [weak self] in await self?.refreshAll() }
        }
    }

    deinit {
        if let observer { NotificationCenter.default.removeObserver(observer) }
    }

    func refreshAll() async {
        async let w: Void = refreshWorld()
        async let m: Void = refreshMilestones()
        async let f: Void = refreshFollowups()
        async let c: Void = refreshCoachState()
        _ = await (w, m, f, c)
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

    func refreshCoachState() async {
        coachState = try? await CoachAPI.shared.coachState()
    }

    func runTickAndRefresh() async {
        isTicking = true
        defer { isTicking = false }
        lastTick = try? await CoachAPI.shared.devTick()
        await refreshAll()
    }
}

// MARK: - Currency badge

private struct CurrencyBadge: View {
    let world: World?
    private var currency: Int { world?.currency ?? 0 }
    private var streak: Int { world?.streakDays ?? 0 }

    var body: some View {
        HStack(spacing: 5) {
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
        .font(.footnote)
        .padding(.horizontal, 10)
        .padding(.vertical, 4)
        .fixedSize()
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

        VStack(spacing: 16) {
            // Identity — most important, lives high in the visual hierarchy.
            VStack(spacing: 6) {
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

            // Visual — a growing mountain. Snow cap rises with effort,
            // an aura warms with streak. Read-only reflection (Principle 2.6).
            SummitHero(
                currency: world?.currency ?? 0,
                streakDays: world?.streakDays ?? 0
            )
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
        VStack(spacing: 12) {
            HStack(spacing: 16) {
                stat(value: "\(world?.currency ?? 0)", label: "Effort")
                Divider().frame(height: 40)
                stat(value: "\(world?.streakDays ?? 0)", label: "Streak (days)")
                Divider().frame(height: 40)
                stat(value: "\(world?.longestStreak ?? 0)", label: "Longest")
            }
            VotesRow(votes: world?.identityVotes ?? 0)
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

/// Atomic Habits ch.2 — every verified action is a vote for who you're becoming.
/// We surface this on the Summit because it's the most important number in the app.
private struct VotesRow: View {
    let votes: Int

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "checkmark.seal.fill")
                .foregroundStyle(.tint)
                .font(.title3)
            VStack(alignment: .leading, spacing: 2) {
                Text("\(votes) \(votes == 1 ? "vote" : "votes") cast")
                    .font(.subheadline.weight(.semibold).monospacedDigit())
                Text("for who you're becoming")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(.horizontal, 4)
        .padding(.top, 2)
    }
}

// MARK: - Summit hero

private struct SummitHero: View {
    let currency: Int
    let streakDays: Int

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var growth: Double { min(Double(currency) / 50.0, 1.0) }
    private var aura: Double { min(Double(streakDays) / 30.0, 1.0) }

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [Color.accentColor.opacity(0.10), Color.accentColor.opacity(0.02)],
                startPoint: .top,
                endPoint: .bottom
            )

            RadialGradient(
                colors: [Color.accentColor.opacity(0.35 * aura), .clear],
                center: UnitPoint(x: 0.5, y: 0.32),
                startRadius: 8,
                endRadius: 160
            )

            BackRangeShape()
                .fill(Color.accentColor.opacity(0.18))
                .frame(height: heroHeight * 0.60)
                .frame(maxHeight: .infinity, alignment: .bottom)

            FrontMountainShape()
                .fill(Color.accentColor.gradient)
                .frame(height: mountainHeight)
                .frame(maxHeight: .infinity, alignment: .bottom)

            FrontMountainShape()
                .fill(Color.white.opacity(0.92))
                .frame(height: mountainHeight)
                .frame(maxHeight: .infinity, alignment: .bottom)
                .mask(alignment: .top) {
                    Rectangle()
                        .frame(height: snowMaskHeight)
                        .frame(maxHeight: .infinity, alignment: .top)
                }

            Image(systemName: "star.fill")
                .font(.title2.weight(.bold))
                .foregroundStyle(.white)
                .shadow(color: Color.accentColor.opacity(0.9), radius: 14)
                .shadow(color: Color.accentColor.opacity(0.55), radius: 5)
                .offset(y: starOffsetY)
                .symbolEffect(.pulse, options: .repeating, isActive: !reduceMotion)
        }
        .frame(height: heroHeight)
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .animation(.spring(response: 0.55, dampingFraction: 0.85), value: growth)
        .animation(.spring(response: 0.55, dampingFraction: 0.85), value: aura)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Your summit, currency \(currency), streak \(streakDays) days")
    }

    private let heroHeight: CGFloat = 220
    private let mountainHeight: CGFloat = 200
    // Peak in hero coords: bottom-aligned mountain's peak sits at
    // heroHeight - mountainHeight + mountainHeight * peakRatio.
    private var peakY: CGFloat { heroHeight - mountainHeight + mountainHeight * 0.30 }

    // Snow line sits just above the peak when growth=0 (no snow) and
    // descends with effort, never below the mountain's mid-flank.
    private var snowMaskHeight: CGFloat {
        let minHeight = peakY - 8
        let maxHeight = peakY + 80
        return minHeight + (maxHeight - minHeight) * CGFloat(growth)
    }

    // Offset is from the ZStack's center, hence subtracting half the height.
    private var starOffsetY: CGFloat { peakY - heroHeight / 2 }
}

private struct FrontMountainShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let w = rect.width
        let h = rect.height
        path.move(to: CGPoint(x: w * 0.10, y: h))
        path.addLine(to: CGPoint(x: w * 0.36, y: h * 0.58))
        path.addLine(to: CGPoint(x: w * 0.46, y: h * 0.66))
        path.addLine(to: CGPoint(x: w * 0.55, y: h * 0.30))
        path.addLine(to: CGPoint(x: w * 0.66, y: h * 0.52))
        path.addLine(to: CGPoint(x: w * 0.78, y: h * 0.68))
        path.addLine(to: CGPoint(x: w * 0.90, y: h))
        path.closeSubpath()
        return path
    }
}

private struct BackRangeShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let w = rect.width
        let h = rect.height
        path.move(to: CGPoint(x: 0, y: h))
        path.addLine(to: CGPoint(x: w * 0.08, y: h * 0.72))
        path.addLine(to: CGPoint(x: w * 0.22, y: h * 0.55))
        path.addLine(to: CGPoint(x: w * 0.36, y: h * 0.78))
        path.addLine(to: CGPoint(x: w * 0.52, y: h * 0.48))
        path.addLine(to: CGPoint(x: w * 0.68, y: h * 0.66))
        path.addLine(to: CGPoint(x: w * 0.82, y: h * 0.54))
        path.addLine(to: CGPoint(x: w, y: h * 0.72))
        path.addLine(to: CGPoint(x: w, y: h))
        path.closeSubpath()
        return path
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
        HStack(spacing: 16) {
            VitalityRing(vitality: vitality)
                .frame(width: 64, height: 64)

            VStack(alignment: .leading, spacing: 4) {
                Text(name).font(.headline)
                Text(vitalityLabel)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(vitalityColor)
                Text("\(Int(vitality * 100))% vitality")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            Spacer(minLength: 0)
        }
        .padding()
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
        .animation(.spring(response: 0.55, dampingFraction: 0.85), value: vitality)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(name), \(vitalityLabel), \(Int(vitality * 100)) percent vitality")
    }

    private var vitalityColor: Color {
        if vitality > 0.7 { return .green }
        if vitality > 0.4 { return .yellow }
        if vitality > 0.0 { return .orange }
        return .secondary
    }

    private var vitalityLabel: String {
        if vitality > 0.7 { return "Thriving" }
        if vitality > 0.4 { return "Steady" }
        if vitality > 0.0 { return "Wilting" }
        return "Dormant"
    }
}

private struct VitalityRing: View {
    let vitality: Double

    private var color: Color {
        if vitality > 0.7 { return .green }
        if vitality > 0.4 { return .yellow }
        if vitality > 0.0 { return .orange }
        return .secondary
    }

    var body: some View {
        ZStack {
            Circle()
                .stroke(color.opacity(0.18), lineWidth: 6)
            Circle()
                .trim(from: 0, to: max(0.02, vitality))
                .stroke(color.gradient, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Image(systemName: "leaf.fill")
                .font(.title3)
                .foregroundStyle(color.gradient)
        }
    }
}

// MARK: - Today tab

private struct TodayContent: View {
    let followupsState: WorldViewModel.AsyncState<[FollowUp]>
    let coachState: CoachState?
    let isTicking: Bool
    let onTick: () async -> Void
    let refresh: () async -> Void
    @State private var selected: FollowUp?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // The "from your coach" moment — surfaced from the journal when
            // the brain has something worth saying. Sits ABOVE the last
            // nudge because it's the rarer + higher-signal thing.
            if let obs = coachState?.latestObservation {
                CoachObservationCard(entry: obs)
            }

            // Last nudge or no-nudge-yet state — the brain's most recent move.
            if let nudge = coachState?.lastNudge {
                LastNudgeCard(nudge: nudge)
            } else if let c = coachState, c.hasProgram {
                EmptyNudgeCard()
            }

            // Followups owed — Rubric A4 loop-closing surface.
            FollowupsSection(state: followupsState, onSelect: { selected = $0 })

            // Dev affordance: trigger a tick without APNs/cron in the loop yet.
            CoachDevCard(isTicking: isTicking, onTick: { Task { await onTick() } })
                .padding(.top, 4)
        }
        .padding(.vertical, 12)
        .sheet(item: $selected, onDismiss: { Task { await refresh() } }) { followup in
            NudgeReplyView(nudgeId: followup.nudgeId, defaultOutcome: "done")
                .presentationDetents([.medium, .large])
        }
    }
}

/// "From your coach" card — surfaces an LLM-authored observation the brain
/// thinks the user should actually hear. Distinct visual treatment from the
/// nudge card so it reads as the coach speaking, not the app firing.
private struct CoachObservationCard: View {
    let entry: JournalEntrySnapshot

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "quote.opening")
                    .foregroundStyle(.tint)
                Text("FROM YOUR COACH")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .tracking(0.8)
            }
            Text(entry.text)
                .font(.body)
                .foregroundStyle(.primary)
            if let reason = entry.reasonForSurface, !reason.isEmpty {
                Text(reason)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color.accentColor.opacity(0.08))
                .overlay {
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(Color.accentColor.opacity(0.25), lineWidth: 1)
                }
        }
    }
}

private struct LastNudgeCard: View {
    let nudge: NudgeSnapshot

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "megaphone.fill")
                    .foregroundStyle(.tint)
                Text("LATEST FROM THE COACH")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                Text(relativeTime)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            Text(nudge.headline)
                .font(.headline)
                .fixedSize(horizontal: false, vertical: true)
            Text(nudge.body)
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)
            if let ii = nudge.implementationIntention, !ii.isEmpty {
                Text(ii)
                    .font(.footnote.italic())
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 8) {
                outcomeBadge
                Text("·").foregroundStyle(.tertiary)
                Text(nudge.firedBecause)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .lineLimit(2)
                    .truncationMode(.middle)
            }
            .padding(.top, 4)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
    }

    private var relativeTime: String {
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .abbreviated
        return f.localizedString(for: nudge.firedAt, relativeTo: Date())
    }

    @ViewBuilder
    private var outcomeBadge: some View {
        let label = nudge.outcome.capitalized
        let color: Color = {
            switch nudge.outcome {
            case "done":     return .green
            case "partial":  return .yellow
            case "skipped", "ignored": return .gray
            default:         return .secondary
            }
        }()
        Text(label)
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.18), in: Capsule())
            .foregroundStyle(color)
    }
}

private struct EmptyNudgeCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Coach hasn't pushed yet today", systemImage: "moon.zzz.fill")
                .font(.subheadline.weight(.semibold))
            Text("Silence is a feature. The brain fires only when an opportunity opens. Tap below to run a check.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
    }
}

private struct FollowupsSection: View {
    let state: WorldViewModel.AsyncState<[FollowUp]>
    let onSelect: (FollowUp) -> Void

    var body: some View {
        switch state {
        case .loading:
            HStack { Spacer(); ProgressView(); Spacer() }.padding()
        case .failed(let msg):
            VStack(alignment: .leading, spacing: 4) {
                Label("Couldn't load follow-ups", systemImage: "exclamationmark.triangle")
                    .font(.subheadline)
                    .foregroundStyle(.orange)
                Text(msg).font(.caption).foregroundStyle(.secondary)
            }
            .padding()
            .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
        case .ready(let followups):
            if followups.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Label("Nothing owed", systemImage: "checkmark.seal")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.green)
                    Text("The coach isn't waiting on a reply. Nothing to clean up.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    Text("FOLLOW-UPS OWED")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    ForEach(followups) { f in
                        Button {
                            onSelect(f)
                        } label: {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(f.actionTitle).font(.subheadline.weight(.semibold))
                                    .foregroundStyle(.primary)
                                Text(f.prompt)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            .padding()
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.yellow.opacity(0.10), in: RoundedRectangle(cornerRadius: 14))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }
}

private struct CoachDevCard: View {
    let isTicking: Bool
    let onTick: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label("Coach engine", systemImage: "cpu")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
            }
            Text("Trigger a tick to wake the brain now (dev affordance — replaces APNs/cron locally).")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Button(action: onTick) {
                HStack {
                    if isTicking { ProgressView().controlSize(.small) }
                    Text(isTicking ? "Ticking…" : "Tick now")
                        .fontWeight(.semibold)
                        .frame(maxWidth: .infinity)
                }
                .padding(.vertical, 2)
            }
            .buttonStyle(.bordered)
            .controlSize(.regular)
            .disabled(isTicking)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.tertiarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
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
