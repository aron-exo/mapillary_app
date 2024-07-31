import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
from shapely.geometry import shape
import mercantile
import base64
from folium.plugins import Draw
import io

try:
    import mapbox_vector_tile
except ImportError:
    st.error("The 'mapbox_vector_tile' module is not installed. Please install it using 'pip install mapbox_vector_tile'.")
    st.stop()

# Mapillary access token
mly_key = st.secrets["mly_key"]

# Initialize the Streamlit app
st.title("Mapillary Feature Explorer")

# Initialize session state
if 'map' not in st.session_state:
    st.session_state['map'] = folium.Map(location=[37.7749, -122.4194], zoom_start=12)
    draw = Draw(export=True)
    draw.add_to(st.session_state['map'])

if 'features' not in st.session_state:
    st.session_state['features'] = []

# Function to get image URL for a feature
def get_image_url(feature_id):
    st.write(f"Fetching image URL for feature ID: {feature_id}")
    url = f'https://graph.mapillary.com/{feature_id}?access_token={mly_key}&fields=thumb_original_url'
    response = requests.get(url)
    st.write(f"API response status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        jpeg_url = data.get('thumb_original_url')
        st.write(f"Image URL: {jpeg_url}")
        return jpeg_url
    else:
        st.write(f"Failed to fetch image URL for feature ID: {feature_id}")
        return None

# Function to get features within a bounding box
def get_features_within_bbox(bbox):
    st.write(f"Fetching features within bbox: {bbox}")
    west, south, east, north = bbox
    tiles = list(mercantile.tiles(west, south, east, north, 18))
    bbox_list = [mercantile.bounds(tile.x, tile.y, tile.z) for tile in tiles]
    
    features = []
    
    for bbox in bbox_list:
        bbox_str = f'{bbox.west},{bbox.south},{bbox.east},{bbox.north}'
        url = f'https://graph.mapillary.com/map_features?access_token={mly_key}&fields=id,object_value,geometry&bbox={bbox_str}'
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json().get('data', [])
            st.write(f"Found {len(data)} features in tile")
            features.extend(data)
    
    st.write(f"Total features found: {len(features)}")
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

# Add a button to start the search
if st.session_state.get('polygon_drawn', False):
    if st.button("Search for features and get image URLs"):
        last_draw = st.session_state['last_draw']
        # Extract coordinates from drawn polygon
        geom = shape(last_draw['geometry'])
        bounds = geom.bounds  # (minx, miny, maxx, maxy)
        
        # Get features within the bounding box
        features = get_features_within_bbox(bounds)
        
        st.success(f"Found {len(features)} features in the selected area.")

        # Get image URLs for each feature
        image_urls = []
        for i, feature in enumerate(features):
            feature_id = feature['id']
            image_url = get_image_url(feature_id)
            if image_url:
                image_urls.append(f"Feature {i+1} ({feature_id}): {image_url}")
            else:
                image_urls.append(f"Feature {i+1} ({feature_id}): No image URL found")

        # Display image URLs
        st.subheader("Image URLs:")
        for url in image_urls:
            st.write(url)

        # Create a text file with image URLs
        url_text = "\n".join(image_urls)
        url_file = io.StringIO()
        url_file.write(url_text)
        url_file.seek(0)

        # Offer the text file for download
        st.download_button(
            label="Download Image URLs",
            data=url_file,
            file_name="mapillary_image_urls.txt",
            mime="text/plain"
        )

else:
    st.write("Draw a polygon on the map, then click the search button to get image URLs.")
