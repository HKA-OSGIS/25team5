# -*- coding: utf-8 -*-
"""
Created on Thu Dec 18 17:10:18 2025

@author: Matthieu
"""

# config.py
import os

# Configuration OSM
OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 180  # secondes
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Types de routes à inclure (selon la classification OSM)
HIGHWAY_TYPES = [
    'motorway', 'trunk', 'primary', 'secondary',
    'tertiary', 'unclassified', 'residential',
    'service', 'pedestrian', 'footway', 'cycleway'
]

# Zones géographiques disponibles (exemples)
PRESET_AREAS = {
    "Paris": "Paris, France",
    "Lyon": "Lyon, France",
    "Marseille": "Marseille, France",
    "Toulouse": "Toulouse, France",
    "Nice": "Nice, France",
    "Berlin": "Berlin, Germany",
    "Madrid": "Madrid, Spain",
    "Rome": "Rome, Italy"
}

# Configuration de l'interface
UI_THEME = "dark"  # dark, light, system
UI_COLORS = {
    "primary": "#1f6aa5",
    "secondary": "#2cc985",
    "background": "#2b2b2b"
}