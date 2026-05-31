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
    @State private var activeSheet: ActiveSheet?

    /// Single source of truth for which sheet is up. We use `.sheet(item:)`
    /// (not multiple `.sheet(isPresented:)` modifiers) because stacking two
    /// isPresented sheets on the same view is a known SwiftUI gotcha — only
    /// one of them actually presents.
    enum ActiveSheet: Identifiable {
        case settings
        case dev
        var id: Self { self }
    }

    /// Which of the 3 v2 tabs is showing. Coach is the default landing (the
    /// cold open shows the coach speaking, not a workout card).
    enum Tab: Hashable { case coach, now, becoming }
    @State private var tab: Tab = .coach

    var body: some View {
        TabView(selection: $tab) {
            CoachTabView(
                onShowSession: { tab = .now },
                onOpenSettings: { activeSheet = .settings },
                onOpenDev: { activeSheet = .dev },
                onEndProgram: { sessionStore.reset() }
            )
            .tabItem { Label("Coach", systemImage: "quote.bubble.fill") }
            .tag(Tab.coach)

            TrainView()
                .tabItem { Label("Now", systemImage: "dumbbell.fill") }
                .tag(Tab.now)

            becomingTab
                .tabItem { Label("Becoming", systemImage: "mountain.2.fill") }
                .tag(Tab.becoming)
        }
        .tabBarMinimizeBehavior(.onScrollDown)
        .task { await model.refreshAll() }
        .sheet(item: $activeSheet,
               onDismiss: { Task { await model.refreshAll() } }) { sheet in
            switch sheet {
            case .settings:
                SettingsSheet().environmentObject(sessionStore)
            case .dev:
                DevScenarioSheet()
            }
        }
    }

    // MARK: - Becoming tab (Summit + Milestones + Habits folded into one)

    private var becomingTab: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 26) {
                    SummitContent(world: model.world,
                                  identityStatement: sessionStore.identityStatement,
                                  vitals: model.vitals)
                    becomingMilestones
                    becomingHabits
                }
                .padding(.horizontal, 18)
            }
            .scrollContentBackground(.hidden)
            .background(AtmosphericBackground())
            .contentMargins(.bottom, 100, for: .scrollContent)
            .refreshable { await model.refreshAll() }
            .navigationTitle("Becoming")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar { settingsButton; votesToolbar }
        }
    }

    @ViewBuilder
    private var becomingMilestones: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionEyebrow(text: "MILESTONES", icon: "flag.fill")
            switch model.milestonesState {
            case .loading:
                HStack { Spacer(); ProgressView().tint(Theme.ember); Spacer() }.padding()
            case .ready(let ms):
                MilestonesList(milestones: ms)
            case .failed(let msg):
                ErrorView(title: "Couldn't load milestones", message: msg,
                          retry: { await model.refreshMilestones() })
            }
        }
    }

    private var becomingHabits: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionEyebrow(text: "HABITS", icon: "leaf.fill")
            HabitsContent(world: model.world)
        }
    }

    // MARK: - Toolbars

    @ToolbarContentBuilder
    private var settingsButton: some ToolbarContent {
        ToolbarItem(placement: .topBarLeading) {
            Button {
                activeSheet = .settings
            } label: {
                Image(systemName: "gearshape")
                    .foregroundStyle(.white.opacity(0.85))
            }
            .accessibilityLabel("Settings")
        }
        // Dev affordance — seed the user to a canned scenario for fast
        // iteration. See DevScenarioSheet.swift.
        ToolbarItem(placement: .topBarLeading) {
            Button {
                activeSheet = .dev
            } label: {
                Image(systemName: "wand.and.stars")
                    .foregroundStyle(Theme.amber.opacity(0.85))
            }
            .accessibilityLabel("Dev scenarios")
        }
    }

    @ToolbarContentBuilder
    private var votesToolbar: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            VotesBadge(votes: model.world?.identityVotes ?? 0)
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
    @Published var vitals: VitalsSummary?
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
        async let v: Void = refreshVitals()
        _ = await (w, m, f, c, v)
    }

    func refreshVitals() async {
        vitals = try? await CoachAPI.shared.vitalsSummary()
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
        HStack(spacing: 6) {
            Image(systemName: "flame.fill")
                .foregroundStyle(Theme.emberGradient)
                .shadow(color: Theme.ember.opacity(0.7), radius: 4)
            Text("\(currency)")
                .fontWeight(.bold)
                .monospacedDigit()
                .foregroundStyle(.white)
            Text("·").foregroundStyle(.white.opacity(0.35))
            Text("\(streak)d")
                .monospacedDigit()
                .foregroundStyle(.white.opacity(0.75))
        }
        .font(.footnote)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .fixedSize()
        .background {
            Capsule()
                .fill(.ultraThinMaterial)
                .overlay { Capsule().strokeBorder(Color.white.opacity(0.12), lineWidth: 1) }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(currency) effort, \(streak) day streak")
    }
}

