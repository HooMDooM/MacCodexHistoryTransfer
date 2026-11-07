import SwiftUI
import AppKit

let accentA = Color(red: 0.45, green: 0.38, blue: 0.98)
let accentB = Color(red: 0.16, green: 0.62, blue: 1.0)
let accentGradient = LinearGradient(colors: [accentA, accentB], startPoint: .leading, endPoint: .trailing)

struct VisualEffect: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = .underWindowBackground
        view.blendingMode = .behindWindow
        view.state = .active
        return view
    }
    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {}
}

struct RootView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        ZStack {
            VisualEffect().ignoresSafeArea()
            Circle().fill(accentA.opacity(0.18)).frame(width: 420).blur(radius: 90).offset(x: -180, y: -260)
            Circle().fill(accentB.opacity(0.14)).frame(width: 380).blur(radius: 90).offset(x: 200, y: 280)
            VStack(alignment: .leading, spacing: 22) {
                Header()
                Group {
                    switch model.screen {
                    case .search: SearchView(model: model)
                    case .connected: ConnectedView(model: model)
                    case .transfer: TransferView(model: model)
                    case .done: DoneView(model: model)
                    case .failed: FailedView(model: model)
                    }
                }
                .transition(.asymmetric(insertion: .opacity.combined(with: .move(edge: .trailing)), removal: .opacity.combined(with: .scale(scale: 0.96))))
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            }
            .padding(.horizontal, 32)
            .padding(.top, 44)
            .padding(.bottom, 26)
        }
        .frame(minWidth: 520, minHeight: 600)
    }
}

struct Header: View {
    var body: some View {
        HStack(spacing: 14) {
            Image(nsImage: NSApp.applicationIconImage).resizable().frame(width: 48, height: 48)
            VStack(alignment: .leading, spacing: 2) {
                Text(appName).font(.system(size: 22, weight: .bold, design: .rounded))
                Text(L("Перенос истории Codex между вашими Mac")).font(.subheadline).foregroundColor(.secondary)
            }
        }
    }
}

struct Card<Content: View>: View {
    let content: Content
    init(@ViewBuilder content: () -> Content) { self.content = content() }
    var body: some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(.regularMaterial))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(Color.primary.opacity(0.07)))
            .shadow(color: .black.opacity(0.08), radius: 14, y: 6)
    }
}

struct Banner: View {
    let icon: String
    let text: String
    let color: Color
    var action: (String, () -> Void)?
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon).font(.system(size: 18, weight: .semibold)).foregroundColor(color)
            Text(text).font(.callout).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
            Spacer(minLength: 8)
            if let action = action { Button(action.0, action: action.1).controlSize(.small) }
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(color.opacity(0.12)))
        .transition(.opacity.combined(with: .move(edge: .top)))
    }
}

struct PrimaryButton: View {
    let title: String
    var icon: String?
    var busy = false
    let action: () -> Void
    @Environment(\.isEnabled) var enabled
    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if busy { ProgressView().controlSize(.small).colorScheme(.dark) }
                else if let icon = icon { Image(systemName: icon) }
                Text(title)
            }
            .font(.system(size: 15, weight: .semibold))
            .foregroundColor(.white)
            .padding(.horizontal, 22)
            .frame(height: 42)
            .background(Capsule().fill(accentGradient).opacity(enabled ? 1 : 0.4))
            .shadow(color: accentA.opacity(enabled ? 0.35 : 0), radius: 10, y: 4)
        }
        .buttonStyle(.plain)
    }
}

struct SecondaryButton: View {
    let title: String
    var icon: String?
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 7) {
                if let icon = icon { Image(systemName: icon) }
                Text(title)
            }
            .font(.system(size: 14, weight: .medium))
            .padding(.horizontal, 18)
            .frame(height: 42)
            .background(Capsule().fill(.thinMaterial))
            .overlay(Capsule().stroke(Color.primary.opacity(0.1)))
        }
        .buttonStyle(.plain)
    }
}

