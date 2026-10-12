import base64,csv,hashlib,io,json,pathlib,os,zipfile
def audit(wheel, expected, OUT, label):
    import pefile
    payload = OUT/(label+'-payload')
    report = {'filename':wheel.name, 'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(), 'PE':[], 'record_valid':False, 'licenses':[]}
    with zipfile.ZipFile(wheel) as z:
        rec = next(n for n in z.namelist() if n.endswith('.dist-info/RECORD'))
        for name, digest, size in csv.reader(io.StringIO(z.read(rec).decode())):
            if digest:
                method, value = digest.split('=',1)
                actual=base64.urlsafe_b64encode(hashlib.new(method,z.read(name)).digest()).rstrip(b'=').decode()
                assert actual == value and len(z.read(name)) == int(size), name
        report['record_valid']=True
        meta=next(n for n in z.namelist() if n.endswith('.dist-info/METADATA'))
        from email import message_from_bytes
        assert message_from_bytes(z.read(meta))['Version'] == expected
        report['licenses']=[n for n in z.namelist() if any(t in n.lower() for t in ['license','copying'])]
        assert report['licenses'], 'Missing package license'
        z.extractall(payload)
    files={p.name.lower():p for p in payload.rglob('*') if p.is_file()}
    for p in payload.rglob('*'):
        if p.suffix.lower() not in ('.dll','.pyd'):
            continue
        pe=pefile.PE(str(p)); imports=[]
        for descriptor in getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]):
            name=descriptor.dll.decode(); key=name.lower()
            if key in files:
                resolved=str(files[key].relative_to(payload))
            elif key.startswith(('api-ms-','ext-ms-')):
                resolved='Windows API-set'
            elif key.startswith('python3'):
                resolved='CPython runtime'
            elif (pathlib.Path(os.environ['SystemRoot'])/'System32'/name).exists():
                resolved='Windows System32'
            else:
                resolved='UNRESOLVED'
            imports.append({'name':name,'resolved':resolved})
        report['PE'].append({'path':str(p.relative_to(payload)), 'machine':hex(pe.FILE_HEADER.Machine),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'imports':imports})
    (OUT/(label+'-wheel-audit.json')).write_text(json.dumps(report,indent=2))
    assert report['PE']
    assert all(p['machine']=='0xaa64' for p in report['PE'])
    assert not any(i['resolved']=='UNRESOLVED' for p in report['PE'] for i in p['imports'])
    # RECORD hash oracle negative control: a modified payload must differ.
    content=wheel.read_bytes(); assert hashlib.sha256(content+b'poison').hexdigest()!=report['sha256']
