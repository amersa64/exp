// Becoming hero — embers rising into a sky of past votes.
//
// The hero on the Summit tab. The metaphor inverts the original pellet-flow:
// instead of pellets falling through obstacles into a cup at the bottom,
// warmth rises from the identity statement at the base — embers lifting off
// a quiet flame, drifting up, and settling as stars in the night sky above.
//
// Why this shape:
//   - Identity at the base, as the source. The statement is what everything
//     grows *from*. The fire is the user's commitment; the embers are today's
//     votes; the stars above are votes already cast — a night sky that thickens
//     over months. The user looks up at what they've built.
//   - Streak makes the flame live. A current streak burns brighter and lifts
//     embers faster. A broken streak doesn't shame — the flame rests low,
//     embers continue to drift from existing stars, the sky stays full. The
//     punishment for stopping is the absence of new warmth, not a red badge.
//   - Growth is cumulative and visible without numbers-as-bars. The star
//     field densifies as votes_cast grows. Early users see a few sparks;
//     long-time users see a constellation that took months to seed.
//   - No friction labels. The original "Schedule conflicts / Tired days /
//     Lost momentum" trio named the user's failure modes back to them daily;
//     this version shows what the user is *building* instead.
//
// The type name `PelletFlowHero` is retained from the previous metaphor so
// the call site in `WorldView` continues to compile — the contract (votes +
// identityStatement) is unchanged. The visual is what changed.

import SwiftUI

struct PelletFlowHero: View {
    let votes: Int
    let identityStatement: String?
    /// Current streak in days. Drives flame brightness and ember rise rate.
    /// Defaulted so callers that don't yet pass it (or pass nil) get a calm
    /// resting flame rather than a build error.
    var streakDays: Int = 0

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    // Hero is ~360pt tall on iPhone — same vertical footprint as the previous
    // PelletFlowHero so the surrounding WorldView layout doesn't shift.
    private let heroHeight: CGFloat = 360
    private let cornerRadius: CGFloat = 28

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = heroHeight

            // Vertical layout regions, top to bottom:
            //   [ sky: stars from past votes ......................... ]   ~58%
            //   [ ember band: drifting motes ........................ ]   ~22%
            //   [ flame: live commitment, brightness = streak ....... ]   ~10%
            //   [ identity statement: the source .................... ]   ~10%
            let skyBottom = h * 0.58
            let flameBaseY = h * 0.78
            let identityY = h * 0.91

