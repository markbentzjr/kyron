import os, sys, shutil, subprocess, glob, zipfile, re

KB = os.path.expanduser('~/kyron-build')
M = os.path.join(KB, 'manual')
W = os.path.join(M, 'work')
SDK = os.path.expanduser('~/AppData/Local/Android/Sdk')
BT = os.path.join(SDK, 'build-tools', '36.0.0')
AJAR = os.path.join(SDK, 'platforms', 'android-37.0', 'android.jar')
JBR = r"C:\Program Files\Android\Android Studio\jbr"
JAVA = os.path.join(JBR, 'bin', 'java.exe')
JAVAC = os.path.join(JBR, 'bin', 'javac.exe')
KOTLINC = r"C:\Program Files\Android\Android Studio\plugins\Kotlin\kotlinc\bin\kotlinc.bat"
D8 = os.path.join(BT, 'lib', 'd8.jar')
APKSIGNER = os.path.join(BT, 'lib', 'apksigner.jar')
ZIPALIGN = os.path.join(BT, 'zipalign.exe')
AAPT2 = os.path.join(BT, 'aapt2.exe')

os.environ['JAVA_HOME'] = JBR
os.environ['PATH'] = os.path.join(JBR, 'bin') + os.pathsep + os.environ.get('PATH', '')

def step(name):
    print(f"\n=== {name} ===")

