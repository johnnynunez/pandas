"""Exact pandas 2.2.3 native diagnostic build; reuse retained fastparquet."""
import ast, hashlib, json, os, pathlib, platform, shutil, subprocess, sys, sysconfig, traceback
ROOT=pathlib.Path.cwd(); OUT=ROOT/'evidence'; OUT.mkdir(exist_ok=True)
SOURCE=ROOT/'source'; FP=ROOT/'fastparquet-source'; PY=sys.executable; STATUS={}

def run(args,name,cwd=None,check=True):
    args=list(map(str,args)); print(name,args,flush=True)
    with (OUT/(name+'.log')).open('w',encoding='utf8') as f:
        r=subprocess.run(args,cwd=cwd,stdout=f,stderr=subprocess.STDOUT)
    STATUS[name]=r.returncode
    print((OUT/(name+'.log')).read_text(encoding='utf8',errors='replace')[-4500:],flush=True)
    if check and r.returncode: raise RuntimeError(name)
    return r.returncode

def main():
    assert sysconfig.get_platform()=='win-arm64' and sys.version_info[:2]==(3,12)
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()
    assert actual=='0691c5cf90477d3503834d983f69350f250a6ff7'
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=FP,text=True).strip()=='95416ad4214a21805c8256e5308272bec60cc177'
    run(['git','fetch','--depth=1','origin','tag','v2.2.3'],'source-tag',SOURCE)
    (OUT/'provenance.json').write_text(json.dumps({'pandas_source':actual,'fastparquet_source':'95416ad4214a21805c8256e5308272bec60cc177','wrapper_sha':os.environ['GITHUB_SHA'],'python':sys.version,'platform':platform.platform(),'sysconfig':sysconfig.get_platform(),'profile':'DIAGNOSTIC NumPy 2.3.0 + pandas 2.2.3; original NumPy 1.26.4 gate OPEN','source_modified':False},indent=2))
    vswhere=pathlib.Path(os.environ['ProgramFiles(x86)'])/'Microsoft Visual Studio/Installer/vswhere.exe'
    installation=subprocess.check_output([vswhere,'-latest','-products','*','-property','installationPath'],text=True).strip()
    vcvars=pathlib.Path(installation)/'VC/Auxiliary/Build/vcvarsall.bat'
    env=subprocess.check_output(f'cmd.exe /s /c ""{vcvars}" arm64 && set"',text=True)
    for line in env.splitlines():
        if '=' in line and not line.startswith('='):
            key,value=line.split('=',1); os.environ[key]=value
    assert os.environ['VSCMD_ARG_TGT_ARCH']=='arm64'
    (OUT/'toolchain.json').write_text(json.dumps({'installation':installation,'cl':shutil.which('cl'),'target':'arm64','WindowsSDKVersion':os.environ.get('WindowsSDKVersion'),'VCToolsVersion':os.environ.get('VCToolsVersion')},indent=2))
    tools=['numpy==2.3.0','Cython==3.0.12','meson==1.2.1','meson-python==0.13.1','versioneer[toml]==0.29','wheel','ninja','pefile','delvewheel','setuptools==80.9.0']
    run([PY,'-m','pip','install','--only-binary=:all:',*tools],'build-tools')
    wheels=OUT/'wheels'; wheels.mkdir(exist_ok=True)
    try:
        run([PY,'-m','pip','wheel','--no-deps','--no-build-isolation','-v','.', '-w', OUT/'raw-wheels','-Cbuild-dir='+str(ROOT/'pandas-build')],'build-pandas',SOURCE)
    finally:
        build=ROOT/'pandas-build'
        for rel in ['compile_commands.json','meson-logs/meson-log.txt','meson-info/intro-buildoptions.json']:
            p=build/rel
            if p.is_file(): shutil.copy(p,OUT/p.name)
    raw=next((OUT/'raw-wheels').glob('*.whl'))
    run([PY,'-m','delvewheel','repair','-w',wheels,raw],'repair-pandas')
    wheel=next(wheels.glob('*.whl'))
    # Reuse the already exercised wheel byte-for-byte; never rebuild fastparquet.
    fpwheel=next((ROOT/'retained').rglob('wheels/fastparquet-2024.11.0-cp312-cp312-win_arm64.whl'))
    assert hashlib.sha256(fpwheel.read_bytes()).hexdigest()=='94a4367dd8ed62395dabae2e62e6e2c2a652866000e6a0c36dc97cdada209b43'
    shutil.copy(fpwheel,wheels/fpwheel.name)
    (OUT/'fastparquet-reuse.json').write_text(json.dumps({'run':38186905680,'artifact_id':11720096917,'artifact_digest':'sha256:89ffc2ef89d3cba47fad07fa0896e47c02bdd93ed4ddb783bdc417608a05bee6','wheel_sha256':hashlib.sha256(fpwheel.read_bytes()).hexdigest(),'original_pandas3_failure_preserved':True},indent=2))
    import wheel_audit
    wheel_audit.audit(wheel,'2.2.3',OUT,'pandas')
    wheel_audit.audit(fpwheel,'2024.11.0',OUT,'fastparquet')
    run([PY,'-m','venv',ROOT/'test-env'],'venv')
    testpy=ROOT/'test-env/Scripts/python.exe'
    deps=['numpy==2.3.0','pytest==8.4.2','pytest-timeout','pytest-xdist','hypothesis','cramjam==2.13.0','fsspec','packaging','duckdb==1.5.6','pytz==2024.1','python-dateutil','tzdata','pytest-localserver','requests','psutil']
    run([testpy,'-m','pip','install','--only-binary=:all:',*deps,wheel,fpwheel],'test-install')
    run([testpy,'-m','pip','freeze','--all'],'test-freeze')
    run([testpy,'-m','pip','check'],'pip-check',check=False)
    clean=ROOT/'clean-test';clean.mkdir(exist_ok=True)
    run([testpy,'-I',ROOT/'wrapper/audit_oracles.py','fastparquet',OUT],'oracles',clean,False)
    run([testpy,'-I',ROOT/'wrapper/runtime_extra.py',OUT,'pandas'],'loaded-crt',clean,False)
    shutil.copytree(FP/'fastparquet/test',clean/'test',dirs_exist_ok=True)
    shutil.copytree(FP/'test-data',clean/'test-data',dirs_exist_ok=True)
    run([testpy,'-m','pytest','-c',FP/'pyproject.toml','test','-q','-ra','--timeout=60','--junitxml='+str(OUT/'fastparquet-full.xml')],'fastparquet-full',clean,False)
    run([testpy,'-m','pytest','-c',SOURCE/'pyproject.toml','--pyargs','pandas.tests.io.test_parquet','-q','-ra','--timeout=60','--junitxml='+str(OUT/'pandas-parquet.xml')],'pandas-parquet',clean,False)

try: main()
except Exception:
    traceback.print_exc(); STATUS['harness-exception']=1
finally:
    (OUT/'status.json').write_text(json.dumps(STATUS,indent=2)); print(STATUS)
sys.exit(int(any(STATUS.values())))
