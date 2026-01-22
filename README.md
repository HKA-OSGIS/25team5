# 🗺️ Street Name Analysis & Battle (OpenStreetMap + PostGIS)

This project analyzes street names using OpenStreetMap (OSM) data and provides
an interactive web application to explore and compare the most frequent street
names per region.

The project was developed as part of an **Open Source GIS** course and focuses on:
- Spatial data processing (ETL)
- PostGIS spatial database
- Interactive data exploration with Streamlit

---

## 💡 Project Idea

**Street Name Battle**

The application allows users to:
- Select a region
- View the **Top 10 most frequent street names** in that region
- Compare two street names (e.g. *PASTEUR vs GAULLE*)
- Visualize the spatial distribution of streets on an interactive map

---

## 🗂️ Data Sources

All spatial data is stored in the `data/` folder:

- **OSM Roads**  
  `gis_osm_roads_free_1.*`  
  → Road network extracted from OpenStreetMap

- **Administrative Regions**  
  `regions_20140306_5m.*`  
  → Regional boundaries used for spatial aggregation

> Data is provided in ESRI Shapefile format.

---

## ⚙️ Architecture Overview

OSM Shapefiles
↓
ETL Pipeline (GeoPandas)
↓
PostGIS Database
↓
Streamlit Web Application



---

## 🔄 ETL Pipeline

The ETL process is implemented in:


Final_ETL.py


### Main Steps:
1. Load road and region shapefiles
2. Perform spatial join (assign each road to a region)
3. Clean and normalize street names
4. Aggregate duplicate street segments
5. Export processed data to **PostGIS**

### Output Table:


rues_nettoyees


---

## 🗄️ Database Setup

### Requirements:
- PostgreSQL
- PostGIS extension

### Create database and enable PostGIS:
```sql
CREATE DATABASE gis_project_db;
\c gis_project_db
CREATE EXTENSION postgis;



🚀 How to Run the Project
1️⃣ Install Python dependencies

pip install -r requirements.txt


2️⃣ Run the ETL pipeline

python Final_ETL.py


3️⃣ Launch the web application


streamlit run Final_WebApp.py

🌐 Web Application Features

Region selection

Top 10 most frequent street names

Street name comparison (battle mode)

Interactive map visualization (Folium)




🛠️ Technologies Used

Python

GeoPandas

PostGIS

PostgreSQL

SQLAlchemy

Streamlit

Folium

OpenStreetMap data




📚 Academic Context

This project was developed for an academic course and demonstrates:

Spatial data processing

Database-driven GIS workflows

Open-source geospatial technologies



License

- Code: MIT License  
- Data: OpenStreetMap data © OpenStreetMap contributors, licensed under the Open Database License (ODbL)
