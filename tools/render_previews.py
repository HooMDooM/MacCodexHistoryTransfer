import pathlib,shutil,subprocess,tempfile
root=pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='codex-transfer-preview-') as tmp:
    work=pathlib.Path(tmp)
    app=work/'Preview.app/Contents'
    (app/'MacOS').mkdir(parents=True)
    (app/'Resources').mkdir()
    shutil.copy2(root/'translations.json',app/'Resources/translations.json')
    source=(root/'main.swift').read_text().split('let app = NSApplication.shared\n')[0]
    source=source.replace('let localName = Host.current().localizedName ?? "Mac"','let localName = "Studio Mac"')
    (work/'Model.swift').write_text(source)
    (work/'Localization.swift').write_text((root/'Localization.swift').read_text().replace('(Locale.preferredLanguages.first ?? "en").lowercased().hasPrefix("ru") ? "ru" : "en"','"en"'))
    code='''import Cocoa
import SwiftUI

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
app.appearance = NSAppearance(named: .darkAqua)
app.applicationIconImage = NSImage(contentsOfFile: CommandLine.arguments[1])
let model = AppModel()
let peer = NearbyMac(id: UUID().uuidString, name: "Travel MacBook", endpoint: "alex@travel-mac.local")
model.peers = [peer]
model.selectedID = peer.id
model.remoteLogin = true
model.connectedName = peer.name
model.connectedHost = peer.endpoint
let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 560, height: 640), styleMask: [.borderless], backing: .buffered, defer: false)
window.backgroundColor = NSColor(calibratedRed: 0.10, green: 0.11, blue: 0.15, alpha: 1)
window.contentView = NSHostingView(rootView: RootView(model: model))
window.orderFront(nil)
for (name, screen) in [("discovery", Screen.search), ("connected", Screen.connected)] {
    model.screen = screen
    RunLoop.current.run(until: Date().addingTimeInterval(0.8))
    let view = window.contentView!
    view.layoutSubtreeIfNeeded()
    let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds)!
    view.cacheDisplay(in: view.bounds, to: bitmap)
    let path = URL(fileURLWithPath: CommandLine.arguments[2]).appendingPathComponent(name + ".png")
    try bitmap.representation(using: .png, properties: [:])!.write(to: path)
}
window.orderOut(nil)
'''
    (work/'main.swift').write_text(code)
    binary=app/'MacOS/Preview'
    subprocess.run(['swiftc','-framework','Cocoa','-framework','SwiftUI',str(work/'main.swift'),str(work/'Model.swift'),str(root/'Views.swift'),str(root/'Discovery.swift'),str(work/'Localization.swift'),'-o',str(binary)],check=True)
    subprocess.run([str(binary),str(root/'docs/images/app-icon.png'),str(root/'docs/images')],check=True)