struct Radar: View {
    var body: some View {
        TimelineView(.animation) { context in
            let t = context.date.timeIntervalSinceReferenceDate
            ZStack {
                ForEach(0..<3) { i in
                    let phase = (t / 2.4 + Double(i) / 3).truncatingRemainder(dividingBy: 1)
                    Circle().stroke(accentB.opacity(0.6 * (1 - phase)), lineWidth: 2)
                        .frame(width: 30 + 110 * phase, height: 30 + 110 * phase)
                }
                Image(systemName: "laptopcomputer").font(.system(size: 26, weight: .medium)).foregroundStyle(accentGradient)
            }
            .frame(height: 140)
        }
    }
}

struct SearchView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(L("Mac рядом")).font(.headline)
                if model.searching { ProgressView().controlSize(.small) }
                Spacer()
            }
            Card {
                if model.peers.isEmpty {
                    VStack(spacing: 10) {
                        Radar()
                        Text(L("Ищем Mac…")).font(.headline)
                        Text(model.hint.isEmpty ? L("Откройте это приложение на втором Mac в той же сети.") : model.hint).font(.callout).foregroundColor(.secondary).multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                } else {
                    VStack(spacing: 6) {
                        ForEach(model.peers, id: \.id) { peer in PeerRow(peer: peer, selected: peer.id == model.selectedID) {
                            withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) { model.selectedID = peer.id }
                        } }
                    }
                }
            }
            if !model.remoteLogin {
                Banner(icon: "lock.shield", text: L("Чтобы другой Mac мог подключиться к этому, включите «Удалённый вход» для своего пользователя."), color: .orange, action: (L("Включить"), model.openSharingSettings))
            }
            if !model.errorText.isEmpty {
                Banner(icon: "exclamationmark.triangle.fill", text: model.errorText, color: .red)
            }
            Spacer(minLength: 0)
            HStack {
                SecondaryButton(title: L("Найти Mac"), icon: "magnifyingglass") { model.search() }.disabled(model.connecting)
                Spacer()
                PrimaryButton(title: model.connecting ? L("Подключаю…") : L("Подключить"), icon: "link", busy: model.connecting) { model.connect() }
                    .disabled(model.selectedPeer == nil || model.connecting)
            }
            if let code = model.fingerprint {
                Text(L("Код этого Mac: ") + code).font(.system(size: 11, design: .monospaced)).foregroundColor(.secondary).textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .center)
            }
        }
    }
}

