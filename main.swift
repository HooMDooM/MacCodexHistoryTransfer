import Cocoa
import SwiftUI

let appName = "Mac Codex History Transfer"
let supportFolder = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Codex Transfer")

struct TransferStatus: Equatable {
    var token = ""
    var phase = "preparing"
    var role = ""
    var peer = ""
    var message = ""
    var percent = 0.0
    var current = 0.0
    var total = 0.0
    var time = 0.0

    static let activePhases: Set<String> = ["preparing", "closing", "comparing", "sending", "receiving", "installing"]
    var active: Bool { Self.activePhases.contains(phase) }

    static func load() -> TransferStatus? {
        guard let data = try? Data(contentsOf: supportFolder.appendingPathComponent("status.json")),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        func number(_ key: String) -> Double { (json[key] as? NSNumber)?.doubleValue ?? 0 }
        return TransferStatus(token: json["token"] as? String ?? "", phase: json["phase"] as? String ?? "", role: json["role"] as? String ?? "",
                              peer: json["peer"] as? String ?? "", message: json["message"] as? String ?? "",
                              percent: number("percent"), current: number("current"), total: number("total"), time: number("time"))
    }
}

enum Screen { case search, connected, transfer, done, failed }

final class AppModel: ObservableObject {
    @Published var peers: [NearbyMac] = []
    @Published var selectedID: String?
    @Published var searching = false
    @Published var connecting = false
    @Published var connectedHost = ""
    @Published var connectedName = ""
    @Published var push = true
    @Published var screen: Screen = .search
    @Published var status: TransferStatus?
    @Published var log = ""
    @Published var errorText = ""
    @Published var remoteLogin = true
    @Published var fingerprint: String?
    @Published var running = false
    @Published var hint = ""
    let localName = Host.current().localizedName ?? "Mac"
    var mode = ""
    var dismissedToken = ""
    var lastError = ""
    var process: Process?
    var inputPipe: Pipe?
    var buffer = Data()
    var timer: Timer?
    var ticks = 0
    var activity: NSObjectProtocol?
    var onActivate: (() -> Void)?
    lazy var discovery: Discovery = {
        let key = "discoveryID"
        let identifier = UserDefaults.standard.string(forKey: key) ?? UUID().uuidString
        UserDefaults.standard.set(identifier, forKey: key)
        return Discovery(identifier: identifier)
    }()

