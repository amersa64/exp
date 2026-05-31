// Renders TheCoach app icon to 1024x1024 PNG.
//
// Run: swift ios/tools/render_icon.swift <output_path>
//
// The icon reuses FrontMountainShape from WorldView.swift (same peak silhouette
// shown on the Summit hero), drawn in ember gradient on a coal/violet
// atmospheric background, with a glowing summit star — matches the in-app
// visual identity exactly.

import AppKit
import CoreGraphics

let size: CGFloat = 1024

guard CommandLine.arguments.count >= 2 else {
    FileHandle.standardError.write("usage: render_icon.swift <output_path>\n".data(using: .utf8)!)
    exit(1)
}
let outputPath = CommandLine.arguments[1]

// MARK: - Palette (matches Theme.swift exactly)

let night   = NSColor(red: 0.040, green: 0.046, blue: 0.110, alpha: 1)
let plum    = NSColor(red: 0.120, green: 0.066, blue: 0.200, alpha: 1)
let coal    = NSColor(red: 0.050, green: 0.035, blue: 0.090, alpha: 1)
let ember   = NSColor(red: 1.000, green: 0.420, blue: 0.210, alpha: 1) // #FF6B35
let gold    = NSColor(red: 1.000, green: 0.690, blue: 0.280, alpha: 1) // #FFB047
let violet  = NSColor(red: 0.486, green: 0.227, blue: 0.929, alpha: 1) // #7C3AED

// MARK: - Bitmap context

let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!
guard let ctx = CGContext(
    data: nil,
    width: Int(size),
    height: Int(size),
    bitsPerComponent: 8,
    bytesPerRow: 0,
    space: colorSpace,
    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
) else {
    fatalError("could not create CGContext")
}

// Flip so y=0 is top (matches SwiftUI coordinates we copy from)
ctx.translateBy(x: 0, y: size)
ctx.scaleBy(x: 1, y: -1)

let rect = CGRect(x: 0, y: 0, width: size, height: size)

// MARK: - Background: atmospheric gradient (night -> plum -> coal)

let bgGradient = CGGradient(
    colorsSpace: colorSpace,
    colors: [night.cgColor, plum.cgColor, coal.cgColor] as CFArray,
    locations: [0.0, 0.55, 1.0]
)!
ctx.drawLinearGradient(
    bgGradient,
    start: CGPoint(x: size / 2, y: 0),
    end: CGPoint(x: size / 2, y: size),
    options: []
)

// Subtle violet glow top-left (matches AtmosphericBackground).
// startRadius MUST be 0 — a non-zero inner radius creates a hard saturated
// dot at the center, which reads as an artifact on a 1024px icon.
ctx.saveGState()
let violetGlow = CGGradient(
    colorsSpace: colorSpace,
    colors: [violet.withAlphaComponent(0.22).cgColor, violet.withAlphaComponent(0).cgColor] as CFArray,
    locations: [0.0, 1.0]
)!
ctx.drawRadialGradient(
    violetGlow,
    startCenter: CGPoint(x: size * 0.18, y: size * 0.18),
    startRadius: 0,
    endCenter: CGPoint(x: size * 0.18, y: size * 0.18),
    endRadius: size * 0.55,
    options: []
)
ctx.restoreGState()

// Warm ember glow rising from below (matches AtmosphericBackground)
ctx.saveGState()
let emberGlow = CGGradient(
    colorsSpace: colorSpace,
    colors: [ember.withAlphaComponent(0.45).cgColor, ember.withAlphaComponent(0).cgColor] as CFArray,
    locations: [0.0, 1.0]
)!
ctx.drawRadialGradient(
    emberGlow,
    startCenter: CGPoint(x: size * 0.5, y: size * 1.02),
    startRadius: 20,
    endCenter: CGPoint(x: size * 0.5, y: size * 1.02),
    endRadius: size * 0.70,
    options: []
)
ctx.restoreGState()

// MARK: - Mountain shape (FrontMountainShape from WorldView.swift)
//
// Inset the mountain a bit from the edges and weight it toward the bottom
// so the silhouette reads cleanly at the home-screen size (~120pt).

let mountainRect = CGRect(
    x: size * 0.08,
    y: size * 0.18,   // shifted down — most of the icon is sky + mountain
    width: size * 0.84,
    height: size * 0.72
)

let mw = mountainRect.width
let mh = mountainRect.height
let mx = mountainRect.minX
let my = mountainRect.minY

