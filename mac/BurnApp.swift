import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var server: Process?
    private let port = Int.random(in: 49152...65535)

    func applicationDidFinishLaunching(_ notification: Notification) {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1120, height: 800),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Burn"
        window.minSize = NSSize(width: 360, height: 560)
        window.contentView = webView
        window.center()
        window.makeKeyAndOrderFront(nil)

        launchServer()
        waitUntilReady(attempt: 0)
    }

    private func launchServer() {
        guard let helper = Bundle.main.resourceURL?.appendingPathComponent("burn-server") else {
            showStartupError()
            return
        }

        let process = Process()
        process.executableURL = helper
        process.arguments = ["--port", String(port)]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self, self.webView.url == nil else { return }
                self.showStartupError()
            }
        }
        do {
            try process.run()
            server = process
        } catch {
            showStartupError()
        }
    }

    private func waitUntilReady(attempt: Int) {
        guard attempt < 100 else {
            showStartupError()
            return
        }
        let url = URL(string: "http://127.0.0.1:\(port)/api/health")!
        URLSession.shared.dataTask(with: url) { [weak self] _, response, _ in
            let ready = (response as? HTTPURLResponse)?.statusCode == 200
            DispatchQueue.main.asyncAfter(deadline: .now() + (ready ? 0 : 0.1)) {
                guard let self else { return }
                if ready {
                    self.webView.load(URLRequest(url: URL(string: "http://127.0.0.1:\(self.port)/")!))
                } else {
                    self.waitUntilReady(attempt: attempt + 1)
                }
            }
        }.resume()
    }

    private func showStartupError() {
        let alert = NSAlert()
        alert.messageText = "Burn could not start"
        alert.informativeText = "Quit Burn, make sure Cursor is installed, then open Burn again."
        alert.addButton(withTitle: "Quit")
        alert.runModal()
        NSApplication.shared.terminate(nil)
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.cancel)
            return
        }
        let isLocal = url.scheme == "http" && url.host == "127.0.0.1" && url.port == port
        decisionHandler(isLocal ? .allow : .cancel)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    func applicationWillTerminate(_ notification: Notification) {
        server?.terminate()
        server?.waitUntilExit()
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.activate(ignoringOtherApps: true)
app.run()
