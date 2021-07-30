import asyncio
import contextlib
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import fsspec.asyn
import fsspec.utils
import logging


fsspec.utils.setup_logging(logger_name="fsspec.http")
logging.basicConfig(level=logging.DEBUG)

requests = pytest.importorskip("requests")
port = 9898
data = b"\n".join([b"some test data"] * 1000)
realfile = "http://localhost:%i/index/realfile" % port
index = b'<a href="%s">Link</a>' % realfile.encode()
listing = open(
    os.path.join(os.path.dirname(__file__), "data", "listing.html"), "rb"
).read()
win = os.name == "nt"


class HTTPTestHandler(BaseHTTPRequestHandler):
    def _respond(self, code=200, headers=None, data=b""):
        headers = headers or {}
        headers.update({"User-Agent": "test"})
        self.send_response(code)
        for k, v in headers.items():
            self.send_header(k, str(v))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/") not in [
            "/index/realfile",
            "/index/otherfile",
            "/index",
            "/data/20020401",
        ]:
            self._respond(404)
            return

        d = data if self.path in ["/index/realfile", "/index/otherfile"] else index
        if self.path == "/data/20020401":
            d = listing
        if "Range" in self.headers:
            ran = self.headers["Range"]
            b, ran = ran.split("=")
            start, end = ran.split("-")
            if start:
                d = d[int(start) : (int(end) + 1) if end else None]
            else:
                # suffix only
                d = d[-int(end) :]
        if "give_length" in self.headers:
            response_headers = {"Content-Length": len(d)}
            self._respond(200, response_headers, d)
        elif "give_range" in self.headers:
            self._respond(200, {"Content-Range": "0-%i/%i" % (len(d) - 1, len(d))}, d)
        else:
            self._respond(200, data=d)

    def do_HEAD(self):
        d = data if self.path == "/index/realfile" else index
        if "head_not_auth" in self.headers:
            self._respond(
                403, {"Content-Length": 123}, b"not authorized for HEAD request"
            )
            return
        if "head_ok" not in self.headers:
            self._respond(405)
            return
        if self.path.rstrip("/") not in ["/index/realfile", "/index"]:
            self._respond(404)
        elif "give_length" in self.headers:
            response_headers = {"Content-Length": len(d)}
            if "zero_length" in self.headers:
                response_headers["Content-Length"] = 0

            self._respond(200, response_headers)
        elif "give_range" in self.headers:
            self._respond(200, {"Content-Range": "0-%i/%i" % (len(d) - 1, len(d))})
        else:
            self._respond(200)  # OK response, but no useful info


@contextlib.contextmanager
def serve():
    server_address = ("", port)
    httpd = HTTPServer(server_address, HTTPTestHandler)
    th = threading.Thread(target=httpd.serve_forever)
    th.daemon = True
    th.start()
    try:
        yield "http://localhost:%i" % port
    finally:
        httpd.socket.close()
        httpd.shutdown()
        th.join()


@pytest.fixture(scope="module")
def server():
    with serve() as s:
        yield s


def test_list(server):
    h = fsspec.filesystem("http")
    out = h.glob(server + "/index/*")
    assert out == [server + "/index/realfile"]


def test_list_invalid_args(server):
    with pytest.raises(TypeError):
        h = fsspec.filesystem("http", use_foobar=True)
        h.glob(server + "/index/*")


def test_list_cache(server):
    h = fsspec.filesystem("http", use_listings_cache=True)
    out = h.glob(server + "/index/*")
    assert out == [server + "/index/realfile"]


def test_list_cache_with_expiry_time_cached(server):
    h = fsspec.filesystem("http", use_listings_cache=True, listings_expiry_time=30)

    # First, the directory cache is not initialized.
    assert not h.dircache

    # By querying the filesystem with "use_listings_cache=True",
    # the cache will automatically get populated.
    out = h.glob(server + "/index/*")
    assert out == [server + "/index/realfile"]

    # Verify cache content.
    assert len(h.dircache) == 1

    out = h.glob(server + "/index/*")
    assert out == [server + "/index/realfile"]


def test_list_cache_with_expiry_time_purged(server):
    h = fsspec.filesystem("http", use_listings_cache=True, listings_expiry_time=0.3)

    # First, the directory cache is not initialized.
    assert not h.dircache

    # By querying the filesystem with "use_listings_cache=True",
    # the cache will automatically get populated.
    out = h.glob(server + "/index/*")
    assert out == [server + "/index/realfile"]
    assert len(h.dircache) == 1

    # Verify cache content.
    assert server + "/index/" in h.dircache
    assert len(h.dircache.get(server + "/index/")) == 1

    # Wait beyond the TTL / cache expiry time.
    time.sleep(0.31)

    # Verify that the cache item should have been purged.
    cached_items = h.dircache.get(server + "/index/")
    assert cached_items is None

    # Verify that after clearing the item from the cache,
    # it can get populated again.
    out = h.glob(server + "/index/*")
    assert out == [server + "/index/realfile"]
    cached_items = h.dircache.get(server + "/index/")
    assert len(cached_items) == 1


