import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
from shapely.geometry import shape
import mercantile
import io
import zipfile
import base64
import matplotlib.pyplot as plt
from PIL import Image
import mapbox_vector_tile

# Mapillary access token
mly_key = st.secrets["mly_key"]

# Initialize the Streamlit app
st.title("Mapillary Feature Explorer")

# Initialize session state
if 'map' not in st.session_state:
    st.session_state['map'] = folium.Map(location=[32.07011233586559, 34.78999632390827], zoom_start=12)
    draw = folium.plugins.Draw(export=True)
    draw.add_to(st.session_state['map'])

if 'features' not in st.session_state:
    st.session_state['features'] = []

if 'zip_buffer' not in st.session_state:
    st.session_state['zip_buffer'] = None

# Function to get image and detection data for a feature
def get_image_and_detection_data(feature_id):
    url = f'https://graph.mapillary.com/{feature_id}?access_token={mly_key}&fields=images'
    response = requests.get(url)
    if response.status_code == 200:
        json_data = response.json()
        if 'images' in json_data and 'data' in json_data['images'] and json_data['images']['data']:
            image_id = json_data['images']['data'][0]['id']
            image_url = f'https://graph.mapillary.com/{image_id}?access_token={mly_key}&fields=thumb_original_url,height,width'
            detections_url = f'https://graph.mapillary.com/{image_id}/detections?access_token={mly_key}&fields=geometry,value'
            
            image_response = requests.get(image_url)
            detections_response = requests.get(detections_url)
            
            if image_response.status_code == 200 and detections_response.status_code == 200:
                image_data = image_response.json()
                detections_data = detections_response.json().get('data', [])
                
                return {
                    'jpeg_url': image_data.get('thumb_original_url'),
                    'height': image_data.get('height'),
                    'width': image_data.get('width'),
                    'detections': detections_data
                }
    return None

# Function to draw detections on image
def draw_detections_on_image(image_url, detections, width, height):
    try:
        response = requests.get(image_url)
        img = Image.open(io.BytesIO(response.content))
        
        fig, ax = plt.subplots()
        ax.imshow(img)
        
        for detection in detections:
            base64_string = detection['geometry']
            vector_data = base64.decodebytes(base64_string.encode('utf-8'))
            decoded_geometry = mapbox_vector_tile.decode(vector_data)
            detection_coordinates = decoded_geometry['mpy-or']['features'][0]['geometry']['coordinates']
            pixel_coords = [[[x/4096 * width, y/4096 * height] for x,y in tuple(coord_pair)] for coord_pair in detection_coordinates]
            
            for coords in pixel_coords:
                x, y = zip(*coords)
                ax.plot(x, y, linewidth=2, color='red')
                ax.text(min(x), min(y), detection['value'], color='red', fontsize=8, bbox=dict(facecolor='white', alpha=0.7))
        
        ax.axis('off')
        
        img_buf = io.BytesIO()
        plt.savefig(img_buf, format='png', bbox_inches='tight', pad_inches=0)
        img_buf.seek(0)
        plt.close(fig)
        
        return img_buf
    except Exception as e:
        st.write(f"Error processing image: {str(e)}")
        return None

# Function to get features within a bounding box
def get_features_within_bbox(bbox):
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
            for feature in data:
                feature['image_data'] = get_image_and_detection_data(feature['id'])
            features.extend(data)
    
    return features

# Function to download images and create a zip file
def create_image_zip(features):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for i, feature in enumerate(features):
            image_data = feature.get('image_data', {})
            if image_data:
                image_url = image_data.get('jpeg_url')
                detections = image_data.get('detections', [])
                width = image_data.get('width')
                height = image_data.get('height')
                
                if image_url and width and height:
                    try:
                        img_buf = draw_detections_on_image(image_url, detections, width, height)
                        if img_buf:
                            file_name = f"feature_{i+1}_{feature['id']}_with_detections.png"
                            zip_file.writestr(file_name, img_buf.getvalue())
                            st.write(f"Added {file_name} to zip")
                        else:
                            st.write(f"Failed to process image for feature {i+1} ({feature['id']})")
                    except Exception as e:
                        st.write(f"Error processing image for feature {i+1} ({feature['id']}): {str(e)}")
                else:
                    st.write(f"Missing image data for feature {i+1} ({feature['id']})")
            else:
                st.write(f"No image data for feature {i+1} ({feature['id']})")
    
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
    if st.button("Search for features and download images with detections"):
        last_draw = st.session_state['last_draw']
        # Extract coordinates from drawn polygon
        geom = shape(last_draw['geometry'])
        bounds = geom.bounds  # (minx, miny, maxx, maxy)
        
        # Get features within the bounding box
        features = get_features_within_bbox(bounds)
        
        st.session_state['features'] = features
        st.success(f"Found {len(features)} features in the selected area.")

        # Create zip file with images including detections
        st.session_state['zip_buffer'] = create_image_zip(features)

        # Display features and add markers to the map
        for feature in features:
            geom = feature['geometry']
            coords = geom['coordinates'][::-1]  # Reverse lat/lon for folium
            image_data = feature.get('image_data', {})
            image_url = image_data.get('jpeg_url', '#')
            popup_content = f"""
            ID: {feature['id']}<br>
            Value: {feature['object_value']}<br>
            <a href="{image_url}" target="_blank">View Original Image</a>
            """
            folium.Marker(location=coords, popup=popup_content).add_to(st.session_state['map'])
        
        # Display the updated map
        st_folium(st.session_state['map'], width=700, height=500)

# Display the download button if zip_buffer exists
if st.session_state['zip_buffer'] is not None:
    st.download_button(
        label="Download Images with Detections",
        data=st.session_state['zip_buffer'],
        file_name="mapillary_images_with_detections.zip",
        mime="application/zip"
    )

else:
    st.write("Draw a polygon on the map, then click the search button to download images with detections and see features.")
