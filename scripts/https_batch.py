"""Fetch release evidence with shared curl connections, retaining TLS verification."""
import atexit, json, pathlib, subprocess, tempfile

class HttpsBatch:
    def __init__(self, work, env):
        self.directory = tempfile.TemporaryDirectory(prefix='https-release-', dir=work)
        atexit.register(self.directory.cleanup)
        self.root = pathlib.Path(self.directory.name)
        self.env = env
        self.responses = {}

    def fetch(self, urls):
        urls = list(dict.fromkeys(urls))
        protocol = self.env.get('RELEASE_HTTP_VERSION', 'http1.1')
        if protocol not in ['http1.1', 'http2']: raise ValueError('Unsupported release HTTP version')
        concurrency = self.env.get('RELEASE_CONCURRENCY', '4')
        config = self.root / 'requests.conf'
        blocks = []
        files = {}
        for i, url in enumerate(urls):
            if not url.startswith('https://'): raise ValueError('Release checks require HTTPS')
            target = self.root / str(i)
            files[url] = target
            options = {'url':url, 'output':str(target), 'write-out':'%{json}\n',
                       'max-time':'3600' if url.split('?')[0].endswith('.pdf') else '300',
                       'connect-timeout':'30', 'retry':'3', 'retry-delay':'2'}
            blocks.append('\n'.join(k+' = '+json.dumps(v) for k,v in options.items())+'\ncompressed\n'+protocol+'\nfail\nretry-all-errors\nsilent\nshow-error')
        config.write_text('\nnext\n'.join(blocks)+'\n')
        errors = (self.root/'errors.log').open('w+')
        process = subprocess.Popen(['curl','--parallel','--parallel-max',concurrency,'--config',str(config)],
                                   stdout=subprocess.PIPE, stderr=errors, text=True, env=self.env)
        for line in process.stdout:
            try: result = json.loads(line)
            except json.JSONDecodeError: continue
            url = result.get('url_effective')
            target = files.get(url)
            if result.get('exitcode') == 0 and result.get('http_code') == 200 and target and target.is_file():
                self.responses[url] = (target, result.get('content_type','').split(';')[0].strip())
                if len(self.responses) % 25 == 0: print(f'HTTPS downloaded: {len(self.responses)}/{len(urls)} resources', flush=True)
        code = process.wait()
        errors.seek(0)
        stderr = errors.read()
        errors.close()
        missing = [u for u in urls if u not in self.responses]
        if code or missing or len(self.responses) != len(urls):
            raise RuntimeError(f'HTTPS batch incomplete: {len(self.responses)}/{len(urls)}; {len(missing)} missing; '+stderr[-700:])

    def get(self, url):
        path, mime = self.responses[url]
        return path.read_bytes(), mime
