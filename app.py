import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
from shapely.geometry import shape

# Mapillary access token
mly_key = st.secrets["mly_key"]

# Initialize the Streamlit app
st.title("Mapillary Feature Explorer")

# Create a folium map
map_center = [37.7749, -122.4194]  # Center of the map (San Francisco for example)
m = folium.Map(location=map_center, zoom_start=12)

# Add draw tools to the map
draw = folium.plugins.Draw(export=True)
draw.add_to(m)

# Display the map
st_map = st_folium(m, width=700, height=500)

# Function to get features within a bounding box
def get_features_within_bbox(bbox):
    bbox_str = f'{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}'
    url = f'https://graph.mapillary.com/map_features?access_token={mly_key}&fields=id,object_value,geometry,images&bbox={bbox_str}'
    response = requests.get(url)
    if response.status_code == 200:
        return response.json().get('data', [])
    return []

# Initialize session state
if 'last_draw' not in st.session_state:
    st.session_state['last_draw'] = None

# Check if a new polygon has been drawn
if st_map is not None and 'last_drawn_feature' in st_map:
    last_draw = st_map['last_drawn_feature']
    if last_draw is not None and last_draw != st.session_state['last_draw']:
        st.session_state['last_draw'] = last_draw
        st.session_state['polygon_drawn'] = True
    else:
        st.session_state['polygon_drawn'] = False
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
        features = get_features_within_bbox(bounds)
        
        # Add features to the map with pop-ups
        for feature in features:
            geom = feature['geometry']
            coords = geom['coordinates'][::-1]  # Reverse lat/lon for folium
            image_url = f"https://graph.mapillary.com/{feature['id']}?access_token={mly_key}&fields=thumb_original_url"
            response = requests.get(image_url)
            image_data = response.json()
            thumb_url = image_data.get('thumb_original_url', '#')
            popup_content = f"<a href='{thumb_url}' target='_blank'>View Image</a>"
            folium.Marker(location=coords, popup=popup_content).add_to(m)
        
        # Display the updated map
        st_folium(m, width=700, height=500)
        
        st.success(f"Found {len(features)} features in the selected area.")
else:
    st.write("Draw a polygon on the map, then click the search button to see features.")
