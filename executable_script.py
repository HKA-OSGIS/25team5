# build_exe.py
import PyInstaller.__main__
import os


# Créer le dossier de distribution si nécessaire
if not os.path.exists('dist'):
    os.makedirs('dist')

# Arguments pour PyInstaller
args = [
    'main.py',
    '--name=OSMStreetAnalyzerCloud',
    '--windowed',
    '--onefile',
    '--icon=assets/icon.ico' if os.path.exists('assets/icon.ico') else '',
    '--add-data=config.py:.',
    '--hidden-import=customtkinter',
    '--hidden-import=geopandas',
    '--hidden-import=shapely',
    '--hidden-import=overpy',
    '--hidden-import=osmnx',
    '--collect-all=geopandas',
    '--collect-all=shapely',
    '--noconfirm',
    '--clean'
]

# Filtrer les arguments vides
args = [arg for arg in args if arg]

PyInstaller.__main__.run(args)