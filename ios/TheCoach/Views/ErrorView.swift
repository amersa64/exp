import SwiftUI

struct ErrorView: View {
    let title: String
    let message: String
    let retry: () async -> Void

    @State private var retrying = false

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 52))
                .foregroundStyle(Theme.amber.gradient)
                .shadow(color: Theme.amber.opacity(0.5), radius: 14)
            Text(title)
                .font(.title3.weight(.bold))
                .foregroundStyle(.white)
                .multilineTextAlignment(.center)
            Text(message)
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.65))
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            Button {
                Task {
                    retrying = true
                    await retry()
                    retrying = false
                }
            } label: {
                HStack {
                    if retrying { ProgressView().tint(.black) }
                    Text(retrying ? "Trying…" : "Try again")
                }
            }
            .buttonStyle(EmberButtonStyle())
            .disabled(retrying)
            .padding(.top, 4)
        }
        .padding(28)
        .frame(maxWidth: .infinity)
        .glassCard()
        .padding(.horizontal, 22)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

#Preview {
    ZStack {
        AtmosphericBackground()
        ErrorView(
            title: "Can't reach the coach",
            message: "Is the backend running on 127.0.0.1:8765?",
            retry: {}
        )
    }
    .preferredColorScheme(.dark)
}