            ZStack(alignment: .topLeading) {
                background

                // Stars from past votes — densifies with votes count.
                starField(width: w, skyBottom: skyBottom)
                    .allowsHitTesting(false)

                // Rising embers — the live, animated layer.
                emberLayer(width: w, flameBaseY: flameBaseY, skyTop: 12)
                    .allowsHitTesting(false)

                // Flame at the source — brightness scales with streak.
                flame(centerX: w / 2, baseY: flameBaseY)
                    .allowsHitTesting(false)

                // Identity statement at the very base — what the fire is for.
                identityCaption
                    .frame(width: w - 32)
                    .position(x: w / 2, y: identityY)
            }
            .frame(width: w, height: h)
        }
        .frame(height: heroHeight)
        .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .strokeBorder(Color.white.opacity(0.10), lineWidth: 1)
        }
        .shadow(color: Theme.violet.opacity(0.35), radius: 30, y: 16)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityDescription)
    }

    // MARK: - Background

    /// Deep-night sky fading to a warm ember horizon at the base — same
    /// "Summit at Dusk" palette as the rest of the app.
    private var background: some View {
        ZStack {
            LinearGradient(
                stops: [
                    .init(color: Theme.night, location: 0.0),
                    .init(color: Theme.plum.opacity(0.85), location: 0.55),
                    .init(color: Theme.coal, location: 1.0),
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            // Warm horizon glow rising from where the flame sits.
            RadialGradient(
                colors: [Theme.ember.opacity(0.55 * flameIntensity), .clear],
                center: UnitPoint(x: 0.5, y: 0.82),
                startRadius: 6,
                endRadius: 240
            )
            // Cooler violet bloom in the upper-left — atmospheric depth.
            RadialGradient(
                colors: [Theme.violet.opacity(0.18), .clear],
                center: UnitPoint(x: 0.2, y: 0.15),
                startRadius: 8,
                endRadius: 220
            )
        }
    }

    // MARK: - Identity caption

    /// The seed of everything above it. Rendered in serif italic at modest
    /// weight so it reads as the *source* of the warmth, not as a header.
    private var identityCaption: some View {
        VStack(spacing: 3) {
            Text(identityLine)
                .font(.system(.subheadline, design: .serif).italic())
                .foregroundStyle(.white.opacity(0.78))
                .multilineTextAlignment(.center)
                .lineLimit(2)
                .truncationMode(.tail)
            HStack(spacing: 6) {
                Text("\(votes)")
                    .font(.caption.weight(.heavy))
                    .monospacedDigit()
                    .foregroundStyle(Theme.gold)
                Text(votes == 1 ? "vote cast" : "votes cast")
                    .font(.caption2.weight(.medium))
                    .tracking(0.6)
                    .foregroundStyle(.white.opacity(0.5))
                if streakDays > 0 {
                    Text("·")
                        .font(.caption2)
                        .foregroundStyle(.white.opacity(0.35))
                    Text("\(streakDays)d streak")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(Theme.ember.opacity(0.85))
                }
            }
        }
    }

    /// Lowercase the first letter so it reads as a continuation of "I am…"
    /// without literally prepending those words (the identity card above the
    /// hero already says "WHO YOU'RE BECOMING" + the statement in full).
    private var identityLine: String {
        let s = (identityStatement ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !s.isEmpty else { return "your summit" }
        let first = s.first.map(String.init)?.lowercased() ?? ""
        return first + s.dropFirst()
    }

    // MARK: - Flame

    /// Brightness multiplier driven by streak. Calm at 0 days, full at ~14.
    /// Asymptotic so a 200-day streak doesn't blow out the visual.
    private var flameIntensity: Double {
        // 0d → 0.35 (a resting ember), 7d → ~0.75, 14d+ → ~0.95
        0.35 + 0.65 * (1.0 - exp(-Double(streakDays) / 7.0))
    }

    /// A small live flame at the base. Two stacked ellipses with a soft glow.
    /// Animated subtly when motion is allowed; otherwise static.
    private func flame(centerX: CGFloat, baseY: CGFloat) -> some View {
        TimelineView(.animation(minimumInterval: 1.0 / 20.0, paused: reduceMotion)) { timeline in
            let t = timeline.date.timeIntervalSinceReferenceDate
            // Gentle breathing — flame doesn't jitter, it breathes.
            let breathe = reduceMotion ? 0 : sin(t * 1.6) * 0.06
            let scale = 1.0 + breathe
            let intensity = flameIntensity

            ZStack {
                // Outer glow halo
                Circle()
                    .fill(Theme.ember.opacity(0.45 * intensity))
                    .frame(width: 90, height: 90)
                    .blur(radius: 22)

                // Inner flame body — taller than wide, ember-to-gold
                Capsule()
                    .fill(
                        LinearGradient(
                            colors: [
                                Theme.gold.opacity(0.95 * intensity),
                                Theme.ember.opacity(0.85 * intensity),
                                Theme.ember.opacity(0.0),
                            ],
                            startPoint: .bottom,
                            endPoint: .top
                        )
                    )
                    .frame(width: 18, height: 38)
                    .scaleEffect(x: 1.0, y: scale, anchor: .bottom)

                // Hot core
                Capsule()
                    .fill(Color.white.opacity(0.55 * intensity))
                    .frame(width: 6, height: 14)
                    .blur(radius: 1)
                    .offset(y: 2)
                    .scaleEffect(x: 1.0, y: scale, anchor: .bottom)
            }
            .position(x: centerX, y: baseY)
        }
    }

    // MARK: - Ember layer

    /// Slow rising embers. Count scales gently with streak (a livelier fire
    /// throws more sparks) but stays modest so the visual is contemplative,
    /// not busy. Capped to avoid runaway when streak is very long.
    private var emberCount: Int {
        // 0d → 14 embers, 7d → ~22, 30d+ → ~30 (capped)
        let base = 14.0
        let extra = 16.0 * (1.0 - exp(-Double(streakDays) / 10.0))
        return Int(base + extra)
    }

    @ViewBuilder
    private func emberLayer(width: CGFloat, flameBaseY: CGFloat, skyTop: CGFloat) -> some View {
        if reduceMotion {
            Canvas { ctx, size in
                drawStaticEmbers(ctx: ctx, size: size, flameBaseY: flameBaseY, skyTop: skyTop)
            }
        } else {
            TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { timeline in
                Canvas { ctx, size in
                    let now = timeline.date.timeIntervalSinceReferenceDate
                    drawRisingEmbers(
                        ctx: ctx, size: size, now: now,
                        flameBaseY: flameBaseY, skyTop: skyTop
                    )
                }
            }
        }
    }

    /// Rise time for one ember from base to fade-out. Slow — embers should
    /// feel like they're being carried by gentle heat, not jet thrust.
    private static let emberRiseDuration: Double = 5.5
    private static let emberLoopDuration: Double = emberRiseDuration + 0.4

    /// Pre-baked per-ember parameters. Deterministic seed so the pattern is
    /// stable within a session and we don't recompute every frame.
    private struct EmberParams {
        let xJitter: CGFloat   // -1..1, multiplied by horizontal spread
        let phase: Double      // 0..loopDuration, staggers ember spawns
        let swayAmp: CGFloat   // horizontal sway amplitude
        let swayFreq: Double   // sway frequency
        let size: CGFloat      // ember radius
    }

    private static let emberParams: [EmberParams] = {
        // Capacity = max possible emberCount. We pre-bake the upper bound and
        // only iterate the first `emberCount` at draw time.
        var rng = SeededGenerator(seed: 0xB17EF1A)
        return (0..<48).map { _ in
            EmberParams(
                xJitter: CGFloat(rng.nextDouble() * 2.0 - 1.0),
                phase: rng.nextDouble() * emberLoopDuration,
                swayAmp: CGFloat(2.0 + rng.nextDouble() * 6.0),
                swayFreq: 0.6 + rng.nextDouble() * 0.8,
                size: CGFloat(1.6 + rng.nextDouble() * 1.8)
            )
        }
    }()

    private func drawRisingEmbers(
        ctx: GraphicsContext,
        size: CGSize,
        now: Double,
        flameBaseY: CGFloat,
        skyTop: CGFloat
    ) {
        let centerX = size.width / 2
        // Embers spawn from a small region around the flame mouth and rise
        // toward the lower edge of the sky layer.
        let spawnY = flameBaseY - 8
        let topY = skyTop + 40
        let rise = spawnY - topY

        // Streak speeds the rise — a brighter flame lifts embers faster.
        // Clamp so even 0-day streaks have visible motion.
        let speedMultiplier = 0.7 + 0.6 * flameIntensity
        let riseDuration = Self.emberRiseDuration / speedMultiplier
        let loopDuration = riseDuration + 0.4

        let count = min(emberCount, Self.emberParams.count)

        for i in 0..<count {
            let p = Self.emberParams[i]
            let elapsed = (now + p.phase).truncatingRemainder(dividingBy: loopDuration)
            guard elapsed >= 0, elapsed < riseDuration else { continue }

            let progress = elapsed / riseDuration   // 0..1
            // Ease-out: embers slow as they rise (heat dissipates).
            let eased = 1.0 - pow(1.0 - progress, 1.6)
            let y = spawnY - CGFloat(eased) * rise

            // Horizontal: starts near flame, drifts wider as it rises, with
            // a slow sinusoidal sway. The widening is what reads as "rising
            // through warm air."
            let baseX = centerX + p.xJitter * (8.0 + CGFloat(progress) * 50.0)
            let sway = sin((now + Double(i) * 0.7) * p.swayFreq) * p.swayAmp * CGFloat(progress)
            let x = baseX + sway

            // Alpha: fade in fast, fade out near the top so embers dissolve
            // into the sky rather than popping.
            let fadeIn = min(1.0, progress * 5.0)
            let fadeOut = min(1.0, (1.0 - progress) * 2.5)
            let alpha = min(fadeIn, fadeOut) * flameIntensity

            let r = p.size
            ctx.fill(
                Path(ellipseIn: CGRect(x: x - r, y: y - r, width: r * 2, height: r * 2)),
                with: .color(Theme.ember.opacity(alpha))
            )
            // Tiny gold core on the larger embers — adds warmth without cost.
            if r > 2.4 {
                let cr = r * 0.45
                ctx.fill(
                    Path(ellipseIn: CGRect(x: x - cr, y: y - cr, width: cr * 2, height: cr * 2)),
                    with: .color(Theme.gold.opacity(alpha * 0.8))
                )
            }
        }
    }

    /// Static distribution for reduce-motion — embers scattered along the
    /// rise path with no animation. Same density as animated version.
    private func drawStaticEmbers(
        ctx: GraphicsContext, size: CGSize,
        flameBaseY: CGFloat, skyTop: CGFloat
    ) {
        let centerX = size.width / 2
        let spawnY = flameBaseY - 8
        let topY = skyTop + 40
        let count = min(emberCount, Self.emberParams.count)
        for i in 0..<count {
            let p = Self.emberParams[i]
            let progress = Double(i) / Double(max(count - 1, 1))
            let y = spawnY - CGFloat(progress) * (spawnY - topY)
            let x = centerX + p.xJitter * (8.0 + CGFloat(progress) * 50.0)
            let r = p.size
            ctx.fill(
                Path(ellipseIn: CGRect(x: x - r, y: y - r, width: r * 2, height: r * 2)),
                with: .color(Theme.ember.opacity(0.6 * flameIntensity))
            )
        }
    }

    // MARK: - Star field (past votes)

    /// Number of stars in the sky. Each star = one cast vote, up to a visual
    /// cap. We cap because a 500-vote user shouldn't see an opaque wall of
    /// stars; past that point, additional votes brighten existing stars
    /// rather than adding new ones.
    private static let maxVisibleStars = 90

    private var visibleStarCount: Int {
        min(votes, Self.maxVisibleStars)
    }

    /// Per-star deterministic positions and twinkle phases. Stable across
    /// renders so a returning user sees the same constellation, just denser.
    /// Capacity matches maxVisibleStars.
    private struct StarParams {
        let nx: CGFloat          // 0..1 normalized x within sky region
        let ny: CGFloat          // 0..1 normalized y within sky region
        let size: CGFloat        // pixel radius
        let baseAlpha: Double    // 0.3..0.85
        let twinklePhase: Double // 0..2π
        let twinkleSpeed: Double // sin frequency
    }

    private static let starParams: [StarParams] = {
        var rng = SeededGenerator(seed: 0xC0FFEE5)
        return (0..<maxVisibleStars).map { _ in
            StarParams(
                nx: CGFloat(rng.nextDouble()),
                // Bias y toward the upper half of the sky — stars feel like
                // sky, not like fog hovering above the flame.
                ny: CGFloat(pow(rng.nextDouble(), 1.6)),
                size: CGFloat(0.7 + rng.nextDouble() * 1.6),
                baseAlpha: 0.35 + rng.nextDouble() * 0.5,
                twinklePhase: rng.nextDouble() * .pi * 2,
                twinkleSpeed: 0.4 + rng.nextDouble() * 0.9
            )
        }
    }()

    @ViewBuilder
    private func starField(width: CGFloat, skyBottom: CGFloat) -> some View {
        let count = visibleStarCount
        if count == 0 {
            // Empty-state: a single hint of a star so the sky doesn't read
            // as bug. "Your first vote will become a star here."
            Canvas { ctx, size in
                let r: CGFloat = 0.9
                let x = size.width * 0.5
                let y = skyBottom * 0.18
                ctx.fill(
                    Path(ellipseIn: CGRect(x: x - r, y: y - r, width: r * 2, height: r * 2)),
                    with: .color(.white.opacity(0.15))
                )
            }
        } else if reduceMotion {
            Canvas { ctx, size in
                drawStars(ctx: ctx, size: size, skyBottom: skyBottom, now: 0, twinkle: false)
            }
        } else {
            TimelineView(.animation(minimumInterval: 1.0 / 15.0)) { timeline in
                Canvas { ctx, size in
                    let now = timeline.date.timeIntervalSinceReferenceDate
                    drawStars(ctx: ctx, size: size, skyBottom: skyBottom, now: now, twinkle: true)
                }
            }
        }
    }

    private func drawStars(
        ctx: GraphicsContext, size: CGSize,
        skyBottom: CGFloat, now: Double, twinkle: Bool
    ) {
        let count = visibleStarCount
        // Stars live in the rectangle (0, 0) → (width, skyBottom).
        // Use a tiny top inset so they don't kiss the rounded corner.
        let inset: CGFloat = 14
        let usableW = size.width - inset * 2
        let usableH = skyBottom - inset
        for i in 0..<count {
            let s = Self.starParams[i]
            let x = inset + s.nx * usableW
            let y = inset + s.ny * usableH
            let twinkleFactor = twinkle
                ? 0.75 + 0.25 * sin(now * s.twinkleSpeed + s.twinklePhase)
                : 1.0
            let alpha = s.baseAlpha * twinkleFactor

            // The newest 3 votes get a gold cast — "still warm" — so a new
            // vote is visibly the freshest star. After that, they cool to
            // the standard white-blue sky color.
            let isFresh = i >= count - 3 && count >= 3
            let color: Color = isFresh ? Theme.gold : .white

            let r = s.size
            ctx.fill(
                Path(ellipseIn: CGRect(x: x - r, y: y - r, width: r * 2, height: r * 2)),
                with: .color(color.opacity(alpha))
            )
            // Soft glow for the larger / fresh stars.
            if isFresh || r > 1.8 {
                let gr = r * 2.4
                ctx.fill(
                    Path(ellipseIn: CGRect(x: x - gr, y: y - gr, width: gr * 2, height: gr * 2)),
                    with: .color(color.opacity(alpha * 0.18))
                )
            }
        }
    }

    // MARK: - Accessibility

    private var accessibilityDescription: String {
        let starsPhrase: String = {
            if votes == 0 { return "An empty night sky waits for your first vote." }
            if votes == 1 { return "One star in the sky for your first cast vote." }
            return "\(votes) stars in the sky, one for each vote you've cast."
        }()
        let flamePhrase: String = {
            if streakDays == 0 { return "A resting ember at the base." }
            if streakDays == 1 { return "A small flame at the base — one-day streak." }
            return "A bright flame at the base — \(streakDays)-day streak."
        }()
        return "\(starsPhrase) \(flamePhrase) Embers rising from your identity statement."
    }
}

// MARK: - Seeded RNG (deterministic — same constellation every render)

/// Linear-congruential generator, seeded once. We use this for star and ember
/// positions because the system RNG would re-shuffle every launch and the
/// constellation should be stable for a given user across sessions.
private struct SeededGenerator: RandomNumberGenerator {
    private var state: UInt64
    init(seed: UInt64) { self.state = seed == 0 ? 1 : seed }

    mutating func next() -> UInt64 {
        state = state &* 6364136223846793005 &+ 1442695040888963407
        return state
    }

    mutating func nextDouble() -> Double {
        Double((next() >> 11) & 0xFFFFFFFF) / Double(UInt32.max)
    }
}
