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
for number in 0..<min(pdf.pageCount, limit) {
    guard let page = pdf.page(at: number) else { continue }
    let bounds = page.bounds(for: .mediaBox)
    let scale = min(3.5, 2400 / max(bounds.width, bounds.height))
    let image = page.thumbnail(of: NSSize(width: bounds.width * scale, height: bounds.height * scale), for: .mediaBox)
    guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["en-US"]
    request.usesLanguageCorrection = false
    try VNImageRequestHandler(cgImage: cg).perform([request])
    var words: [[Any]] = []
    for observation in request.results ?? [] {
        guard let candidate = observation.topCandidates(1).first else { continue }
        let text = candidate.string
        let expression = try NSRegularExpression(pattern: "\\S+")
        for match in expression.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
            guard let range = Range(match.range, in: text), let box = try candidate.boundingBox(for: range) else { continue }
            let rect = box.boundingBox
            words.append([rect.minX * bounds.width, (1-rect.maxY) * bounds.height,
                          rect.maxX * bounds.width, (1-rect.minY) * bounds.height,
                          String(text[range]), candidate.confidence])
        }
    }
    pages.append(["page": number+1, "width": bounds.width, "height": bounds.height, "words": words])
}
let data = try JSONSerialization.data(withJSONObject: ["engine":"Apple Vision accurate; language correction disabled", "pages":pages], options: [.sortedKeys])
FileHandle.standardOutput.write(data)
