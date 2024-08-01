import streamlit as st
import httpx
import folium
from streamlit_folium import st_folium
from shapely.geometry import shape
import mercantile
import json
from arcgis.gis import GIS
from arcgis.mapping import WebMap
from arcgis.features import FeatureSet
import time

# Mapillary access token
mly_key = st.secrets["mly_key"]
arcgis_username = st.secrets["arcgis_username"]
arcgis_password = st.secrets["arcgis_password"]
st.write(arcgis_username)
st.write(arcgis_password)
st.write("hello")
# Initialize the Streamlit app
st.title("Mapillary Feature Explorer")

# Initialize session state
if 'map' not in st.session_state:
    st.session_state['map'] = folium.Map(location=[32.07011233586559, 34.78999632390827], zoom_start=12)
    draw = folium.plugins.Draw(export=True)
    draw.add_to(st.session_state['map'])

if 'features' not in st.session_state:
    st.session_state['features'] = []

def get_symbol_url(object_value):
    signs_base_url = "https://raw.githubusercontent.com/mapillary/mapillary_sprite_source/master/package_signs/"
    objects_base_url = "https://raw.githubusercontent.com/mapillary/mapillary_sprite_source/master/package_objects/"
    
    sign_url = f"{signs_base_url}{object_value}.svg"
    object_url = f"{objects_base_url}{object_value}.svg"
    
    with httpx.Client() as client:
        response = client.head(sign_url)
        if response.status_code == 200:
            return sign_url
        
        response = client.head(object_url)
        if response.status_code == 200:
            return object_url
    
    return None

def get_features_within_bbox(bbox, max_retries=3, delay=1):
    west, south, east, north = bbox
    tiles = list(mercantile.tiles(west, south, east, north, 22))
    bbox_list = [mercantile.bounds(tile.x, tile.y, tile.z) for tile in tiles]
    
    features = []
    
    with httpx.Client() as client:
        for bbox in bbox_list:
            bbox_str = f'{bbox.west},{bbox.south},{bbox.east},{bbox.north}'
            url = f'https://graph.mapillary.com/map_features?access_token={mly_key}&fields=id,object_value,geometry&bbox={bbox_str}'
            
            for attempt in range(max_retries):
                try:
                    response = client.get(url, timeout=10)
                    response.raise_for_status()
                    data = response.json().get('data', [])
                    for feature in data:
                        feature['symbol_url'] = get_symbol_url(feature['object_value'])
                    features.extend(data)
                    break
                except httpx.RequestError as e:
                    if attempt == max_retries - 1:
                        st.error(f"Failed to fetch features after {max_retries} attempts: {str(e)}")
                    else:
                        time.sleep(delay)
    
    return features

# Display the map
st_map = st_folium(st.session_state['map'], width=700, height=500)

# Check if a new polygon has been drawn
if st_map is not None and 'all_drawings' in st_map:
    last_draw = st_map['all_drawings'][-1] if st_map['all_drawings'] else None
    if last_draw is not None:
        st.session_state['last_draw'] = last_draw
        st.session_state['polygon_drawn'] = True
    else:
        st.session_state['polygon_drawn'] = False

# ... (previous code remains the same)

# Add a button to start the search
if st.button("Search for features and create map"):
    if st.session_state.get('polygon_drawn', False):
        last_draw = st.session_state['last_draw']
        geom = shape(last_draw['geometry'])
        bounds = geom.bounds  # (minx, miny, maxx, maxy)
        
        with st.spinner('Fetching features...'):
            features = get_features_within_bbox(bounds)
        
        if features:
            st.success(f"Found {len(features)} features in the selected area.")
    
            try:
                # Initialize ArcGIS GIS
                gis = GIS("https://www.arcgis.com", arcgis_username, arcgis_password)
                st.write("Initializing GIS...")

                webmap = WebMap()
                st.write("Creating webmap...")

                # Prepare features for ArcGIS
                geojson_data = {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": feature['geometry'],
                            "properties": {
                                "object_value": feature['object_value'],
                                "symbol_url": feature['symbol_url']
                            }
                        } for feature in features
                    ]
                }

                # Create a single layer with all features
                fs = FeatureSet.from_geojson(geojson_data)
                webmap.add_layer(fs, {
                    "title": "Mapillary Features",
                    "renderer": "simple"  # You might want to customize this based on your needs
                })

                # Save web map
                webmap_properties = {
                    "title": "Mapillary Features Web Map",
                    "snippet": "A web map showing Mapillary features with their symbols",
                    "tags": ["Mapillary", "GeoJSON", "Web Map"],
                    "extent": {
                        "spatialReference": {"wkid": 4326},
                        "xmin": bounds[0],
                        "ymin": bounds[1],
                        "xmax": bounds[2],
                        "ymax": bounds[3]
                    }
                }

                st.write("Saving webmap...")
                webmap_item = webmap.save(item_properties=webmap_properties)
                webmap_item.share(everyone=True)

                webmap_url = f"https://www.arcgis.com/apps/mapviewer/index.html?webmap={webmap_item.id}"
                st.success(f"Web map saved and made public. [View the web map]({webmap_url})")
                st.success(f"Web map saved with ID: {webmap_item.id}")

            except Exception as e:
                st.error(f"Failed to create ArcGIS web map: {str(e)}")
                st.write("Displaying features on Streamlit map instead.")

            # Add markers to the Streamlit map
            for feature in features:
                coords = feature['geometry']['coordinates'][::-1]  # Reverse lat/lon for folium
                popup_content = f"""
                ID: {feature['id']}<br>
                Value: {feature['object_value']}<br>
                <a href="{feature['symbol_url']}" target="_blank">View Symbol</a>
                """
                folium.Marker(location=coords, popup=popup_content).add_to(st.session_state['map'])
            
            # Display the updated map
            st_folium(st.session_state['map'], width=700, height=500)

        else:
            st.write("No features found within the drawn polygon.")
    else:
        st.write("Please draw a polygon on the map first.")

else:
    st.write("Draw a polygon on the map, then click the search button to see features and create a map.")