    func startup() {
        discovery.onChange = { [weak self] found in
            guard let self = self else { return }
            withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                self.peers = found
                if let id = self.selectedID, !found.contains(where: { $0.id == id }) { self.selectedID = nil }
                if self.selectedID == nil, found.count == 1 { self.selectedID = found[0].id }
            }
        }
        discovery.onStatus = { [weak self] text in self?.hint = text }
        search()
        checkAccess()
        timer = Timer.scheduledTimer(withTimeInterval: 0.4, repeats: true) { [weak self] _ in self?.poll() }
    }

    func search() {
        guard !running else { return }
        errorText = ""
        discovery.start()
        withAnimation { searching = true }
        DispatchQueue.main.asyncAfter(deadline: .now() + 4) { [weak self] in withAnimation { self?.searching = false } }
    }

    var selectedPeer: NearbyMac? { peers.first { $0.id == selectedID } }

    func checkAccess() {
        DispatchQueue.global(qos: .utility).async {
            let open = Self.execute("/usr/bin/nc", ["-z", "-G", "1", "127.0.0.1", "22"]).status == 0
            let output = Self.execute("/usr/bin/ssh-keygen", ["-lf", "/etc/ssh/ssh_host_ed25519_key.pub", "-E", "sha256"]).output
            let code = output.split(separator: " ").first { $0.hasPrefix("SHA256:") }.map(String.init)
            DispatchQueue.main.async {
                withAnimation { self.remoteLogin = open; self.fingerprint = open ? code : nil }
            }
        }
    }

    static func execute(_ path: String, _ arguments: [String]) -> (status: Int32, output: String) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: path)
        p.arguments = arguments
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = Pipe()
        do { try p.run() } catch { return (1, "") }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        return (p.terminationStatus, String(decoding: data, as: UTF8.self))
    }

    func openSharingSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.Sharing-Settings.extension") { NSWorkspace.shared.open(url) }
    }

    func poll() {
        ticks += 1
        if ticks % 12 == 0 && screen == .search { checkAccess() }
        let now = Date().timeIntervalSince1970
        guard let s = TransferStatus.load(), s.token != dismissedToken, !s.token.isEmpty else {
            if screen == .transfer && !running && mode != "transfer" { fail(L("Связь с другим Mac прервалась.")) }
            return
        }
        let fresh = now - s.time < 20
        if s.active && fresh {
            if status != s { withAnimation(.easeOut(duration: 0.35)) { status = s } }
            if screen != .transfer {
                withAnimation(.spring(response: 0.5, dampingFraction: 0.85)) { screen = .transfer }
                keepAwake(true)
                onActivate?()
            }
        } else if screen == .transfer && !running {
            if s.phase == "done" { status = s; complete() }
            else if s.phase == "error" { status = s; fail(L(s.message)) }
            else if !fresh { fail(L("Связь с другим Mac прервалась.")) }
        }
    }

    func keepAwake(_ on: Bool) {
        if on, activity == nil {
            activity = ProcessInfo.processInfo.beginActivity(options: [.idleSystemSleepDisabled, .userInitiated], reason: "Codex history transfer")
        } else if !on, let a = activity {
            ProcessInfo.processInfo.endActivity(a)
            activity = nil
        }
    }

    func complete() {
        keepAwake(false)
        withAnimation(.spring(response: 0.55, dampingFraction: 0.75)) { screen = .done }
    }

    func fail(_ message: String) {
        keepAwake(false)
        errorText = message.isEmpty ? L("Перенос остановлен.") : message
        withAnimation(.spring(response: 0.5, dampingFraction: 0.85)) { screen = .failed }
    }

    func dismiss() {
        dismissedToken = status?.token ?? dismissedToken
        status = nil
        errorText = ""
        withAnimation(.spring(response: 0.5, dampingFraction: 0.85)) { screen = connectedHost.isEmpty ? .search : .connected }
    }

    func disconnect() {
        connectedHost = ""
        connectedName = ""
        withAnimation(.spring(response: 0.5, dampingFraction: 0.85)) { screen = .search }
        search()
    }

    func connect() {
        guard let peer = selectedPeer else { return }
        errorText = ""
        withAnimation { connecting = true }
        launch("pair", [peer.endpoint])
    }

    var sourceName: String { push ? localName : connectedName }
    var destinationName: String { push ? connectedName : localName }

    func transfer() {
        let alert = NSAlert()
        alert.messageText = L("Перенести историю?") + "\n" + sourceName + " → " + destinationName
        alert.informativeText = L("Завершите активные задачи. Codex закроется на обоих Mac, история на принимающем Mac будет заменена. Резервная копия не создаётся.")
        alert.addButton(withTitle: L("Перенести"))
        alert.addButton(withTitle: L("Отмена"))
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        status = TransferStatus(role: push ? "source" : "destination", peer: connectedName)
        log = ""
        withAnimation(.spring(response: 0.5, dampingFraction: 0.85)) { screen = .transfer }
        keepAwake(true)
        launch("transfer", ["transfer", connectedHost, push ? "push" : "pull"])
    }

    func launch(_ kind: String, _ arguments: [String]) {
        guard !running, let script = Bundle.main.url(forResource: kind == "pair" ? "pairing" : "transfer", withExtension: "py") else { return }
        mode = kind
        running = true
        lastError = ""
        buffer.removeAll()
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        p.arguments = ["-u", script.path] + arguments
        var env = ProcessInfo.processInfo.environment
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["CODEX_TRANSFER_LANGUAGE"] = appLanguage
        p.environment = env
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        let input = Pipe()
        inputPipe = input
        p.standardInput = input
        process = p
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                try p.run()
                while true {
                    let data = pipe.fileHandleForReading.availableData
                    if data.isEmpty { break }
                    DispatchQueue.main.async {
                        self.buffer.append(data)
                        while let newline = self.buffer.firstIndex(of: 10) {
                            let line = String(decoding: self.buffer.prefix(through: newline), as: UTF8.self)
                            self.buffer.removeSubrange(...newline)
                            self.handle(line)
                        }
                    }
                }
                p.waitUntilExit()
                DispatchQueue.main.async { self.finish(p.terminationStatus) }
            } catch {
                DispatchQueue.main.async { self.lastError = error.localizedDescription; self.finish(1) }
            }
        }
    }

    func handle(_ line: String) {
        if let data = line.data(using: .utf8), let event = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let kind = event["prompt"] as? String, let message = event["message"] as? String { answer(kind, message); return }
            if event["event"] as? String == "connected" {
                connectedHost = event["host"] as? String ?? ""
                connectedName = event["name"] as? String ?? connectedHost
                return
            }
        }
        let text = line.trimmingCharacters(in: .whitespacesAndNewlines)
        for prefix in ["ОШИБКА: ", "ERROR: "] where text.hasPrefix(prefix) { lastError = String(text.dropFirst(prefix.count)) }
        log += line
    }

    func answer(_ kind: String, _ message: String) {
        let alert = NSAlert()
        var field: NSSecureTextField?
        if kind == "trust" {
            alert.messageText = L("Подтвердите второй Mac")
            alert.informativeText = L("Сравните код с кодом внизу окна приложения на втором Mac:") + "\n\n" + message
            alert.addButton(withTitle: L("Код совпадает"))
        } else if kind == "password" {
            alert.messageText = L("Пароль пользователя второго Mac")
            alert.informativeText = message + "\n" + L("Нужен один раз для подключения и не сохраняется.")
            let input = NSSecureTextField(frame: NSRect(x: 0, y: 0, width: 320, height: 24))
            alert.accessoryView = input
            field = input
            alert.addButton(withTitle: L("Подключить"))
        } else { return }
        alert.addButton(withTitle: L("Отмена"))
        if let field = field { alert.window.initialFirstResponder = field }
        let accepted = alert.runModal() == .alertFirstButtonReturn
        let value: Any = accepted ? (kind == "trust" ? "yes" : field?.stringValue ?? "") : NSNull()
        if let data = try? JSONSerialization.data(withJSONObject: ["answer": value]) {
            try? inputPipe?.fileHandleForWriting.write(contentsOf: data + Data([10]))
        }
        field?.stringValue = ""
    }

    func finish(_ code: Int32) {
        if !buffer.isEmpty { handle(String(decoding: buffer, as: UTF8.self)); buffer.removeAll() }
        running = false
        process = nil
        inputPipe = nil
        let kind = mode
        mode = ""
        if kind == "pair" {
            withAnimation { connecting = false }
            if code == 0 && !connectedHost.isEmpty {
                withAnimation(.spring(response: 0.5, dampingFraction: 0.85)) { screen = .connected }
            } else {
                withAnimation { errorText = lastError.isEmpty ? L("Не удалось подключиться.") : lastError }
            }
        } else if code == 0 {
            if var s = status { s.phase = "done"; s.percent = 100; status = s }
            if let s = TransferStatus.load(), s.phase == "done" { status = s }
            complete()
        } else {
            if let s = TransferStatus.load(), s.phase == "error" { status = s }
            fail(lastError)
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var window: NSWindow!
    let model = AppModel()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        let menu = NSMenu()
        let item = NSMenuItem()
        menu.addItem(item)
        let sub = NSMenu()
        sub.addItem(withTitle: L("Закрыть ") + appName, action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = sub
        let editItem = NSMenuItem()
        menu.addItem(editItem)
        let edit = NSMenu(title: "Edit")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit
        NSApp.mainMenu = menu
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 560, height: 640), styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
        window.title = appName
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = true
        window.minSize = NSSize(width: 520, height: 600)
        window.delegate = self
        window.contentView = NSHostingView(rootView: RootView(model: model))
        window.center()
        model.onActivate = { [weak self] in
            self?.window.deminiaturize(nil)
            self?.window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
        model.startup()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationWillTerminate(_ notification: Notification) { model.discovery.stop() }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if model.running { NSSound.beep(); return .terminateCancel }
        return .terminateNow
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool { !model.running }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
