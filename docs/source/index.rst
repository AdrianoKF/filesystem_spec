fsspec's: python filesystem interfaces
======================================

Filesystem Spec is a project to unify various projects and classes to work with remote filesystems and
file-system-like abstractions using a standard pythonic interface.


.. _highlight:

Highlights
----------

- based on s3fs and gcsfs
- ``fsspec`` instances are serializable and can be passed between processes/machines
- the ``OpenFiles`` file-like instances are also serializable
- implementations provide random access, to enable only the part of a file required to be read; plus a template
  to base other file-like classes on
- file access can use transparent compression and text-mode
- any file-system directory can be viewed as a key-value/mapping store
- if installed, all file-system classes also subclass from ``pyarrow.filesystem.FileSystem``, so
  can work with any arrow function expecting such an instance
- writes can be transactional: stored in a temporary location and only moved to the final
  destination when the transaction is committed
- FUSE: mount any path from any backend to a point on your file-system
- cached instances tokenised on the instance parameters

These are described further in the :doc:`features` section.

Installation
------------

   pip install fsspec

or

   conda install -c conda-forge fsspec

Implementations
---------------

This repo contains several file-system implementations, see :ref:`implementations`. However,
the external projects ``s3fs`` and ``gcsfs`` are also developing compatibility with ``fsspec`` and
will eventually depend upon it.


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   intro.rst
   usage.rst
   features.rst
   api.rst


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