struct PeerRow: View {
    let peer: NearbyMac
    let selected: Bool
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 10, style: .continuous).fill(selected ? AnyShapeStyle(accentGradient) : AnyShapeStyle(Color.primary.opacity(0.06)))
                    Image(systemName: "laptopcomputer").font(.system(size: 17, weight: .medium)).foregroundColor(selected ? .white : .primary)
                }
                .frame(width: 40, height: 40)
                VStack(alignment: .leading, spacing: 2) {
                    Text(peer.name).font(.system(size: 14, weight: .semibold)).lineLimit(1)
                    Text(peer.endpoint).font(.caption).foregroundColor(.secondary).lineLimit(1)
                }
                Spacer()
                Image(systemName: selected ? "checkmark.circle.fill" : "circle").font(.system(size: 19)).foregroundStyle(selected ? AnyShapeStyle(accentGradient) : AnyShapeStyle(Color.secondary.opacity(0.5)))
            }
            .padding(10)
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(selected ? accentA.opacity(0.1) : Color.clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

struct MacBadge: View {
    let name: String
    let caption: String
    var highlight = false
    var body: some View {
        VStack(spacing: 8) {
            ZStack {
                RoundedRectangle(cornerRadius: 22, style: .continuous).fill(highlight ? AnyShapeStyle(accentGradient) : AnyShapeStyle(.regularMaterial))
                    .shadow(color: (highlight ? accentA : .black).opacity(0.2), radius: 12, y: 5)
                Image(systemName: "laptopcomputer").font(.system(size: 36, weight: .regular)).foregroundColor(highlight ? .white : .primary)
            }
            .frame(width: 92, height: 92)
            Text(name).font(.system(size: 14, weight: .semibold)).lineLimit(1).truncationMode(.middle)
            Text(caption).font(.caption).foregroundColor(.secondary)
        }
        .frame(width: 150)
    }
}

struct FlowDots: View {
    var active = true
    var body: some View {
        TimelineView(.animation(minimumInterval: nil, paused: !active)) { context in
            let t = context.date.timeIntervalSinceReferenceDate
            HStack(spacing: 7) {
                ForEach(0..<7) { i in
                    let wave = max(0, sin(t * 4 - Double(i) * 0.7))
                    Circle().fill(accentGradient).frame(width: 7 + 3 * wave, height: 7 + 3 * wave).opacity(active ? 0.25 + 0.75 * wave : 0.3)
                }
            }
            .frame(height: 12)
        }
    }
}

struct Pair: View {
    let source: String
    let destination: String
    let localIsSource: Bool
    var animated = true
    var body: some View {
        HStack(spacing: 0) {
            MacBadge(name: source, caption: localIsSource ? L("Этот Mac · отправляет") : L("Отправляет"), highlight: true)
            FlowDots(active: animated).frame(maxWidth: .infinity)
            MacBadge(name: destination, caption: localIsSource ? L("Получает") : L("Этот Mac · получает"))
        }
    }
}

struct ConnectedView: View {
    @ObservedObject var model: AppModel
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Card {
                VStack(spacing: 14) {
                    Pair(source: model.sourceName, destination: model.destinationName, localIsSource: model.push, animated: false)
                        .id(model.push)
                        .transition(.opacity)
                    Button {
                        withAnimation(.spring(response: 0.45, dampingFraction: 0.8)) { model.push.toggle() }
                    } label: {
                        Label(L("Поменять направление"), systemImage: "arrow.left.arrow.right").font(.callout.weight(.medium))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(accentGradient)
                }
                .padding(.vertical, 6)
            }
            Card {
                VStack(alignment: .leading, spacing: 10) {
                    Info(icon: "xmark.app", text: L("Codex автоматически закроется на обоих Mac."))
                    Info(icon: "bolt.horizontal", text: L("Передаются только новые и изменённые данные."))
                    Info(icon: "arrow.triangle.2.circlepath", text: L("История на принимающем Mac будет заменена. Резервная копия не создаётся."))
                    Info(icon: "folder", text: L("Проекты, вход в аккаунт и настройки остаются на своих Mac."))
                }
            }
            Spacer(minLength: 0)
            HStack {
                SecondaryButton(title: L("Другой Mac"), icon: "chevron.left") { model.disconnect() }
                Spacer()
                PrimaryButton(title: L("Перенести"), icon: "arrow.right.circle.fill") { model.transfer() }
            }
        }
    }
}

struct Info: View {
    let icon: String
    let text: String
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon).frame(width: 20).foregroundStyle(accentGradient)
            Text(text).font(.callout).fixedSize(horizontal: false, vertical: true)
        }
    }
}

struct ProgressBar: View {
    let value: Double
    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Color.primary.opacity(0.08))
                Capsule().fill(accentGradient)
                    .frame(width: max(14, geo.size.width * value / 100))
                    .overlay(
                        TimelineView(.animation) { context in
                            let t = context.date.timeIntervalSinceReferenceDate
                            let x = (t / 1.6).truncatingRemainder(dividingBy: 1)
                            LinearGradient(colors: [.clear, .white.opacity(0.45), .clear], startPoint: .leading, endPoint: .trailing)
                                .frame(width: 90)
                                .offset(x: -90 + (geo.size.width * value / 100 + 90) * x)
                        }
                        .clipShape(Capsule()), alignment: .leading)
            }
        }
        .frame(height: 12)
    }
}

func phaseTitle(_ phase: String, _ role: String) -> String {
    switch phase {
    case "closing": return L("Закрываю Codex на обоих Mac…")
    case "comparing": return L("Ищу новое и изменённое…")
    case "sending": return L("Отправляю изменения…")
    case "receiving": return L("Получаю изменения…")
    case "installing": return L("Проверяю и устанавливаю историю…")
    default: return L("Подготовка…")
    }
}