def test_list_cache_reuse(server):
    h = fsspec.filesystem("http", use_listings_cache=True, listings_expiry_time=5)

    # First, the directory cache is not initialized.
    assert not h.dircache

    # By querying the filesystem with "use_listings_cache=True",
    # the cache will automatically get populated.
    out = h.glob(server + "/index/*")
    assert out == [server + "/index/realfile"]

    # Verify cache content.
    assert len(h.dircache) == 1

    # Verify another instance without caching enabled does not have cache content.
    h = fsspec.filesystem("http", use_listings_cache=False)
    assert not h.dircache

    # Verify that yet another new instance, with caching enabled,
    # will see the same cache content again.
    h = fsspec.filesystem("http", use_listings_cache=True, listings_expiry_time=5)
    assert len(h.dircache) == 1

    # However, yet another instance with a different expiry time will also not have
    # any valid cache content.
    h = fsspec.filesystem("http", use_listings_cache=True, listings_expiry_time=666)
    assert len(h.dircache) == 0


def test_ls_raises_filenotfound(server):
    h = fsspec.filesystem("http")

    with pytest.raises(FileNotFoundError):
        h.ls(server + "/not-a-key")


def test_list_cache_with_max_paths(server):
    h = fsspec.filesystem("http", use_listings_cache=True, max_paths=5)
    out = h.glob(server + "/index/*")
    assert out == [server + "/index/realfile"]


def test_list_cache_with_skip_instance_cache(server):
    h = fsspec.filesystem("http", use_listings_cache=True, skip_instance_cache=True)
    out = h.glob(server + "/index/*")
    assert out == [server + "/index/realfile"]


def test_isdir(server):
    h = fsspec.filesystem("http")
    assert h.isdir(server + "/index/")
    assert not h.isdir(server + "/index/realfile")


def test_policy_arg(server):
    h = fsspec.filesystem("http", size_policy="get")
    out = h.glob(server + "/index/*")
    assert out == [server + "/index/realfile"]


def test_exists(server):
    h = fsspec.filesystem("http")
    assert not h.exists(server + "/notafile")
    with pytest.raises(FileNotFoundError):
        h.cat(server + "/notafile")


def test_read(server):
    h = fsspec.filesystem("http")
    out = server + "/index/realfile"
    with h.open(out, "rb") as f:
        assert f.read() == data
    with h.open(out, "rb", block_size=0) as f:
        assert f.read() == data
    with h.open(out, "rb") as f:
        assert f.read(100) + f.read() == data


def test_file_pickle(server):
    import pickle

    # via HTTPFile
    h = fsspec.filesystem("http", headers={"give_length": "true", "head_ok": "true"})
    out = server + "/index/realfile"
    with h.open(out, "rb") as f:
        pic = pickle.dumps(f)
        assert f.read() == data
    with pickle.loads(pic) as f:
        assert f.read() == data

    # via HTTPStreamFile
    h = fsspec.filesystem("http")
    out = server + "/index/realfile"
    with h.open(out, "rb") as f:
        out = pickle.dumps(f)
        assert f.read() == data
    with pickle.loads(out) as f:
        assert f.read() == data


def test_methods(server):
    h = fsspec.filesystem("http")
    url = server + "/index/realfile"
    assert h.exists(url)
    assert h.cat(url) == data


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"give_length": "true"},
        {"give_length": "true", "head_ok": "true"},
        {"give_range": "true"},
        {"give_length": "true", "head_not_auth": "true"},
        {"give_range": "true", "head_not_auth": "true"},
    ],
)
def test_random_access(server, headers):
    h = fsspec.filesystem("http", headers=headers)
    url = server + "/index/realfile"
    with h.open(url, "rb") as f:
        if headers:
            assert f.size == len(data)
        assert f.read(5) == data[:5]

        if headers:
            f.seek(5, 1)
            assert f.read(5) == data[10:15]
        else:
            with pytest.raises(ValueError):
                f.seek(5, 1)


def test_mapper_url(server):
    h = fsspec.filesystem("http")
    mapper = h.get_mapper(server + "/index/")
    assert mapper.root.startswith("http:")
    assert list(mapper)

    mapper2 = fsspec.get_mapper(server + "/index/")
    assert mapper2.root.startswith("http:")
    assert list(mapper) == list(mapper2)


def test_content_length_zero(server):
    h = fsspec.filesystem(
        "http", headers={"give_length": "true", "zero_length": "true"}
    )
    url = server + "/index/realfile"

    with h.open(url, "rb") as f:
        assert f.read() == data


