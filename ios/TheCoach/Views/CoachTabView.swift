// Coach tab (v2) — the default landing and the app's voice.
//
// One tab, five server-selected shapes (design/v2/screens/01-coach-tab.md):
//   A Quiet · B Prescription · C Slip (the moat) · D Return · E Pause
//
// The brain decides which shape via GET /coach/today; this view renders it and
// wires its CTAs. The coach line is hand-authored Marcus voice (deterministic
// server-side), never generated — the moat surfaces can't drift.
//
// This tab is NOT a feed. One thing, decided by the brain, that the user should
// hear right now. Quiet is a valid output.

import SwiftUI

struct CoachTabView: View {
    /// Switch the parent TabView to the Now tab (the prescription surface).
    let onShowSession: () -> Void
    let onOpenSettings: () -> Void
    let onOpenDev: () -> Void
    /// Shape D "I'm done" — parent owns the session reset (it holds SessionStore).
    let onEndProgram: () -> Void

    @StateObject private var model = CoachTodayViewModel()
    @State private var cantTodayShown = false
    @State private var confirmDone = false
    @State private var extendPauseShown = false

    var body: some View {
        NavigationStack {
            ZStack {
                AtmosphericBackground()
                Group {
                    switch model.state {
                    case .loading:
                        ProgressView().controlSize(.large).tint(Theme.ember)
                    case .failed(let msg):
                        ErrorView(title: "Your coach can't be reached",
                                  message: msg, retry: { await model.refresh() })
                    case .ready(let today):
                        ScrollView {
                            VStack(alignment: .leading, spacing: 22) {
                                CoachLineBlock(today: today)
                                shapeCTAs(today)
                                if !today.followups.isEmpty {
                                    FollowupsBlock(followups: today.followups,
                                                   onDone: { Task { await model.refresh() } })
                                }
                            }
                            .padding(.horizontal, 20)
                            .padding(.top, 12)
                        }
                        .scrollContentBackground(.hidden)
                        .contentMargins(.bottom, 100, for: .scrollContent)
                        .refreshable { await model.refresh() }
                    }
                }
            }
            .navigationTitle("Coach")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { onOpenSettings() } label: {
                        Image(systemName: "gearshape").foregroundStyle(.white.opacity(0.85))
                    }.accessibilityLabel("Settings")
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button { onOpenDev() } label: {
                        Image(systemName: "wand.and.stars").foregroundStyle(Theme.amber.opacity(0.85))
                    }.accessibilityLabel("Dev scenarios")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    VotesBadge(votes: model.votes)
                }
            }
            .task { await model.refresh() }
        }
    }

    // MARK: - Per-shape CTAs

    @ViewBuilder
    private func shapeCTAs(_ today: CoachToday) -> some View {
        switch today.shape {
        case "prescription":
            VStack(spacing: 12) {
                Button { onShowSession() } label: { Label("Show me the session", systemImage: "dumbbell.fill") }
                    .buttonStyle(EmberButtonStyle())
                Button { cantTodayShown = true } label: { Text("I can't today") }
                    .buttonStyle(GhostButtonStyle())
            }
            .confirmationDialog("What's the conflict?", isPresented: $cantTodayShown, titleVisibility: .visible) {
                Button("Try later today") { cantTodayShown = false }
                Button("Try tomorrow") { Task { await model.reportCant(reason: "schedule conflict — tomorrow") } }
                Button("Body needs a day") { Task { await model.reportCant(reason: "body needs a day") } }
                Button("Cancel", role: .cancel) {}
            }

        case "slip":
            VStack(alignment: .leading, spacing: 16) {
                Button {
                    Task { await model.doMinimum() }
                } label: {
                    HStack {
                        if model.acting { ProgressView().controlSize(.small).tint(.black) }
                        Text("I did the minimum")
                    }
                }
                .buttonStyle(EmberButtonStyle())
                .disabled(model.acting)

                FrictionTags { tag in Task { await model.reportFriction(tag) } }
            }

        case "return":
            VStack(spacing: 12) {
                Button { onShowSession() } label: { Text("Back in") }
                    .buttonStyle(EmberButtonStyle())
                Button { Task { await model.pause(days: 7) } } label: { Text("Give me a week") }
                    .buttonStyle(GhostButtonStyle())
                Button(role: .destructive) { confirmDone = true } label: { Text("I'm done") }
                    .buttonStyle(GhostButtonStyle())
                    .tint(Theme.rose)
            }
            .confirmationDialog("End the program?", isPresented: $confirmDone, titleVisibility: .visible) {
                Button("End it", role: .destructive) { onEndProgram() }
                Button("Keep going", role: .cancel) {}
            } message: {
                Text("Your history stays. You can start a new one anytime.")
            }

        case "pause":
            VStack(spacing: 12) {
                Button { Task { await model.resume() } } label: { Text("Resume now") }
                    .buttonStyle(EmberButtonStyle())
                Button { extendPauseShown = true } label: { Text("Extend pause") }
                    .buttonStyle(GhostButtonStyle())
            }
            .confirmationDialog("Extend the pause", isPresented: $extendPauseShown, titleVisibility: .visible) {
                Button("One week") { Task { await model.pause(days: 7) } }
                Button("One month") { Task { await model.pause(days: 30) } }
                Button("Cancel", role: .cancel) {}
            }

        default: // quiet
            if today.actionId != nil {
                Button { onShowSession() } label: {
                    Label("See the session", systemImage: "chevron.right")
                }
                .buttonStyle(GhostButtonStyle())
            }
        }
    }
}

