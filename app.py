import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
from shapely.geometry import shape
import mercantile
import base64
from folium.plugins import Draw
import matplotlib.pyplot as plt
import io
from PIL import Image
import zipfile
import logging

logging.basicConfig(level=logging.INFO)

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

# Function to get image and detection data
def get_image_and_detection_data(image_id):
    # ... (keep this function as is)

# Function to draw detections on image
def draw_detections_on_image(image_url, detections):
    if not image_url or image_url == '#':
        logging.warning(f"Invalid image URL: {image_url}")
        return None
    
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content))
    except requests.RequestException as e:
        logging.error(f"Error fetching image: {e}")
        return None
    except IOError as e:
        logging.error(f"Error opening image: {e}")
        return None
    
    fig, ax = plt.subplots()
    ax.imshow(img)
    
    for detection in detections:
        coords = detection['pixel_coords']
        x, y = zip(*coords)
        ax.plot(x, y, linewidth=2, color='red')
        ax.text(min(x), min(y), detection['value'], color='red', fontsize=8, bbox=dict(facecolor='white', alpha=0.7))
    
    ax.axis('off')
    
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', bbox_inches='tight', pad_inches=0)
    img_buf.seek(0)
    plt.close(fig)
    
    return img_buf

# Function to get features within a bounding box
def get_features_within_bbox(bbox):
    # ... (keep this function as is)

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
    if st.button("Search for features and generate zip"):
        last_draw = st.session_state['last_draw']
        # Extract coordinates from drawn polygon
        geom = shape(last_draw['geometry'])
        bounds = geom.bounds  # (minx, miny, maxx, maxy)
        
        # Get features within the bounding box
        features = get_features_within_bbox(bounds)
        
        st.success(f"Found {len(features)} features in the selected area.")

        # Create a zip file with images
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            for i, feature in enumerate(features):
                image_data = feature.get('image_data', {})
                jpeg_url = image_data.get('jpeg_url', '#')
                detections = image_data.get('detections', [])
                
                # Draw detections on image
                img_buf = draw_detections_on_image(jpeg_url, detections)
                if img_buf:
                    zip_file.writestr(f"feature_{i+1}.png", img_buf.getvalue())
                    logging.info(f"Added feature_{i+1}.png to zip file")
                else:
                    logging.warning(f"Failed to process image for feature {i+1}")

        # Offer the zip file for download
        zip_buffer.seek(0)
        st.download_button(
            label="Download Images with Detections",
            data=zip_buffer,
            file_name="mapillary_features.zip",
            mime="application/zip"
        )

        # Log the size of the zip file
        zip_size = zip_buffer.getbuffer().nbytes
        logging.info(f"Zip file size: {zip_size} bytes")

else:
    st.write("Draw a polygon on the map, then click the search button to generate a zip file with feature images.")