// MARK: - Summit tab

private struct SummitContent: View {
    let world: World?
    let identityStatement: String?
    let vitals: VitalsSummary?

    var body: some View {
        // `identityStatement` is always set by IntakeView's submit handler before
        // WorldView becomes reachable (SessionStore.hasCompletedIntake gates this).
        // The empty-string check is defensive only.
        let statement = (identityStatement?.isEmpty == false)
            ? identityStatement!
            : "Your summit."

        VStack(spacing: 22) {
            // Identity — most important, lives high in the visual hierarchy.
            VStack(spacing: 10) {
                SectionEyebrow(text: "WHO YOU'RE BECOMING", icon: "sparkles")
                Text(statement)
                    .font(.system(.title, design: .serif, weight: .bold))
                    .foregroundStyle(.white)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                Text("The summit grows with every verified session.")
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.55))
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 8)
            .padding(.top, 6)

            // Becoming hero — embers rising from the user's identity into a
            // sky of past votes. The flame's brightness scales with streak;
            // each cast vote becomes a star above. Replaces the previous
            // pellet-flow funnel-and-cup visualization, which read as failure
            // modes falling into a cup. The type name is unchanged so this
            // call site keeps working; see PelletFlowHero.swift for rationale.
            PelletFlowHero(
                votes: world?.identityVotes ?? 0,
                identityStatement: identityStatement,
                streakDays: world?.streakDays ?? 0
            )

            // Numbers — already in the toolbar badge, so overlap with the tab
            // bar's glass effect is acceptable.
            StatsCard(world: world)

            VotesCard(votes: world?.identityVotes ?? 0)

            // "Your body is changing" — HealthKit trends tied to identity.
            if let vitals, !vitals.metrics.isEmpty {
                VitalsSection(vitals: vitals)
            }
        }
        .padding(.vertical, 8)
    }
}

// MARK: - Vitals dashboard (HealthKit trends)

/// Surfaces the broad-ingestion trends on the Summit: insight cards first
/// (weight trajectory, relative strength), then a compact list of every metric
/// the user has data for, colored by whether the movement is good.
private struct VitalsSection: View {
    let vitals: VitalsSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionEyebrow(text: "YOUR BODY IS CHANGING", icon: "waveform.path.ecg")

            ForEach(vitals.insights) { insight in
                VitalsInsightCard(insight: insight)
            }

            if !vitals.metrics.isEmpty {
                VStack(spacing: 0) {
                    ForEach(Array(vitals.metrics.enumerated()), id: \.element.id) { idx, m in
                        if idx > 0 { Divider().background(Color.white.opacity(0.06)) }
                        VitalMetricRow(metric: m)
                    }
                }
                .padding(14)
                .glassCard()
            }
        }
        .padding(.top, 4)
    }
}

private struct VitalsInsightCard: View {
    let insight: VitalsInsight

    private var tint: Color {
        switch insight.direction {
        case "down": return Theme.emerald   // weight down = good in this app's framing
        case "up":   return Theme.gold
        default:     return Theme.gold
        }
    }

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: insight.kind == "relative_strength" ? "figure.strengthtraining.traditional" : "chart.line.downtrend.xyaxis")
                .font(.title3)
                .foregroundStyle(tint)
                .frame(width: 28)
            VStack(alignment: .leading, spacing: 3) {
                Text(insight.title)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.white)
                Text(insight.detail)
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.7))
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCardTinted(tint)
    }
}

