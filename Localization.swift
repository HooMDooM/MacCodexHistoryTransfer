import Foundation

let appLanguage = (Locale.preferredLanguages.first ?? "en").lowercased().hasPrefix("ru") ? "ru" : "en"
let translations: [String: String] = {
    guard let url = Bundle.main.url(forResource: "translations", withExtension: "json"),
          let data = try? Data(contentsOf: url),
          let result = try? JSONDecoder().decode([String: String].self, from: data) else { return [:] }
    return result
}()

func L(_ text: String) -> String {
    if appLanguage == "ru" { return text }
    var result = text
    for key in translations.keys.sorted(by: { $0.count > $1.count }) {
        result = result.replacingOccurrences(of: key, with: translations[key]!)
    }
    return result
}