def test_download(server, tmpdir):
    h = fsspec.filesystem("http", headers={"give_length": "true", "head_ok": "true "})
    url = server + "/index/realfile"
    fn = os.path.join(tmpdir, "afile")
    h.get(url, fn)
    assert open(fn, "rb").read() == data


def test_multi_download(server, tmpdir):
    h = fsspec.filesystem("http", headers={"give_length": "true", "head_ok": "true "})
    urla = server + "/index/realfile"
    urlb = server + "/index/otherfile"
    fna = os.path.join(tmpdir, "afile")
    fnb = os.path.join(tmpdir, "bfile")
    h.get([urla, urlb], [fna, fnb])
    assert open(fna, "rb").read() == data
    assert open(fnb, "rb").read() == data


def test_ls(server):
    h = fsspec.filesystem("http")
    l = h.ls(server + "/data/20020401/", detail=False)
    nc = server + "/data/20020401/GRACEDADM_CLSM0125US_7D.A20020401.030.nc4"
    assert nc in l
    assert len(l) == 11
    assert all(u["type"] == "file" for u in h.ls(server + "/data/20020401/"))
    assert h.glob(server + "/data/20020401/*.nc4") == [nc]


def test_mcat(server):
    h = fsspec.filesystem("http", headers={"give_length": "true", "head_ok": "true "})
    urla = server + "/index/realfile"
    urlb = server + "/index/otherfile"
    out = h.cat([urla, urlb])
    assert out == {urla: data, urlb: data}


def test_cat_file_range(server):
    h = fsspec.filesystem("http", headers={"give_length": "true", "head_ok": "true "})
    urla = server + "/index/realfile"
    assert h.cat(urla, start=1, end=10) == data[1:10]
    assert h.cat(urla, start=1) == data[1:]

    assert h.cat(urla, start=-10) == data[-10:]
    assert h.cat(urla, start=-10, end=-2) == data[-10:-2]

    assert h.cat(urla, end=-10) == data[:-10]


def test_mcat_cache(server):
    urla = server + "/index/realfile"
    urlb = server + "/index/otherfile"
    fs = fsspec.filesystem("simplecache", target_protocol="http")
    assert fs.cat([urla, urlb]) == {urla: data, urlb: data}


def test_mcat_expand(server):
    h = fsspec.filesystem("http", headers={"give_length": "true", "head_ok": "true "})
    out = h.cat(server + "/index/*")
    assert out == {server + "/index/realfile": data}


@pytest.mark.xfail(
    condition=sys.flags.optimize > 1, reason="no docstrings when optimised"
)
def test_docstring():
    h = fsspec.filesystem("http")
    # most methods have empty docstrings and draw from base class, but this one
    # is generated
    assert h.pipe.__doc__


def test_async_other_thread(server):
    import threading

    loop = asyncio.get_event_loop()
    th = threading.Thread(target=loop.run_forever)

    th.daemon = True
    th.start()
    fs = fsspec.filesystem("http", asynchronous=True, loop=loop)
    asyncio.run_coroutine_threadsafe(fs.set_session(), loop=loop).result()
    url = server + "/index/realfile"
    cor = fs._cat([url])
    fut = asyncio.run_coroutine_threadsafe(cor, loop=loop)
    assert fut.result() == {url: data}
    loop.call_soon_threadsafe(loop.stop)


@pytest.mark.skipif(sys.version_info < (3, 7), reason="no asyncio.run in py36")
def test_async_this_thread(server):
    async def _():
        fs = fsspec.filesystem("http", asynchronous=True)

        session = await fs.set_session()  # creates client

        url = server + "/index/realfile"
        with pytest.raises((NotImplementedError, RuntimeError)):
            fs.cat([url])
        out = await fs._cat([url])
        del fs
        assert out == {url: data}
        await session.close()

    asyncio.run(_())


def _inner_pass(fs, q, fn):
    # pass the FS instance, but don't use it; in new process, the instance
    # cache should be skipped to make a new instance
    import traceback

    try:
        fs = fsspec.filesystem("http")
        q.put(fs.cat(fn))
    except Exception:
        q.put(traceback.format_exc())


@pytest.mark.parametrize("method", ["spawn", "forkserver"])
def test_processes(server, method):
    import multiprocessing as mp

    if win and method != "spawn":
        pytest.skip("Windows can only spawn")
    ctx = mp.get_context(method)
    fn = server + "/index/realfile"
    fs = fsspec.filesystem("http")

    q = ctx.Queue()
    p = ctx.Process(target=_inner_pass, args=(fs, q, fn))
    p.start()
    out = q.get()
    assert out == fs.cat(fn)
    p.join()
