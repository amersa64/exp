import Foundation

@MainActor
final class BackendHealth: ObservableObject {
    enum Status: Equatable {
        case checking
        case reachable
        case unreachable(String)
    }

    @Published var status: Status = .checking

    private let baseURL: URL
    private let session: URLSession

    init(baseURL: URL = URL(string: "http://127.0.0.1:8765")!) {
        self.baseURL = baseURL
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = 3
        cfg.timeoutIntervalForResource = 3
        cfg.waitsForConnectivity = false
        self.session = URLSession(configuration: cfg)
    }

    func probe() async {
        status = .checking
        do {
            let url = baseURL.appendingPathComponent("/healthz")
            let (_, response) = try await session.data(from: url)
            if let http = response as? HTTPURLResponse, http.statusCode == 200 {
                status = .reachable
            } else {
                status = .unreachable("Backend responded but isn't healthy.")
            }
        } catch {
            status = .unreachable("Can't reach the coach. Is the backend running on \(baseURL.absoluteString)?")
        }
    }
}
