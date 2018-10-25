from __future__ import print_function, division, absolute_import

import os
from bz2 import BZ2File
from gzip import GzipFile
# zip-files are read-only and contain multiple files
# from zipfile import ZipFile


def noop_file(file, **kwargs):
    return file


# should be functions of the form func(infile, mode=, **kwargs) -> file-like
compr = {'gzip': lambda f, **kwargs: GzipFile(fileobj=f, **kwargs),
         None: lambda f, **kwargs: noop_file(f),
         'bz2': lambda f, **kwargs: BZ2File(f, **kwargs)}

try:
    import lzma
    compr['xz'] = lzma.LZMAFile
except ImportError:
    pass

try:
    import lzmaffi
    compr['xz'] = lzmaffi.LZMAFile
except ImportError:
    pass