private struct VitalMetricRow: View {
    let metric: VitalMetricSummary

    private var changeColor: Color {
        guard let good = metric.directionGood else { return .white.opacity(0.5) }
        return good ? Theme.emerald : Theme.rose
    }

    private var changeText: String? {
        guard metric.change != 0 else { return nil }
        let arrow = metric.change > 0 ? "↑" : "↓"
        return "\(arrow) \(abs(metric.change).formatted(.number.precision(.fractionLength(0...1)))) \(metric.unit)"
    }

    var body: some View {
        HStack {
            Text(metric.label)
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.85))
            Spacer()
            Text("\(metric.current.formatted(.number.precision(.fractionLength(0...1)))) \(metric.unit)")
                .font(.subheadline.weight(.semibold).monospacedDigit())
                .foregroundStyle(.white)
            if let change = changeText {
                Text(change)
                    .font(.caption.weight(.bold).monospacedDigit())
                    .foregroundStyle(changeColor)
                    .frame(minWidth: 56, alignment: .trailing)
            } else {
                Text("·").foregroundStyle(.white.opacity(0.3))
                    .frame(minWidth: 56, alignment: .trailing)
            }
        }
        .padding(.vertical, 9)
        .accessibilityElement(children: .combine)
    }
}

private struct StatsCard: View {
    let world: World?
    var body: some View {
        HStack(spacing: 0) {
            stat(value: "\(world?.currency ?? 0)", label: "Effort")
            divider
            stat(value: "\(world?.streakDays ?? 0)", label: "Streak")
            divider
            stat(value: "\(world?.longestStreak ?? 0)", label: "Longest")
        }
        .padding(.vertical, 18)
        .padding(.horizontal, 12)
        .glassCard()
    }

    private func stat(value: String, label: String) -> some View {
        VStack(spacing: 6) {
            Text(value).displayNumber(size: 32)
            Text(label.uppercased())
                .font(.caption2.weight(.heavy))
                .tracking(1.2)
                .foregroundStyle(.white.opacity(0.55))
        }
        .frame(maxWidth: .infinity)
    }

    private var divider: some View {
        Rectangle()
            .fill(Color.white.opacity(0.10))
            .frame(width: 1, height: 36)
    }
}

/// Atomic Habits ch.2 — every verified action is a vote for who you're becoming.
/// We surface this on the Summit because it's the most important number in the app.
private struct VotesCard: View {
    let votes: Int

    var body: some View {
        HStack(spacing: 14) {
            ZStack {
                Circle()
                    .fill(Theme.emberGradient)
                    .frame(width: 44, height: 44)
                    .shadow(color: Theme.ember.opacity(0.55), radius: 12)
                Image(systemName: "checkmark.seal.fill")
                    .font(.title3.weight(.bold))
                    .foregroundStyle(.black)
            }
            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text("\(votes)")
                        .font(.title.weight(.heavy))
                        .monospacedDigit()
                        .foregroundStyle(.white)
                    Text(votes == 1 ? "vote cast" : "votes cast")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.white.opacity(0.7))
                }
                Text("for who you're becoming")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.5))
            }
            Spacer()
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }
}

// MARK: - Summit hero

private struct SummitHero: View {
    let currency: Int
    let streakDays: Int

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var twinkle = false

    private var growth: Double { min(Double(currency) / 50.0, 1.0) }
    private var aura: Double { min(Double(streakDays) / 30.0, 1.0) }

    var body: some View {
        ZStack {
            // Sky — deep night gradient.
            LinearGradient(
                colors: [Color(red: 0.05, green: 0.06, blue: 0.18),
                         Color(red: 0.15, green: 0.08, blue: 0.28)],
                startPoint: .top,
                endPoint: .bottom
            )

            // Stars scattered across the sky — only above the back range.
            StarsLayer()
                .opacity(0.7)

            // Aurora glow at the horizon — warms with streak.
            RadialGradient(
                colors: [Theme.ember.opacity(0.55 * aura),
                         Theme.violet.opacity(0.35 * aura),
                         .clear],
                center: UnitPoint(x: 0.5, y: 0.55),
                startRadius: 8,
                endRadius: 240
            )

            // Distant ridges.
            BackRangeShape()
                .fill(LinearGradient(
                    colors: [Color(red: 0.18, green: 0.10, blue: 0.32),
                             Color(red: 0.10, green: 0.06, blue: 0.20)],
                    startPoint: .top, endPoint: .bottom))
                .frame(height: heroHeight * 0.55)
                .frame(maxHeight: .infinity, alignment: .bottom)

            // Foreground summit — gradient body.
            FrontMountainShape()
                .fill(LinearGradient(
                    colors: [Color(red: 0.28, green: 0.16, blue: 0.42),
                             Color(red: 0.10, green: 0.05, blue: 0.18)],
                    startPoint: .top, endPoint: .bottom))
                .frame(height: mountainHeight)
                .frame(maxHeight: .infinity, alignment: .bottom)

            // Snow cap — rises as effort grows.
            FrontMountainShape()
                .fill(LinearGradient(
                    colors: [.white, Color(white: 0.85)],
                    startPoint: .top, endPoint: .bottom))
                .frame(height: mountainHeight)
                .frame(maxHeight: .infinity, alignment: .bottom)
                .mask(alignment: .top) {
                    Rectangle()
                        .frame(height: snowMaskHeight)
                        .frame(maxHeight: .infinity, alignment: .top)
                }
                .shadow(color: .white.opacity(0.35 + aura * 0.4), radius: 12)

            // Summit beacon — ember star at the peak, glow scales with streak.
            ZStack {
                Circle()
                    .fill(Theme.ember.opacity(0.55 + aura * 0.4))
                    .frame(width: 38, height: 38)
                    .blur(radius: 14)
                Image(systemName: "star.fill")
                    .font(.title2.weight(.bold))
                    .foregroundStyle(Theme.emberGradient)
                    .shadow(color: Theme.ember.opacity(0.95), radius: 12)
                    .shadow(color: Theme.gold.opacity(0.7), radius: 4)
                    .symbolEffect(.pulse, options: .repeating, isActive: !reduceMotion)
            }
            .offset(y: starOffsetY)
        }
        .frame(height: heroHeight)
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .strokeBorder(Color.white.opacity(0.10), lineWidth: 1)
        }
        .shadow(color: Theme.violet.opacity(0.35), radius: 30, y: 16)
        .animation(.spring(response: 0.55, dampingFraction: 0.85), value: growth)
        .animation(.spring(response: 0.55, dampingFraction: 0.85), value: aura)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Your summit, currency \(currency), streak \(streakDays) days")
        .onAppear {
            guard !reduceMotion else { return }
            withAnimation(.easeInOut(duration: 2.4).repeatForever(autoreverses: true)) {
                twinkle = true
            }
        }
    }

    private let heroHeight: CGFloat = 260
    private let mountainHeight: CGFloat = 220
    // Peak in hero coords: bottom-aligned mountain's peak sits at
    // heroHeight - mountainHeight + mountainHeight * peakRatio.
    private var peakY: CGFloat { heroHeight - mountainHeight + mountainHeight * 0.30 }

    // Snow line sits just above the peak when growth=0 (no snow) and
    // descends with effort, never below the mountain's mid-flank.
    private var snowMaskHeight: CGFloat {
        let minHeight = peakY - 8
        let maxHeight = peakY + 90
        return minHeight + (maxHeight - minHeight) * CGFloat(growth)
    }

    // Offset is from the ZStack's center, hence subtracting half the height.
    private var starOffsetY: CGFloat { peakY - heroHeight / 2 - 4 }
}

/// Static, deterministic starfield over the sky portion of the hero.
private struct StarsLayer: View {
    var body: some View {
        Canvas { ctx, size in
            // Deterministic pseudo-random — same field on every render.
            var seed: UInt64 = 0x5EED
            func rand() -> Double {
                seed = seed &* 6364136223846793005 &+ 1442695040888963407
                return Double((seed >> 11) & 0xFFFFFFFF) / Double(UInt32.max)
            }
            for _ in 0..<55 {
                let x = rand() * size.width
                let y = rand() * size.height * 0.55  // sky only
                let r = 0.4 + rand() * 1.3
                let opacity = 0.35 + rand() * 0.55
                ctx.fill(
                    Path(ellipseIn: CGRect(x: x - r, y: y - r, width: r * 2, height: r * 2)),
                    with: .color(.white.opacity(opacity))
                )
            }
        }
    }
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
            VStack(spacing: 16) {
                Image(systemName: "flag")
                    .font(.system(size: 56))
                    .foregroundStyle(Theme.emberGradient)
                    .shadow(color: Theme.ember.opacity(0.5), radius: 16)
                Text("No milestones yet")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(.white)
                Text("Once your program is built, you'll see waypoints here.")
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.6))
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(28)
            .frame(maxWidth: .infinity)
            .glassCard()
            .padding(.top, 24)
        } else {
            VStack(spacing: 12) {
                ForEach(milestones) { m in
                    MilestoneRow(milestone: m)
                }
            }
            .padding(.top, 12)
        }
    }
}

private struct MilestoneRow: View {
    let milestone: Milestone

    private var achieved: Bool { milestone.achievedAt != nil }

    var body: some View {
        HStack(spacing: 14) {
            ZStack {
                Circle()
                    .fill(achieved ? AnyShapeStyle(Theme.emberGradient)
                                   : AnyShapeStyle(Color.white.opacity(0.06)))
                    .frame(width: 38, height: 38)
                    .overlay {
                        Circle().strokeBorder(achieved ? Color.clear : Color.white.opacity(0.15), lineWidth: 1)
                    }
                Image(systemName: achieved ? "checkmark" : "flag.fill")
                    .font(.footnote.weight(.bold))
                    .foregroundStyle(achieved ? .black : .white.opacity(0.6))
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(milestone.title)
                    .font(.headline)
                    .foregroundStyle(.white)
                Text(milestone.description)
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.6))
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }
}

// MARK: - Habits tab

private struct HabitsContent: View {
    let world: World?

    var body: some View {
        if let systems = world?.livingSystems, !systems.isEmpty {
            VStack(spacing: 14) {
                ForEach(Array(systems.keys.sorted()), id: \.self) { id in
                    let vitality = systems[id] ?? 0
                    HabitCard(name: "Strength training", vitality: vitality)
                }
                Text("A living system thrives while you sustain it.")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.5))
                    .multilineTextAlignment(.center)
                    .padding(.top, 4)
            }
            .padding(.top, 12)
        } else {
            VStack(spacing: 16) {
                Image(systemName: "leaf")
                    .font(.system(size: 56))
                    .foregroundStyle(Theme.emerald.gradient)
                    .shadow(color: Theme.emerald.opacity(0.4), radius: 14)
                Text("Habits aren't growing yet")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(.white)
                Text("A living system thrives once you start reporting verified sessions.")
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.6))
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(28)
            .frame(maxWidth: .infinity)
            .glassCard()
            .padding(.top, 24)
        }
    }
}

private struct HabitCard: View {
    let name: String
    let vitality: Double

