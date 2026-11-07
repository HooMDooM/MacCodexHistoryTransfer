import Foundation

struct NearbyMac: Equatable {
    let id: String
    let name: String
    let endpoint: String
}

final class Discovery: NSObject, NetServiceBrowserDelegate, NetServiceDelegate {
    static let serviceType = "_codex-xfer._tcp."
    let identifier: String
    var onChange: (([NearbyMac]) -> Void)?
    var onStatus: ((String) -> Void)?
    private let browser = NetServiceBrowser()
    private var publisher: NetService?
    private var services: [NetService] = []
    private var peers: [ObjectIdentifier: NearbyMac] = [:]

    init(identifier: String) {
        self.identifier = identifier
        super.init()
    }

    func start() {
        stop()
        let computer = Host.current().localizedName ?? ProcessInfo.processInfo.hostName
        var name = computer + " · " + NSUserName()
        while name.utf8.count > 60 { name.removeLast() }
        let service = NetService(domain: "local.", type: Self.serviceType, name: name, port: 22)
        service.delegate = self
        service.setTXTRecord(NetService.data(fromTXTRecord: [
            "id": Data(identifier.utf8),
            "user": Data(NSUserName().utf8),
            "version": Data("1".utf8)
        ]))
        publisher = service
        service.publish()
        browser.delegate = self
        browser.searchForServices(ofType: Self.serviceType, inDomain: "local.")
        onStatus?(L("Ищу Mac в локальной сети… Откройте приложение на втором Mac."))
    }

    func stop() {
        browser.stop()
        publisher?.stop()
        publisher = nil
        services.forEach { $0.stop() }
        services.removeAll()
        peers.removeAll()
        changed()
    }

    private func changed() {
        onChange?(peers.values.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending })
    }

    static func peer(name: String, hostname: String?, port: Int, txt: Data?, ownID: String) -> NearbyMac? {
        guard let txt = txt, let hostname = hostname, port == 22 else { return nil }
        let fields = NetService.dictionary(fromTXTRecord: txt)
        guard let idData = fields["id"], let id = String(data: idData, encoding: .utf8), UUID(uuidString: id) != nil, id != ownID,
              let userData = fields["user"], let user = String(data: userData, encoding: .utf8),
              fields["version"] == Data("1".utf8) else { return nil }
        let host = hostname.hasSuffix(".") ? String(hostname.dropLast()) : hostname
        guard user.range(of: "^[A-Za-z0-9_][A-Za-z0-9_.-]*$", options: .regularExpression) != nil,
              host.range(of: "^[A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9]$", options: .regularExpression) != nil,
              host.lowercased().hasSuffix(".local") else { return nil }
        return NearbyMac(id: id, name: String(name.prefix(100)), endpoint: user + "@" + host)
    }

    func netServiceBrowser(_ browser: NetServiceBrowser, didFind service: NetService, moreComing: Bool) {
        services.append(service)
        service.delegate = self
        service.resolve(withTimeout: 10)
    }

    func netServiceDidResolveAddress(_ sender: NetService) {
        guard services.contains(where: { $0 === sender }) else { return }
        if let peer = Self.peer(name: sender.name, hostname: sender.hostName, port: sender.port, txt: sender.txtRecordData(), ownID: identifier) {
            peers[ObjectIdentifier(sender)] = peer
            changed()
            onStatus?(L("Выберите свой Mac и нажмите «Подключить»."))
        }
    }

    func netServiceBrowser(_ browser: NetServiceBrowser, didRemove service: NetService, moreComing: Bool) {
        let matching = services.filter { $0.name == service.name && $0.domain == service.domain && $0.type == service.type }
        for item in matching { item.stop(); peers.removeValue(forKey: ObjectIdentifier(item)) }
        services.removeAll { item in matching.contains { $0 === item } }
        changed()
        if peers.isEmpty { onStatus?(L("Другой Mac не найден. Проверьте сеть и откройте на нём это приложение.")) }
    }

    func netServiceBrowser(_ browser: NetServiceBrowser, didNotSearch errorDict: [String: NSNumber]) {
        onStatus?(L("Поиск недоступен. Разрешите локальную сеть в настройках macOS. Код: \(errorDict[NetService.errorCode]?.intValue ?? 0)"))
    }

    func netService(_ sender: NetService, didNotPublish errorDict: [String: NSNumber]) {
        onStatus?(L("Этот Mac не удалось объявить в сети. Проверьте разрешение локальной сети."))
    }

    func netService(_ sender: NetService, didNotResolve errorDict: [String: NSNumber]) {
        if sender !== publisher { onStatus?(L("Не удалось получить адрес одного из Mac. Нажмите «Найти Mac».")) }
    }
}
