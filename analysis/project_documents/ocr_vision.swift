// Local macOS OCR for image-only POW pages. Preserves word boxes and confidence.
import Foundation
import AppKit
import PDFKit
import Vision
let arguments = CommandLine.arguments
if arguments.count < 2 { fputs("Usage: swift ocr_vision.swift input.pdf [page-limit]\n", stderr); exit(2) }
guard let pdf = PDFDocument(url: URL(fileURLWithPath: arguments[1])) else { exit(2) }
let limit = arguments.count > 2 ? Int(arguments[2]) ?? 100 : 100
var pages: [[String: Any]] = []
func rotate(_ source: CGImage, clockwise: Bool) -> CGImage? {
    let width = source.width, height = source.height
    guard let colorSpace = source.colorSpace,
          let context = CGContext(data: nil, width: height, height: width,
                                  bitsPerComponent: 8, bytesPerRow: 0,
                                  space: colorSpace, bitmapInfo: source.bitmapInfo.rawValue) else { return nil }
    if clockwise {
        context.translateBy(x: CGFloat(height), y: 0)
        context.rotate(by: .pi / 2)
    } else {
        context.translateBy(x: 0, y: CGFloat(width))
        context.rotate(by: -.pi / 2)
    }
    context.draw(source, in: CGRect(x: 0, y: 0, width: CGFloat(width), height: CGFloat(height)))
    return context.makeImage()
}
func rotateHalfTurn(_ source: CGImage) -> CGImage? {
    guard let colorSpace = source.colorSpace,
          let context = CGContext(data: nil, width: source.width, height: source.height,
                                  bitsPerComponent: 8, bytesPerRow: 0,
                                  space: colorSpace, bitmapInfo: source.bitmapInfo.rawValue) else { return nil }
    context.translateBy(x: CGFloat(source.width), y: CGFloat(source.height))
    context.rotate(by: .pi)
    context.draw(source, in: CGRect(x: 0, y: 0, width: CGFloat(source.width), height: CGFloat(source.height)))
    return context.makeImage()
}
func recognize(_ image: CGImage) -> (Int, [[Any]]) {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["en-US"]
    request.usesLanguageCorrection = false
    do { try VNImageRequestHandler(cgImage: image).perform([request]) } catch { return (0, []) }
    var words: [[Any]] = [], strings: [String] = []
    for observation in request.results ?? [] {
        guard let candidate = observation.topCandidates(1).first else { continue }
        let text = candidate.string
        strings.append(text)
        let expression = try! NSRegularExpression(pattern: "\\S+")
        for match in expression.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
            guard let range = Range(match.range, in: text), let box = try? candidate.boundingBox(for: range) else { continue }
            let rect = box.boundingBox
            words.append([rect.minX * CGFloat(image.width), (1-rect.maxY) * CGFloat(image.height),
                          rect.maxX * CGFloat(image.width), (1-rect.minY) * CGFloat(image.height),
                          String(text[range]), candidate.confidence])
        }
    }
    let text = strings.joined(separator: " ").uppercased()
    let cues = ["ITEM NO", "DESCRIPTION", "QUANTITY", "DIRECT COST", "TOTAL COST", "TOTAL UNIT COST"]
    let score = cues.reduce(0) { $0 + (text.contains($1) ? 10 : 0) } + min(words.count, 30) / 3 + headerAlignment(words)
    return (score, words)
}
func headerAlignment(_ words: [[Any]]) -> Int {
    let terms = Set(["ITEM", "DESCRIPTION", "QUANTITY", "DIRECT", "TOTAL", "UNIT"])
    var buckets: [Int: Set<String>] = [:]
    for word in words where word.count > 4 {
        guard let y = word[1] as? CGFloat, let token = word[4] as? String else { continue }
        let key = token.uppercased().trimmingCharacters(in: CharacterSet(charactersIn: ".:%"))
        if terms.contains(key) { buckets[Int(y / 65), default: []].insert(key) }
    }
    return (buckets.values.map(\.count).max() ?? 0) * 8
}
for number in 0..<min(pdf.pageCount, limit) {
    guard let page = pdf.page(at: number) else { continue }
    let bounds = page.bounds(for: .mediaBox)
    let scale = min(3.5, 2400 / max(bounds.width, bounds.height))
    let image = page.thumbnail(of: NSSize(width: bounds.width * scale, height: bounds.height * scale), for: .mediaBox)
    guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let candidates: [(Int, CGImage)] = [(0, cg)] +
        (rotate(cg, clockwise: true).map { [(90, $0)] } ?? []) +
        (rotateHalfTurn(cg).map { [(180, $0)] } ?? []) +
        (rotate(cg, clockwise: false).map { [(270, $0)] } ?? [])
    let ranked = candidates.map { candidate in
        let (score, words) = recognize(candidate.1)
        return (score, candidate.0, candidate.1, words)
    }
    let best = ranked.max { $0.0 < $1.0 }!
    pages.append(["page": number+1, "width": best.2.width, "height": best.2.height,
                  "rotation": best.1, "words": best.3])
}
let data = try JSONSerialization.data(withJSONObject: ["engine":"Apple Vision accurate; language correction disabled", "pages":pages], options: [.sortedKeys])
FileHandle.standardOutput.write(data)
