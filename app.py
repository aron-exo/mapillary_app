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

logging.basicConfig(level=logging.DEBUG)

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
    st.write(f"Fetching data for image ID: {image_id}")
    image_url = f'https://graph.mapillary.com/{image_id}?access_token={mly_key}&fields=height,width,thumb_original_url'
    detections_url = f'https://graph.mapillary.com/{image_id}/detections?access_token={mly_key}&fields=geometry,value'

    # Get image data
    response = requests.get(image_url)
    st.write(f"Image API response status: {response.status_code}")
    if response.status_code == 200:
        image_data = response.json()
        height = image_data.get('height')
        width = image_data.get('width')
        jpeg_url = image_data.get('thumb_original_url')
        st.write(f"Image data fetched successfully for {image_id}")
        st.write(f"JPEG URL: {jpeg_url}")

        if not jpeg_url:
            st.write(f"Warning: No JPEG URL found for image {image_id}")
            return None

        # Get detection data
        response = requests.get(detections_url)
        st.write(f"Detections API response status: {response.status_code}")
        if response.status_code == 200:
            detections_data = response.json().get('data', [])
            st.write(f"Number of detections: {len(detections_data)}")
            decoded_detections = []
            for detection in detections_data:
                base64_string = detection['geometry']
                vector_data = base64.decodebytes(base64_string.encode('utf-8'))
                decoded_geometry = mapbox_vector_tile.decode(vector_data)
                detection_coordinates = decoded_geometry['mpy-or']['features'][0]['geometry']['coordinates']
                pixel_coords = [[[x/4096 * width, y/4096 * height] for x,y in tuple(coord_pair)] for coord_pair in detection_coordinates]
                decoded_detections.append({
                    'value': detection['value'],
                    'pixel_coords': pixel_coords[0]  # We only need the outer ring
                })
            st.write(f"Detection data fetched successfully for {image_id}")
            return {
                'jpeg_url': jpeg_url,
                'height': height,
                'width': width,
                'detections': decoded_detections
            }
        else:
            st.write(f"Failed to fetch detection data for image ID: {image_id}")
    else:
        st.write(f"Failed to fetch image data for image ID: {image_id}")
    return None

# Function to draw detections on image
def draw_detections_on_image(image_url, detections):
    st.write(f"Drawing detections on image: {image_url}")
    if not image_url or image_url == '#':
        st.write(f"Invalid image URL: {image_url}")
        return None
    
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content))
        st.write("Image opened successfully")
    except requests.RequestException as e:
        st.write(f"Error fetching image: {e}")
        return None
    except IOError as e:
        st.write(f"Error opening image: {e}")
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
    
    st.write("Detections drawn successfully")
    return img_buf

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
            for feature in data:
                image_data = get_image_and_detection_data(feature['id'])
                if image_data:
                    feature['image_data'] = image_data
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
                image_data = feature.get('image_data')
                if image_data:
                    jpeg_url = image_data.get('jpeg_url')
                    detections = image_data.get('detections', [])
                    
                    if jpeg_url and jpeg_url != '#':
                        # Draw detections on image
                        img_buf = draw_detections_on_image(jpeg_url, detections)
                        if img_buf:
                            zip_file.writestr(f"feature_{i+1}.png", img_buf.getvalue())
                            st.write(f"Added feature_{i+1}.png to zip file")
                        else:
                            st.write(f"Failed to process image for feature {i+1}")
                    else:
                        st.write(f"No valid JPEG URL for feature {i+1}")
                else:
                    st.write(f"No image data for feature {i+1}")

        # Offer the zip file for download
        zip_buffer.seek(0)
        zip_size = zip_buffer.getbuffer().nbytes
        st.write(f"Zip file size: {zip_size} bytes")
        
        if zip_size > 0:
            st.download_button(
                label="Download Images with Detections",
                data=zip_buffer,
                file_name="mapillary_features.zip",
                mime="application/zip"
            )
        else:
            st.error("No images were processed. The zip file is empty.")

else:
    st.write("Draw a polygon on the map, then click the search button to generate a zip file with feature images.")
