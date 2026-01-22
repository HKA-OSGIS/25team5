#!/usr/bin/env python
# coding: utf-8

# In[22]:


import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine
import re

# --- CONFIGURATION ---
#DB_URL = "postgresql://amirzarezadeh@localhost:5432/opengisproject" # Change user/pass
DB_URL ="postgresql://amirzarezadeh@localhost:5432/gis_project_db"
engine = create_engine(
    DB_URL,
    connect_args={"options": "-c client_encoding=utf8"}
)

#INPUT_ROADS = r"Travail/Karlsruhe/OpenGIS/data/gis_osm_roads_free_1.shp"
#INPUT_REGIONS = r"Travail/Karlsruhe/OpenGIS/data/regions_20140306_5m.shp"

# --- FONCTIONS DE NETTOYAGE ---

def clean_street_name(name, lang='fr'):
    """
    Extrait le nom principal de la rue en retirant le type (Rue, Strasse, etc.)
    """
    if not isinstance(name, str):
        return None, None
    
    name_upper = name.upper().strip()
    street_type = "UNKNOWN"
    clean_name = name_upper

    if lang == 'fr':
        # Regex pour capturer le type au début (ex: RUE DE LA PAIX -> PAIX)
        # On cherche : Début + Type + (de/du/des/l') optionnel
        pattern = r"^(RUE|AVENUE|BOULEVARD|BD|IMPASSE|ALLÉE|ALLEE|PLACE|CHEMIN|ROUTE)\s+(D'|DE\s+LA\s+|DU\s+|DES\s+|DE\s+)?"
        match = re.search(pattern, name_upper)
        if match:
            street_type = match.group(1)
            clean_name = re.sub(pattern, "", name_upper).strip()
            
    elif lang == 'de':
        # Regex pour capturer le type à la fin (ex: HAUPTSTRASSE -> HAUPT)
        # On cherche un suffixe collé
        pattern = r"(.*?)(STRASSE|STR\.|WEG|PLATZ|ALLEE|GASSE)$"
        match = re.search(pattern, name_upper)
        if match:
            clean_name = match.group(1).strip() # La partie avant le suffixe
            street_type = match.group(2)
            
    return clean_name, street_type

# --- PROCESSUS ETL ---

def run_etl():
    print("1. Chargement des données géographiques...")
    # On charge les routes et les régions
    #gdf_roads = gpd.read_file(INPUT_ROADS)
    #gdf_regions = gpd.read_file(INPUT_REGIONS)
    gdf_roads_alsace = gpd.read_file("gis_osm_roads_free_1.shp")
    gdf_regions_france = gpd.read_file(
        "regions_20140306_5m.shp",
        encoding="ISO-8859-1"
    )

    # S'assurer que tout est en projection WGS84 (lat/lon)
    gdf_roads_alsace = gdf_roads_alsace.to_crs(epsg=4326)
    gdf_regions_france = gdf_regions_france.to_crs(epsg=4326)

    print("2. Jointure Spatiale (Assigner une région à chaque route)...")
    # Cette étape est cruciale : on ajoute la colonne 'region' aux routes selon leur position
    # Assure-toi que ton fichier région a une colonne 'nom_region' ou 'NAME'
    gdf_joined = gpd.sjoin(gdf_roads_alsace, gdf_regions_france[['nom', 'geometry']], how="inner", predicate="intersects")
    gdf_joined = gdf_joined.rename(columns={'nom': 'region_name'})

    print("3. Nettoyage des noms...")
    # Application de la fonction de nettoyage
    # On suppose ici que c'est la France ('fr'), change en 'de' si besoin
    # Assure-toi que la colonne du nom de rue s'appelle 'name' ou 'NOM_VOIE' dans ton shapefile
    results = gdf_joined['name'].apply(lambda x: clean_street_name(x, lang='fr'))
    
    gdf_joined['nom_normalise'] = [res[0] for res in results]
    gdf_joined['type_voie'] = [res[1] for res in results]

    # Filtrer les noms vides ou nuls
    gdf_joined = gdf_joined[gdf_joined['nom_normalise'].notna() & (gdf_joined['nom_normalise'] != "")]

    print("4. Dédoublonnage (Aggregation par Ville)...")
    # Pour éviter d'avoir 50 segments pour "Rue de la Paix" dans la même ville
    # On suppose qu'il y a une colonne 'city' ou code postal. Sinon, il faut faire une jointure avec une couche 'communes'.
    # Ici, on va simplifier en dissolvant par Nom Normalisé + Région (si pas de colonne ville dispo)
    
    # On garde les géométries : Dissolve combine les segments en une seule ligne (MultiLineString)
    gdf_final = gdf_joined.dissolve(by=['region_name', 'nom_normalise', 'type_voie'], as_index=False)

    print("5. Export vers PostGIS...")
    
    for col in gdf_final.select_dtypes(include="object").columns:
        gdf_final[col] = (
            gdf_final[col]
            .astype(str)
            .str.encode("utf-8", errors="ignore")
            .str.decode("utf-8")
        )
    
    # Envoi dans la table 'rues_nettoyees'. 'replace' écrase la table si elle existe.
    gdf_final.to_postgis("rues_nettoyees", engine, if_exists='replace', index=False)
    
    print("ETL terminé avec succès !")