    var body: some View {
        HStack(spacing: 18) {
            VitalityRing(vitality: vitality)
                .frame(width: 72, height: 72)

            VStack(alignment: .leading, spacing: 6) {
                Text(name)
                    .font(.headline)
                    .foregroundStyle(.white)
                Text(vitalityLabel)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(vitalityColor)
                Text("\(Int(vitality * 100))% vitality")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.white.opacity(0.5))
            }

            Spacer(minLength: 0)
        }
        .padding(16)
        .glassCard()
        .animation(.spring(response: 0.55, dampingFraction: 0.85), value: vitality)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(name), \(vitalityLabel), \(Int(vitality * 100)) percent vitality")
    }

    private var vitalityColor: Color {
        if vitality > 0.7 { return Theme.emerald }
        if vitality > 0.4 { return Theme.amber }
        if vitality > 0.0 { return Theme.ember }
        return .white.opacity(0.5)
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
        if vitality > 0.7 { return Theme.emerald }
        if vitality > 0.4 { return Theme.amber }
        if vitality > 0.0 { return Theme.ember }
        return .white.opacity(0.4)
    }

    var body: some View {
        ZStack {
            Circle()
                .stroke(Color.white.opacity(0.08), lineWidth: 7)
            Circle()
                .trim(from: 0, to: max(0.02, vitality))
                .stroke(color.gradient, style: StrokeStyle(lineWidth: 7, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .shadow(color: color.opacity(0.6), radius: 6)
            Image(systemName: "leaf.fill")
                .font(.title3.weight(.semibold))
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
        .padding(.vertical, 16)
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
        VStack(alignment: .leading, spacing: 12) {
            SectionEyebrow(text: "FROM YOUR COACH", icon: "quote.opening")
            Text(entry.text)
                .font(.system(.title3, design: .serif, weight: .medium))
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)
            if let reason = entry.reasonForSurface, !reason.isEmpty {
                Text(reason)
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.55))
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCardTinted(Theme.ember)
    }
}

private struct LastNudgeCard: View {
    let nudge: NudgeSnapshot

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                SectionEyebrow(text: "LATEST FROM THE COACH", icon: "megaphone.fill")
                Spacer()
                Text(relativeTime)
                    .font(.caption2)
                    .foregroundStyle(.white.opacity(0.4))
            }
            Text(nudge.headline)
                .font(.headline)
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)
            Text(nudge.body)
                .font(.body)
                .foregroundStyle(.white.opacity(0.78))
                .fixedSize(horizontal: false, vertical: true)
            if let ii = nudge.implementationIntention, !ii.isEmpty {
                Text(ii)
                    .font(.footnote.italic())
                    .foregroundStyle(.white.opacity(0.55))
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 8) {
                outcomeBadge
                Text("·").foregroundStyle(.white.opacity(0.25))
                Text(nudge.firedBecause)
                    .font(.caption2)
                    .foregroundStyle(.white.opacity(0.4))
                    .lineLimit(2)
                    .truncationMode(.middle)
            }
            .padding(.top, 4)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
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
            case "done":     return Theme.emerald
            case "partial":  return Theme.amber
            case "skipped", "ignored": return .white.opacity(0.5)
            default:         return .white.opacity(0.5)
            }
        }()
        Text(label)
            .font(.caption2.weight(.bold))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.18), in: Capsule())
            .overlay { Capsule().strokeBorder(color.opacity(0.4), lineWidth: 1) }
            .foregroundStyle(color)
    }
}

private struct EmptyNudgeCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label {
                Text("Coach hasn't pushed yet today").foregroundStyle(.white)
            } icon: {
                Image(systemName: "moon.zzz.fill").foregroundStyle(Theme.violet)
            }
            .font(.subheadline.weight(.semibold))
            Text("Silence is a feature. The brain fires only when an opportunity opens. Tap below to run a check.")
                .font(.caption)
                .foregroundStyle(.white.opacity(0.55))
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }
}

private struct FollowupsSection: View {
    let state: WorldViewModel.AsyncState<[FollowUp]>
    let onSelect: (FollowUp) -> Void

    var body: some View {
        switch state {
        case .loading:
            HStack { Spacer(); ProgressView().tint(Theme.ember); Spacer() }.padding()
        case .failed(let msg):
            VStack(alignment: .leading, spacing: 4) {
                Label {
                    Text("Couldn't load follow-ups").foregroundStyle(.white)
                } icon: {
                    Image(systemName: "exclamationmark.triangle").foregroundStyle(Theme.amber)
                }
                .font(.subheadline)
                Text(msg).font(.caption).foregroundStyle(.white.opacity(0.55))
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .glassCard()
        case .ready(let followups):
            if followups.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Label {
                        Text("Nothing owed").foregroundStyle(.white)
                    } icon: {
                        Image(systemName: "checkmark.seal.fill").foregroundStyle(Theme.emerald)
                    }
                    .font(.subheadline.weight(.semibold))
                    Text("The coach isn't waiting on a reply. Nothing to clean up.")
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.55))
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .glassCard()
            } else {
                VStack(alignment: .leading, spacing: 10) {
                    SectionEyebrow(text: "FOLLOW-UPS OWED", icon: "envelope.fill")
                    ForEach(followups) { f in
                        Button {
                            onSelect(f)
                        } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "arrow.uturn.left.circle.fill")
                                    .font(.title3)
                                    .foregroundStyle(Theme.amber)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(f.actionTitle)
                                        .font(.subheadline.weight(.semibold))
                                        .foregroundStyle(.white)
                                    Text(f.prompt)
                                        .font(.caption)
                                        .foregroundStyle(.white.opacity(0.6))
                                        .fixedSize(horizontal: false, vertical: true)
                                        .multilineTextAlignment(.leading)
                                }
                                Spacer(minLength: 0)
                                Image(systemName: "chevron.right")
                                    .font(.caption.weight(.bold))
                                    .foregroundStyle(.white.opacity(0.35))
                            }
                            .padding(14)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .glassCardTinted(Theme.amber, cornerRadius: 16)
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
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label {
                    Text("Coach engine").foregroundStyle(.white.opacity(0.7))
                } icon: {
                    Image(systemName: "cpu").foregroundStyle(Theme.violet)
                }
                .font(.caption.weight(.semibold))
                Spacer()
            }
            Text("Trigger a tick to wake the brain now (dev affordance — replaces APNs/cron locally).")
                .font(.caption)
                .foregroundStyle(.white.opacity(0.5))
                .fixedSize(horizontal: false, vertical: true)
            Button(action: onTick) {
                HStack {
                    if isTicking { ProgressView().controlSize(.small).tint(.black) }
                    Text(isTicking ? "Ticking…" : "Tick now")
                }
            }
            .buttonStyle(EmberButtonStyle())
            .disabled(isTicking)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }
}

