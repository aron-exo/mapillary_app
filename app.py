import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
from shapely.geometry import shape
import mercantile
import io
import zipfile

# Mapillary access token
mly_key = st.secrets["mly_key"]

# Initialize the Streamlit app
st.title("Mapillary Feature Explorer")

# Initialize session state
if 'map' not in st.session_state:
    st.session_state['map'] = folium.Map(location=[34.78999632390827,
          32.07011233586559], zoom_start=12)
    draw = folium.plugins.Draw(export=True)
    draw.add_to(st.session_state['map'])

if 'features' not in st.session_state:
    st.session_state['features'] = []

# Function to get image URL for a feature
def get_image_url(feature_id):
    url = f'https://graph.mapillary.com/{feature_id}?access_token={mly_key}&fields=images'
    response = requests.get(url)
    if response.status_code == 200:
        json_data = response.json()
        if 'images' in json_data and 'data' in json_data['images'] and json_data['images']['data']:
            image_id = json_data['images']['data'][0]['id']
            image_url = f'https://graph.mapillary.com/{image_id}?access_token={mly_key}&fields=thumb_original_url'
            response = requests.get(image_url)
            if response.status_code == 200:
                image_data = response.json()
                return image_data.get('thumb_original_url')
    return None

# Function to get features within a bounding box
def get_features_within_bbox(bbox):
    west, south, east, north = bbox
    tiles = list(mercantile.tiles(west, south, east, north, 10))
    bbox_list = [mercantile.bounds(tile.x, tile.y, tile.z) for tile in tiles]
    
    features = []
    
    for bbox in bbox_list:
        bbox_str = f'{bbox.west},{bbox.south},{bbox.east},{bbox.north}'
        url = f'https://graph.mapillary.com/map_features?access_token={mly_key}&fields=id,object_value,geometry&bbox={bbox_str}'
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json().get('data', [])
            for feature in data:
                feature['image_url'] = get_image_url(feature['id'])
            features.extend(data)
    
    return features

# Function to download images and create a zip file
def create_image_zip(features):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for i, feature in enumerate(features):
            image_url = feature.get('image_url')
            if image_url:
                try:
                    response = requests.get(image_url)
                    if response.status_code == 200:
                        image_data = response.content
                        file_name = f"feature_{i+1}_{feature['id']}.jpg"
                        zip_file.writestr(file_name, image_data)
                        st.write(f"Added {file_name} to zip")
                    else:
                        st.write(f"Failed to download image for feature {i+1} ({feature['id']})")
                except Exception as e:
                    st.write(f"Error downloading image for feature {i+1} ({feature['id']}): {str(e)}")
            else:
                st.write(f"No image URL for feature {i+1} ({feature['id']})")
    
    zip_buffer.seek(0)
    return zip_buffer

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

# Add a button to start the search
if st.session_state.get('polygon_drawn', False):
    if st.button("Search for features and download images"):
        last_draw = st.session_state['last_draw']
        # Extract coordinates from drawn polygon
        geom = shape(last_draw['geometry'])
        bounds = geom.bounds  # (minx, miny, maxx, maxy)
        
        # Get features within the bounding box
        features = get_features_within_bbox(bounds)
        
        st.session_state['features'] = features
        st.success(f"Found {len(features)} features in the selected area.")

        # Create zip file with images
        zip_buffer = create_image_zip(features)
        
        # Offer the zip file for download
        st.download_button(
            label="Download Images",
            data=zip_buffer,
            file_name="mapillary_images.zip",
            mime="application/zip"
        )

        # Display features and add markers to the map
        for feature in features:
            geom = feature['geometry']
            coords = geom['coordinates'][::-1]  # Reverse lat/lon for folium
            image_url = feature.get('image_url', '#')
            popup_content = f"""
            ID: {feature['id']}<br>
            Value: {feature['object_value']}<br>
            <a href="{image_url}" target="_blank">View Image</a>
            """
            folium.Marker(location=coords, popup=popup_content).add_to(st.session_state['map'])
        
        # Display the updated map
        st_folium(st.session_state['map'], width=700, height=500)

else:
    st.write("Draw a polygon on the map, then click the search button to download images and see features.")
