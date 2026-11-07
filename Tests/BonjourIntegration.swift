import Foundation

@main
struct BonjourIntegration {
    static func main() {
        let discovery = Discovery(identifier: UUID().uuidString)
        let remoteID = UUID().uuidString
        let fixture = NetService(domain: "local.", type: Discovery.serviceType, name: "Codex Transfer Test " + String(remoteID.prefix(8)), port: 22)
        fixture.setTXTRecord(NetService.data(fromTXTRecord: ["id": Data(remoteID.utf8), "user": Data(NSUserName().utf8), "version": Data("1".utf8)]))
        var found = false
        var removed = false
        discovery.onChange = { peers in
            if peers.contains(where: { $0.id == remoteID }) { found = true }
            if found && !peers.contains(where: { $0.id == remoteID }) { removed = true }
        }
        discovery.start()
        fixture.publish()
        let deadline = Date().addingTimeInterval(12)
        while !found && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.1)) }
        fixture.stop()
        let removalDeadline = Date().addingTimeInterval(5)
        while found && !removed && Date() < removalDeadline { RunLoop.current.run(until: Date().addingTimeInterval(0.1)) }
        discovery.stop()
        if found && removed { print("Bonjour publication, discovery, resolution and removal passed on this Mac") }
        else { print("Bonjour integration unavailable or incomplete: found=\(found), removed=\(removed)"); exit(1) }
    }
}
