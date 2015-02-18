.. parltrack documentation master file, created by
   sphinx-quickstart on Fri Apr 22 23:05:26 2011.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to parltrack's documentation!
=====================================

Contents:

.. toctree::
   :maxdepth: 2

notification api:
i just checked, and i think you attempt is very ambitious, but will fail. the
correct syntax can be gleaned from:
    /notification/<string:g_id>/add/<any(dossiers, emails):item>/<path:value>
which is not very intuitive, an example:
    /notifications/JURI/add/dossiers/2014/2228(INI)
what happens if you replace dossiers with emails and what the correct
parameter to that is, is an easy exercise for the comprehending reader :)
also you might like this one:
   /notification/<string:g_id>/del/<any(dossiers, emails):item>/<path:value>

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

