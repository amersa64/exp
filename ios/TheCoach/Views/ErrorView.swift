import SwiftUI

struct ErrorView: View {
    let title: String
    let message: String
    let retry: () async -> Void

    @State private var retrying = false

    var body: some View {
        ContentUnavailableView {
            Label(title, systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        } actions: {
            Button {
                Task {
                    retrying = true
                    await retry()
                    retrying = false
                }
            } label: {
                if retrying {
                    ProgressView()
                } else {
                    Text("Try again")
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(retrying)
        }
    }
}

#Preview {
    ErrorView(
        title: "Can't reach the coach",
        message: "Is the backend running on 127.0.0.1:8765?",
        retry: {}
    )
}