struct TransferView: View {
    @ObservedObject var model: AppModel
    var body: some View {
        let s = model.status ?? TransferStatus()
        let localIsSource = s.role.isEmpty ? model.push : s.role == "source"
        let peer = s.peer.isEmpty ? model.connectedName : s.peer
        VStack(spacing: 20) {
            Card {
                VStack(spacing: 22) {
                    Pair(source: localIsSource ? model.localName : peer, destination: localIsSource ? peer : model.localName, localIsSource: localIsSource)
                    Text("\(Int(s.percent.rounded(.down)))%")
                        .font(.system(size: 60, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .contentTransition(.numericText())
                        .foregroundStyle(accentGradient)
                    ProgressBar(value: s.percent).animation(.easeOut(duration: 0.4), value: s.percent)
                    VStack(spacing: 4) {
                        Text(phaseTitle(s.phase, s.role)).font(.headline)
                        if s.total > 0 && (s.phase == "sending" || s.phase == "receiving") {
                            Text(ByteCountFormatter.string(fromByteCount: Int64(s.current), countStyle: .file) + " / " + ByteCountFormatter.string(fromByteCount: Int64(s.total), countStyle: .file))
                                .font(.callout).monospacedDigit().foregroundColor(.secondary)
                        }
                    }
                }
                .padding(.vertical, 10)
            }
            Banner(icon: "exclamationmark.circle", text: L("Не открывайте Codex и не выключайте Mac до завершения."), color: .orange)
            Spacer(minLength: 0)
            if model.running && !model.log.isEmpty { LogView(text: model.log) }
        }
    }
}

struct LogView: View {
    let text: String
    @State var open = false
    var body: some View {
        DisclosureGroup(L("Подробности"), isExpanded: $open) {
            ScrollView {
                Text(text).font(.system(size: 11, design: .monospaced)).frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
            }
            .frame(height: 110)
        }
        .font(.callout)
    }
}

struct ResultIcon: View {
    let icon: String
    let color: Color
    @State var shown = false
    var body: some View {
        ZStack {
            Circle().fill(color.opacity(0.15)).frame(width: 130, height: 130).scaleEffect(shown ? 1 : 0.4)
            Circle().fill(color).frame(width: 92, height: 92).shadow(color: color.opacity(0.4), radius: 16, y: 6)
            Image(systemName: icon).font(.system(size: 42, weight: .bold)).foregroundColor(.white).scaleEffect(shown ? 1 : 0.2)
        }
        .scaleEffect(shown ? 1 : 0.6)
        .opacity(shown ? 1 : 0)
        .onAppear { withAnimation(.spring(response: 0.55, dampingFraction: 0.55).delay(0.1)) { shown = true } }
    }
}

struct DoneView: View {
    @ObservedObject var model: AppModel
    var body: some View {
        let s = model.status ?? TransferStatus()
        let localIsDestination = s.role.isEmpty ? !model.push : s.role == "destination"
        let peer = s.peer.isEmpty ? model.connectedName : s.peer
        VStack(spacing: 18) {
            Spacer(minLength: 0)
            ResultIcon(icon: "checkmark", color: .green)
            Text(L("История перенесена")).font(.system(size: 26, weight: .bold, design: .rounded))
            Text(localIsDestination ? L("Можно открыть Codex на этом Mac.") : L("Откройте Codex на Mac: ") + peer)
                .font(.callout).foregroundColor(.secondary).multilineTextAlignment(.center)
            Spacer(minLength: 0)
            PrimaryButton(title: L("Готово"), icon: "checkmark") { model.dismiss() }
        }
        .frame(maxWidth: .infinity)
    }
}

struct FailedView: View {
    @ObservedObject var model: AppModel
    var body: some View {
        VStack(spacing: 18) {
            Spacer(minLength: 0)
            ResultIcon(icon: "xmark", color: .orange)
            Text(L("Перенос не выполнен")).font(.system(size: 26, weight: .bold, design: .rounded))
            Text(model.errorText).font(.callout).foregroundColor(.secondary).multilineTextAlignment(.center).textSelection(.enabled)
            Spacer(minLength: 0)
            if !model.log.isEmpty { LogView(text: model.log) }
            PrimaryButton(title: L("Назад"), icon: "chevron.left") { model.dismiss() }
        }
        .frame(maxWidth: .infinity)
    }
}
