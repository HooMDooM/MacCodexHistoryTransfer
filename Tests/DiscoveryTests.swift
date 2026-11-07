import Foundation

@main
struct DiscoveryTests {
    static func main() {
        let ownID = UUID().uuidString
        let otherID = UUID().uuidString
        func txt(_ user: String, _ id: String = otherID, _ version: String = "1") -> Data {
            NetService.data(fromTXTRecord: ["id": Data(id.utf8), "user": Data(user.utf8), "version": Data(version.utf8)])
        }
        func peer(_ hostname: String? = "Second-Mac.local.", _ port: Int = 22, _ data: Data? = nil) -> NearbyMac? {
            Discovery.peer(name: "Second Mac", hostname: hostname, port: port, txt: data ?? txt("alex"), ownID: ownID)
        }
        precondition(peer()?.endpoint == "alex@Second-Mac.local")
        precondition(peer("Second-Mac.local")?.endpoint == "alex@Second-Mac.local")
        precondition(peer("Second-Mac.local.", 22, txt("alex", ownID)) == nil)
        precondition(peer("Second-Mac.local.", 22, txt("alex", otherID, "2")) == nil)
        precondition(peer("Second-Mac.local.", 22, txt("user;touch /tmp/x")) == nil)
        precondition(peer("-oProxyCommand=x.local") == nil)
        precondition(peer("example.com") == nil)
        precondition(peer(nil) == nil)
        precondition(peer("Second-Mac.local.", 2222) == nil)
        precondition(peer("Second-Mac.local.", 22, txt("alex", "invalid")) == nil)
        precondition(Discovery.peer(name: "Mac", hostname: "mac.local", port: 22, txt: nil, ownID: ownID) == nil)
        print("11 discovery checks passed")
    }
}
