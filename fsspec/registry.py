import importlib
__all__ = ['registry', 'get_filesystem_class', 'default']

# mapping protocol: implementation class
registry = {}
default = 'file'
gcs = {'class': 'gcsfs.GCSFileSystem', 'err': 'Please install gcsfs'}

known_implementations = {
    'file': {'class': 'fsspec.implementations.local.LocalFileSystem'},
    'memory': {'class': 'fsspec.implementations.memory.MemoryFileSystem'},
    'http': {'class': 'fsspec.implementations.http.HTTPFileSystem',
             'err': 'HTTPFileSystem requires "requests" to be installed'},
    'https': {'class': 'fsspec.implementations.http.HTTPFileSystem',
              'err': 'HTTPFileSystem requires "requests" to be installed'},
    'zip': {'class': 'fsspec.implementations.zip.ZipFileSystem'},
    'gcs': gcs, 'gs': gcs,
    'sftp': {'class': 'fsspec.implementations.sftp.SFTPFileSystem',
             'err': 'SFTPFileSystem requires "paramiko" to be installed'}
}


def get_filesystem_class(protocol):
    if protocol is None:
        protocol = default
    if protocol not in registry:
        if protocol not in known_implementations:
            raise ValueError("Protocol not known: %s" % protocol)
        bit = known_implementations[protocol]
        mod, name = bit['class'].rsplit('.', 1)
        err = None
        try:
            mod = importlib.import_module(mod)
        except ImportError:
            err = ImportError(bit['err'])
        except Exception as e:
            err = e
        if err is not None:
            raise RuntimeError(str(err))
        registry[protocol] = getattr(mod, name)
    cls = registry[protocol]
    if cls.protocol == 'abstract' or cls.protocol is None:
        cls.protocol = protocol

    return cls
