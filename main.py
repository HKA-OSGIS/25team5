# main.py
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, MultiLineString, Polygon, Point, shape
import requests
import overpy
import threading
import queue
import json
import time
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import traceback
import sys
import os

# Configuration de CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class OSMAPIHandler:
    """Gestionnaire des API OSM avec gestion des erreurs améliorée"""
    
    def __init__(self):
        # Initialiser Overpass
        self.overpass_api = overpy.Overpass()
        self.nominatim_url = "https://nominatim.openstreetmap.org/search"
        self.overpass_url = "https://overpass-api.de/api/interpreter"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'StreetAnalyzer/1.0',
            'Accept': 'application/json'
        })
    
    def get_boundary_from_nominatim(self, place_name):
        """Récupère les limites via Nominatim"""
        params = {
            'q': place_name,
            'format': 'json',
            'polygon_geojson': 1,
            'limit': 1,
            'addressdetails': 1
        }
        
        print(f"Recherche Nominatim: {place_name}")
        
        try:
            response = self.session.get(
                self.nominatim_url, 
                params=params, 
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if not data:
                print(f"Aucun résultat pour {place_name}")
                return None
            
            result = data[0]
            print(f"Résultat trouvé: {result.get('display_name', 'N/A')}")
            
            # Essayer d'abord avec le polygone GeoJSON
            if 'geojson' in result:
                try:
                    geometry = shape(result['geojson'])
                    print(f"Géométrie GeoJSON: {geometry.geom_type}")
                    return geometry
                except Exception as e:
                    print(f"Erreur parsing GeoJSON: {e}")
            
            # Fallback: utiliser boundingbox
            if 'boundingbox' in result:
                bbox = result['boundingbox']
                print(f"Utilisation de bounding box: {bbox}")
                
                polygon = Polygon([
                    (float(bbox[2]), float(bbox[0])),
                    (float(bbox[3]), float(bbox[0])),
                    (float(bbox[3]), float(bbox[1])),
                    (float(bbox[2]), float(bbox[1])),
                    (float(bbox[2]), float(bbox[0]))
                ])
                return polygon
            
            print("Aucune géométrie trouvée dans la réponse")
            return None
            
        except requests.exceptions.Timeout:
            print("Timeout Nominatim")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Erreur requête Nominatim: {e}")
            return None
        except Exception as e:
            print(f"Erreur inattendue Nominatim: {e}")
            return None
    
    def get_ways_in_area(self, polygon):
        """Récupère les voies dans une zone via Overpass"""
        try:
            bbox = polygon.bounds
            print(f"Bounds de la zone: {bbox}")
            
            # Limiter la taille de la zone si trop grande
            area_size = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            if area_size > 0.05:
                print(f"Zone trop grande ({area_size:.4f} sq deg), réduction...")
                center = polygon.centroid
                bbox = (
                    center.x - 0.05, center.y - 0.05,
                    center.x + 0.05, center.y + 0.05
                )
                print(f"Nouveaux bounds: {bbox}")
            
            # Construire la requête Overpass
            query = f"""
            [out:json][timeout:90];
            (
              way["highway"]["name"]({bbox[1]:.6f},{bbox[0]:.6f},{bbox[3]:.6f},{bbox[2]:.6f});
            );
            out body;
            >;
            out skel qt;
            """
            
            print("Exécution requête Overpass...")
            
            response = self.session.post(
                self.overpass_url,
                data={'data': query},
                timeout=120
            )
            response.raise_for_status()
            
            data = response.json()
            elements = data.get('elements', [])
            print(f"Overpass a retourné {len(elements)} éléments")
            
            return self._process_osm_elements(data)
            
        except requests.exceptions.Timeout:
            print("Timeout Overpass")
            raise Exception("La requête a pris trop de temps. Essayez une zone plus petite.")
        except requests.exceptions.RequestException as e:
            print(f"Erreur requête Overpass: {e}")
            raise Exception(f"Erreur de connexion: {e}")
        except Exception as e:
            print(f"Erreur inattendue Overpass: {e}")
            print(traceback.format_exc())
            raise Exception(f"Erreur: {str(e)}")
    
    def _process_osm_elements(self, data):
        """Traite les éléments OSM pour créer un GeoDataFrame"""
        ways_data = []
        
        nodes = {}
        for element in data.get('elements', []):
            if element['type'] == 'node':
                nodes[element['id']] = (element['lon'], element['lat'])
        
        way_count = 0
        for element in data.get('elements', []):
            if element['type'] == 'way' and 'tags' in element:
                tags = element['tags']
                if 'name' in tags and 'highway' in tags:
                    way_count += 1
                    
                    way_nodes = []
                    node_ids = element.get('nodes', [])
                    
                    for node_id in node_ids:
                        if node_id in nodes:
                            way_nodes.append(nodes[node_id])
                    
                    if len(way_nodes) >= 2:
                        ways_data.append({
                            'name': tags['name'],
                            'highway': tags['highway'],
                            'geometry': LineString(way_nodes),
                            'osmid': element['id'],
                            'node_count': len(node_ids)
                        })
        
        print(f"{way_count} ways avec nom et highway, {len(ways_data)} convertis en LineString")
        
        if ways_data:
            gdf = gpd.GeoDataFrame(ways_data, crs="EPSG:4326")
            return gdf
        else:
            return gpd.GeoDataFrame()

class StreetAnalyzer:
    """Analyse et fusion des rues"""
    
    def merge_street_segments(self, ways_gdf):
        """Fusionne les segments d'une même rue"""
        if ways_gdf.empty:
            print("Aucune donnée à fusionner")
            return ways_gdf
        
        print(f"Fusion de {len(ways_gdf)} segments...")
        
        merged_data = []
        
        ways_gdf['name_lower'] = ways_gdf['name'].str.lower()
        
        for name_lower in ways_gdf['name_lower'].unique():
            segments = ways_gdf[ways_gdf['name_lower'] == name_lower]
            
            if not segments.empty:
                original_name = segments.iloc[0]['name']
                
                all_coords = []
                for geom in segments.geometry:
                    if geom.geom_type == 'LineString':
                        all_coords.extend(list(geom.coords))
                    elif geom.geom_type == 'MultiLineString':
                        for subgeom in geom.geoms:
                            all_coords.extend(list(subgeom.coords))
                
                if len(all_coords) >= 2:
                    try:
                        merged_line = LineString(all_coords)
                        length_m = merged_line.length * 111000
                        
                        merged_data.append({
                            'name': original_name,
                            'geometry': merged_line,
                            'segment_count': len(segments),
                            'length_m': length_m
                        })
                        
                    except Exception as e:
                        print(f"Erreur création LineString pour {original_name}: {e}")
        
        print(f"Fusion terminée: {len(merged_data)} rues fusionnées")
        
        if merged_data:
            merged_gdf = gpd.GeoDataFrame(merged_data, crs=ways_gdf.crs)
            if 'name_lower' in merged_gdf.columns:
                merged_gdf = merged_gdf.drop(columns=['name_lower'])
            return merged_gdf
        else:
            return gpd.GeoDataFrame()
    
    def get_top_streets(self, merged_gdf, top_n=10):
        """Retourne le top N des rues par longueur"""
        if merged_gdf.empty:
            print("Aucune donnée pour le top")
            return pd.DataFrame()
        
        if 'length_m' not in merged_gdf.columns:
            merged_gdf['length_m'] = merged_gdf.geometry.length * 111000
        
        merged_gdf['length_km'] = merged_gdf['length_m'] / 1000
        
        top_streets = merged_gdf.sort_values('length_m', ascending=False).head(top_n)
        
        result = top_streets[['name', 'length_km', 'segment_count']].copy()
        result = result.reset_index(drop=True)
        
        print(f"Top {len(result)} rues trouvées")
        return result
    
    def battle_streets(self, street_names, merged_gdf):
        """Compare plusieurs rues entre elles"""
        if merged_gdf.empty:
            print("Aucune donnée pour la battle")
            return pd.DataFrame()
        
        results = []
        
        for street_name in street_names:
            matching = merged_gdf[
                merged_gdf['name'].str.lower().str.contains(
                    street_name.lower(), na=False
                )
            ]
            
            if not matching.empty:
                total_length = matching['length_m'].sum() / 1000
                total_segments = matching['segment_count'].sum()
                score = total_length * total_segments
            else:
                total_length = 0
                total_segments = 0
                score = 0
            
            results.append({
                'name': street_name,
                'length_km': total_length,
                'segments': total_segments,
                'score': score
            })
        
        results_df = pd.DataFrame(results)
        if not results_df.empty:
            results_df = results_df.sort_values('score', ascending=False)
            results_df['rank'] = range(1, len(results_df) + 1)
        
        print(f"Battle terminée pour {len(street_names)} rues")
        return results_df

class StreetAnalyzerApp(ctk.CTk):
    """Application principale"""
    
    def __init__(self):
        super().__init__()
        
        self.title("Analyseur de Voies OSM")
        self.geometry("1200x800")
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.queue = queue.Queue()
        self.is_loading = False
        self.current_area = None
        self.current_streets = None
        self.merged_streets = None
        
        self.osm_handler = OSMAPIHandler()
        self.analyzer = StreetAnalyzer()
        
        self.setup_ui()
        
        self.after(100, self.check_queue)
        
        print("Application initialisée")
    
    def setup_ui(self):
        """Configure l'interface utilisateur"""
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Contrôles supérieurs
        control_frame = ctk.CTkFrame(main_frame)
        control_frame.pack(fill="x", pady=(0, 10))
        
        # Zone de recherche
        search_frame = ctk.CTkFrame(control_frame)
        search_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(search_frame, text="Zone à analyser:", 
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 5))
        
        # CORRECTION : Utiliser une variable StringVar correctement
        self.search_var = ctk.StringVar()
        
        # Champ de recherche
        self.search_entry = ctk.CTkEntry(
            search_frame, 
            textvariable=self.search_var,
            placeholder_text="Ex: Paris, France ou Rue du Bac, Paris",
            height=40,
            font=ctk.CTkFont(size=13)
        )
        self.search_entry.pack(fill="x", pady=(0, 5))
        self.search_entry.bind('<Return>', lambda e: self.load_area())
        
        # Bouton de chargement
        self.load_btn = ctk.CTkButton(
            search_frame,
            text="Charger la zone",
            command=self.load_area,
            height=40,
            font=ctk.CTkFont(size=13)
        )
        self.load_btn.pack(fill="x")
        
        # Information sur la zone
        info_frame = ctk.CTkFrame(control_frame)
        info_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.area_info = ctk.CTkLabel(
            info_frame,
            text="Aucune zone chargée",
            text_color="gray",
            font=ctk.CTkFont(size=12)
        )
        self.area_info.pack(anchor="w")
        
        # Barre de progression
        self.progress = ctk.CTkProgressBar(control_frame)
        self.progress.pack(fill="x", padx=10, pady=(0, 5))
        self.progress.set(0)
        
        # Onglets
        self.tabview = ctk.CTkTabview(main_frame)
        self.tabview.pack(fill="both", expand=True)
        
        # Onglet Top 10
        self.top10_tab = self.tabview.add("Top 10")
        self.setup_top10_tab()
        
        # Onglet Battle
        self.battle_tab = self.tabview.add("Battle")
        self.setup_battle_tab()
        
        # Onglet Export
        self.export_tab = self.tabview.add("Export")
        self.setup_export_tab()
        
        # Journal
        log_frame = ctk.CTkFrame(main_frame)
        log_frame.pack(fill="x", pady=(10, 0))
        
        ctk.CTkLabel(log_frame, text="Journal:", 
                    font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5, 0))
        
        self.log_text = ctk.CTkTextbox(log_frame, height=100)
        self.log_text.pack(fill="x", padx=10, pady=(0, 10))
        self.log_text.insert("1.0", "Entrez une zone (ville, quartier, adresse) et cliquez sur 'Charger la zone'.\n")
        self.log_text.configure(state="disabled")
    
    def setup_top10_tab(self):
        """Configure l'onglet Top 10"""
        frame = self.top10_tab
        
        button_frame = ctk.CTkFrame(frame)
        button_frame.pack(fill="x", padx=10, pady=10)
        
        self.top10_btn = ctk.CTkButton(
            button_frame,
            text="Analyser le Top 10",
            command=self.analyze_top10,
            state="disabled",
            height=40
        )
        self.top10_btn.pack(pady=5)
        
        results_frame = ctk.CTkFrame(frame)
        results_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        columns = ("Rang", "Nom de la rue", "Longueur (km)", "Segments")
        self.top10_tree = ttk.Treeview(results_frame, columns=columns, show="headings", height=15)
        
        for col in columns:
            self.top10_tree.heading(col, text=col)
            self.top10_tree.column(col, width=200 if col == "Nom de la rue" else 100)
        
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.top10_tree.yview)
        self.top10_tree.configure(yscrollcommand=scrollbar.set)
        
        self.top10_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def setup_battle_tab(self):
        """Configure l'onglet Battle"""
        frame = self.battle_tab
        
        ctk.CTkLabel(frame, text="Entrez 2 à 5 noms de rues à comparer:",
                    font=ctk.CTkFont(size=13)).pack(anchor="w", padx=20, pady=(15, 5))
        
        self.battle_entries = []
        entry_frame = ctk.CTkFrame(frame)
        entry_frame.pack(fill="x", padx=20, pady=5)
        
        for i in range(5):
            entry = ctk.CTkEntry(
                entry_frame,
                placeholder_text=f"Nom de la rue {i+1}",
                height=35
            )
            entry.pack(fill="x", pady=2)
            self.battle_entries.append(entry)
        
        self.battle_btn = ctk.CTkButton(
            frame,
            text="Lancer la Battle",
            command=self.analyze_battle,
            state="disabled",
            height=40
        )
        self.battle_btn.pack(pady=10)
        
        results_frame = ctk.CTkFrame(frame)
        results_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        
        columns = ("Position", "Rue", "Score", "Longueur (km)")
        self.battle_tree = ttk.Treeview(results_frame, columns=columns, show="headings", height=10)
        
        for col in columns:
            self.battle_tree.heading(col, text=col)
            self.battle_tree.column(col, width=250 if col == "Rue" else 100)
        
        battle_scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.battle_tree.yview)
        self.battle_tree.configure(yscrollcommand=battle_scrollbar.set)
        
        self.battle_tree.pack(side="left", fill="both", expand=True)
        battle_scrollbar.pack(side="right", fill="y")
    
    def setup_export_tab(self):
        """Configure l'onglet Export"""
        frame = self.export_tab
        
        ctk.CTkLabel(frame, text="Export des données:",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(pady=20)
        
        export_frame = ctk.CTkFrame(frame)
        export_frame.pack(expand=True)
        
        self.export_csv_btn = ctk.CTkButton(
            export_frame,
            text="Exporter en CSV",
            command=self.export_csv,
            state="disabled",
            width=200,
            height=40
        )
        self.export_csv_btn.pack(pady=10)
        
        self.export_geojson_btn = ctk.CTkButton(
            export_frame,
            text="Exporter en GeoJSON",
            command=self.export_geojson,
            state="disabled",
            width=200,
            height=40
        )
        self.export_geojson_btn.pack(pady=10)
    
    def log(self, message):
        """Ajoute un message au journal"""
        self.log_text.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.update_idletasks()
    
    def load_area(self):
        """Charge une zone depuis Nominatim"""
        if self.is_loading:
            self.log("Une opération est déjà en cours...")
            return
        
        # CORRECTION : Récupérer directement la valeur du champ d'entrée
        place_name = self.search_entry.get().strip()
        if not place_name:
            messagebox.showwarning("Attention", "Veuillez entrer un nom de lieu")
            return
        
        self.is_loading = True
        self.load_btn.configure(state="disabled")
        self.progress.set(0.2)
        self.log(f"Chargement de la zone: {place_name}")
        
        thread = threading.Thread(
            target=self._load_area_thread,
            args=(place_name,),
            daemon=True
        )
        thread.start()
    
    def _load_area_thread(self, place_name):
        """Thread pour charger la zone"""
        try:
            area = self.osm_handler.get_boundary_from_nominatim(place_name)
            
            if area is None:
                self.queue.put(("error", f"Zone '{place_name}' non trouvée. Essayez un nom différent."))
                return
            
            area_km2 = area.area * 111 * 111
            
            self.queue.put(("area_loaded", (place_name, area, area_km2)))
            self.queue.put(("progress", 1.0))
            self.queue.put(("log", f"Zone chargée: {area_km2:.1f} km²"))
            
        except Exception as e:
            error_msg = f"Erreur lors du chargement: {str(e)}"
            self.queue.put(("error", error_msg))
        finally:
            self.queue.put(("loading_done", None))
    
    def analyze_top10(self):
        """Analyse le top 10 des rues"""
        if self.current_area is None:
            messagebox.showwarning("Attention", "Veuillez d'abord charger une zone")
            return
        
        if self.is_loading:
            self.log("Une opération est déjà en cours...")
            return
        
        self.is_loading = True
        self.top10_btn.configure(state="disabled")
        self.progress.set(0.1)
        self.log("Analyse Top 10 en cours...")
        
        thread = threading.Thread(target=self._analyze_top10_thread, daemon=True)
        thread.start()
    
    def _analyze_top10_thread(self):
        """Thread d'analyse top 10"""
        try:
            self.queue.put(("progress", 0.3))
            self.queue.put(("log", "Récupération des voies depuis OSM..."))
            
            streets = self.osm_handler.get_ways_in_area(self.current_area)
            
            if streets.empty:
                self.queue.put(("error", "Aucune voie trouvée dans cette zone"))
                return
            
            self.queue.put(("progress", 0.5))
            self.queue.put(("log", f"{len(streets)} segments trouvés"))
            
            self.queue.put(("log", "Fusion des segments de rue..."))
            merged = self.analyzer.merge_street_segments(streets)
            
            if merged.empty:
                self.queue.put(("error", "Erreur lors de la fusion des segments"))
                return
            
            self.current_streets = streets
            self.merged_streets = merged
            
            self.queue.put(("progress", 0.7))
            self.queue.put(("log", f"{len(merged)} rues fusionnées"))
            
            top10 = self.analyzer.get_top_streets(merged, 10)
            
            results = []
            for idx, (_, row) in enumerate(top10.iterrows(), 1):
                results.append((
                    idx,
                    row['name'][:60],
                    f"{row['length_km']:.2f}",
                    int(row['segment_count'])
                ))
            
            self.queue.put(("top10_results", results))
            self.queue.put(("progress", 1.0))
            self.queue.put(("log", "Top 10 terminé!"))
            
            self.queue.put(("enable_export", True))
            
        except Exception as e:
            error_msg = f"Erreur lors de l'analyse: {str(e)}"
            self.queue.put(("error", error_msg))
        finally:
            self.queue.put(("loading_done", None))
    
    def analyze_battle(self):
        """Analyse la battle entre rues"""
        if self.current_area is None:
            messagebox.showwarning("Attention", "Veuillez d'abord charger une zone")
            return
        
        street_names = [entry.get().strip() for entry in self.battle_entries if entry.get().strip()]
        if len(street_names) < 2:
            messagebox.showwarning("Attention", "Entrez au moins 2 noms de rues")
            return
        
        if self.is_loading:
            self.log("Une opération est déjà en cours...")
            return
        
        self.is_loading = True
        self.battle_btn.configure(state="disabled")
        self.progress.set(0.1)
        self.log(f"Battle en cours avec {len(street_names)} rues...")
        
        thread = threading.Thread(
            target=self._analyze_battle_thread,
            args=(street_names,),
            daemon=True
        )
        thread.start()
    
    def _analyze_battle_thread(self, street_names):
        """Thread d'analyse battle"""
        try:
            if self.merged_streets is None:
                self.queue.put(("progress", 0.3))
                self.queue.put(("log", "Récupération des données..."))
                
                streets = self.osm_handler.get_ways_in_area(self.current_area)
                if streets.empty:
                    self.queue.put(("error", "Aucune voie trouvée"))
                    return
                
                merged = self.analyzer.merge_street_segments(streets)
                self.merged_streets = merged
            else:
                merged = self.merged_streets
            
            self.queue.put(("progress", 0.7))
            
            results_df = self.analyzer.battle_streets(street_names, merged)
            
            battle_results = []
            for _, row in results_df.iterrows():
                battle_results.append((
                    int(row['rank']),
                    row['name'][:60],
                    f"{row['score']:.0f}",
                    f"{row['length_km']:.2f}"
                ))
            
            self.queue.put(("battle_results", battle_results))
            self.queue.put(("progress", 1.0))
            self.queue.put(("log", "Battle terminée!"))
            
        except Exception as e:
            error_msg = f"Erreur lors de la battle: {str(e)}"
            self.queue.put(("error", error_msg))
        finally:
            self.queue.put(("loading_done", None))
    
    def export_csv(self):
        """Exporte les résultats en CSV"""
        if self.merged_streets is None:
            messagebox.showwarning("Attention", "Aucune donnée à exporter")
            return
        
        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                title="Exporter en CSV"
            )
            
            if filename:
                df = pd.DataFrame({
                    'nom_rue': self.merged_streets['name'],
                    'longueur_km': self.merged_streets['length_m'] / 1000,
                    'segments': self.merged_streets['segment_count']
                })
                
                df.to_csv(filename, index=False, encoding='utf-8')
                self.log(f"Données exportées en CSV: {os.path.basename(filename)}")
                messagebox.showinfo("Succès", f"Données exportées avec succès:\n{filename}")
                
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de l'export: {str(e)}")
    
    def export_geojson(self):
        """Exporte les données en GeoJSON"""
        if self.merged_streets is None:
            messagebox.showwarning("Attention", "Aucune donnée à exporter")
            return
        
        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=".geojson",
                filetypes=[("GeoJSON files", "*.geojson"), ("All files", "*.*")],
                title="Exporter en GeoJSON"
            )
            
            if filename:
                self.merged_streets.to_file(filename, driver='GeoJSON')
                self.log(f"Données exportées en GeoJSON: {os.path.basename(filename)}")
                messagebox.showinfo("Succès", f"Données exportées avec succès:\n{filename}")
                
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de l'export: {str(e)}")
    
    def check_queue(self):
        """Vérifie les messages dans la file d'attente"""
        try:
            while True:
                try:
                    msg_type, data = self.queue.get_nowait()
                    
                    if msg_type == "log":
                        self.log(data)
                    elif msg_type == "error":
                        messagebox.showerror("Erreur", data)
                        self.log(f"Erreur: {data}")
                    elif msg_type == "progress":
                        self.progress.set(data)
                    elif msg_type == "area_loaded":
                        place_name, area, area_km2 = data
                        self.current_area = area
                        
                        self.area_info.configure(
                            text=f"{place_name} | Superficie: {area_km2:.1f} km²",
                            text_color="white"
                        )
                        
                        self.top10_btn.configure(state="normal")
                        self.battle_btn.configure(state="normal")
                        
                    elif msg_type == "loading_done":
                        self.is_loading = False
                        self.load_btn.configure(state="normal")
                        self.top10_btn.configure(state="normal")
                        self.battle_btn.configure(state="normal")
                        self.progress.set(0)
                        
                    elif msg_type == "top10_results":
                        self._display_top10_results(data)
                    elif msg_type == "battle_results":
                        self._display_battle_results(data)
                    elif msg_type == "enable_export":
                        self.export_csv_btn.configure(state="normal")
                        self.export_geojson_btn.configure(state="normal")
                    
                except queue.Empty:
                    break
        except Exception as e:
            print(f"Erreur dans check_queue: {e}")
        
        self.after(100, self.check_queue)
    
    def _display_top10_results(self, results):
        """Affiche les résultats du top 10"""
        for item in self.top10_tree.get_children():
            self.top10_tree.delete(item)
        
        for result in results:
            self.top10_tree.insert("", "end", values=result)
        
        self.tabview.set("Top 10")
    
    def _display_battle_results(self, results):
        """Affiche les résultats de la battle"""
        for item in self.battle_tree.get_children():
            self.battle_tree.delete(item)
        
        for result in results:
            self.battle_tree.insert("", "end", values=result)
        
        self.tabview.set("Battle")
    
    def on_closing(self):
        """Gère la fermeture de l'application"""
        if messagebox.askokcancel("Quitter", "Voulez-vous vraiment quitter l'application ?"):
            self.destroy()

def main():
    """Fonction principale"""
    try:
        print("Démarrage de l'analyseur de voies OSM...")
        app = StreetAnalyzerApp()
        app.mainloop()
    except Exception as e:
        print(f"Erreur fatale: {e}")
        print(traceback.format_exc())

if __name__ == "__main__":
    main()