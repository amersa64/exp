// Design system — "Summit at Dusk".
//
// The app is a coach for becoming someone. The visual story is the moment
// before the climb: deep plum night at the top, ember glow rising from the
// horizon, snow-bright type catching the first light. Cards float on glass.
// Everything reads in dark mode; light mode is not supported by design.

import SwiftUI

enum Theme {
    // MARK: - Palette

    static let night   = Color(red: 0.040, green: 0.046, blue: 0.110)
    static let plum    = Color(red: 0.120, green: 0.066, blue: 0.200)
    static let coal    = Color(red: 0.050, green: 0.035, blue: 0.090)
    static let ember   = Color(red: 1.000, green: 0.420, blue: 0.210) // #FF6B35
    static let gold    = Color(red: 1.000, green: 0.690, blue: 0.280) // #FFB047
    static let violet  = Color(red: 0.486, green: 0.227, blue: 0.929) // #7C3AED
    static let emerald = Color(red: 0.204, green: 0.831, blue: 0.600) // #34D399
    static let amber   = Color(red: 0.984, green: 0.749, blue: 0.141) // #FBBF24
    static let rose    = Color(red: 0.973, green: 0.443, blue: 0.443) // #F87171

    // MARK: - Gradients

    static let atmosphere = LinearGradient(
        stops: [
            .init(color: night, location: 0.0),
            .init(color: plum,  location: 0.55),
            .init(color: coal,  location: 1.0),
        ],
        startPoint: .top,
        endPoint: .bottom
    )

    static let emberGradient = LinearGradient(
        colors: [gold, ember],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )

    static let emberSoft = LinearGradient(
        colors: [ember.opacity(0.35), violet.opacity(0.18), .clear],
        startPoint: .top,
        endPoint: .bottom
    )
}

// MARK: - Atmospheric background

/// Full-screen "summit at dusk" backdrop: plum-to-coal gradient with a warm
/// ember glow rising from below. Drop behind any root container.
struct AtmosphericBackground: View {
    var body: some View {
        ZStack {
            Theme.atmosphere
            RadialGradient(
                colors: [Theme.ember.opacity(0.30), .clear],
                center: UnitPoint(x: 0.5, y: 1.05),
                startRadius: 20,
                endRadius: 520
            )
            RadialGradient(
                colors: [Theme.violet.opacity(0.20), .clear],
                center: UnitPoint(x: 0.15, y: 0.1),
                startRadius: 10,
                endRadius: 340
            )
        }
        .ignoresSafeArea()
    }
}

// MARK: - Glass card

/// Floating glass card — material backed, hairline stroke, generous corner.
struct GlassCard: ViewModifier {
    var cornerRadius: CGFloat = 20
    var tinted: Bool = false
    var tint: Color = Theme.ember

    func body(content: Content) -> some View {
        content
            .background {
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(.ultraThinMaterial)
                    .overlay {
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .fill(tinted ? tint.opacity(0.10) : Color.white.opacity(0.02))
                    }
                    .overlay {
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .strokeBorder(Color.white.opacity(0.08), lineWidth: 1)
                    }
            }
    }
}

extension View {
    func glassCard(cornerRadius: CGFloat = 20) -> some View {
        modifier(GlassCard(cornerRadius: cornerRadius))
    }

    func glassCardTinted(_ tint: Color = Theme.ember, cornerRadius: CGFloat = 20) -> some View {
        modifier(GlassCard(cornerRadius: cornerRadius, tinted: true, tint: tint))
    }
}

// MARK: - Buttons

/// Primary action — ember-gradient fill with a soft glow.
struct EmberButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(.black)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(Theme.emberGradient)
            }
            .overlay {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder(Color.white.opacity(0.25), lineWidth: 1)
            }
            .shadow(color: Theme.ember.opacity(0.45), radius: 18, y: 8)
            .scaleEffect(configuration.isPressed ? 0.97 : 1.0)
            .opacity(configuration.isPressed ? 0.9 : 1.0)
            .animation(.spring(response: 0.25, dampingFraction: 0.7), value: configuration.isPressed)
    }
}

/// Secondary action — translucent border, no fill.
struct GhostButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(.white.opacity(0.92))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(Color.white.opacity(0.06))
            }
            .overlay {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder(Color.white.opacity(0.18), lineWidth: 1)
            }
            .scaleEffect(configuration.isPressed ? 0.97 : 1.0)
            .opacity(configuration.isPressed ? 0.85 : 1.0)
            .animation(.spring(response: 0.25, dampingFraction: 0.7), value: configuration.isPressed)
    }
}

// MARK: - Type styles

/// Section eyebrow — tracked uppercase caption in the secondary tint.
struct SectionEyebrow: View {
    let text: String
    var icon: String? = nil
    var tint: Color = Theme.gold

    var body: some View {
        HStack(spacing: 6) {
            if let icon {
                Image(systemName: icon)
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(tint)
            }
            Text(text)
                .font(.caption2.weight(.heavy))
                .tracking(1.4)
                .foregroundStyle(.white.opacity(0.55))
        }
    }
}

extension View {
    /// Display number with ember-gradient fill, rounded weight.
    func displayNumber(size: CGFloat = 42) -> some View {
        self
            .font(.system(size: size, weight: .heavy, design: .rounded))
            .monospacedDigit()
            .foregroundStyle(Theme.emberGradient)
    }
}
