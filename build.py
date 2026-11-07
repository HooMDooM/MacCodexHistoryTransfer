import pathlib,plistlib,shutil,subprocess
root=pathlib.Path(__file__).resolve().parent
name='Mac Codex History Transfer'
version='0.4.0'
executable='MacCodexHistoryTransfer'
app=root/'dist'/(name+'.app')
if app.exists(): shutil.rmtree(app)
contents=app/'Contents'
(contents/'MacOS').mkdir(parents=True)
(contents/'Resources').mkdir()
for file in ['agent.py','transfer.py','pairing.py','localization.py','translations.json','README.txt','README-en.txt']: shutil.copy2(root/file,contents/'Resources'/file)
subprocess.run(['/usr/bin/swift',str(root/'Icon.swift'),str(root/'dist/AppIcon.iconset')],check=True)
subprocess.run(['/usr/bin/iconutil','-c','icns',str(root/'dist/AppIcon.iconset'),'-o',str(contents/'Resources/AppIcon.icns')],check=True)
info={'CFBundleName':name,'CFBundleDisplayName':name,'CFBundleIdentifier':'local.codex.transfer','CFBundleExecutable':executable,'CFBundleIconFile':'AppIcon','CFBundleVersion':'6','CFBundleShortVersionString':version,'CFBundlePackageType':'APPL','LSMinimumSystemVersion':'13.0','NSAppleEventsUsageDescription':'Закрытие Codex перед переносом истории между вашими Mac.','CFBundleLocalizations':['ru','en'],'CFBundleDevelopmentRegion':'en','NSHighResolutionCapable':True,'NSLocalNetworkUsageDescription':'Поиск второго Mac для переноса истории Codex.','NSBonjourServices':['_codex-xfer._tcp.']}
(contents/'Info.plist').write_bytes(plistlib.dumps(info))
for language,network,events in [
    ('ru','Поиск второго Mac для переноса истории.','Закрытие Codex перед переносом истории.'),
    ('en','Find your other Mac to transfer chat history.','Close Codex before transferring chat history.')]:
    folder=contents/'Resources'/(language+'.lproj')
    folder.mkdir(exist_ok=True)
    (folder/'InfoPlist.strings').write_text('"CFBundleDisplayName" = "'+name+'";\n"NSLocalNetworkUsageDescription" = "'+network+'";\n"NSAppleEventsUsageDescription" = "'+events+'";\n')
sources=[str(root/f) for f in ['main.swift','Views.swift','Discovery.swift','Localization.swift']]
binaries=[]
for arch in ['arm64','x86_64']:
    binary=root/'dist'/(executable+'-'+arch)
    subprocess.run(['/usr/bin/swiftc','-O','-target',arch+'-apple-macos13.0','-framework','Cocoa','-framework','SwiftUI',*sources,'-o',str(binary)],check=True)
    binaries.append(str(binary))
subprocess.run(['/usr/bin/lipo','-create',*binaries,'-output',str(contents/'MacOS'/executable)],check=True)
for binary in binaries:pathlib.Path(binary).unlink()
subprocess.run(['/usr/bin/codesign','--force','--deep','--sign','-',str(app)],check=True)
archive=root/'dist'/('Mac-Codex-History-Transfer-'+version+'.zip')
if archive.exists(): archive.unlink()
subprocess.run(['/usr/bin/ditto','-c','-k','--keepParent',str(app),str(archive)],check=True)
print(app)
print(archive)