def main():
    os.makedirs(W, exist_ok=True)
    os.makedirs(os.path.join(W, 'merged'), exist_ok=True)
    os.makedirs(os.path.join(W, 'aars'), exist_ok=True)

    src_app = os.path.abspath('kyron/app')
    dst_src = os.path.join(M, 'src')
    os.makedirs(dst_src, exist_ok=True)

    # Single source of build metadata (plain KEY=VALUE lines; shared with
    # app/build_manual.sh and app/build_windows.sh).
    app_meta = {}
    with open(os.path.join(src_app, 'version.properties'), encoding='utf-8') as vf:
        for val_line in vf:
            val_line = val_line.strip()
            if val_line and not val_line.startswith('#') and '=' in val_line:
                key, _, val = val_line.partition('=')
                app_meta[key.strip()] = val.strip()
    version_code, version_name = app_meta['VERSION_CODE'], app_meta['VERSION_NAME']
    min_sdk, target_sdk = app_meta['MIN_SDK'], app_meta['TARGET_SDK']
    print(f"version: {version_name} (code {version_code}), minSdk {min_sdk}, targetSdk {target_sdk}")

    app_src = os.path.join(src_app, 'src')
    if os.path.exists(app_src):
        for item in os.listdir(app_src):
            s = os.path.join(app_src, item)
            d = os.path.join(dst_src, item)
            if os.path.isdir(s):
                if os.path.exists(d): shutil.rmtree(d)
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)

    for f in glob.glob(os.path.join(src_app, '*.py')):
        shutil.copy2(f, dst_src)

    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), 'generate_test_seed.py')], check=True)

    step("0/8 unpack AAR dependencies")
    for f in glob.glob(os.path.join(M, 'deps', '*.aar')):
        name = os.path.splitext(os.path.basename(f))[0]
        out_dir = os.path.join(W, 'aars', name)
        os.makedirs(out_dir, exist_ok=True)
        with zipfile.ZipFile(f, 'r') as z:
            z.extractall(out_dir)
        print(f"Unpacked {name}.aar")

    appcompat_vals = os.path.join(W, 'aars', 'appcompat-1.7.0', 'res', 'values', 'values.xml')
    if os.path.exists(appcompat_vals):
        content = open(appcompat_vals, encoding='utf-8').read()
        def repl(m):
            inner = m.group(1)
            cleaned = re.sub(r'<attr\s+name="android:[^"]+"\s*/>', '', inner)
            return cleaned
        new_content = re.sub(r'<declare-styleable\s+name="SearchView">(.*?)</declare-styleable>', repl, content, flags=re.DOTALL)
        open(appcompat_vals, 'w', encoding='utf-8').write(new_content)
        print("Patched appcompat values.xml (unwrapped SearchView styleable)")

    cl_vals = os.path.join(W, 'aars', 'constraintlayout-2.1.4', 'res', 'values', 'values.xml')
    if os.path.exists(cl_vals):
        content = open(cl_vals, encoding='utf-8').read()
        new_content = content.replace('name="Carousel"', 'name="ConstraintCarousel"')
        open(cl_vals, 'w', encoding='utf-8').write(new_content)
        print("Patched constraintlayout values.xml (renamed Carousel to ConstraintCarousel)")

    step("1/8 merge manifests")
    merge_script = os.path.join(dst_src, 'merge_manifest.py')
    main_manifest = os.path.join(dst_src, 'main', 'AndroidManifest.xml')
    merged_manifest = os.path.join(W, 'merged', 'AndroidManifest.xml')
    aars_dir = os.path.join(W, 'aars')
    subprocess.run([sys.executable, merge_script, main_manifest, aars_dir, merged_manifest], check=True)

    step("2/8 validation gates")
    subprocess.run([sys.executable, os.path.join(M, 'tools', 'validate_pathdata.py'), os.path.join(dst_src, 'main', 'res')], check=True)
    seed_file = os.path.join(dst_src, 'main', 'assets', 'places_seed_geocoded.json')
    subprocess.run([sys.executable, os.path.join(M, 'tools', 'validate_seed.py'), seed_file], check=True)
    subprocess.run([sys.executable, os.path.join(M, 'tools', 'canary_gate.py'), seed_file, os.path.join(M, 'tools', 'canaries.json')], check=True)

    pkgs = []
    for name in sorted(os.listdir(aars_dir)):
        mp = os.path.join(aars_dir, name, 'AndroidManifest.xml')
        if os.path.exists(mp):
            import xml.etree.ElementTree as ET
            try:
                pkg = ET.parse(mp).getroot().get('package')
                resdir = os.path.join(aars_dir, name, 'res')
                if pkg and os.path.isdir(resdir) and os.listdir(resdir):
                    pkgs.append(pkg)
            except Exception:
                pass
    extra_pkgs = ':'.join(pkgs)
    print("extra packages:", extra_pkgs)

    step("3/8 aapt2 compile resources")
    res_compiled = os.path.join(W, 'res_compiled')
    if os.path.exists(res_compiled): shutil.rmtree(res_compiled)
    os.makedirs(res_compiled, exist_ok=True)
    subprocess.run([AAPT2, 'compile', '--dir', os.path.join(dst_src, 'main', 'res'), '-o', os.path.join(res_compiled, 'app.zip')], check=True)

    i = 0
    for d in sorted(glob.glob(os.path.join(aars_dir, '*/'))):
        res_d = os.path.join(d, 'res')
        if os.path.isdir(res_d) and os.listdir(res_d):
            i += 1
            lib_zip = os.path.join(res_compiled, f'lib{i}.zip')
            subprocess.run([AAPT2, 'compile', '--dir', res_d, '-o', lib_zip], check=True)
    print(f"compiled {i} library res dirs")

    step("4/8 aapt2 link (targetSdk 36)")
    assets_merged = os.path.join(W, 'assets_merged')
    if os.path.exists(assets_merged): shutil.rmtree(assets_merged)
    os.makedirs(assets_merged, exist_ok=True)

    app_assets = os.path.join(dst_src, 'main', 'assets')
    if os.path.isdir(app_assets):
        for item in os.listdir(app_assets):
            s_item = os.path.join(app_assets, item)
            d_item = os.path.join(assets_merged, item)
            if os.path.isdir(s_item): shutil.copytree(s_item, d_item)
            else: shutil.copy2(s_item, d_item)

    for d in glob.glob(os.path.join(aars_dir, '*/')):
        ast_d = os.path.join(d, 'assets')
        if os.path.isdir(ast_d) and os.listdir(ast_d):
            for item in os.listdir(ast_d):
                s_item = os.path.join(ast_d, item)
                d_item = os.path.join(assets_merged, item)
                if not os.path.exists(d_item):
                    if os.path.isdir(s_item): shutil.copytree(s_item, d_item)
                    else: shutil.copy2(s_item, d_item)

    gen_dir = os.path.join(W, 'gen')
    if os.path.exists(gen_dir): shutil.rmtree(gen_dir)
    os.makedirs(gen_dir, exist_ok=True)

    res_zips = glob.glob(os.path.join(res_compiled, '*.zip'))
    link_cmd = [
        AAPT2, 'link',
        '-o', os.path.join(W, 'resources.apk'),
        '-I', AJAR,
        '--manifest', merged_manifest,
        '--java', gen_dir,
        '-A', assets_merged,
        '--min-sdk-version', min_sdk,
        '--target-sdk-version', target_sdk,
        '--version-code', version_code,
        '--version-name', version_name,
        '--auto-add-overlay',
    ]
    if extra_pkgs:
        link_cmd.extend(['--extra-packages', extra_pkgs])
    link_cmd.extend(res_zips)
    subprocess.run(link_cmd, check=True)
    print("linked resources.apk with targetSdk 36")

    step("5/8 compile Kotlin + generated R")
    deps_jars = glob.glob(os.path.join(M, 'deps', '*.jar'))
    aar_classes = glob.glob(os.path.join(aars_dir, '*/classes.jar'))
    aar_libs = glob.glob(os.path.join(aars_dir, '*/libs/*.jar'))
    cp = ';'.join(deps_jars + aar_classes + aar_libs + [AJAR])

    sources_txt = os.path.join(W, 'sources.txt')
    with open(sources_txt, 'w', encoding='utf-8') as sf:
        for root, dirs, files in os.walk(os.path.join(dst_src, 'main', 'java')):
            for f in files:
                if f.endswith('.kt'):
                    sf.write(os.path.join(root, f) + '\n')
        for root, dirs, files in os.walk(gen_dir):
            for f in files:
                if f.endswith('.java'):
                    sf.write(os.path.join(root, f) + '\n')

    classes_jar = os.path.join(W, 'classes.jar')
    kotlinc_args = [
        KOTLINC,
        '-classpath', cp,
        '-d', classes_jar,
        '-jvm-target', '17',
        '-no-stdlib', '-no-reflect',
        '@' + sources_txt
    ]
    subprocess.run(kotlinc_args, check=True)
    print("compiled classes.jar via kotlinc")

    r_sources = []
    for root, dirs, files in os.walk(gen_dir):
        for f in files:
            if f == 'R.java':
                r_sources.append(os.path.join(root, f))
    rclasses = os.path.join(W, 'rclasses')
    if os.path.exists(rclasses): shutil.rmtree(rclasses)
    os.makedirs(rclasses, exist_ok=True)
    if r_sources:
        javac_cmd = [JAVAC, '-encoding', 'UTF-8', '-nowarn', '-cp', AJAR, '-d', rclasses] + r_sources
        subprocess.run(javac_cmd, check=True)
        subprocess.run([JAVA.replace('java.exe', 'jar.exe'), 'uf', classes_jar, '-C', rclasses, '.'], check=True)
        print("R classes compiled and added to classes.jar")

    step("6/8 dex with d8")
    dex_dir = os.path.join(W, 'dex')
    if os.path.exists(dex_dir): shutil.rmtree(dex_dir)
    os.makedirs(dex_dir, exist_ok=True)

    d8_inputs = [classes_jar] + deps_jars + aar_classes + aar_libs
    d8_cmd = [JAVA, '-Xmx640m', '-cp', D8, 'com.android.tools.r8.D8', '--lib', AJAR, '--min-api', '29', '--output', dex_dir] + d8_inputs
    subprocess.run(d8_cmd, check=True)
    print("D8 dexing complete")

    step("7/8 assemble + align")
    unsigned_apk = os.path.join(W, 'kyron-unsigned.apk')
    shutil.copy2(os.path.join(W, 'resources.apk'), unsigned_apk)

    services_stage = os.path.join(W, 'services_stage')
    if os.path.exists(services_stage): shutil.rmtree(services_stage)
    os.makedirs(services_stage, exist_ok=True)

    all_jars = [j for j in (deps_jars + aar_classes + aar_libs) if 'stubs' not in j]
    for j in all_jars:
        try:
            with zipfile.ZipFile(j, 'r') as z:
                for name in z.namelist():
                    if name.startswith('META-INF/services/'):
                        target_path = os.path.join(services_stage, name)
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with open(target_path, 'ab') as tf, z.open(name) as sf:
                            tf.write(sf.read())
                            tf.write(b'\n')
        except Exception:
            pass

    if os.path.exists(os.path.join(services_stage, 'META-INF')):
        with zipfile.ZipFile(unsigned_apk, 'a', zipfile.ZIP_DEFLATED) as z_apk:
            for root, dirs, files in os.walk(services_stage):
                for f in files:
                    fp = os.path.join(root, f)
                    arcname = os.path.relpath(fp, services_stage)
                    z_apk.write(fp, arcname)
        print("Merged META-INF/services into APK")

    with zipfile.ZipFile(unsigned_apk, 'a', zipfile.ZIP_DEFLATED) as z_apk:
        for dex_f in glob.glob(os.path.join(dex_dir, 'classes*.dex')):
            z_apk.write(dex_f, os.path.basename(dex_f))

    step("gate: APK dex audit (referenced classes must be packaged)")
    subprocess.run(
        [sys.executable, os.path.join(dst_src, 'audit_apk.py'), unsigned_apk],
        check=True)

    aligned_apk = os.path.join(W, 'kyron-aligned.apk')
    subprocess.run([ZIPALIGN, '-f', '-p', '4', unsigned_apk, aligned_apk], check=True)
    print("Zipaligned APK")

    step("8/8 sign")
    keystore = os.path.join(KB, 'debug.keystore')
    if not os.path.exists(keystore):
        keytool = JAVA.replace('java.exe', 'keytool.exe')
        subprocess.run([
            keytool, '-genkeypair', '-keystore', keystore,
            '-storepass', 'android', '-keypass', 'android',
            '-alias', 'androiddebugkey', '-keyalg', 'RSA',
            '-keysize', '2048', '-validity', '10950',
            '-dname', 'CN=Android Debug,O=Android,C=US'
        ], check=True)

    final_apk = os.path.join(M, f'Kyron-{version_name}.apk')
    sign_cmd = [
        JAVA, '-jar', APKSIGNER, 'sign',
        '--ks', keystore,
        '--ks-pass', 'pass:android',
        '--key-pass', 'pass:android',
        '--out', final_apk,
        aligned_apk
    ]
    subprocess.run(sign_cmd, check=True)

    verify_cmd = [JAVA, '-jar', APKSIGNER, 'verify', '--print-certs', final_apk]
    subprocess.run(verify_cmd, check=True)
    print(f"\nBUILD SUCCESS: {final_apk} ({os.path.getsize(final_apk)} bytes)")

if __name__ == '__main__':
    main()