// MARK: - Settings sheet

private struct SettingsSheet: View {
    @EnvironmentObject var sessionStore: SessionStore
    @Environment(\.dismiss) var dismiss
    @State private var confirmReset = false

    var body: some View {
        NavigationStack {
            ZStack {
                AtmosphericBackground()
                ScrollView {
                    VStack(spacing: 14) {
                        settingsGroup("BACKEND") {
                            settingsRow(label: "URL", value: "http://127.0.0.1:8765")
                        }

                        settingsGroup("IDENTITY") {
                            settingsRow(
                                label: "Statement",
                                value: sessionStore.identityStatement ?? "(not set)"
                            )
                            Divider().background(Color.white.opacity(0.06))
                            settingsRow(label: "User", value: sessionStore.userId)
                        }

                        settingsGroup("PROGRAM") {
                            programButton("Pause for a week", icon: "pause.circle") {
                                try? await CoachAPI.shared.pauseProgram(days: 7); dismiss()
                            }
                            Divider().background(Color.white.opacity(0.06))
                            programButton("Pause for a month", icon: "pause.circle") {
                                try? await CoachAPI.shared.pauseProgram(days: 30); dismiss()
                            }
                            Divider().background(Color.white.opacity(0.06))
                            programButton("Resume now", icon: "play.circle") {
                                try? await CoachAPI.shared.resumeProgram(); dismiss()
                            }
                        }

                        VStack(alignment: .leading, spacing: 10) {
                            Button(role: .destructive) {
                                confirmReset = true
                            } label: {
                                Label("Reset onboarding", systemImage: "arrow.counterclockwise")
                                    .foregroundStyle(Theme.rose)
                            }
                            .buttonStyle(GhostButtonStyle())
                            Text("Clears your identity statement and intake completion locally. The backend still remembers your program until you reset its database.")
                                .font(.caption)
                                .foregroundStyle(.white.opacity(0.5))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .padding(.top, 6)
                    }
                    .padding(18)
                }
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                        .foregroundStyle(Theme.ember)
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

    private func settingsGroup<Content: View>(_ header: String, @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionEyebrow(text: header)
                .padding(.leading, 4)
            VStack(spacing: 0) {
                content()
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .glassCard()
        }
    }

    private func programButton(_ title: String, icon: String, action: @escaping () async -> Void) -> some View {
        Button { Task { await action() } } label: {
            HStack {
                Label(title, systemImage: icon).foregroundStyle(.white)
                Spacer()
            }
            .font(.callout)
            .padding(.vertical, 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func settingsRow(label: String, value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label).foregroundStyle(.white.opacity(0.6))
            Spacer()
            Text(value)
                .foregroundStyle(.white)
                .multilineTextAlignment(.trailing)
                .lineLimit(3)
        }
        .font(.callout)
        .padding(.vertical, 6)
    }
}
