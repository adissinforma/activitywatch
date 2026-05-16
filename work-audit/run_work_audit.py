#!/usr/bin/env python3
"""Punto de entrada de nivel superior de work-audit.

Sirve para dos cosas:

- Arrancar la app sin usar ``-m``:  ``python run_work_audit.py``.
- Empaquetar con PyInstaller, que necesita un script de nivel superior
  (no un módulo con imports relativos) como punto de partida.

Solo delega en ``work_audit.__main__.main``.
"""

from work_audit.__main__ import main

if __name__ == "__main__":
    main()
