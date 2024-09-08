from flask import Flask, render_template, jsonify
from flask import request
import numpy as np
import pandas as pd
import openpyxl
import geopandas as gpd
import folium
import esda
from pysal.lib import weights
import os 
####INTRODUCE JAVASCRIPT 
#Initialization of Flask App
dash = Flask(__name__)

#Directory to Excel Sheets for analysis 
data = "data"

#Function for Converting Data to Pandas selected_period_data
def read_data(file_path):
    selected_period_data = pd.read_csv(file_path)
    return selected_period_data

#Function for converting period_data (that already has fetched lat, long via google API in table) to gdf
def create_gdf(selected_period_data):
    selected_period_data[['latitude', 'longitude']] = selected_period_data['coordinates'].str.split(',', expand=True)

    selected_period_data['latitude'] = selected_period_data['latitude'].astype(float)
    selected_period_data['longitude'] = selected_period_data['longitude'].astype(float)
    
    period_data_gdf = gpd.GeoDataFrame(
    selected_period_data, 
    geometry=gpd.points_from_xy(selected_period_data['longitude'], selected_period_data['latitude'])
    )
    return period_data_gdf

#Function that filters data by period requested by user
def filter_by_period(selected_period_data):
    return selected_period_data

#Function for creating aggregate of average site screening
def average_screening_per_site(period_data_gdf):
    average_site_screen_lvl = period_data_gdf.groupby(['Organization', 'Address']).agg({
    'Screening Level': 'mean',
    'longitude': 'first',
    'latitude': 'first'
    }).reset_index()
    renamed_col_avg = average_site_screen_lvl.rename(columns={'Screening Level': 'Average Screening Level'}, inplace=False)
    avg_screening_sorted = renamed_col_avg.sort_values(by='Average Screening Level', ascending=False).reset_index(drop=True)
    avg_screening_sorted_gdf = gpd.GeoDataFrame(
    avg_screening_sorted, 
    geometry=gpd.points_from_xy(avg_screening_sorted['longitude'], avg_screening_sorted['latitude'])
    )
    return avg_screening_sorted_gdf

#Function for average screening level across all sites for a period 
def average_screening_period(period_data_gdf):
    average_screening_total = period_data_gdf['Screening Level'].mean()
    return average_screening_total

#Function for I-moran Statistic 
def calculate_moran(avg_screening_sorted_gdf):
    #CRS and Geodataframe Conversion
    avg_screening_sorted_gdf.crs = 'epsg:4326'
    screen_values = avg_screening_sorted_gdf["Average Screening Level"].values
    #Weight for KNN matrix generation
    n = len(avg_screening_sorted_gdf)
    #Import math lib(?)
    k = int(np.sqrt(n))
    weight = weights.KNN.from_dataframe(avg_screening_sorted_gdf, k=k)
    weight.transform = 'r'
    moran_analysis = esda.moran.Moran(screen_values, weight) 
    return moran_analysis.I, moran_analysis.EI, moran_analysis.z_norm, moran_analysis.p_norm

#Function for creating map using Folium
def create_map(avg_screening_sorted_gdf):
    #Sets initial map zoom and location
    harlem_lat, harlem_lon = 40.8116, -73.9465
    base_map = folium.Map(location=[harlem_lat, harlem_lon], zoom_start=14, min_zoom=12.5, max_zoom=14, control_scale=True, max_bounds=[harlem_lat, harlem_lon], tiles="cartodbpositron")
    plotted_map = base_map
    #Looks for unique organization rows
    unique_org = avg_screening_sorted_gdf['Organization'].unique()
    #iterates over unique organizations, creates index
    org_index = {seq: idx for idx, seq in enumerate(unique_org)}
    #Marker colors for each organization
    marker_colors = ["red", "orange", "green", "blue", "yellow", "purple"]
    #Needed for map
    avg_screening_sorted_gdf.crs = 'epsg:4326'
    #Folium with marker color programmed based on org
    folium.GeoJson(
        avg_screening_sorted_gdf,
        name="Harlem Strong Sites Visited During Selected Period",
        zoom_on_click=True,
        marker=folium.Marker(icon=folium.Icon(icon="glyphicon glyphicon-ok")),
        tooltip=folium.GeoJsonTooltip(fields=['Address', 'Organization', 'Average Screening Level']),
        popup=folium.GeoJsonPopup(fields=['Address', 'Organization', 'Average Screening Level']),
        style_function=lambda x: {
        'markerColor': marker_colors[org_index[x['properties']['Organization']] % len(marker_colors)],
     },
    ).add_to(plotted_map)
    return plotted_map

#Routes to the 'dash' app that was initialized
@dash.route('/')
def index():
    #Available periods by number of excel files
    periods = [f"Period{i}" for i in range(1, 9)]
    return render_template("index.html", periods=periods)

#Routes to the 'dash' app and handles file creation using POST
@dash.route('/analyze', methods=["POST"])
def analyze():
    #Period selection
    selected_period = request.form.get('period')
    if not selected_period:
        return render_template('index.html', 
                               error='No period selected.',
                               periods=[f'Period{i}' for i in range(1, 9)],
                               selected_period=None)
    
    file_path = os.path.join(data, f'{selected_period}.csv')
    if not os.path.isfile(file_path):
        return render_template('index.html', 
                               error='Data Not Yet Collected.',
                               periods=[f'Period{i}' for i in range(1, 9)],
                               selected_period=selected_period)
    else:
        #Conversion to df and gdf
        selected_period_data = read_data(file_path)
        period_data_gdf = create_gdf(selected_period_data)
        #Applying functions that were defined 
        avg_screening_sorted = average_screening_per_site(period_data_gdf) 
        average_screening_total = average_screening_period(selected_period_data)
        moran_results = calculate_moran(avg_screening_sorted)
        #Creation of Map 
        map_html = create_map(avg_screening_sorted)._repr_html_()
        #Returns webpage with html version of python analyses and maps
        return render_template('index.html',
                            periods = [f"Period{i}" for i in range(1, 9)],
                            avg_per_site = avg_screening_sorted.to_html(),
                            avg_period = round(average_screening_total, 2),
                            moran_results = moran_results,
                            map_html = map_html,
                            selected_period = selected_period)

#Debugging and initialization 
if __name__ == '__main__':
    dash.run(debug=True)

