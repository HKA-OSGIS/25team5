# -*- coding: utf-8 -*-
"""
Created on Thu Dec 18 18:04:09 2025

@author: Matthieu
"""

# build_final.py
import PyInstaller.__main__
import os
import shutil
import sys

# Nettoyer les anciennes builds
for folder in ['build', 'dist', '__pycache__']:
    if os.path.exists(folder):
        shutil.rmtree(folder, ignore_errors=True)

# Arguments optimisés pour PyInstaller
args = [
    'main.py',
    '--name=OSMStreetAnalyzer',
    '--windowed',
    '--onefile',
    '--clean',
    '--noconfirm',
    
    # Nettoyer les imports
    '--hidden-import=customtkinter',
    '--hidden-import=geopandas',
    '--hidden-import=shapely.geometry',
    '--hidden-import=pandas',
    '--hidden-import=numpy',
    '--hidden-import=matplotlib',
    '--hidden-import=requests',
    '--hidden-import=overpy',
    '--hidden-import=queue',
    '--hidden-import=threading',
    '--hidden-import=json',
    '--hidden-import=datetime',
    
    # Collecter les packages nécessaires
    '--collect-all=geopandas',
    '--collect-all=shapely',
    '--collect-all=customtkinter',
    
    # Exclure les packages problématiques
    '--exclude-module=tkinter',
    '--exclude-module=osmnx',
    '--exclude-module=test',
    '--exclude-module=unittest',
    
    # Optimisations
    '--optimize=2',
]

print("Construction de l'exécutable...")
print("Cette opération peut prendre quelques minutes...")

try:
    PyInstaller.__main__.run(args)
    print("\n✅ Construction terminée avec succès!")
    print("📁 L'exécutable se trouve dans: dist/OSMStreetAnalyzer.exe")
    
except Exception as e:
    print(f"\n❌ Erreur lors de la construction: {e}")
    sys.exit(1)