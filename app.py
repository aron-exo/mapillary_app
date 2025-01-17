import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
from shapely.geometry import shape
import mercantile
import io
import zipfile
from folium import CustomIcon

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

#if 'zip_buffer' not in st.session_state:
  #  st.session_state['zip_buffer'] = None

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

# Function to get symbol URL for a feature
def get_symbol_url(object_value):
    signs_base_url = "https://raw.githubusercontent.com/mapillary/mapillary_sprite_source/master/package_signs/"
    objects_base_url = "https://raw.githubusercontent.com/mapillary/mapillary_sprite_source/master/package_objects/"
    
    sign_url = f"{signs_base_url}{object_value}.svg"
    object_url = f"{objects_base_url}{object_value}.svg"
    
    response = requests.head(sign_url)
    if response.status_code == 200:
        return sign_url
    
    response = requests.head(object_url)
    if response.status_code == 200:
        return object_url
    
    return None

# Function to get features within a bounding box
def get_features_within_bbox(bbox):
    west, south, east, north = bbox
    tiles = list(mercantile.tiles(west, south, east, north, 22))
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
                feature['symbol_url'] = get_symbol_url(feature['object_value'])
            features.extend(data)
    
    return features

# Function to download images and create a zip file
def create_image_zip(features):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for i, feature in enumerate(features):
            image_url = feature.get('image_url')
            symbol_url = feature.get('symbol_url')
            
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
            
            if symbol_url:
                try:
                    response = requests.get(symbol_url)
                    if response.status_code == 200:
                        symbol_data = response.content
                        file_name = f"symbol_{i+1}_{feature['id']}.svg"
                        zip_file.writestr(file_name, symbol_data)
                        st.write(f"Added {file_name} to zip")
                    else:
                        st.write(f"Failed to download symbol for feature {i+1} ({feature['id']})")
                except Exception as e:
                    st.write(f"Error downloading symbol for feature {i+1} ({feature['id']}): {str(e)}")
            else:
                st.write(f"No symbol URL for feature {i+1} ({feature['id']})")
    
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

        # Create zip file with images and symbols
       # st.session_state['zip_buffer'] = create_image_zip(features)

        # Display features and add markers to the map
        for feature in features:
            geom = feature['geometry']
            coords = geom['coordinates'][::-1]  # Reverse lat/lon for folium
            image_url = feature.get('image_url', '#')
            symbol_url = feature.get('symbol_url', '#')
            popup_content = f"""
            ID: {feature['id']}<br>
            Value: {feature['object_value']}<br>
            <a href="{image_url}" target="_blank">View Image</a><br>
            <a href="{symbol_url}" target="_blank">View Symbol</a>
            """
            if symbol_url:
                icon = CustomIcon(
                    icon_image=symbol_url,
                    icon_size=(30, 30),
                    icon_anchor=(15, 15),
                )
                folium.Marker(
                    location=coords,
                    popup=popup_content,
                    icon=icon
                ).add_to(st.session_state['map'])
            else:
                folium.Marker(
                    location=coords,
                    popup=popup_content
                ).add_to(st.session_state['map'])
        
        # Display the updated map
        st_folium(st.session_state['map'], width=700, height=500)
        
# Display the download button if zip_buffer exists
#if st.session_state['zip_buffer'] is not None:
    #st.download_button(
     #   label="Download Images and Symbols",
      #  data=st.session_state['zip_buffer'],
      #  file_name="mapillary_images_and_symbols.zip",
      #  mime="application/zip"
   # )

else:
    st.write("Draw a polygon on the map, then click the search button to download images and symbols and see features.")