// MARK: - Coach line

private struct CoachLineBlock: View {
    let today: CoachToday

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionEyebrow(text: "FROM YOUR COACH", icon: "quote.opening")
            Text(today.coachLine)
                .font(.system(.title2, design: .serif, weight: .medium))
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)
                .lineSpacing(3)
        }
        .padding(.top, 8)
    }
}

// MARK: - Friction tags (Shape C)

private struct FrictionTags: View {
    let onPick: (String) -> Void
    private let tags = ["work got busy", "body's off", "lost the routine", "something else"]
    @State private var custom = ""
    @State private var showCustom = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionEyebrow(text: "WHAT'S GETTING IN THE WAY", icon: "exclamationmark.bubble")
            FlowTags(tags: tags) { tag in
                if tag == "something else" { showCustom = true } else { onPick(tag) }
            }
            if showCustom {
                HStack {
                    TextField("what happened", text: $custom)
                        .textFieldStyle(.plain)
                        .padding(10)
                        .background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
                        .foregroundStyle(.white)
                    Button("Send") {
                        let t = custom.trimmingCharacters(in: .whitespaces)
                        if !t.isEmpty { onPick(t) }
                        custom = ""; showCustom = false
                    }
                    .foregroundStyle(Theme.ember)
                    .disabled(custom.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard()
    }
}

/// Simple wrapping tag row.
private struct FlowTags: View {
    let tags: [String]
    let onPick: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(tags, id: \.self) { tag in
                Button { onPick(tag) } label: {
                    Text(tag)
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.white.opacity(0.9))
                        .padding(.horizontal, 14).padding(.vertical, 9)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(.white.opacity(0.06), in: Capsule())
                        .overlay { Capsule().strokeBorder(Color.white.opacity(0.12), lineWidth: 1) }
                }
                .buttonStyle(.plain)
            }
        }
    }
}

// MARK: - Follow-ups

private struct FollowupsBlock: View {
    let followups: [FollowupSnapshot]
    let onDone: () -> Void
    @State private var selected: FollowupSnapshot?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionEyebrow(text: "FOLLOW-UPS", icon: "envelope.fill")
            ForEach(followups) { f in
                Button { selected = f } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "arrow.uturn.left.circle.fill")
                            .font(.title3).foregroundStyle(Theme.amber)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(f.title).font(.subheadline.weight(.semibold)).foregroundStyle(.white)
                            Text(f.prompt).font(.caption).foregroundStyle(.white.opacity(0.6))
                                .fixedSize(horizontal: false, vertical: true)
                                .multilineTextAlignment(.leading)
                        }
                        Spacer(minLength: 0)
                        Image(systemName: "chevron.right").font(.caption.weight(.bold))
                            .foregroundStyle(.white.opacity(0.35))
                    }
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .glassCardTinted(Theme.amber, cornerRadius: 16)
                }
                .buttonStyle(.plain)
            }
        }
        .sheet(item: $selected, onDismiss: onDone) { f in
            NudgeReplyView(nudgeId: f.nudgeId, defaultOutcome: "done")
                .presentationDetents([.medium, .large])
        }
    }
}