if __name__ == "__main__":
    run_etl()


# In[1]:


import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine
import re
import unicodedata
import os

# --- 1. CONFIGURATION ET SÉCURITÉ ENCODAGE ---
# On force l'encodage au niveau de l'OS pour la session Python
os.environ['PGCLIENTENCODING'] = 'utf-8'

# Utilisation du driver 'psycopg' (v3) au lieu de 'psycopg2'
# La syntaxe de l'URL change : 'postgresql+psycopg://...'
DB_URL = "postgresql+psycopg://amirzarezadeh@127.0.0.1:5432/gis_project_db"

# Création de l'engine avec le nouveau driver
# Psycopg3 gère nativement l'UTF-8 sans arguments supplémentaires
engine = create_engine(DB_URL)

# --- 2. FONCTIONS DE NETTOYAGE ---

def remove_accents(input_str):
    """ Supprime les accents et convertit en ASCII pur pour éviter les erreurs de driver """
    if not isinstance(input_str, str):
        return input_str
    # Normalisation NFKD pour séparer les accents des lettres
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    # On ne garde que les caractères qui ne sont pas des marques d'accentuation
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def clean_street_name(name, lang='fr'):
    """ Nettoie le nom de rue en supprimant les types (Rue, Avenue, etc.) """
    if not isinstance(name, str):
        return None, "UNKNOWN"
    
    # On enlève les accents et on passe en majuscules pour uniformiser
    name_clean = remove_accents(name).upper().strip()
    
    street_type = "UNKNOWN"
    main_name = name_clean

    if lang == 'fr':
        # Regex simplifiée (plus d'accents à gérer)
        pattern = r"^(RUE|AVENUE|BOULEVARD|BD|IMPASSE|ALLEE|PLACE|CHEMIN|ROUTE)\s+(D'|DE\s+LA\s+|DU\s+|DES\s+|DE\s+)?"
        match = re.search(pattern, name_clean)
        if match:
            street_type = match.group(1)
            main_name = re.sub(pattern, "", name_clean).strip()
            
    return main_name, street_type

# --- 3. PROCESSUS ETL ---

def run_etl():
    print("1. Chargement des données géographiques...")
    # Chargement avec encodages explicites
    gdf_roads = gpd.read_file("gis_osm_roads_free_1.shp")
    gdf_regions = gpd.read_file("regions_20140306_5m.shp", encoding="ISO-8859-1")

    # Projection WGS84
    gdf_roads = gdf_roads.to_crs(epsg=4326)
    gdf_regions = gdf_regions.to_crs(epsg=4326)

    print("2. Jointure Spatiale (Assignation des régions)...")
    gdf_joined = gpd.sjoin(gdf_roads, gdf_regions[['nom', 'geometry']], how="inner", predicate="intersects")
    gdf_joined = gdf_joined.rename(columns={'nom': 'region_name'})

    print("3. Nettoyage (Suppression accents + Normalisation)...")
    # 3a. Nettoyer les noms de régions
    gdf_joined['region_name'] = gdf_joined['region_name'].apply(remove_accents)
    
    # 3b. Nettoyer les noms de rues
    # On applique la fonction qui sépare type et nom
    results = gdf_joined['name'].apply(lambda x: clean_street_name(x, lang='fr'))
    gdf_joined['nom_normalise'] = [res[0] for res in results]
    gdf_joined['type_voie'] = [res[1] for res in results]

    # Filtrage des lignes vides
    gdf_joined = gdf_joined[gdf_joined['nom_normalise'].notna() & (gdf_joined['nom_normalise'] != "")]

    print("4. Fusion des segments (Dissolve)...")
    # Regroupe les géométries par région et par nom de rue
    gdf_final = gdf_joined.dissolve(by=['region_name', 'nom_normalise', 'type_voie'], as_index=False)

    print("5. Export vers PostGIS (via Psycopg 3)...")
    # Sécurité ultime : on s'assure que TOUTES les colonnes texte sont en ASCII pur
    for col in gdf_final.select_dtypes(include="object").columns:
        gdf_final[col] = gdf_final[col].apply(remove_accents)

    # Envoi dans la table 'rues_nettoyees'
    try:
        gdf_final.to_postgis("rues_nettoyees", engine, if_exists='replace', index=False)
        print("\n--- ETL terminé avec succès ! ---")
        print(f"Table 'rues_nettoyees' créée avec {len(gdf_final)} lignes.")
    except Exception as e:
        print(f"\nErreur lors de l'export : {e}")

if __name__ == "__main__":
    run_etl()


# In[ ]:




