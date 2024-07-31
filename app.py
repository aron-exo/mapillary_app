import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
from shapely.geometry import shape
import mercantile
import base64
import mapbox_vector_tile

# Mapillary access token
mly_key = st.secrets["mly_key"]

# Initialize the Streamlit app
st.title("Mapillary Feature Explorer")

# Initialize session state
if 'map' not in st.session_state:
    st.session_state['map'] = folium.Map(location=[37.7749, -122.4194], zoom_start=12)
    draw = folium.plugins.Draw(export=True)
    draw.add_to(st.session_state['map'])

if 'features' not in st.session_state:
    st.session_state['features'] = []

# Function to get image and detection data
def get_image_and_detection_data(image_id):
    image_url = f'https://graph.mapillary.com/{image_id}?access_token={mly_key}&fields=height,width,thumb_original_url'
    detections_url = f'https://graph.mapillary.com/{image_id}/detections?access_token={mly_key}&fields=geometry,value'

    # Get image data
    response = requests.get(image_url)
    if response.status_code == 200:
        image_data = response.json()
        height = image_data['height']
        width = image_data['width']
        jpeg_url = image_data['thumb_original_url']

        # Get detection data
        response = requests.get(detections_url)
        if response.status_code == 200:
            detections_data = response.json()['data']
            decoded_detections = []
            for detection in detections_data:
                base64_string = detection['geometry']
                vector_data = base64.decodebytes(base64_string.encode('utf-8'))
                decoded_geometry = mapbox_vector_tile.decode(vector_data)
                detection_coordinates = decoded_geometry['mpy-or']['features'][0]['geometry']['coordinates']
                pixel_coords = [[[x/4096 * width, y/4096 * height] for x,y in tuple(coord_pair)] for coord_pair in detection_coordinates]
                decoded_detections.append({
                    'value': detection['value'],
                    'pixel_coords': pixel_coords
                })

            return {
                'jpeg_url': jpeg_url,
                'height': height,
                'width': width,
                'detections': decoded_detections
            }
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
                image_data = get_image_and_detection_data(feature['id'])
                if image_data:
                    feature['image_data'] = image_data
            features.extend(data)
    
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
    if st.button("Search for features in the drawn area"):
        last_draw = st.session_state['last_draw']
        # Extract coordinates from drawn polygon
        geom = shape(last_draw['geometry'])
        bounds = geom.bounds  # (minx, miny, maxx, maxy)
        
        # Get features within the bounding box
        st.session_state['features'] = get_features_within_bbox(bounds)
        
        st.success(f"Found {len(st.session_state['features'])} features in the selected area.")

# Display features and add markers to the map
if st.session_state['features']:
    for feature in st.session_state['features']:
        geom = feature['geometry']
        coords = geom['coordinates'][::-1]  # Reverse lat/lon for folium
        folium.Marker(location=coords).add_to(st.session_state['map'])
    
    # Display the updated map
    st_folium(st.session_state['map'], width=700, height=500)
    
    # Display feature information
    st.subheader("Found Features:")
    for i, feature in enumerate(st.session_state['features']):
        st.write(f"Feature {i+1}:")
        st.write(f"ID: {feature['id']}")
        st.write(f"Value: {feature['object_value']}")
        
        image_data = feature.get('image_data', {})
        jpeg_url = image_data.get('jpeg_url')
        if jpeg_url:
            st.write(f"[View Image]({jpeg_url})")
        
        detections = image_data.get('detections', [])
        if detections:
            st.write("Detections:")
            for detection in detections:
                st.write(f"- {detection['value']}")
        
        st.write("---")
else:
    st.write("Draw a polygon on the map, then click the search button to see features.")
