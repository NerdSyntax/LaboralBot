import sys
import os

# Set up path to import from the project
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from constantes import CT_CIUDADES

print("Testing ChileTrabajos city mappings...")
print("Santiago:", CT_CIUDADES.get("Santiago"))
print("Concepción:", CT_CIUDADES.get("Concepción"))
print("Región Metropolitana:", CT_CIUDADES.get("Región Metropolitana"))

print("Done.")
