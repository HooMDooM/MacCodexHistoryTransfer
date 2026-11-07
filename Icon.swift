import AppKit

let target = CommandLine.arguments[1]
let image = NSImage(size: NSSize(width: 1024, height: 1024))
image.lockFocus()
let background = NSBezierPath(roundedRect: NSRect(x: 38, y: 38, width: 948, height: 948), xRadius: 212, yRadius: 212)
NSGradient(starting: NSColor(calibratedRed: 0.18, green: 0.20, blue: 0.33, alpha: 1), ending: NSColor(calibratedRed: 0.055, green: 0.075, blue: 0.14, alpha: 1))!.draw(in: background, angle: -65)
let glow = NSBezierPath(ovalIn: NSRect(x: 390, y: 420, width: 510, height: 430))
NSColor(calibratedRed: 0.47, green: 0.44, blue: 0.98, alpha: 0.08).setFill()
glow.fill()
func bubble(_ rect: NSRect, _ color: NSColor) {
    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.22)
    shadow.shadowBlurRadius = 20
    shadow.shadowOffset = NSSize(width: 0, height: -12)
    NSGraphicsContext.saveGraphicsState()
    shadow.set()
    let shape = NSBezierPath(roundedRect: rect, xRadius: 48, yRadius: 48)
    color.setFill()
    shape.fill()
    NSGraphicsContext.restoreGraphicsState()
    let tail = NSBezierPath()
    tail.move(to: NSPoint(x: rect.minX + 58, y: rect.minY + 5))
    tail.line(to: NSPoint(x: rect.minX + 58, y: rect.minY - 42))
    tail.line(to: NSPoint(x: rect.minX + 118, y: rect.minY + 5))
    tail.close()
    color.setFill()
    tail.fill()
    let mark = NSBezierPath()
    mark.lineWidth = 16
    mark.lineCapStyle = .round
    mark.lineJoinStyle = .round
    mark.move(to: NSPoint(x: rect.midX - 44, y: rect.midY + 27))
    mark.line(to: NSPoint(x: rect.midX - 12, y: rect.midY))
    mark.line(to: NSPoint(x: rect.midX - 44, y: rect.midY - 27))
    mark.move(to: NSPoint(x: rect.midX + 16, y: rect.midY - 27))
    mark.line(to: NSPoint(x: rect.midX + 56, y: rect.midY - 27))
    NSColor(calibratedRed: 0.10, green: 0.13, blue: 0.22, alpha: 1).setStroke()
    mark.stroke()
}
bubble(NSRect(x: 166, y: 530, width: 320, height: 250), NSColor(calibratedRed: 0.87, green: 0.90, blue: 1, alpha: 1))
bubble(NSRect(x: 538, y: 244, width: 320, height: 250), NSColor(calibratedRed: 0.66, green: 0.64, blue: 1, alpha: 1))
func arrow(_ points: [NSPoint], _ head: [NSPoint]) {
    let path = NSBezierPath()
    path.lineWidth = 25
    path.lineCapStyle = .round
    path.lineJoinStyle = .round
    path.move(to: points[0])
    path.curve(to: points[3], controlPoint1: points[1], controlPoint2: points[2])
    path.move(to: head[0])
    path.line(to: head[1])
    path.line(to: head[2])
    NSColor(calibratedRed: 0.62, green: 0.95, blue: 0.84, alpha: 1).setStroke()
    path.stroke()
}
arrow([NSPoint(x: 554, y: 690),NSPoint(x: 710, y: 735),NSPoint(x: 790, y: 675),NSPoint(x: 773, y: 570)], [NSPoint(x: 734, y: 607),NSPoint(x: 773, y: 565),NSPoint(x: 817, y: 601)])
arrow([NSPoint(x: 471, y: 338),NSPoint(x: 318, y: 290),NSPoint(x: 240, y: 351),NSPoint(x: 256, y: 454)], [NSPoint(x: 211, y: 422),NSPoint(x: 256, y: 462),NSPoint(x: 296, y: 420)])
image.unlockFocus()
let dir = URL(fileURLWithPath: target)
try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
for size in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let pixels = size * scale
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
        NSGraphicsContext.current?.imageInterpolation = .high
        image.draw(in: NSRect(x: 0, y: 0, width: pixels, height: pixels), from: .zero, operation: .copy, fraction: 1)
        NSGraphicsContext.restoreGraphicsState()
        let suffix = scale == 2 ? "@2x" : ""
        try bitmap.representation(using: .png, properties: [:])!.write(to: dir.appendingPathComponent("icon_\(size)x\(size)\(suffix).png"))
    }
}