let mountain = CGMutablePath()
mountain.move(to:    CGPoint(x: mx + mw * 0.10, y: my + mh))
mountain.addLine(to: CGPoint(x: mx + mw * 0.36, y: my + mh * 0.58))
mountain.addLine(to: CGPoint(x: mx + mw * 0.46, y: my + mh * 0.66))
mountain.addLine(to: CGPoint(x: mx + mw * 0.55, y: my + mh * 0.30))   // peak
mountain.addLine(to: CGPoint(x: mx + mw * 0.66, y: my + mh * 0.52))
mountain.addLine(to: CGPoint(x: mx + mw * 0.78, y: my + mh * 0.68))
mountain.addLine(to: CGPoint(x: mx + mw * 0.90, y: my + mh))
mountain.closeSubpath()

// Drop shadow under the mountain (violet, soft)
ctx.saveGState()
ctx.setShadow(
    offset: CGSize(width: 0, height: 18),
    blur: 60,
    color: violet.withAlphaComponent(0.55).cgColor
)
// Stub fill to lay down the shadow only
ctx.addPath(mountain)
ctx.setFillColor(CGColor(red: 0, green: 0, blue: 0, alpha: 1))
ctx.fillPath()
ctx.restoreGState()

// Mountain fill — ember linear gradient (gold top-leading -> ember bottom-trailing)
ctx.saveGState()
ctx.addPath(mountain)
ctx.clip()
let emberGradient = CGGradient(
    colorsSpace: colorSpace,
    colors: [gold.cgColor, ember.cgColor] as CFArray,
    locations: [0.0, 1.0]
)!
ctx.drawLinearGradient(
    emberGradient,
    start: CGPoint(x: mountainRect.minX, y: mountainRect.minY),
    end: CGPoint(x: mountainRect.maxX, y: mountainRect.maxY),
    options: []
)
ctx.restoreGState()

// MARK: - Summit star (small, glowing)
//
// 5-point star centered just above the peak. Glow halo first, then crisp white
// star with ember tint — matches the Summit hero treatment.

let peakX = mx + mw * 0.55
let peakY = my + mh * 0.30
let starCenter = CGPoint(x: peakX, y: peakY - size * 0.02)
let starOuterR: CGFloat = size * 0.055
let starInnerR: CGFloat = starOuterR * 0.42

// Halo (warm glow)
ctx.saveGState()
let haloGradient = CGGradient(
    colorsSpace: colorSpace,
    colors: [gold.withAlphaComponent(0.85).cgColor, ember.withAlphaComponent(0).cgColor] as CFArray,
    locations: [0.0, 1.0]
)!
ctx.drawRadialGradient(
    haloGradient,
    startCenter: starCenter,
    startRadius: starOuterR * 0.4,
    endCenter: starCenter,
    endRadius: starOuterR * 3.2,
    options: []
)
ctx.restoreGState()

// Star path
let star = CGMutablePath()
for i in 0..<10 {
    let angle = CGFloat(i) * .pi / 5 - .pi / 2  // start pointing up
    let r = (i % 2 == 0) ? starOuterR : starInnerR
    let x = starCenter.x + r * cos(angle)
    let y = starCenter.y + r * sin(angle)
    if i == 0 { star.move(to: CGPoint(x: x, y: y)) }
    else      { star.addLine(to: CGPoint(x: x, y: y)) }
}
star.closeSubpath()

// Star fill — white at top, gold at bottom
ctx.saveGState()
ctx.addPath(star)
ctx.clip()
let starGradient = CGGradient(
    colorsSpace: colorSpace,
    colors: [NSColor.white.cgColor, gold.cgColor] as CFArray,
    locations: [0.0, 1.0]
)!
ctx.drawLinearGradient(
    starGradient,
    start: CGPoint(x: starCenter.x, y: starCenter.y - starOuterR),
    end: CGPoint(x: starCenter.x, y: starCenter.y + starOuterR),
    options: []
)
ctx.restoreGState()

// MARK: - Output

guard let cgImage = ctx.makeImage() else {
    fatalError("could not produce CGImage")
}

let bitmap = NSBitmapImageRep(cgImage: cgImage)
guard let pngData = bitmap.representation(using: .png, properties: [:]) else {
    fatalError("could not encode PNG")
}

let url = URL(fileURLWithPath: outputPath)
try pngData.write(to: url)

print("wrote \(Int(size))x\(Int(size)) icon to \(outputPath)")