// MARK: - Votes badge (votes only — no streak, per v2)

struct VotesBadge: View {
    let votes: Int
    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "checkmark.seal.fill")
                .foregroundStyle(Theme.emberGradient)
                .shadow(color: Theme.ember.opacity(0.6), radius: 4)
            Text("\(votes)")
                .fontWeight(.bold).monospacedDigit().foregroundStyle(.white)
        }
        .font(.footnote)
        .padding(.horizontal, 12).padding(.vertical, 6)
        .background {
            Capsule().fill(.ultraThinMaterial)
                .overlay { Capsule().strokeBorder(Color.white.opacity(0.12), lineWidth: 1) }
        }
        .accessibilityLabel("\(votes) votes cast")
    }
}

// MARK: - View model

@MainActor
final class CoachTodayViewModel: ObservableObject {
    enum State { case loading, ready(CoachToday), failed(String) }
    @Published var state: State = .loading
    @Published var votes: Int = 0
    @Published var acting = false

    private var observer: NSObjectProtocol?

    init() {
        observer = NotificationCenter.default.addObserver(
            forName: .coachStateChanged, object: nil, queue: .main
        ) { [weak self] _ in Task { @MainActor [weak self] in await self?.refresh() } }
    }
    deinit { if let observer { NotificationCenter.default.removeObserver(observer) } }

    func refresh() async {
        do {
            let today = try await CoachAPI.shared.coachToday()
            votes = today.votes
            state = .ready(today)
        } catch let e as URLError {
            state = .failed(e.localizedDescription)
        } catch {
            // 401/409 etc. before onboarding — treat as a quiet-ish failure.
            state = .failed("Setup isn't finished yet.")
        }
    }

    /// Shape C primary — log the minimum dose (every prescribed lift marked
    /// done with the 2-minute-rule note). Resets the slip counter server-side.
    func doMinimum() async {
        acting = true; defer { acting = false }
        guard let next = try? await CoachAPI.shared.nextSession() else { return }
        let exercises = Dictionary(uniqueKeysWithValues: next.session.exercises.map {
            ($0.name, CoachAPI.ExerciseLogPayload(outcome: .done, calibrationSlot: $0.calibrationSlot))
        })
        _ = try? await CoachAPI.shared.logSession(
            actionId: next.actionId, friction: "minimum dose — 2-min rule", exercises: exercises)
        await refresh()
    }

    /// Shape C friction tag — feed the named friction into the program so the
    /// next session adapts to it (reuses the program-feedback path).
    func reportFriction(_ note: String) async {
        _ = try? await CoachAPI.shared.programFeedback(note: "Getting in the way: \(note)")
        await refresh()
    }

    /// Shape B "I can't today" — report the "no". Reporting no is still a vote
    /// for the relationship; we log it as a skip with the reason as friction.
    func reportCant(reason: String) async {
        guard let next = try? await CoachAPI.shared.nextSession() else { return }
        let exercises = Dictionary(uniqueKeysWithValues: next.session.exercises.map {
            ($0.name, CoachAPI.ExerciseLogPayload(outcome: .skipped, calibrationSlot: $0.calibrationSlot))
        })
        _ = try? await CoachAPI.shared.logSession(
            actionId: next.actionId, friction: reason, exercises: exercises)
        await refresh()
    }

    func pause(days: Int) async {
        try? await CoachAPI.shared.pauseProgram(days: days)
        await refresh()
    }

    func resume() async {
        try? await CoachAPI.shared.resumeProgram()
        await refresh()
    }
}
