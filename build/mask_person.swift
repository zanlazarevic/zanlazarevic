// Write a person-segmentation mask (white = person, black = background) for a photo,
// using the macOS Vision framework. No downloads, no Python deps.
//   usage: swift build/mask_person.swift assets/photo.jpg assets/photo-mask.png
import Foundation
import AppKit
import Vision
import CoreImage

let args = CommandLine.arguments
guard args.count == 3 else { fputs("usage: mask_person.swift <photo> <mask.png>\n", stderr); exit(64) }
guard let nsimg = NSImage(contentsOfFile: args[1]),
      let cg = nsimg.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    fputs("cannot read \(args[1])\n", stderr); exit(66)
}
let request = VNGeneratePersonSegmentationRequest()
request.qualityLevel = .accurate
request.outputPixelFormat = kCVPixelFormatType_OneComponent8
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
do { try handler.perform([request]) } catch { fputs("vision failed: \(error)\n", stderr); exit(70) }
guard let buffer = request.results?.first?.pixelBuffer else { fputs("no mask produced\n", stderr); exit(70) }
let mask = CIImage(cvPixelBuffer: buffer)
let scaled = mask.transformed(by: CGAffineTransform(scaleX: CGFloat(cg.width) / mask.extent.width,
                                                    y: CGFloat(cg.height) / mask.extent.height))
guard let out = CIContext().createCGImage(scaled, from: CGRect(x: 0, y: 0, width: cg.width, height: cg.height)),
      let png = NSBitmapImageRep(cgImage: out).representation(using: .png, properties: [:]) else {
    fputs("cannot render mask\n", stderr); exit(70)
}
do { try png.write(to: URL(fileURLWithPath: args[2])) } catch { fputs("write failed: \(error)\n", stderr); exit(73) }
print("mask written: \(args[2]) \(cg.width)x\(cg.height)")
