#!/usr/bin/env python
# coding: utf-8

import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from sqlalchemy import create_engine, text
import streamlit.components.v1 as components

# =====================================================
# PAGE CONFIG (MUST BE FIRST STREAMLIT COMMAND)
# =====================================================
st.set_page_config(
    layout="wide",
    page_title="Street Name Analysis (GIS Project)"
)

# =====================================================
# DATABASE CONFIG
# =====================================================
DB_URL = "postgresql://amirzarezadeh@localhost:5432/gis_project_db"

@st.cache_resource
def get_engine():
    return create_engine(DB_URL)

engine = get_engine()

# =====================================================
# HEADER
# =====================================================
st.title("🗺️ Street Name Analysis (GIS Project)")
st.markdown("Ranking and comparison of the most frequent street names based on OpenStreetMap data.")

# =====================================================
# SIDEBAR
# =====================================================
with st.sidebar:
    st.header("Settings")
    try:
        regions_df = pd.read_sql(
            "SELECT DISTINCT region_name FROM rues_nettoyees ORDER BY region_name",
            engine
        )
        region = st.selectbox("Select a region", regions_df["region_name"])
    except Exception:
        st.error("Database connection failed. Did you run the ETL pipeline?")
        st.stop()

# =====================================================
# TABS
# =====================================================
tab1, tab2 = st.tabs(["🏆 Top 10 Street Names", "🗺️ Street Name Battle + Map"])

# =====================================================
# TAB 1 — TOP 10
# =====================================================
with tab1:
    st.subheader(f"Top 10 most frequent street names in {region}")

    sql_top10 = text("""
        SELECT
            nom_normalise AS street_name,
            COUNT(*) AS occurrences,
            STRING_AGG(DISTINCT type_voie, ', ') AS street_types
        FROM rues_nettoyees
        WHERE region_name = :region
        GROUP BY nom_normalise
        ORDER BY occurrences DESC
        LIMIT 10
    """)

    df_top10 = pd.read_sql(sql_top10, engine, params={"region": region})

    col_chart, col_table = st.columns([2, 1])

    with col_chart:
        st.bar_chart(df_top10.set_index("street_name")["occurrences"])

    with col_table:
        st.dataframe(df_top10, use_container_width=True)

# =====================================================
# TAB 2 — STREET NAME BATTLE + MAP
# =====================================================
with tab2:
    st.subheader("Street Name Battle + Map")

    st.caption(
        "Tip: enter the **street name only** (normalized), not the street type. "
        "Example: use 'CHATEAU' instead of 'RUE CHATEAU'."
    )

    col1, col2 = st.columns(2)
    street_a = col1.text_input("Street A (e.g. CHATEAU)").strip().upper()
    street_b = col2.text_input("Street B (e.g. GARE)").strip().upper()

    if st.button("Compare") and street_a and street_b:
        sql_compare = text("""
            SELECT
                nom_normalise AS street_name,
                COUNT(*) AS occurrences
            FROM rues_nettoyees
            WHERE region_name = :region
              AND nom_normalise IN (:a, :b)
            GROUP BY nom_normalise
        """)

        df_compare = pd.read_sql(
            sql_compare,
            engine,
            params={"region": region, "a": street_a, "b": street_b}
        )

        if df_compare.empty:
            st.warning("No data found for the selected street names in this region.")
        else:
            st.subheader("Comparison Result")
            st.bar_chart(df_compare.set_index("street_name")["occurrences"])

            # ================= MAP =================
            st.subheader("Spatial Distribution")
            st.info("Map display is limited to 100 random segments for performance.")

            # IMPORTANT: your geometry column is named "geometry" (not "geom")
            sql_map = text("""
                SELECT nom_normalise, geometry
                FROM rues_nettoyees
                WHERE region_name = :region
                  AND nom_normalise IN (:a, :b)
                ORDER BY RANDOM()
                LIMIT 100
            """)

            gdf_map = gpd.read_postgis(
                sql_map,
                engine,
                geom_col="geometry",
                params={"region": region, "a": street_a, "b": street_b}
            )

            if gdf_map.empty:
                st.warning("No geometries found.")
            else:
                center = gdf_map.unary_union.centroid

                m = folium.Map(
                    location=[center.y, center.x],
                    zoom_start=9,
                    tiles="CartoDB dark_matter"
                )

                colors = {street_a: "blue", street_b: "red"}

                for _, row in gdf_map.iterrows():
                    geom = row["geometry"]
                    name = row["nom_normalise"]

                    # Handle MultiLineString vs LineString
                    if geom.geom_type == "MultiLineString":
                        lines = list(geom.geoms)
                    else:
                        lines = [geom]

                    for line in lines:
                        coords = [[y, x] for x, y in line.coords]
                        folium.PolyLine(
                            coords,
                            color=colors.get(name, "green"),
                            weight=3,
                            tooltip=name
                        ).add_to(m)

                # ✅ NO streamlit_folium (avoids JSON serialization crash)
                components.html(m._repr_html_(), height=520)
