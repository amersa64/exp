// The growing world (Section 6).
//
// READ-ONLY (Section 6.3, Principle 2.6). No view in this file may compute
// currency, streak, or unlocks. Everything is fetched from the backend, which
// derives it from VerifiedEvents.
//
// Four-level zoom (Rubric E2):
//   Identity (summit)  ←  Milestones (unlocks)  ←  Habits (living systems)  ←  Atomic Actions (currency)

import SwiftUI

struct WorldView: View {
    @State private var world: World?
    @State private var followups: [FollowUp] = []
    @State private var zoom: Zoom = .summit

    enum Zoom { case summit, milestones, habits, actions }

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                header
                ZStack {
                    switch zoom {
                    case .summit:    SummitView(world: world)
                    case .milestones: MilestonesView()
                    case .habits:    HabitsView(world: world)
                    case .actions:   ActionsView()
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 320)
                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16))

                Picker("Zoom", selection: $zoom) {
                    Text("Summit").tag(Zoom.summit)
                    Text("Milestones").tag(Zoom.milestones)
                    Text("Habits").tag(Zoom.habits)
                    Text("Today").tag(Zoom.actions)
                }.pickerStyle(.segmented)

                if !followups.isEmpty {
                    FollowupsSection(followups: followups)
                }
            }
            .padding()
        }
        .task { await refresh() }
        .refreshable { await refresh() }
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading) {
                Text(world?.theme.capitalized ?? "Your world").font(.title2).bold()
                Text("currency reflects verified real-world action — not taps")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing) {
                Text("\(world?.currency ?? 0) effort").font(.headline)
                Text("\(world?.streakDays ?? 0)-day streak").font(.caption)
            }
        }
    }

    private func refresh() async {
        world = try? await CoachAPI.shared.world()
        followups = (try? await CoachAPI.shared.openFollowups()) ?? []
    }
}

// MARK: - Zoom levels (sketched; real visuals are stage 6 of Section 13).

struct SummitView: View {
    let world: World?
    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "mountain.2.fill").font(.system(size: 80))
            Text("Strong. Energetic. Durable.").font(.headline)
            Text("The summit grows nearer with every verified session.").font(.caption)
        }.padding()
    }
}

struct MilestonesView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(["Squat bodyweight x5", "12 sessions in 4 weeks", "Squat 1.5x bw x5"], id: \.self) { m in
                HStack { Image(systemName: "flag.fill"); Text(m) }
            }
        }.padding()
    }
}

struct HabitsView: View {
    let world: World?
    var body: some View {
        VStack(spacing: 12) {
            ForEach(Array((world?.livingSystems ?? [:]).keys), id: \.self) { id in
                let v = world?.livingSystems[id] ?? 0
                HStack {
                    Text("Strength training").bold()
                    Spacer()
                    ProgressView(value: v).frame(width: 120)
                }
            }
            Text("A living system thrives while you sustain it.").font(.caption).foregroundStyle(.secondary)
        }.padding()
    }
}

struct ActionsView: View {
    var body: some View {
        VStack {
            Text("Today's prescribed action arrives as a nudge.").font(.headline)
            Text("The app's job is to push it; the world's job is to reflect it.")
                .font(.caption).foregroundStyle(.secondary)
        }.padding()
    }
}

struct FollowupsSection: View {
    let followups: [FollowUp]
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Loose ends").font(.headline)
            ForEach(followups) { f in
                VStack(alignment: .leading, spacing: 4) {
                    Text(f.actionTitle).bold()
                    Text(f.prompt).font(.callout)
                }.padding(.vertical, 4)
            }
        }
    }
}
